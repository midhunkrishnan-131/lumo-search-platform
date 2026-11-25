"""LUMO Phase 16 Intelligence Automation Engine package."""

from app.automation.conditions import evaluate_condition
from app.automation.engine import AutomationManager, automation_manager, compute_next_run
from app.automation.templates import AUTOMATION_TEMPLATES

__all__ = [
    "AutomationManager",
    "automation_manager",
    "compute_next_run",
    "evaluate_condition",
    "AUTOMATION_TEMPLATES",
]
