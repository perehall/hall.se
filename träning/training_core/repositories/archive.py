"""Explicit adapter for the generated week archive manifest.

The manifest is publication metadata, not canonical training state. This
adapter never infers availability by inspecting generated HTML directories.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol, Sequence

from training_core.presentation.navigation import PublishedWeek


class WeekArchiveRepository(Protocol):
    def published_weeks(self) -> Sequence[PublishedWeek]: ...


@dataclass(frozen=True)
class ManifestWeekArchiveRepository:
    path: Path

    def published_weeks(self) -> list[PublishedWeek]:
        document = json.loads(self.path.read_text(encoding="utf-8"))
        if document.get("schema_version") != 2:
            raise RuntimeError("unsupported week archive manifest")
        result = []
        for row in document.get("weeks") or []:
            key = str(row.get("key") or "").strip()
            start = date.fromisoformat(str(row.get("week_start") or ""))
            end = date.fromisoformat(str(row.get("week_end") or ""))
            url = str(row.get("url") or "").strip()
            if not key or not url or (end - start).days != 6:
                raise RuntimeError(f"invalid week archive manifest row: {row!r}")
            result.append(
                PublishedWeek(
                    key=key,
                    week_start=start,
                    week_end=end,
                    url=url,
                )
            )
        return result
