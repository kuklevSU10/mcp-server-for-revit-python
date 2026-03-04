"""
execute_v2 — KUKAI AI code execution engine for Revit.

Phase 1 MVP: SandboxValidator, SafeNamespace, TransactionExecutor, instrument_loops
Phase 2 Smart Pipeline: IntentClassifier, ContextBuilder, CodeGenerator, ResultFormatter, Pipeline
Phase 3 Production Polish: SessionState, AuditLog, ModelRouter
"""

from .sandbox_validator import SandboxValidator
from .safe_namespace import build_safe_namespace
from .transaction_executor import TransactionExecutor
from .timeout_instrumenter import instrument_loops
from .intent_classifier import IntentClassifier, IntentType
from .context_builder import ContextBuilder
from .code_generator import CodeGenerator
from .result_formatter import ResultFormatter
from .retry_loop import RetryLoop
from .pipeline import ExecuteV2Pipeline
from .session_state import SessionState, SessionManager
from .audit_log import AuditLog
from .model_router import ModelRouter

__all__ = [
    # Phase 1
    "SandboxValidator",
    "build_safe_namespace",
    "TransactionExecutor",
    "instrument_loops",
    # Phase 2
    "IntentClassifier",
    "IntentType",
    "ContextBuilder",
    "CodeGenerator",
    "ResultFormatter",
    "RetryLoop",
    "ExecuteV2Pipeline",
    # Phase 3
    "SessionState",
    "SessionManager",
    "AuditLog",
    "ModelRouter",
]
