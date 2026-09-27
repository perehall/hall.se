"""Typed device-sync presentation state for structured planned workouts."""

from __future__ import annotations

from dataclasses import dataclass


STATUS_COPY = {
    "pending": "Klocksync väntar",
    "synced": "Klocksync skickad",
    "error": "Klocksync fel",
}

STATUS_HELP = {
    "pending": "Strukturerat pass väntar på transport via Intervals.icu till Garmin.",
    "synced": (
        "Passet är verifierat i Intervals.icu och kan därifrån skickas vidare "
        "till Garmin; leverans till själva klockan kan inte verifieras av träningssystemet."
    ),
    "error": (
        "Transporten via Intervals.icu misslyckades senast och försöks igen "
        "i nästa träningsjobb."
    ),
}

VALID_STORED_STATUSES = {"pending", "synced", "error", "deferred"}


@dataclass(frozen=True)
class DeviceSyncReadModel:
    status: str
    label: str
    help_text: str
    transport: str


def build_device_sync_read_model(
    payload: dict | None,
    *,
    completed: bool,
) -> DeviceSyncReadModel | None:
    if completed:
        return None

    raw = (payload or {}).get("device_sync")
    workout = (payload or {}).get("device_workout")
    if raw is None and workout is None:
        return None
    if not isinstance(raw, dict) or not isinstance(workout, dict):
        raise RuntimeError("device_sync/device_workout must exist together")

    status = str(raw.get("status") or "").strip().lower()
    if status not in VALID_STORED_STATUSES:
        raise RuntimeError(f"invalid device sync status: {status!r}")

    source_hash = str(raw.get("source_hash") or "").strip()
    workout_hash = str(workout.get("source_hash") or "").strip()
    if not source_hash or source_hash != workout_hash:
        raise RuntimeError("device sync source hash differs from device workout")

    delivery = str(raw.get("device_delivery") or "").strip().lower()
    if delivery and delivery != "unverified":
        raise RuntimeError(
            "device sync must not claim verified delivery to the physical watch"
        )

    if status == "deferred":
        return None

    transport = str(raw.get("transport") or "").strip()
    if transport and transport != "intervals_icu":
        raise RuntimeError(f"unsupported device sync transport: {transport!r}")

    return DeviceSyncReadModel(
        status=status,
        label=STATUS_COPY[status],
        help_text=STATUS_HELP[status],
        transport=transport or "intervals_icu",
    )
