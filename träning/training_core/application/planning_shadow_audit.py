"""Append-only audit records for non-authoritative Planning Engine v1 shadow runs."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import date
from enum import Enum
from fractions import Fraction
from typing import Any, Protocol

from .planning_shadow import ShadowPlanningRunInput, ShadowPlanningRunResult


class ShadowRunAuditError(ValueError):
    pass


def _required_text(value: str, field: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ShadowRunAuditError(f"{field} must be non-empty")
    return normalized


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Fraction):
        return {
            "numerator": value.numerator,
            "denominator": value.denominator,
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, date):
        return value.isoformat()
    if is_dataclass(value):
        return {
            field.name: _jsonable(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, dict):
        return {
            str(key): _jsonable(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    raise ShadowRunAuditError(
        f"unsupported shadow audit value type: {type(value).__name__}"
    )


@dataclass(frozen=True)
class ShadowRunAuditRecord:
    event_key: str
    trigger_source: str
    microcycle_key: str | None
    source_revision: str
    semantic_input_hash: str | None
    strategy_revision_id: str | None
    engine_version: str | None
    affected_from: str
    affected_until: str
    readiness_status: str
    blocker_codes: tuple[str, ...]
    solver_status: str | None
    plan_content_hash: str | None
    semantic_input: dict | None
    plan_content: dict | None
    objective_vector: dict | None
    decision_trace: dict

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "event_key",
            _required_text(self.event_key, "event_key"),
        )
        object.__setattr__(
            self,
            "trigger_source",
            _required_text(self.trigger_source, "trigger_source"),
        )
        object.__setattr__(
            self,
            "source_revision",
            _required_text(self.source_revision, "source_revision"),
        )
        if self.readiness_status not in {"ready", "blocked"}:
            raise ShadowRunAuditError("invalid readiness_status")
        if self.solver_status not in {None, "current", "blocked"}:
            raise ShadowRunAuditError("invalid solver_status")
        if self.readiness_status == "blocked" and self.solver_status is not None:
            raise ShadowRunAuditError(
                "readiness-blocked shadow record cannot contain solver status"
            )
        if self.readiness_status == "ready" and self.solver_status is None:
            raise ShadowRunAuditError(
                "ready shadow record requires solver status"
            )
        if self.solver_status == "current":
            if not self.plan_content_hash or self.plan_content is None:
                raise ShadowRunAuditError(
                    "current shadow solve requires exact plan content/hash"
                )
        if self.solver_status == "blocked":
            if self.plan_content_hash is not None or self.plan_content is not None:
                raise ShadowRunAuditError(
                    "blocked shadow solve cannot expose plan content"
                )

    def as_db_row(self) -> dict[str, Any]:
        return {
            "event_key": self.event_key,
            "trigger_source": self.trigger_source,
            "microcycle_key": self.microcycle_key,
            "source_revision": self.source_revision,
            "semantic_input_hash": self.semantic_input_hash,
            "strategy_revision_id": self.strategy_revision_id,
            "engine_version": self.engine_version,
            "affected_from": self.affected_from,
            "affected_until": self.affected_until,
            "readiness_status": self.readiness_status,
            "blocker_codes": list(self.blocker_codes),
            "solver_status": self.solver_status,
            "plan_content_hash": self.plan_content_hash,
            "semantic_input": self.semantic_input,
            "plan_content": self.plan_content,
            "objective_vector": self.objective_vector,
            "decision_trace": self.decision_trace,
        }


class ShadowRunAuditRepository(Protocol):
    """Append-only persistence boundary for shadow evidence."""

    def append(self, record: ShadowRunAuditRecord) -> None:
        ...


def build_shadow_audit_record(
    request: ShadowPlanningRunInput,
    result: ShadowPlanningRunResult,
    *,
    event_key: str,
    trigger_source: str,
    microcycle_key: str | None = None,
) -> ShadowRunAuditRecord:
    readiness_trace = {
        "ready": result.readiness.ready,
        "blockers": _jsonable(result.readiness.blockers),
    }

    if result.solve_result is None:
        return ShadowRunAuditRecord(
            event_key=event_key,
            trigger_source=trigger_source,
            microcycle_key=microcycle_key,
            source_revision=result.readiness.source_revision,
            semantic_input_hash=None,
            strategy_revision_id=None,
            engine_version=None,
            affected_from=request.affected_from.isoformat(),
            affected_until=request.affected_until.isoformat(),
            readiness_status="blocked",
            blocker_codes=result.readiness.blocker_codes,
            solver_status=None,
            plan_content_hash=None,
            semantic_input=None,
            plan_content=None,
            objective_vector=None,
            decision_trace={"readiness": readiness_trace},
        )

    solved = result.solve_result
    state = solved.authority_state
    trace = {
        "readiness": readiness_trace,
        "solver": _jsonable(solved.trace),
        "blocked_reason_codes": list(state.blocked_reason_codes),
    }
    return ShadowRunAuditRecord(
        event_key=event_key,
        trigger_source=trigger_source,
        microcycle_key=microcycle_key,
        source_revision=state.source_revision,
        semantic_input_hash=state.semantic_input_hash,
        strategy_revision_id=state.strategy_revision_id,
        engine_version=state.engine_version,
        affected_from=request.affected_from.isoformat(),
        affected_until=request.affected_until.isoformat(),
        readiness_status="ready",
        blocker_codes=(),
        solver_status=state.status.value,
        plan_content_hash=state.plan_content_hash,
        semantic_input=_jsonable(result.semantic_input_payload),
        plan_content=_jsonable(solved.plan),
        objective_vector=_jsonable(solved.objective_vector),
        decision_trace=trace,
    )


def append_shadow_audit_record(
    request: ShadowPlanningRunInput,
    result: ShadowPlanningRunResult,
    repository: ShadowRunAuditRepository,
    *,
    event_key: str,
    trigger_source: str,
    microcycle_key: str | None = None,
) -> ShadowRunAuditRecord:
    record = build_shadow_audit_record(
        request,
        result,
        event_key=event_key,
        trigger_source=trigger_source,
        microcycle_key=microcycle_key,
    )
    repository.append(record)
    return record
