from __future__ import annotations

from pathlib import Path

from config import settings

PROMPT_SCOPES = ("post", "event")
PROMPT_STEPS = ("context", "routing", "expert", "public_opinion", "synthesis", "reviewer")


class PromptNotFoundError(FileNotFoundError):
    pass


class PromptLoader:
    def __init__(self, root_path: str | Path | None = None) -> None:
        base = Path(root_path) if root_path is not None else Path(settings.REPORT_V2_PROMPTS_ROOT)
        self.root_path = base

    def _validate_scope(self, scope: str) -> None:
        if scope not in PROMPT_SCOPES:
            raise ValueError(f"Unsupported prompt scope: {scope}")

    def _validate_step(self, step: str) -> None:
        if step not in PROMPT_STEPS:
            raise ValueError(f"Unsupported prompt step: {step}")

    def path_for(self, scope: str, step: str) -> Path:
        self._validate_scope(scope)
        self._validate_step(step)
        return self.root_path / scope / f"{step}.md"

    def load(self, scope: str, step: str) -> str:
        path = self.path_for(scope, step)
        if not path.exists():
            raise PromptNotFoundError(f"Prompt file not found: {path}")
        return path.read_text(encoding="utf-8").strip()

    def load_bundle(self, scope: str) -> dict[str, str]:
        self._validate_scope(scope)
        return {step: self.load(scope, step) for step in PROMPT_STEPS}
