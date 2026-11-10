"""Prompt loader forwarding layer.

Exposes the loader's public API via ``from agent.prompts import load_system_prompt_text, load_sdk_docs_reference``
so callers do not depend on ``agent.prompts.loader`` directly.
"""

from .loader import (
    load_system_prompt_text,
    load_prompt_section_text,
    load_sdk_docs_reference,
)

__all__ = [
    "load_system_prompt_text",
    "load_prompt_section_text",
    "load_sdk_docs_reference",
]
