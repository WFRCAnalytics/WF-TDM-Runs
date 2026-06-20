"""
tdmruns — orchestration framework for TDM sensitivity testing.

This package never modifies the TDM submodule's own model code, defaults
library, or scenario-folder conventions. It only: resolves and validates the
requested TDM version, renders a per-run Control Center file from layered
config, invokes the TDM's fixed batch entry point, curates a size-bounded
subset of outputs into this repository, and records structured run metadata.
"""

__version__ = "0.1.0"
