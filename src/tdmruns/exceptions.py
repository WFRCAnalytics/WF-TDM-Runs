"""Custom exceptions, kept specific so CLI output and logs can be precise about
what failed and why -- this matters for the framework's validation-before-execution
and traceability goals."""


class tdmrunsError(Exception):
    """Base class for all framework errors."""


class ConfigValidationError(tdmrunsError):
    """Raised when a run_set.yaml / scenario.yaml / framework.yaml fails schema
    validation, or references something (a run set, scenario, or baseline file)
    that does not exist."""


class VersionResolutionError(tdmrunsError):
    """Raised when the requested TDM ref cannot be resolved, the submodule
    working tree is dirty, or the resolved state cannot be verified."""


class ControlCenterError(tdmrunsError):
    """Raised when a Control Center baseline file cannot be read, or when a
    scenario/run set override key does not exist in the chosen baseline."""


class ExecutionError(tdmrunsError):
    """Raised when the TDM batch entry point exits with a non-zero status."""


class OutputCollectionError(tdmrunsError):
    """Raised when a selected output file exceeds the configured size limit,
    or an output selection pattern matches nothing and is marked as required."""


class PrepScriptError(tdmrunsError):
    """Raised when a declared prep script is not found or exits non-zero."""
