from __future__ import annotations

import pytest

from services.prompts.loader import PROMPT_STEPS, PromptLoader, PromptNotFoundError


def test_prompt_loader_loads_post_and_event_bundles() -> None:
    loader = PromptLoader()

    post_bundle = loader.load_bundle("post")
    event_bundle = loader.load_bundle("event")

    assert set(post_bundle.keys()) == set(PROMPT_STEPS)
    assert set(event_bundle.keys()) == set(PROMPT_STEPS)
    assert all(post_bundle[step] for step in PROMPT_STEPS)
    assert all(event_bundle[step] for step in PROMPT_STEPS)
    assert all("TODO" not in post_bundle[step] for step in PROMPT_STEPS)
    assert all("TODO" not in event_bundle[step] for step in PROMPT_STEPS)


def test_synthesis_prompts_define_five_component_order_contract() -> None:
    loader = PromptLoader()
    for scope in ("post", "event"):
        text = loader.load(scope, "synthesis").lower()
        assert "1. event" in text
        assert "2. context" in text
        assert "3. public reaction" in text
        assert "4. interpretation" in text
        assert "5. consequences" in text


def test_prompt_loader_rejects_unknown_scope_or_step() -> None:
    loader = PromptLoader()

    with pytest.raises(ValueError, match="Unsupported prompt scope"):
        loader.load("process", "context")

    with pytest.raises(ValueError, match="Unsupported prompt step"):
        loader.load("post", "planner")


def test_prompt_loader_raises_when_prompt_file_missing(tmp_path) -> None:
    loader = PromptLoader(root_path=tmp_path)

    (tmp_path / "post").mkdir(parents=True, exist_ok=True)

    with pytest.raises(PromptNotFoundError, match="Prompt file not found"):
        loader.load("post", "context")
