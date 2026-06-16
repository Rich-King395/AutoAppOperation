"""Metadata writing utilities for top-level orchestration runs.

This module owns only per-run metadata files.  It does not write collected
signal data, does not control mobile devices, and does not talk to hardware.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class MetadataLogger:
    """Create run output directories and write per-run metadata files."""

    filename = "metadata.json"

    def build_metadata(
        self,
        run: dict[str, Any],
        status: str,
        start_time: str,
        end_time: str | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        """Build normalized metadata for one planned or simulated run."""
        return {
            "run_id": run["run_id"],
            "experiment_id": run["experiment_id"],
            "environment_id": run["environment_id"],
            "device_id": run["device_id"],
            "hardware_id": run["hardware_id"],
            "router_id": run["router_id"],
            "app_id": run["app_id"],
            "app_label": run["app_label"],
            "duration_sec": run["duration_sec"],
            "app_warmup_sec": run.get("app_warmup_sec", 0),
            "output_group": run.get("output_group"),
            "file_stem": run.get("file_stem"),
            "repetition_id": run["repetition_id"],
            "output_dir": run["output_dir"],
            "status": status,
            "start_time": start_time,
            "end_time": end_time,
            "error": error,
        }

    def write(self, metadata: dict[str, Any]) -> Path:
        """Write metadata under ``output_dir`` using the run file stem when available."""
        output_dir = Path(str(metadata["output_dir"]))
        output_dir.mkdir(parents=True, exist_ok=True)
        file_stem = str(metadata.get("file_stem") or "").strip()
        filename = f"{file_stem}_metadata.json" if file_stem else self.filename
        path = output_dir / filename
        path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path


def utc_now_iso() -> str:
    """Return the current UTC timestamp as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()
