"""Load and render prompt templates from prompts/."""

from __future__ import annotations

import logging
from pathlib import Path
from string import Template

logger = logging.getLogger(__name__)

DEFAULT_PROMPT_DIR = Path("prompts")


class PromptLibrary:
    """Loads ``{name}.md`` templates and renders them with ``$placeholder``
    substitution (``string.Template`` — safe with JSON braces in the template)."""

    def __init__(self, prompt_dir: Path = DEFAULT_PROMPT_DIR) -> None:
        self.prompt_dir = Path(prompt_dir)
        self._cache: dict[str, str] = {}

    def load(self, name: str) -> str:
        if name not in self._cache:
            self._cache[name] = (self.prompt_dir / f"{name}.md").read_text(encoding="utf-8")
        return self._cache[name]

    def render(self, name: str, **context: object) -> str:
        return Template(self.load(name)).safe_substitute(**context)
