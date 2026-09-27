"""Typed sport icon registry for the v2 presentation boundary."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


KNOWN_ICON_KEYS = {"run", "swim", "bike", "enduro", "strength", "activity"}


@dataclass(frozen=True)
class SportIcon:
    key: str
    view_box: str
    path: str
    solid: bool = True


@dataclass(frozen=True)
class SportIconRegistry:
    icons: dict[str, SportIcon]

    def require(self, key: str) -> SportIcon:
        normalized = key if key in KNOWN_ICON_KEYS else "activity"
        icon = self.icons.get(normalized)
        if icon is None:
            raise RuntimeError(f"missing sport icon asset: {normalized}")
        return icon


class SportIconRepository(Protocol):
    def current(self) -> SportIconRegistry: ...


@dataclass(frozen=True)
class FileSportIconRepository:
    path: Path

    def current(self) -> SportIconRegistry:
        document = json.loads(self.path.read_text(encoding="utf-8"))
        raw = document.get("icons") or {}
        icons: dict[str, SportIcon] = {}
        for key, value in raw.items():
            if key not in KNOWN_ICON_KEYS:
                continue
            if not isinstance(value, dict):
                raise RuntimeError(f"invalid sport icon entry: {key}")
            view_box = str(value.get("viewBox") or "").strip()
            path = str(value.get("path") or "").strip()
            if not view_box or not path:
                raise RuntimeError(f"incomplete sport icon entry: {key}")
            icons[key] = SportIcon(key=key, view_box=view_box, path=path, solid=True)

        # "activity" is the only fallback and can be a simple line glyph.
        if "activity" not in icons:
            icons["activity"] = SportIcon(
                key="activity",
                view_box="0 0 24 24",
                path="M3 12h4l2-5 4 10 2-5h6",
                solid=False,
            )
        for required in ("run", "swim", "bike", "enduro", "strength"):
            if required not in icons:
                raise RuntimeError(f"sport icon registry missing required icon: {required}")
        return SportIconRegistry(icons=icons)
