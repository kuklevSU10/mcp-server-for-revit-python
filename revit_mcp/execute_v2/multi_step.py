"""
Multi-Step Executor — chains of operations for complex multi-part requests.

Splits a user task into sequential steps, executes each through the Pipeline,
and handles dependencies between steps via SessionState.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("kukai.execute_v2.multi_step")


# Patterns that indicate a multi-step request
_MULTI_STEP_PATTERNS_RU = [
    r"сначала\b.*\b(?:потом|затем|после)",
    r"\bпотом\b",
    r"\bзатем\b",
    r"\bпосле\s+этого\b",
    r"\bа\s+затем\b",
    r"\bи\s+создай\b",
    r"\bи\s+переименуй\b",
    r"\bво-первых\b.*\bво-вторых\b",
    r"\b1\)\s.*\b2\)\s",
    r"\bшаг\s+1\b.*\bшаг\s+2\b",
]

_MULTI_STEP_PATTERNS_EN = [
    r"\bfirst\b.*\bthen\b",
    r"\band\s+then\b",
    r"\bafter\s+that\b",
    r"\bnext[\s,]+",
    r"\bstep\s+1\b.*\bstep\s+2\b",
]

_ALL_PATTERNS = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in _MULTI_STEP_PATTERNS_RU + _MULTI_STEP_PATTERNS_EN]


def detect_multi_step(user_request: str) -> bool:
    """
    Determine if the user request requires a multi-step plan.

    Looks for sequential language markers in Russian and English.
    """
    if not user_request:
        return False
    for pattern in _ALL_PATTERNS:
        if pattern.search(user_request):
            return True
    return False


class StepResult:
    """Result of a single step execution."""

    def __init__(self, step_index: int, description: str, status: str, output: str, elements_affected: Optional[List[int]] = None):
        self.step_index = step_index
        self.description = description
        self.status = status  # "success" | "error" | "rejected"
        self.output = output
        self.elements_affected = elements_affected or []

    def to_dict(self) -> Dict:
        return {
            "step_index": self.step_index,
            "description": self.description,
            "status": self.status,
            "output": self.output,
            "elements_affected": self.elements_affected,
        }


class MultiStepPlan:
    """Plan consisting of multiple sequential steps."""

    def __init__(self, steps: List[Dict], description: str = ""):
        """
        Args:
            steps: List of {"description": str, "request": str, "depends_on": int|None}
            description: Overall plan description.
        """
        self.steps = steps
        self.description = description

    @classmethod
    def from_llm_response(cls, llm_response: str) -> "MultiStepPlan":
        """
        Parse a MultiStepPlan from LLM JSON response.

        Expected format:
        {
            "description": "Overall plan description",
            "steps": [
                {"description": "Step 1", "request": "...", "depends_on": null},
                {"description": "Step 2", "request": "...", "depends_on": 0},
                ...
            ]
        }
        """
        # Try to extract JSON from the response (may be wrapped in markdown)
        json_match = re.search(r'\{[\s\S]*\}', llm_response)
        if not json_match:
            raise ValueError("No JSON found in LLM response")

        data = json.loads(json_match.group())

        steps = data.get("steps", [])
        if not steps:
            raise ValueError("No steps found in plan")

        for i, step in enumerate(steps):
            if "request" not in step:
                raise ValueError("Step {} missing 'request' field".format(i))
            if "description" not in step:
                step["description"] = "Шаг {}".format(i + 1)
            if "depends_on" not in step:
                step["depends_on"] = None

        return cls(steps=steps, description=data.get("description", ""))

    def __len__(self):
        return len(self.steps)


class MultiStepPlanner:
    """Uses LLM to plan a sequence of steps for a complex request."""

    def __init__(self, openrouter_key: str = None, model: str = "anthropic/claude-sonnet-4-6"):
        import requests
        self.openrouter_key = openrouter_key
        self.model = model
        self.requests = requests

    def plan(self, user_request: str, context: Dict) -> MultiStepPlan:
        """Generate a multi-step plan."""
        prompt = (
            "You are a Revit API assistant. Break down the user request into a sequence of steps.\n"
            "Respond ONLY with valid JSON. Do not include markdown formatting.\n\n"
            "User Request: {}\n\n"
            "Format:\n"
            "{{\n"
            "  \"description\": \"Overall plan description\",\n"
            "  \"steps\": [\n"
            "    {{\"description\": \"Step 1...\", \"request\": \"...\", \"depends_on\": null}},\n"
            "    {{\"description\": \"Step 2...\", \"request\": \"...\", \"depends_on\": 0}}\n"
            "  ]\n"
            "}}"
        ).format(user_request)

        headers = {
            "Authorization": "Bearer {}".format(self.openrouter_key) if self.openrouter_key else "",
            "HTTP-Referer": "https://kukai.ai",
            "X-Title": "KUKAI Revit",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}]
        }
        
        response = self.requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data)
        response.raise_for_status()
        
        content = response.json()["choices"][0]["message"]["content"]
        return MultiStepPlan.from_llm_response(content)

class MultiStepExecutor:
    """Executes a multi-step plan through the Pipeline, step by step."""

    def __init__(self, pipeline):
        """
        Args:
            pipeline: ExecuteV2Pipeline instance.
        """
        self.pipeline = pipeline

    def execute_plan(
        self,
        plan: MultiStepPlan,
        doc: Any,
        uidoc: Any,
        DB: Any,
        revit: Any,
        session_id: str,
    ) -> Dict:
        """
        Execute all steps in the plan sequentially.

        If a step depends on a previous one, elements are passed via SessionState.
        On error, stops and returns partial results.

        Returns:
            {
                "status": "success" | "partial" | "error",
                "steps_completed": int,
                "steps_total": int,
                "results": [StepResult.to_dict(), ...],
                "summary": str,
            }
        """
        results: List[StepResult] = []
        steps_total = len(plan)

        # Start a TransactionGroup to allow rollback if any step fails
        tg = None
        if hasattr(DB, "TransactionGroup"):
            tg = DB.TransactionGroup(doc, "KUKAI Multi-Step: {}".format(plan.description[:50] if plan.description else "Plan"))
            tg.Start()

        for i, step in enumerate(plan.steps):
            description = step.get("description", "Шаг {}".format(i + 1))
            request = step["request"]
            depends_on = step.get("depends_on")

            logger.info("Executing step %d/%d: %s", i + 1, steps_total, description)

            # If this step depends on a previous one, inject context
            if depends_on is not None and 0 <= depends_on < len(results):
                prev = results[depends_on]
                if prev.elements_affected:
                    # Store previous elements in session so pipeline can access them
                    session = self.pipeline.session_manager.get_or_create(session_id)
                    session.store_elements(prev.elements_affected, "step_{}_result".format(depends_on))

            try:
                result = self.pipeline.run(
                    user_request=request,
                    doc=doc,
                    uidoc=uidoc,
                    DB=DB,
                    revit=revit,
                    session_id=session_id,
                )
            except Exception as e:
                logger.error("Step %d failed with exception: %s", i + 1, e)
                step_result = StepResult(
                    step_index=i,
                    description=description,
                    status="error",
                    output="Exception: {}".format(str(e)),
                )
                results.append(step_result)
                if tg and tg.HasStarted() and not tg.HasEnded():
                    tg.RollBack()
                return self._build_response(results, steps_total, "error")

            # Extract element IDs from result if available
            elements = []
            raw = result.get("raw_result", {})
            result_val = raw.get("result") or raw.get("__result__")
            if isinstance(result_val, list):
                try:
                    elements = [int(e) for e in result_val]
                except (ValueError, TypeError):
                    pass
            elif isinstance(result_val, dict) and "details" in result_val:
                try:
                    elements = [int(e.get("id")) for e in result_val["details"] if isinstance(e, dict) and "id" in e]
                except (ValueError, TypeError):
                    pass

            step_result = StepResult(
                step_index=i,
                description=description,
                status=result.get("status", "error"),
                output=result.get("response", ""),
                elements_affected=elements,
            )
            results.append(step_result)

            if result.get("status") == "error":
                if tg and tg.HasStarted() and not tg.HasEnded():
                    tg.RollBack()
                return self._build_response(results, steps_total, "partial")

        if tg and tg.HasStarted() and not tg.HasEnded():
            tg.Assimilate()

        return self._build_response(results, steps_total, "success")

    def _build_response(self, results: List[StepResult], steps_total: int, status: str) -> Dict:
        """Build the final multi-step response dict."""
        completed = sum(1 for r in results if r.status == "success")

        step_summaries = []
        for r in results:
            icon = "✅" if r.status == "success" else "❌"
            step_summaries.append("{} Шаг {}: {}".format(icon, r.step_index + 1, r.description))

        summary = "Выполнено {}/{} шагов:\n{}".format(completed, steps_total, "\n".join(step_summaries))

        return {
            "status": status,
            "steps_completed": completed,
            "steps_total": steps_total,
            "results": [r.to_dict() for r in results],
            "summary": summary,
        }
