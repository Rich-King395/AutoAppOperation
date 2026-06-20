"""Top-level experiment orchestration skeleton and dry-run planner.

The orchestrator is responsible for coordinating mobile automation and
voltage/RF collection across one or more app experiments.  This skeleton keeps
the two existing subsystems independent: mobile automation remains in
``src/appcollector`` flows/drivers, and voltage collection remains in
``RFEHDataCollection``.

No concrete app gestures or hardware collection protocol are implemented here.
The implemented dry-run planner only parses a matrix config and describes the
runs that would be executed.
"""

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import sleep
from typing import Any

import yaml

from appcollector.errors import ConfigError
from appcollector.integration.metadata_logger import MetadataLogger, utc_now_iso
from appcollector.integration.mobile_automation_client import MobileAutomationClient
from appcollector.integration.rf_collector_client import RFCollectorClient
from appcollector.run_logger import make_run_id


REQUIRED_MATRIX_KEYS = {
    "experiment_id",
    "device_id",
    "hardware_id",
    "environment_id",
    "router_id",
    "apps",
    "duration_sec",
    "repetitions",
    "output_root",
}


def safe_path_token(value: Any) -> str:
    """Return a compact filesystem-safe path token."""
    token = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", str(value)).strip(" ._")
    token = re.sub(r"\s+", "_", token)
    return token or "unknown"


def load_matrix_config(path: Path | str) -> dict[str, Any]:
    """Load an orchestration config from YAML or JSON."""
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(f"Experiment config file not found: {config_path}")

    text = config_path.read_text(encoding="utf-8")
    if config_path.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        data = yaml.safe_load(text)

    if not isinstance(data, dict):
        raise ConfigError(f"Experiment config must contain a mapping: {config_path}")
    return data


def validate_matrix_config(config: dict[str, Any]) -> None:
    """Validate the high-level orchestration config shape."""
    missing = sorted(REQUIRED_MATRIX_KEYS - set(config))
    if missing:
        raise ConfigError(f"Experiment config missing required keys: {', '.join(missing)}")

    if not isinstance(config["apps"], list) or not config["apps"]:
        raise ConfigError("Experiment config 'apps' must be a non-empty list.")

    try:
        duration_sec = int(config["duration_sec"])
        repetitions = int(config["repetitions"])
        app_warmup_sec = int(config.get("app_warmup_sec", 0))
    except (TypeError, ValueError) as exc:
        raise ConfigError("duration_sec, repetitions, and app_warmup_sec must be integers.") from exc

    if duration_sec <= 0:
        raise ConfigError("duration_sec must be greater than 0.")
    if repetitions <= 0:
        raise ConfigError("repetitions must be greater than 0.")
    if app_warmup_sec < 0:
        raise ConfigError("app_warmup_sec must be greater than or equal to 0.")


@dataclass
class ExperimentOrchestrator:
    """Coordinate app automation and RF collection at the experiment level."""

    mobile_client: MobileAutomationClient | None = None
    rf_client: RFCollectorClient | None = None
    config: dict[str, Any] | None = None
    metadata_logger: MetadataLogger | None = None

    @classmethod
    def from_config_file(cls, path: Path | str) -> "ExperimentOrchestrator":
        """Create an orchestrator from a YAML/JSON dry-run matrix config."""
        config = load_matrix_config(path)
        validate_matrix_config(config)
        return cls(config=config)

    def plan_runs(self) -> list[dict[str, Any]]:
        """Generate dry-run plan entries without touching phones or hardware."""
        if self.config is None:
            raise ConfigError("ExperimentOrchestrator requires config before planning runs.")

        validate_matrix_config(self.config)
        experiment_id = str(self.config["experiment_id"])
        device_id = str(self.config["device_id"])
        hardware_id = str(self.config["hardware_id"])
        environment_id = str(self.config["environment_id"])
        router_id = str(self.config["router_id"])
        output_root = Path(str(self.config["output_root"]))
        duration_sec = int(self.config["duration_sec"])
        repetitions = int(self.config["repetitions"])
        app_warmup_sec = int(self.config.get("app_warmup_sec", 0))
        base_time = datetime.now(UTC)

        runs: list[dict[str, Any]] = []
        for repetition in range(1, repetitions + 1):
            for app_index, app in enumerate(self.config["apps"], start=1):
                app_id = self._app_id(app)
                app_label = self._app_label(app)
                run_time = base_time + timedelta(microseconds=len(runs))
                run_id = make_run_id(
                    experiment_id,
                    device_name=device_id,
                    app_label=app_id,
                    scenario_name=f"rep-{repetition}",
                    now=run_time,
                )
                output_group = str(
                    Path(safe_path_token(experiment_id))
                    / safe_path_token(router_id)
                    / safe_path_token(device_id)
                )
                app_output_dir = output_root / safe_path_token(router_id) / safe_path_token(device_id) / safe_path_token(app_label)
                file_stem = safe_path_token(app_label)
                runs.append(
                    {
                        "run_id": run_id,
                        "experiment_id": experiment_id,
                        "device_id": device_id,
                        "hardware_id": hardware_id,
                        "environment_id": environment_id,
                        "router_id": router_id,
                        "app_id": app_id,
                        "app_label": app_label,
                        "app": app,
                        "duration_sec": duration_sec,
                        "app_warmup_sec": app_warmup_sec,
                        "output_group": output_group,
                        "file_stem": file_stem,
                        "repetition": repetition,
                        "repetition_id": repetition,
                        "app_index": app_index,
                        "output_dir": str(app_output_dir),
                        "dry_run": True,
                    }
                )
        return runs

    def dry_run_plan(self) -> dict[str, Any]:
        """Return a printable plan for the configured matrix."""
        runs = self.plan_runs()
        return {
            "mode": "dry_run",
            "experiment_id": self.config["experiment_id"] if self.config else None,
            "run_count": len(runs),
            "runs": runs,
        }

    def build_run_context(self, experiment_id: str) -> dict[str, Any]:
        """Build shared run context such as run_id, output paths, and duration."""
        for run in self.plan_runs():
            if run["run_id"] == experiment_id or run["experiment_id"] == experiment_id:
                return run
        raise ConfigError(f"Run or experiment id not found in planned matrix: {experiment_id}")

    def run_one(self, run: dict[str, Any]) -> dict[str, Any]:
        """Run one coordinated mobile automation + RF collection sequence."""
        logger = self.metadata_logger or MetadataLogger()
        start_time = utc_now_iso()
        mobile_client = self.mobile_client or MobileAutomationClient()
        rf_client = self.rf_client or RFCollectorClient(config=(self.config or {}).get("rf_collector"))
        metadata = logger.build_metadata(
            run=run,
            status="running",
            start_time=start_time,
            end_time=None,
            error=None,
        )
        run_context = {**run, "metadata": metadata}
        metadata_path = logger.write(metadata)

        rf_started = False
        app_launched = False
        try:
            mobile_client.check_ready(run_context)
            metadata["mobile_check_ready"] = "ok"
            metadata["rf_check_ready"] = rf_client.check_ready()
            mobile_client.launch_app(str(run["app_id"]))
            app_launched = True
            metadata["mobile_launch"] = "ok"
            prepare_playback = getattr(mobile_client, "prepare_playback", None)
            if callable(prepare_playback):
                metadata["playback_prepare"] = prepare_playback(str(run["app_id"]), run_context=run_context)
                logger.write(metadata)
            app_warmup_sec = int(run.get("app_warmup_sec", 0))
            metadata["app_warmup_sec"] = app_warmup_sec
            if app_warmup_sec > 0:
                metadata["warmup_started_at"] = utc_now_iso()
                logger.write(metadata)
                sleep(app_warmup_sec)
                metadata["warmup_finished_at"] = utc_now_iso()
                logger.write(metadata)
            metadata["rf_start"] = rf_client.start_recording(
                run_id=str(run["run_id"]),
                output_dir=str(run["output_dir"]),
                duration_sec=int(run["duration_sec"]),
                run_context=run_context,
            )
            rf_started = True
            metadata["mobile_result"] = mobile_client.run_app_flow(
                str(run["app_id"]),
                int(run["duration_sec"]),
                run_context=run_context,
            )
            metadata["rf_finished"] = rf_client.wait_until_finished(
                run_id=str(run["run_id"]),
                duration_sec=int(run["duration_sec"]),
            )
            rf_started = False
            metadata["mobile_stop"] = mobile_client.stop_app(str(run["app_id"])) or "ok"
            app_launched = False
            metadata["status"] = "completed"
        except Exception as exc:
            metadata["status"] = "failed"
            metadata["error"] = str(exc)
            if rf_started:
                try:
                    metadata["rf_finished_after_mobile_error"] = rf_client.wait_until_finished(
                        run_id=str(run["run_id"]),
                        duration_sec=int(run["duration_sec"]),
                    )
                    rf_started = False
                except Exception as wait_exc:
                    metadata["rf_wait_after_mobile_error"] = str(wait_exc)
                    try:
                        metadata["rf_stop_after_error"] = rf_client.stop_recording()
                    except Exception as stop_exc:
                        metadata["rf_stop_error"] = str(stop_exc)
            if app_launched:
                try:
                    metadata["mobile_stop_after_error"] = mobile_client.stop_app(str(run["app_id"])) or "ok"
                except Exception as stop_exc:
                    metadata["mobile_stop_error"] = str(stop_exc)
        finally:
            try:
                mobile_client.cleanup(run_context)
            except Exception as cleanup_exc:
                metadata["cleanup_error"] = str(cleanup_exc)
            metadata["end_time"] = utc_now_iso()
            metadata_path = logger.write(metadata)
        return {**metadata, "metadata_path": str(metadata_path)}

    def run_matrix(
        self,
        experiment_ids: list[str] | None = None,
        continue_on_error: bool = False,
    ) -> list[dict[str, Any]]:
        """Run a sequence of coordinated experiments and write metadata."""
        runs = self.plan_runs()
        selected = set(experiment_ids or [])
        if selected:
            runs = [run for run in runs if run["run_id"] in selected or run["experiment_id"] in selected]
        results = []
        for run in runs:
            result = self.run_one(run)
            results.append(result)
            if result.get("status") == "failed" and not continue_on_error:
                break
        return results

    def _app_id(self, app: Any) -> str:
        if isinstance(app, str):
            return app
        if isinstance(app, dict):
            for key in ("app_id", "app_label", "name"):
                value = app.get(key)
                if value:
                    return str(value)
        raise ConfigError(f"Each app must be a string or mapping with app_id/app_label/name: {app}")

    def _app_label(self, app: Any) -> str:
        if isinstance(app, str):
            return app
        if isinstance(app, dict):
            for key in ("app_label", "label", "name", "app_id"):
                value = app.get(key)
                if value:
                    return str(value)
        raise ConfigError(f"Each app must be a string or mapping with app_label/label/name/app_id: {app}")
