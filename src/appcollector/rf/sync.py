from dataclasses import dataclass
from pathlib import Path


class DummyRfSync:
    def start(self, run_id: str) -> None:
        return None

    def stop(self, run_id: str) -> None:
        return None


@dataclass
class ManualRfSync:
    marker_dir: Path = Path("logs/runs")

    def start(self, run_id: str) -> Path:
        self.marker_dir.mkdir(parents=True, exist_ok=True)
        path = self.marker_dir / f"{run_id}.rf.start"
        path.write_text("manual rf start\n", encoding="utf-8")
        return path

    def stop(self, run_id: str) -> Path:
        self.marker_dir.mkdir(parents=True, exist_ok=True)
        path = self.marker_dir / f"{run_id}.rf.stop"
        path.write_text("manual rf stop\n", encoding="utf-8")
        return path
