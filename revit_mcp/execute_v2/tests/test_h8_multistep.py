import pytest
from revit_mcp.execute_v2.multi_step import MultiStepPlan, MultiStepExecutor, detect_multi_step

class TestMultiStepV2:
    def test_detect_multi_step(self):
        assert detect_multi_step("сначала найди двери, а потом удали их") is True
        assert detect_multi_step("шаг 1: найди, шаг 2: удали") is True
        assert detect_multi_step("найди все двери") is False

    def test_plan_from_llm(self):
        llm_response = """
        Here is the plan:
        {
            "description": "Test plan",
            "steps": [
                {"description": "Step 1", "request": "Req 1", "depends_on": null},
                {"description": "Step 2", "request": "Req 2", "depends_on": 0}
            ]
        }
        """
        plan = MultiStepPlan.from_llm_response(llm_response)
        assert len(plan) == 2
        assert plan.description == "Test plan"
        assert plan.steps[0]["request"] == "Req 1"
        assert plan.steps[1]["depends_on"] == 0