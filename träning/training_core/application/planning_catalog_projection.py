"""Strict Planning Engine v1 workout-catalog projection.

Only explicit planning_engine_v1 catalog semantics are accepted. Legacy recipe
names, option values and load-dimension labels are not interpreted implicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from training_core.planning.models import (
    ApprovedWorkoutOption,
    LoadDimensionExposure,
    LoadDimensionLevel,
    LoadEstimate,
    PlanningContractError,
    WorkoutComponentIntent,
)


class CatalogProjectionError(PlanningContractError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


class DoseEvidenceMode(str, Enum):
    NUMERIC = "numeric"
    QUALITATIVE = "qualitative"


@dataclass(frozen=True)
class OptionDoseEvidence:
    recipe_id: str
    dose_option_id: str
    capability: str
    mode: DoseEvidenceMode
    source_refs: tuple[str, ...]
    metric: str | None = None
    value: float | None = None

    def __post_init__(self) -> None:
        for field in ("recipe_id", "dose_option_id", "capability"):
            value = str(getattr(self, field) or "").strip()
            if not value:
                raise CatalogProjectionError(
                    "INVALID_V1_CATALOG_CONTRACT",
                    f"{field} must be non-empty",
                )
            object.__setattr__(self, field, value)
        refs = tuple(str(item or "").strip() for item in self.source_refs)
        if not refs or any(not item for item in refs) or len(set(refs)) != len(refs):
            raise CatalogProjectionError(
                "INVALID_V1_CATALOG_CONTRACT",
                "eligibility basis requires unique non-empty source_refs",
            )
        object.__setattr__(self, "source_refs", refs)

        if not isinstance(self.mode, DoseEvidenceMode):
            raise CatalogProjectionError(
                "INVALID_V1_CATALOG_CONTRACT",
                "eligibility basis mode must be DoseEvidenceMode",
            )
        if self.mode is DoseEvidenceMode.NUMERIC:
            metric = str(self.metric or "").strip()
            if not metric:
                raise CatalogProjectionError(
                    "INVALID_V1_CATALOG_CONTRACT",
                    "numeric eligibility basis requires metric",
                )
            if isinstance(self.value, bool) or not isinstance(
                self.value, (int, float)
            ):
                raise CatalogProjectionError(
                    "INVALID_V1_CATALOG_CONTRACT",
                    "numeric eligibility basis requires numeric value",
                )
            if float(self.value) < 0:
                raise CatalogProjectionError(
                    "INVALID_V1_CATALOG_CONTRACT",
                    "numeric eligibility basis value must be >= 0",
                )
            object.__setattr__(self, "metric", metric)
            object.__setattr__(self, "value", float(self.value))
        else:
            if self.metric is not None or self.value is not None:
                raise CatalogProjectionError(
                    "INVALID_V1_CATALOG_CONTRACT",
                    "qualitative eligibility basis cannot carry numeric metric/value",
                )

    @property
    def eligibility_key(self) -> tuple[str, str, str]:
        return self.recipe_id, self.dose_option_id, self.capability


@dataclass(frozen=True)
class PlanningCatalogProjection:
    revision_id: str
    approved_options: tuple[ApprovedWorkoutOption, ...]
    eligibility_basis: tuple[OptionDoseEvidence, ...]
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        revision = str(self.revision_id or "").strip()
        if not revision:
            raise CatalogProjectionError(
                "INVALID_V1_CATALOG_CONTRACT",
                "catalog revision_id must be non-empty",
            )
        object.__setattr__(self, "revision_id", revision)
        options = tuple(self.approved_options)
        if not options:
            raise CatalogProjectionError(
                "INVALID_V1_CATALOG_CONTRACT",
                "catalog projection requires approved options",
            )
        keys = [item.option_key for item in options]
        if len(set(keys)) != len(keys):
            raise CatalogProjectionError(
                "INVALID_V1_CATALOG_CONTRACT",
                "catalog projection contains duplicate option keys",
            )
        object.__setattr__(self, "approved_options", options)

        basis = tuple(self.eligibility_basis)
        basis_keys = [item.eligibility_key for item in basis]
        if len(set(basis_keys)) != len(basis_keys):
            raise CatalogProjectionError(
                "INVALID_V1_CATALOG_CONTRACT",
                "catalog projection contains duplicate eligibility basis",
            )
        expected = {
            (option.recipe_id, option.dose_option_id, capability)
            for option in options
            for capability in option.capabilities
        }
        if set(basis_keys) != expected:
            missing = sorted(expected - set(basis_keys))
            unexpected = sorted(set(basis_keys) - expected)
            raise CatalogProjectionError(
                "INCOMPLETE_V1_ELIGIBILITY_BASIS",
                f"missing={missing} unexpected={unexpected}",
            )
        object.__setattr__(self, "eligibility_basis", basis)

        refs = tuple(str(item or "").strip() for item in self.source_refs)
        if not refs or any(not item for item in refs) or len(set(refs)) != len(refs):
            raise CatalogProjectionError(
                "INVALID_V1_CATALOG_CONTRACT",
                "catalog projection requires unique non-empty source_refs",
            )
        object.__setattr__(self, "source_refs", refs)


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CatalogProjectionError(
            "INVALID_V1_CATALOG_SOURCE",
            f"{field} must be an object",
        )
    return value


def _list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise CatalogProjectionError(
            "INVALID_V1_CATALOG_SOURCE",
            f"{field} must be an array",
        )
    return value


def _strings(value: Any, field: str) -> tuple[str, ...]:
    return tuple(str(item) for item in _list(value, field))


def _dimension(row: dict[str, Any], field: str) -> LoadDimensionExposure:
    try:
        return LoadDimensionExposure(
            dimension=str(row.get("dimension") or ""),
            level=LoadDimensionLevel(str(row.get("level") or "")),
            provenance_refs=_strings(
                row.get("provenance_refs"),
                f"{field}.provenance_refs",
            ),
        )
    except (PlanningContractError, ValueError) as exc:
        raise CatalogProjectionError(
            "INVALID_V1_CATALOG_CONTRACT",
            str(exc),
        ) from exc


def _load(row: dict[str, Any], field: str) -> LoadEstimate:
    try:
        return LoadEstimate(
            scope=str(row.get("scope") or ""),
            subject=str(row.get("subject") or ""),
            metric=str(row.get("metric") or ""),
            unit=str(row.get("unit") or ""),
            min_value=row.get("min_value"),
            max_value=row.get("max_value"),
            provenance_refs=_strings(
                row.get("provenance_refs"),
                f"{field}.provenance_refs",
            ),
        )
    except PlanningContractError as exc:
        raise CatalogProjectionError(
            "INVALID_V1_CATALOG_CONTRACT",
            str(exc),
        ) from exc


def compile_catalog_projection(
    canonical_catalog: dict[str, Any],
) -> PlanningCatalogProjection:
    root = _mapping(canonical_catalog, "canonical_catalog")
    v1 = root.get("planning_engine_v1")
    if not isinstance(v1, dict):
        raise CatalogProjectionError(
            "MISSING_V1_CATALOG_PROJECTION",
            "canonical catalog lacks explicit planning_engine_v1 section",
        )
    if v1.get("schema_version") != 1:
        raise CatalogProjectionError(
            "UNSUPPORTED_V1_CATALOG_SCHEMA",
            "planning_engine_v1.schema_version must equal 1",
        )
    source = _mapping(
        v1.get("catalog_revision"),
        "planning_engine_v1.catalog_revision",
    )
    option_rows = _list(source.get("options"), "catalog_revision.options")

    options: list[ApprovedWorkoutOption] = []
    bases: list[OptionDoseEvidence] = []
    for index, raw in enumerate(option_rows):
        row = _mapping(raw, f"catalog_revision.options[{index}]")
        recipe_id = str(row.get("recipe_id") or "")
        dose_option_id = str(row.get("dose_option_id") or "")
        capabilities = _strings(
            row.get("capabilities"),
            f"catalog_revision.options[{index}].capabilities",
        )
        components = tuple(
            WorkoutComponentIntent(
                discipline=str(component.get("discipline") or ""),
                order=component.get("order"),
            )
            for component in (
                _mapping(
                    item,
                    f"catalog_revision.options[{index}].components[{component_index}]",
                )
                for component_index, item in enumerate(
                    _list(
                        row.get("components"),
                        f"catalog_revision.options[{index}].components",
                    )
                )
            )
        )
        dimensions = tuple(
            _dimension(
                _mapping(
                    item,
                    f"catalog_revision.options[{index}].load_dimensions[{dimension_index}]",
                ),
                f"catalog_revision.options[{index}].load_dimensions[{dimension_index}]",
            )
            for dimension_index, item in enumerate(
                _list(
                    row.get("load_dimensions"),
                    f"catalog_revision.options[{index}].load_dimensions",
                )
            )
        )
        loads = tuple(
            _load(
                _mapping(
                    item,
                    f"catalog_revision.options[{index}].quantitative_load[{load_index}]",
                ),
                f"catalog_revision.options[{index}].quantitative_load[{load_index}]",
            )
            for load_index, item in enumerate(
                _list(
                    row.get("quantitative_load", []),
                    f"catalog_revision.options[{index}].quantitative_load",
                )
            )
        )

        try:
            option = ApprovedWorkoutOption(
                recipe_id=recipe_id,
                dose_option_id=dose_option_id,
                capabilities=capabilities,
                components=components,
                load_dimensions=dimensions,
                quantitative_load=loads,
                source_refs=_strings(
                    row.get("source_refs"),
                    f"catalog_revision.options[{index}].source_refs",
                ),
                development_character=str(
                    row.get("development_character") or ""
                ),
                planning_priority=row.get("planning_priority", 100),
            )
        except PlanningContractError as exc:
            raise CatalogProjectionError(
                "INVALID_V1_CATALOG_CONTRACT",
                str(exc),
            ) from exc
        options.append(option)

        for basis_index, raw_basis in enumerate(
            _list(
                row.get("eligibility_basis"),
                f"catalog_revision.options[{index}].eligibility_basis",
            )
        ):
            basis_row = _mapping(
                raw_basis,
                f"catalog_revision.options[{index}].eligibility_basis[{basis_index}]",
            )
            try:
                mode = DoseEvidenceMode(str(basis_row.get("mode") or ""))
            except ValueError as exc:
                raise CatalogProjectionError(
                    "INVALID_V1_CATALOG_CONTRACT",
                    "unknown eligibility basis mode",
                ) from exc
            bases.append(
                OptionDoseEvidence(
                    recipe_id=recipe_id,
                    dose_option_id=dose_option_id,
                    capability=str(basis_row.get("capability") or ""),
                    mode=mode,
                    metric=(
                        str(basis_row.get("metric"))
                        if basis_row.get("metric") is not None
                        else None
                    ),
                    value=basis_row.get("value"),
                    source_refs=_strings(
                        basis_row.get("source_refs"),
                        f"catalog_revision.options[{index}].eligibility_basis[{basis_index}].source_refs",
                    ),
                )
            )

    return PlanningCatalogProjection(
        revision_id=str(source.get("revision_id") or ""),
        approved_options=tuple(options),
        eligibility_basis=tuple(bases),
        source_refs=_strings(
            source.get("source_refs"),
            "catalog_revision.source_refs",
        ),
    )
