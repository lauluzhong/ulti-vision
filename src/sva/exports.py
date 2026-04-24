"""Versioned CSV export helpers built from canonical persisted events."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any

from sva.events_dao import list_event_rows

EXPORT_VERSION = "events.v1"
EXPORT_COLUMNS = [
    "export_version",
    "game_id",
    "point_id",
    "point_ordinal",
    "video_ts_ms",
    "in_point_ts_ms",
    "event_type",
    "team",
    "turnover_subtype",
    "throw_type",
    "pass_direction",
    "confidence",
]


def _export_row(row: Any) -> dict[str, object]:
    confidence = "" if row.confidence is None else float(row.confidence)
    return {
        "export_version": EXPORT_VERSION,
        "game_id": row.game_id,
        "point_id": row.point_id,
        "point_ordinal": int(row.point_ordinal),
        "video_ts_ms": int(row.video_ts_ms),
        "in_point_ts_ms": int(row.in_point_ts_ms),
        "event_type": row.type,
        "team": row.team,
        "turnover_subtype": row.turnover_subtype or "",
        "throw_type": row.throw_type or "",
        "pass_direction": row.pass_direction or "",
        "confidence": confidence,
    }


def render_events_csv(game_id: str) -> str:
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=EXPORT_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in list_event_rows(game_id):
        writer.writerow(_export_row(row))
    return buffer.getvalue()


__all__ = ["EXPORT_COLUMNS", "EXPORT_VERSION", "render_events_csv"]
