import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _slug(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-")


def make_run_id(
    experiment_id: str,
    device_name: str = "device",
    app_label: str = "app",
    scenario_name: str = "scenario",
    now: datetime | None = None,
) -> str:
    current = now or datetime.now(UTC)
    stamp = current.strftime("%Y%m%dT%H%M%S%fZ")
    parts = [_slug(experiment_id), _slug(device_name), _slug(app_label), _slug(scenario_name), stamp]
    return "-".join(part for part in parts if part)


class RunLogger:
    def __init__(self, runs_dir: Path | str = "logs/runs") -> None:
        self.runs_dir = Path(runs_dir)

    def write(self, metadata: dict) -> Path:
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        path = self.runs_dir / f"{metadata['run_id']}.json"
        with path.open("w", encoding="utf-8") as handle:
            json.dump(metadata, handle, indent=2, sort_keys=True)
            handle.write("\n")
        return path


class MetadataEventLogger:
    def __init__(self, metadata: dict[str, Any]) -> None:
        self.metadata = metadata
        self.metadata.setdefault("events", [])

    def event(self, event: str, **fields: Any) -> None:
        self.metadata["events"].append(
            {
                "event": event,
                "at": datetime.now(UTC).isoformat(),
                **fields,
            }
        )
