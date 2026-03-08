# -*- coding: UTF-8 -*-
"""
execute_revit_code v2 route — KUKAI pipeline endpoint.

Архитектура (async 2-step):
  1. POST /execute_v2/         → Revit main thread; запускает фоновый Python3, возвращает job_id
  2. POST /execute_v2/result/<job_id>/ → Revit main thread; ждёт code из файла, выполняет, возвращает result

IronPython = сбор контекста + выполнение кода на главном Revit треде (обязательно)
Python 3   = AI пайплайн (генерация кода) — в фоновом .NET Thread, не блокирует Revit
"""
from pyrevit import routes, revit, DB
import json
import os
import re
import sys
import traceback
import time

# ── Temp директория (fallback если C:\Temp недоступен) ─────────────────────────
_TMP_DIR_PRIMARY  = r"C:\Temp"
_TMP_DIR_FALLBACK = os.path.join(os.environ.get("TEMP", r"C:\Windows\Temp"), "kukai_jobs")
_TMP_DIR = _TMP_DIR_PRIMARY

def _ensure_tmp():
    """Создаёт рабочую директорию, при ошибке переключается на fallback."""
    global _TMP_DIR
    for candidate in (_TMP_DIR_PRIMARY, _TMP_DIR_FALLBACK):
        try:
            if not os.path.exists(candidate):
                os.makedirs(candidate)
            # Тест записи
            test_file = os.path.join(candidate, ".kukai_write_test")
            with open(test_file, "w") as f:
                f.write("ok")
            os.remove(test_file)
            _TMP_DIR = candidate
            return
        except Exception:
            continue
    raise IOError("Cannot create temp directory. Tried: {}, {}".format(
        _TMP_DIR_PRIMARY, _TMP_DIR_FALLBACK))

# Инициализируем при загрузке модуля
try:
    _ensure_tmp()
except Exception:
    pass


# ── Автоматическая очистка старых temp файлов ──────────────────────────────────
_LAST_CLEANUP_TIME = [0.0]
_CLEANUP_INTERVAL  = 120   # секунд между очистками
_JOB_TTL           = 300   # секунд — файлы старше 5 минут удаляются

def _auto_cleanup():
    """Удаляет устаревшие kukai_* файлы (запускается не чаще раза в 2 минуты)."""
    now = time.time()
    if now - _LAST_CLEANUP_TIME[0] < _CLEANUP_INTERVAL:
        return
    _LAST_CLEANUP_TIME[0] = now
    try:
        cutoff = now - _JOB_TTL
        for name in os.listdir(_TMP_DIR):
            if not name.startswith("kukai_"):
                continue
            path = os.path.join(_TMP_DIR, name)
            try:
                if os.path.getmtime(path) < cutoff:
                    os.remove(path)
            except Exception:
                pass
    except Exception:
        pass


# ── Поиск Python 3 на машине ──────────────────────────────────────────────────
def _find_python3():
    """
    Находит python.exe на машине (только проверка файлов — без subprocess).
    subprocess.communicate() блокирует main Revit thread в IronPython.
    Порядок: env var KUKAI_PYTHON3 → стандартные пути → "python" fallback.
    """
    try:
        # 1. Переменная окружения (позволяет пользователю переопределить)
        configured = os.environ.get("KUKAI_PYTHON3", "")
        if configured and os.path.isfile(configured):
            return configured

        # 2. Стандартные пути установки Python на Windows
        username    = os.environ.get("USERNAME", "")
        appdata     = os.environ.get("LOCALAPPDATA",
                                     r"C:\Users\{}\AppData\Local".format(username))
        userprofile = os.environ.get("USERPROFILE",
                                     r"C:\Users\{}".format(username))
        candidates = []
        for ver in ("314", "313", "312", "311", "310", "39", "38"):
            candidates.append(r"C:\Python{}\python.exe".format(ver))
            candidates.append(os.path.join(
                appdata, "Programs", "Python", "Python{}".format(ver), "python.exe"))
        # conda / miniforge / winget Python
        for base in (userprofile, r"C:\ProgramData", r"C:\tools"):
            for distro in ("miniconda3", "anaconda3", "miniforge3", "python"):
                candidates.append(os.path.join(base, distro, "python.exe"))

        for c in candidates:
            try:
                if c and os.path.isfile(c):
                    return c
            except Exception:
                continue

    except Exception:
        pass

    # Последний fallback: надеемся что "python" есть в PATH
    return "python"


_HERE            = os.path.dirname(__file__)
_PROJECT         = os.path.dirname(_HERE)
_PYTHON3         = _find_python3()
_PIPELINE_SCRIPT = os.path.join(_HERE, "execute_v2", "run_pipeline.py")

# Compat shim для unit-тестов
_pipeline_instance = None
def _get_pipeline():
    return _pipeline_instance


# ── Сбор контекста Revit (быстрый, на главном треде) ──────────────────────────
def _collect_context(doc):
    """Собирает минимальный контекст. Только быстрые операции — не блокирует main thread."""
    ctx = {"doc_title": "", "doc_path": "", "levels": [], "categories": []}
    try:
        ctx["doc_title"] = doc.Title or ""
        ctx["doc_path"]  = doc.PathName or ""
    except Exception:
        pass
    try:
        from Autodesk.Revit.DB import FilteredElementCollector, Level
        levels = FilteredElementCollector(doc).OfClass(Level).ToElements()
        ctx["levels"] = [
            {"name": l.Name, "elevation": round(l.Elevation * 0.3048, 2)}
            for l in levels
        ]
    except Exception:
        pass
    # Категории не собираем — итерация 400+ категорий блокирует main thread на 5-10s
    return ctx


# ── Запуск AI пайплайна в фоновом .NET Thread ─────────────────────────────────
def _start_pipeline_thread(job_id, payload):
    """Запускает Python 3 пайплайн асинхронно. Не блокирует Revit main thread."""
    from System.Threading import Thread, ThreadStart

    tmp_in  = os.path.join(_TMP_DIR, "kukai_in_{}.json".format(job_id))
    tmp_out = os.path.join(_TMP_DIR, "kukai_out_{}.json".format(job_id))
    tmp_err = os.path.join(_TMP_DIR, "kukai_err_{}.txt".format(job_id))
    tmp_bat = os.path.join(_TMP_DIR, "kukai_run_{}.bat".format(job_id))

    _ensure_tmp()

    # Пишем входные данные в UTF-8 (критично для кириллицы)
    with open(tmp_in, "wb") as f:
        f.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    # chcp 65001 = UTF-8 консоль, -X utf8 = UTF-8 stdin/stdout для Python
    bat_content = (
        "@echo off\r\n"
        "chcp 65001 > nul\r\n"
        "{py} -X utf8 {script} < {inp} > {out} 2> {err}\r\n"
    ).format(py=_PYTHON3, script=_PIPELINE_SCRIPT,
             inp=tmp_in, out=tmp_out, err=tmp_err)

    # Пишем bat как байты — IronPython 2.7 не поддерживает encoding= kwarg в open()
    with open(tmp_bat, "wb") as f:
        f.write(bat_content.encode("ascii", "replace"))

    def run_bg():
        try:
            from System.Diagnostics import Process, ProcessStartInfo
            psi = ProcessStartInfo()
            psi.FileName        = "cmd.exe"
            psi.Arguments       = "/c " + tmp_bat
            psi.UseShellExecute = False
            psi.CreateNoWindow  = True
            psi.WorkingDirectory = _PROJECT

            proc = Process()
            proc.StartInfo = psi
            proc.Start()
            # 120s — LLM API может занять 60-90s для сложных запросов
            proc.WaitForExit(120000)
            try:
                proc.Kill()
            except Exception:
                pass
        except Exception as e:
            err_data = {"status": "error", "error": "Pipeline thread: " + str(e), "code": None}
            try:
                with open(tmp_out, "wb") as f:
                    f.write(json.dumps(err_data, ensure_ascii=False).encode("utf-8"))
            except Exception:
                pass

    t = Thread(ThreadStart(run_bg))
    t.IsBackground = True
    t.Start()


# ── Исполнение IronPython кода с таймаутом ────────────────────────────────────
_EXEC_TIMEOUT_SECONDS = 15  # максимальное время выполнения кода (15 секунд)

def _execute_code(code, doc, uidoc):
    """
    Выполняет IronPython код на главном Revit треде.
    Защиты:
      - Security scan (блокирует опасные паттерны)
      - Execution timeout 15s (через sys.settrace — прерывает зависшие циклы)
      - Auto Transaction для WRITE операций
    """
    # ── Security scan (только реально опасное) ────────────────────────────────
    blocked_patterns = [
        (r'\bProcess\.Start\s*\(',        "Process.Start() is blocked"),
        (r'\b__subclasses__\b',           "__subclasses__ is blocked"),
        (r'\b__globals__\b',              "__globals__ is blocked"),
        (r'\bfrom\s+\S+\s+import\s+\*',  "wildcard import is blocked"),
    ]
    for pattern, msg in blocked_patterns:
        if re.search(pattern, code):
            return {"status": "error", "error": "Security: " + msg}

    # ── Namespace ──────────────────────────────────────────────────────────────
    def eid_value(eid):
        """ElementId → int. Совместимо с Revit 2023/2024/2025."""
        try:
            return eid.IntegerValue
        except AttributeError:
            try:
                return int(str(eid))
            except Exception:
                return str(eid)

    namespace = {
        "doc":          doc,
        "uidoc":        uidoc,
        "DB":           DB,
        "revit":        revit,
        "eid_value":    eid_value,
        "__builtins__": __builtins__,
        "__result__":   None,
    }

    # ── Execution timeout via sys.settrace ────────────────────────────────────
    # Работает в IronPython 2.7 на .NET Framework.
    # Проверяет время раз в 500 шагов (минимальный overhead).
    _start_time  = [time.time()]
    _step_count  = [0]
    _timeout_msg = [None]

    def _timeout_trace(frame, event, arg):
        _step_count[0] += 1
        if _step_count[0] % 500 == 0:
            elapsed = time.time() - _start_time[0]
            if elapsed > _EXEC_TIMEOUT_SECONDS:
                _timeout_msg[0] = (
                    u"Execution timeout: code ran for {:.1f}s (limit {}s). "
                    u"Optimize: avoid iterating >500 elements individually, "
                    u"use GetElementCount() for counts."
                ).format(elapsed, _EXEC_TIMEOUT_SECONDS)
                raise RuntimeError(_timeout_msg[0])
        return _timeout_trace

    # ── Transaction автообёртка для WRITE операций ────────────────────────────
    write_signs       = ['.Set(', '.Create(', 'Name =', '.Value =', '.Delete(', '.Move(', '.Copy(']
    has_own_txn       = 'Transaction(' in code or 'DB.Transaction(' in code
    is_write          = any(s in code for s in write_signs)
    needs_auto_txn    = is_write and not has_own_txn

    # ── Выполнение ────────────────────────────────────────────────────────────
    # sys.gettrace/settrace могут отсутствовать в некоторых сборках IronPython
    old_trace = getattr(sys, "gettrace", lambda: None)()
    _has_settrace = hasattr(sys, "settrace")
    try:
        if _has_settrace:
            sys.settrace(_timeout_trace)

        if needs_auto_txn:
            t = DB.Transaction(doc, "KUKAI: AI Execute")
            t.Start()
            try:
                exec(compile(code, "<kukai>", "exec"), namespace)
                t.Commit()
            except Exception as e:
                try:
                    t.RollBack()
                except Exception:
                    pass
                raise
        else:
            exec(compile(code, "<kukai>", "exec"), namespace)

    except Exception as e:
        return {
            "status":    "error",
            "error":     str(e),
            "traceback": traceback.format_exc()
        }
    finally:
        if _has_settrace:
            sys.settrace(old_trace)

    result = namespace.get("__result__")
    return {"status": "ok", "result": result}


# ── Routes ────────────────────────────────────────────────────────────────────

def register_execute_v2_routes(api):

    @api.route("/execute_v2/", methods=["POST"])
    def execute_v2(doc, uidoc, request):
        """
        Шаг 1: принять NL запрос, запустить AI пайплайн в фоне.
        Возвращает job_id. Клиент опрашивает /execute_v2/result/<job_id>/.
        """
        try:
            # Автоочистка старых temp файлов (не чаще раза в 2 мин)
            _auto_cleanup()

            data = json.loads(request.data) if isinstance(request.data, str) else request.data
            user_request = data.get("request", "")
            session_id   = data.get("session_id", "default")
            confirm      = data.get("confirm", False)

            if not user_request or not str(user_request).strip():
                return routes.make_response(data={"error": "No request"}, status=400)

            job_id = str(int(time.time() * 1000))
            ctx    = _collect_context(doc)

            _start_pipeline_thread(job_id, {
                "request":    user_request,
                "session_id": session_id,
                "confirm":    confirm,
                "context":    ctx,
            })

            return routes.make_response(data={
                "status":   "pending",
                "job_id":   job_id,
                "poll_url": "/revit_mcp/execute_v2/result/{}/".format(job_id),
                "message":  "AI pipeline started. Poll result in 5-10 seconds.",
            })

        except Exception as e:
            return routes.make_response(
                data={"error": str(e), "traceback": traceback.format_exc()},
                status=500
            )

    @api.route("/execute_v2/result/<job_id>/", methods=["POST"])
    def execute_v2_result(doc, uidoc, request, job_id):
        """
        Шаг 2: прочитать AI код из файла и выполнить в Revit.
        Возвращает: pending / confirm_required / ok / error
        """
        try:
            tmp_out = os.path.join(_TMP_DIR, "kukai_out_{}.json".format(job_id))

            # Файл ещё не готов
            if not os.path.exists(tmp_out) or os.path.getsize(tmp_out) == 0:
                return routes.make_response(data={"status": "pending", "job_id": job_id})

            # Читаем результат пайплайна
            try:
                out_bytes = open(tmp_out, "rb").read()
                out_txt   = out_bytes.decode("utf-8", "replace").strip()
                pipeline_result = json.loads(out_txt)
            except Exception as e:
                return routes.make_response(
                    data={"error": "Cannot parse pipeline result: " + str(e)}, status=500)

            # Пайплайн вернул ошибку
            if pipeline_result.get("status") == "error":
                return routes.make_response(
                    data={"error": pipeline_result.get("error", "Pipeline error")}, status=500)

            # Пайплайн требует подтверждения (WRITE + confirm=false)
            if pipeline_result.get("status") == "confirm_required":
                return routes.make_response(data=pipeline_result)

            # Defense-in-depth: если пайплайн вернул WRITE код без confirm_required —
            # проверяем confirm из исходного запроса и блокируем если нужно
            if pipeline_result.get("intent") == "write":
                tmp_in_chk   = os.path.join(_TMP_DIR, "kukai_in_{}.json".format(job_id))
                orig_confirm = False
                if os.path.exists(tmp_in_chk):
                    try:
                        orig_payload = json.loads(
                            open(tmp_in_chk, "rb").read().decode("utf-8"))
                        orig_confirm = bool(orig_payload.get("confirm", False))
                    except Exception:
                        pass
                if not orig_confirm:
                    return routes.make_response(data={
                        "status":  "confirm_required",
                        "message": u"Операция изменяет модель. Добавьте confirm=true для выполнения.",
                        "intent":  "write",
                        "code":    None,
                    })

            # Получаем код
            code = pipeline_result.get("code") or ""
            if not code.strip():
                return routes.make_response(
                    data={"error": "Pipeline returned empty code"}, status=500)

            # Выполняем код в Revit (с timeout, security check, auto-transaction)
            exec_result = _execute_code(code, doc, uidoc)

            # Очищаем temp файлы этого job
            for suffix, ext in [("in","json"),("out","json"),("err","txt"),("run","bat")]:
                try:
                    p = os.path.join(_TMP_DIR, "kukai_{}_{}.{}".format(suffix, job_id, ext))
                    if os.path.exists(p):
                        os.remove(p)
                except Exception:
                    pass

            return routes.make_response(data={
                "status": exec_result.get("status"),
                "result": exec_result.get("result"),
                "error":  exec_result.get("error"),
                "code":   code,
                "intent": pipeline_result.get("intent"),
                "job_id": job_id,
            })

        except Exception as e:
            return routes.make_response(
                data={"error": str(e), "traceback": traceback.format_exc()},
                status=500
            )

    @api.route("/execute_v2/stats/", methods=["GET"])
    def get_stats(doc, uidoc, request):
        """Статус системы: pending jobs, Python путь, temp dir."""
        try:
            jobs = [f for f in os.listdir(_TMP_DIR) if f.startswith("kukai_out_")]
            return routes.make_response(data={
                "pending_jobs": len(jobs),
                "jobs":         jobs[:10],
                "python3_path": _PYTHON3,
                "python3_ok":   os.path.isfile(_PYTHON3),
                "tmp_dir":      _TMP_DIR,
            })
        except Exception as e:
            return routes.make_response(data={"error": str(e)}, status=500)

    @api.route("/execute_v2/session/<session_id>/", methods=["GET"])
    def get_session(doc, uidoc, request, session_id):
        """Получить историю сессии."""
        tmp = os.path.join(_TMP_DIR, "kukai_session_{}.json".format(session_id))
        if os.path.exists(tmp):
            try:
                return routes.make_response(data=json.loads(open(tmp, "rb").read().decode("utf-8")))
            except Exception:
                pass
        return routes.make_response(data={"session_id": session_id, "history": []})
