"""
ExecuteV2 Pipeline — main orchestrator for AI code execution in Revit.

Connects: IntentClassifier → ContextBuilder → CodeGenerator → SandboxValidator
         → TimeoutInstrumenter → TransactionExecutor → RetryLoop → ResultFormatter

Phase 3: + SessionState, AuditLog, ModelRouter integration.
Phase 4: + MultiStep, TemplateLibrary, ProgressTracker integration.
"""

import logging
import time
from typing import Any, Dict, Optional

from .intent_classifier import IntentClassifier
from .context_builder import ContextBuilder
from .code_generator import CodeGenerator
from .sandbox_validator import SandboxValidator
from .safe_namespace import build_safe_namespace
from .transaction_executor import TransactionExecutor
from .timeout_instrumenter import instrument_loops
from .result_formatter import ResultFormatter
from .retry_loop import RetryLoop
from .session_state import SessionManager
from .audit_log import AuditLog
from .model_router import ModelRouter
from .multi_step import detect_multi_step, MultiStepExecutor, MultiStepPlan
from .template_library import TemplateLibrary
from .streaming import ProgressTracker
from .code_cache import CodeCache


logger = logging.getLogger("kukai.execute_v2.pipeline")


class ExecuteV2Pipeline:
    """
    Main pipeline for execute_revit_code v2.
    
    Flow:
        1. Classify intent (instant, rule-based)
        2. Build Revit context (cached, 5 min TTL)
        3. Route to optimal LLM model
        4. Generate code via LLM (with session context)
        5. Validate (sandbox) + instrument (loop guards)
        6. Execute in Revit
        7. Retry on error (up to max_retries)
        8. Format human-readable response
        9. Store results in session + audit log
    """

    def __init__(self, api_url=None, openrouter_key=None, log_dir=None):
        """
        Args:
            api_url: KUKAI backend URL (future use).
            openrouter_key: OpenRouter API key (falls back to env var).
            log_dir: Directory for audit logs (default: logs/execute_v2/).
        """
        self.classifier = IntentClassifier()
        self.context_builder = ContextBuilder()
        self.generator = CodeGenerator(api_url=api_url, api_key=openrouter_key)
        self.validator = SandboxValidator()
        self.executor = TransactionExecutor()
        self.formatter = ResultFormatter()
        self.model_router = ModelRouter()
        self.audit_log = AuditLog(log_dir=log_dir)
        self.session_manager = SessionManager.get_instance()
        self.template_library = TemplateLibrary()
        self.multi_step_executor = MultiStepExecutor(self)
        self.code_cache = CodeCache.get_instance()

    def run(
        self,
        user_request: str,
        doc: Any,
        uidoc: Any,
        DB: Any,
        revit: Any,
        max_retries: int = 2,
        context_override: Optional[Dict] = None,
        session_id: str = None,
        confirm: bool = False,
        progress_tracker: Optional[ProgressTracker] = None,
    ) -> Dict:
        """
        Execute user request end-to-end.

        Args:
            user_request: Natural language request (RU or EN).
            doc: Revit Document.
            uidoc: Revit UIDocument.
            DB: Autodesk.Revit.DB module.
            revit: pyRevit revit module.
            max_retries: Maximum LLM fix attempts on error.
            context_override: Pre-built context dict (skips ContextBuilder).
            session_id: Session ID for multi-turn conversation memory.
            confirm: True if user confirmed a dangerous operation.
            progress_tracker: Optional ProgressTracker for status updates.

        Returns:
            {
                "status": "success" | "error" | "rejected" | "needs_confirmation",
                "response": "Human-readable response with emoji",
                "intent": {"intent_type": "...", "confidence": N, "detected_keywords": [...]},
                "retries": N,
                "code_executed": "final code string",
                "raw_result": {...},
                "session_id": "...",
                "model_used": "...",
                "duration_ms": N,
            }
        """
        start_time = time.time()
        model_used = None
        code = ""
        retries = 0

        if progress_tracker:
            progress_tracker.update("classifying", 5, "Анализ запроса...")

        # Session setup (before multi-step so session is available)
        session = None
        if session_id:
            session = self.session_manager.get_or_create(session_id)
            session.set_last_request(user_request)

        # Multi-step detection: delegate to MultiStepExecutor if applicable
        if detect_multi_step(user_request):
            logger.info("Multi-step request detected, delegating to MultiStepExecutor")
            if progress_tracker:
                progress_tracker.update("executing", 10, "Многошаговая операция...")
            # Split on sequential markers and run each sub-request as a separate pipeline call
            import re as _re
            parts = _re.split(
                r'\b(потом|затем|после этого|and then|then)\b',
                user_request,
                flags=_re.IGNORECASE,
            )
            sub_requests = [
                p.strip() for p in parts
                if p.strip() and not _re.match(
                    r'^(потом|затем|после этого|and then|then)$', p.strip(), _re.IGNORECASE
                )
            ]
            if len(sub_requests) > 1:
                step_results = []
                for i, sub_req in enumerate(sub_requests):
                    logger.info(
                        "Multi-step: executing sub-request %d/%d: %s",
                        i + 1, len(sub_requests), sub_req[:50],
                    )
                    sub_result = self._execute_pipeline(
                        user_request=sub_req,
                        doc=doc,
                        uidoc=uidoc,
                        DB=DB,
                        revit=revit,
                        max_retries=max_retries,
                        context_override=context_override,
                        session=session,
                        confirm=confirm,
                        progress_tracker=None,
                    )
                    step_results.append({
                        "step": i + 1,
                        "request": sub_req,
                        "result": sub_result,
                    })
                    # Save step result to session for chaining
                    if session and sub_result.get("status") == "success":
                        raw = sub_result.get("raw_result", {})
                        result_val = raw.get("result") or raw.get("__result__")
                        if isinstance(result_val, list):
                            try:
                                elements = [int(e) for e in result_val]
                                if elements:
                                    session.store_elements(elements, "step_{}_result".format(i))
                            except (ValueError, TypeError):
                                pass
                    if sub_result.get("status") == "error":
                        break
                # Combine results
                all_ok = all(
                    r["result"].get("status") == "success" for r in step_results
                )
                combined_response = "\n".join(
                    "Шаг {}: {}".format(r["step"], r["result"].get("response", ""))
                    for r in step_results
                )
                duration_ms = (time.time() - start_time) * 1000
                return {
                    "status": "success" if all_ok else "partial",
                    "response": combined_response,
                    "intent": {
                        "intent_type": "write",
                        "confidence": 0.9,
                        "detected_keywords": [],
                    },
                    "retries": 0,
                    "code_executed": "",
                    "raw_result": {"steps": step_results},
                    "model_used": model_used,
                    "session_id": session_id or "",
                    "duration_ms": round(duration_ms, 1),
                }

        try:
            result = self._execute_pipeline(
                user_request=user_request,
                doc=doc,
                uidoc=uidoc,
                DB=DB,
                revit=revit,
                max_retries=max_retries,
                context_override=context_override,
                session=session,
                confirm=confirm,
                progress_tracker=progress_tracker,
            )

            code = result.get("code_executed", "")
            retries = result.get("retries", 0)
            model_used = result.get("model_used")
            duration_ms = (time.time() - start_time) * 1000

            # Store elements in session
            if session and result.get("status") == "success":
                raw = result.get("raw_result", {})
                output = raw.get("output", "")
                # Try to extract element IDs from __result__
                result_val = raw.get("__result__")
                if isinstance(result_val, list):
                    try:
                        ids = [int(e) for e in result_val]
                        session.store_elements(ids)
                    except (ValueError, TypeError):
                        pass

            # Add metadata
            result["session_id"] = session_id or ""
            result["model_used"] = model_used
            result["duration_ms"] = round(duration_ms, 1)

            # Audit log
            self.audit_log.log_execution(
                session_id=session_id or "anonymous",
                user_request=user_request,
                intent_type=result.get("intent", {}).get("intent_type", "unknown"),
                code_executed=code,
                result_status=result.get("status", "error"),
                retries=retries,
                duration_ms=duration_ms,
                model_used=model_used,
                error=result.get("raw_result", {}).get("error_message"),
                traceback=result.get("raw_result", {}).get("traceback"),
            )

            # Mark progress as done
            if progress_tracker:
                progress_tracker.done(result)

            return result

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error("Pipeline failed: %s", e)
            self.audit_log.log_execution(
                session_id=session_id or "anonymous",
                user_request=user_request,
                intent_type="unknown",
                code_executed=code,
                result_status="error",
                retries=retries,
                duration_ms=duration_ms,
                model_used=model_used,
                error=str(e),
            )
            raise

    def _execute_pipeline(
        self,
        user_request: str,
        doc: Any,
        uidoc: Any,
        DB: Any,
        revit: Any,
        max_retries: int,
        context_override: Optional[Dict],
        session: Any,
        confirm: bool,
        progress_tracker: Optional[ProgressTracker] = None,
    ) -> Dict:
        """Core pipeline logic (extracted for clean audit/session wrapping)."""

        # 1. Classify intent
        if progress_tracker:
            progress_tracker.update("classifying", 10, "Классификация намерения...")
        intent = self.classifier.classify(user_request)
        logger.info("Intent: %s (confidence: %.2f)", intent["intent_type"], intent["confidence"])

        # 2. Build context
        if progress_tracker:
            progress_tracker.update("building_context", 20, "Сбор контекста модели...")
        if context_override is not None:
            context = context_override
        else:
            # Use minimal context for READ/ANALYZE requests (faster), full context for WRITE
            use_minimal = intent.get("intent_type") in ("read", "analyze")
            context = self._build_context(doc, uidoc, DB=DB, minimal=use_minimal)

        # 2b. Inject session context
        session_snippet = ""
        if session:
            session.add_to_history("user", user_request)
            session_snippet = session.to_prompt_snippet()
            context["session_state"] = session_snippet

        # 3. Route to model
        context_str = str(context)
        model = self.model_router.route(user_request, intent["intent_type"], len(context_str))

        # 3b. Check template library before LLM generation
        template_matches = self.template_library.search(user_request)
        if template_matches:
            logger.info("Found %d template matches for request", len(template_matches))

        # 4. Generate code via LLM
        if progress_tracker:
            progress_tracker.update("generating", 40, "Генерация кода...")
        try:
            # Inject session context into the request for the LLM
            augmented_request = user_request
            if session_snippet:
                augmented_request = (
                    "{}\n\nКонтекст сессии:\n{}"
                ).format(user_request, session_snippet)

            # Check code cache
            cached_gen = self.code_cache.get(augmented_request, context)
            if cached_gen:
                logger.info("Using cached generated code")
                gen = cached_gen
            else:
                # Override model in generator
                original_model = self.generator.DEFAULT_MODEL
                self.generator.DEFAULT_MODEL = model
                try:
                    gen = self.generator.generate(
                        augmented_request,
                        context,
                        intent["intent_type"],
                        hints=intent.get("hints"),
                    )
                    # Save to cache
                    self.code_cache.set(augmented_request, context, gen)
                finally:
                    self.generator.DEFAULT_MODEL = original_model

            code = gen.get("code", "")
        except Exception as e:
            logger.error("Code generation failed: %s", e)
            return self._error_response(
                "Ошибка генерации кода: {}".format(str(e)),
                intent,
                model_used=model,
            )

        if not code:
            return self._error_response(
                "LLM не сгенерировал код",
                intent,
                model_used=model,
            )

        # 5. Validate
        if progress_tracker:
            progress_tracker.update("validating", 60, "Проверка безопасности кода...")
        validation = self.validator.validate(code)
        if not validation["valid"]:
            logger.warning("Code rejected by sandbox: %s", validation.get("reason"))
            result = {"status": "rejected", "reason": validation["reason"]}
            human_response = self.formatter.format(result, user_request, intent["intent_type"])
            return {
                "status": "rejected",
                "response": human_response,
                "intent": intent,
                "retries": 0,
                "code_executed": code,
                "raw_result": result,
                "model_used": model,
            }

        # 6. Instrument loops
        try:
            code = instrument_loops(code)
        except SyntaxError as e:
            return self._error_response(
                "Синтаксическая ошибка в коде: {}".format(str(e)),
                intent,
                code=code,
                model_used=model,
            )

        # 7. Execute
        if progress_tracker:
            progress_tracker.update("executing", 75, "Выполнение кода в Revit...")
        namespace = build_safe_namespace(doc, uidoc, DB, revit, [])
        result = self.executor.execute(code, doc, uidoc, namespace, intent["intent_type"])

        # 8. Retry on error
        retries = 0
        if result["status"] == "error" and max_retries > 0:
            retry_loop = RetryLoop(
                generator=self.generator,
                validator=self.validator,
                executor=self.executor,
                max_retries=max_retries,
            )
            retry_result = retry_loop.run(
                initial_code=code,
                doc=doc,
                uidoc=uidoc,
                DB=DB,
                revit=revit,
                intent_type=intent["intent_type"],
                initial_result=result,
                context=context,
            )
            result = retry_result["result"]
            code = retry_result["code"]
            retries = retry_result["retries"]

        # 9. Format result
        if progress_tracker:
            progress_tracker.update("formatting", 90, "Формирование ответа...")
        human_response = self.formatter.format(result, user_request, intent["intent_type"])

        # Record to session history
        if session:
            session.add_to_history("assistant", human_response, code)

        return {
            "status": result.get("status", "error"),
            "response": human_response,
            "intent": intent,
            "retries": retries,
            "code_executed": code,
            "raw_result": result,
            "model_used": model,
        }

    def _build_context(self, doc, uidoc, DB=None, minimal=False) -> Dict:
        """Build context from Revit (executes IronPython context collector).
        
        Tries exec-based collection first (real Revit data), falls back to
        direct _collect_context (works with mocks in tests).
        """
        # Check cache first
        now = time.time()
        if (self.context_builder._cache is not None and
                (now - self.context_builder._cache_time) < self.context_builder.CACHE_TTL_SECONDS):
            return self.context_builder._cache

        # Try exec-based collection (works inside Revit with real DB)
        if DB is not None:
            try:
                if minimal:
                    code = self.context_builder.get_minimal_context_code()
                else:
                    code = self.context_builder.get_context_code()
                instrumented = instrument_loops(code)
                namespace = build_safe_namespace(doc, uidoc, DB, None, [])
                exec(instrumented, namespace)
                result = namespace.get('__result__', {})
                if result:
                    return self.context_builder.build_from_result(result)
            except Exception as e:
                logger.warning("Context collection via exec failed: %s", e)

        # Fallback to direct collection (mock-friendly)
        try:
            return self.context_builder.build(doc, uidoc)
        except Exception as e:
            logger.error("Context build failed: %s", e)
            return {"error": str(e)}

    def _error_response(self, message: str, intent: Dict, code: str = "", model_used: str = None) -> Dict:
        """Build a standard error response."""
        result = {
            "status": "error",
            "output": message,
            "error_type": "PipelineError",
            "error_message": message,
        }
        human_response = self.formatter.format(result, "", intent["intent_type"])
        return {
            "status": "error",
            "response": human_response,
            "intent": intent,
            "retries": 0,
            "code_executed": code,
            "raw_result": result,
            "model_used": model_used,
        }
