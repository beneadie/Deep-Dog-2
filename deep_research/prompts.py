"""
Dynamic Prompt Loader for Deep Research Agent.

This module acts as a router to select specific prompt versions based on the
PROMPT_VERSION setting in src/config.py.
"""

from deep_research.config import PROMPT_VERSION

# Legacy version names map to the renamed modules.
_PROMPT_VERSION_ALIASES = {
    "FINANCE_V1": "OPEN_DRAFT",
    "ORIGINAL": "LEAN_ENFORCED",
    "K1_2": "STRICT_ENFORCED",
}

_active = _PROMPT_VERSION_ALIASES.get(PROMPT_VERSION, PROMPT_VERSION).upper()

if _active == "OPEN":
    from deep_research.prompts_open import *
elif _active == "OPEN_DRAFT":
    from deep_research.prompts_open_draft import *
elif _active == "LEAN_ENFORCED":
    from deep_research.prompts_lean_enforced import *
elif _active == "STRICT_ENFORCED":
    from deep_research.prompts_strict_enforced import *
else:
    # Fallback to LEAN_ENFORCED (the base version) if version unknown
    from deep_research.prompts_lean_enforced import *
