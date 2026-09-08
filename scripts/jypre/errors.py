from __future__ import annotations


class JypreError(Exception):
    """Base error carrying a stable machine-readable code."""

    code = "jypre_error"


class ConfigError(JypreError):
    code = "invalid_config"


class DraftError(JypreError):
    code = "invalid_draft"


class PlanError(JypreError):
    code = "invalid_plan"


class ApplyError(JypreError):
    code = "apply_failed"


class RollbackError(JypreError):
    code = "rollback_failed"
