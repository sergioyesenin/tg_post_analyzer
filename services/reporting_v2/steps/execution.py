from __future__ import annotations

import inspect
from typing import Any, Awaitable, Callable, TypeVar

TState = TypeVar("TState")

SIX_STEP_SEQUENCE = (
    "context",
    "routing",
    "expert",
    "public_opinion",
    "synthesis",
    "reviewer",
)

TraceMutator = Callable[[dict[str, Any]], None]
StateStepHandler = Callable[[TState], TState | Awaitable[TState]]


class StepExecutionError(RuntimeError):
    def __init__(self, *, step_name: str, reason: str) -> None:
        super().__init__(f"Step '{step_name}' failed: {reason}")
        self.step_name = step_name
        self.reason = reason


def default_step_provenance() -> dict[str, Any]:
    return {
        "provider": "deterministic",
        "model": "reporting_v2_policy",
        "executed": True,
        "success": True,
        "latency_ms": None,
        "input_ref": None,
        "input_hash": None,
        "output_ref": None,
        "output_hash": None,
        "fallback_used": False,
        "fallback_reason": None,
        "attempt_index": 0,
        "status": "completed",
    }


def build_step_traces(step_names: tuple[str, ...] = SIX_STEP_SEQUENCE) -> dict[str, dict[str, Any]]:
    return {
        step: {
            "status": "completed",
            "run_count": 1,
            "provenance": default_step_provenance(),
            "provenance_source": "observed",
        }
        for step in step_names
    }


def sync_step_provenance(step_traces: dict[str, dict[str, Any]]) -> None:
    for _step_name, trace in step_traces.items():
        provenance = dict(trace.get("provenance") or default_step_provenance())
        run_count = int(trace.get("run_count") or 1)
        trace_status = str(trace.get("status") or "completed")
        provenance_attempt = int(provenance.get("attempt_index") or 0)
        provenance["attempt_index"] = max(provenance_attempt, max(0, run_count - 1))
        provenance["status"] = trace_status if trace_status in {"completed", "failed", "skipped"} else "completed"
        if provenance["status"] == "failed":
            provenance["success"] = False
        trace["provenance"] = provenance


def provider_from_adapter(adapter: Any) -> str:
    if adapter is None:
        return "deterministic"
    base_url = str(getattr(getattr(adapter, "config", None), "base_url", "") or "").lower()
    if "openrouter" in base_url:
        return "openrouter"
    return "openai_compatible"


def mark_provider_backed_execution(
    *,
    step_traces: dict[str, dict[str, Any]],
    provider: str,
    model: str,
    step_names: tuple[str, ...] = SIX_STEP_SEQUENCE,
) -> None:
    for step_name in step_names:
        trace = dict(step_traces.get(step_name) or {})
        provenance = dict(trace.get("provenance") or default_step_provenance())
        provenance["provider"] = provider
        provenance["model"] = model
        trace["provenance"] = provenance
        step_traces[step_name] = trace


def is_canonical_openrouter_ready_path(
    step_traces: dict[str, dict[str, Any]],
    *,
    step_names: tuple[str, ...] = SIX_STEP_SEQUENCE,
) -> bool:
    for step_name in step_names:
        trace = dict(step_traces.get(step_name) or {})
        provenance = dict(trace.get("provenance") or {})
        if provenance.get("provider") != "openrouter":
            return False
        if provenance.get("executed") is not True:
            return False
        if provenance.get("success") is not True:
            return False
        if provenance.get("fallback_used") is True:
            return False
        if str(provenance.get("status") or "") != "completed":
            return False
    return True


def request_step_rerun(step_traces: dict[str, dict[str, Any]], *, step_name: str) -> None:
    trace = dict(step_traces.get(step_name) or {})
    trace["run_count"] = int(trace.get("run_count") or 1) + 1
    trace["rerun_requested"] = True
    step_traces[step_name] = trace


def apply_step_trace_envelope(
    step_traces: dict[str, dict[str, Any]],
    *,
    step_name: str,
    mutator: TraceMutator,
) -> None:
    trace = dict(step_traces.get(step_name) or {})
    try:
        mutator(trace)
        trace["status"] = str(trace.get("status") or "completed")
    except Exception as exc:
        trace["status"] = "failed"
        raise StepExecutionError(step_name=step_name, reason=f"{type(exc).__name__}: {exc}") from exc
    step_traces[step_name] = trace


async def execute_state_step(*, state: TState, step_name: str, handler: StateStepHandler[TState]) -> TState:
    try:
        result = handler(state)
        if inspect.isawaitable(result):
            return await result
        return result
    except Exception as exc:
        raise StepExecutionError(step_name=step_name, reason=f"{type(exc).__name__}: {exc}") from exc
