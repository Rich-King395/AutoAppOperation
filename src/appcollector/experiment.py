from dataclasses import dataclass
from datetime import UTC, datetime
from time import sleep
from typing import Any

from appcollector.config import get_config_value, index_by
from appcollector.errors import ConfigError
from appcollector.run_logger import RunLogger, make_run_id


@dataclass(frozen=True)
class ExperimentRun:
    experiment_id: str
    environment: str
    router: str
    device: dict[str, Any]
    app_config: dict[str, Any]
    scenario: dict[str, Any]
    rounds: int = 1

    @classmethod
    def from_configs(cls, experiment_id: str, configs: dict[str, dict[str, Any]]) -> "ExperimentRun":
        devices = index_by(configs["devices"].get("devices", []), "name")
        apps = index_by(configs["apps"].get("apps", []), "app_label")
        scenarios = index_by(configs["scenarios"].get("scenarios", []), "name")
        experiments = index_by(configs["experiment_matrix"].get("experiments", []), "experiment_id")

        if experiment_id not in experiments:
            raise ConfigError(f"Experiment '{experiment_id}' was not found in configs/experiment_matrix.yaml")

        row = experiments[experiment_id]
        try:
            device = devices[row["device"]]
        except KeyError as exc:
            raise ConfigError(f"Device '{row.get('device')}' was not found in configs/devices.yaml") from exc
        try:
            app_config = apps[row["app"]]
        except KeyError as exc:
            raise ConfigError(f"App '{row.get('app')}' was not found in configs/apps.yaml") from exc
        try:
            scenario = scenarios[row["scenario"]]
        except KeyError as exc:
            raise ConfigError(f"Scenario '{row.get('scenario')}' was not found in configs/scenarios.yaml") from exc

        device_platform = str(get_config_value(device, "platformName", "platform")).lower()
        app_platform = str(get_config_value(app_config, "platformName", "platform")).lower()
        if device_platform != app_platform:
            raise ConfigError(f"Device and app platform mismatch for experiment: {experiment_id}")
        return cls(
            experiment_id=experiment_id,
            environment=row["environment"],
            router=row["router"],
            device=device,
            app_config=app_config,
            scenario=scenario,
            rounds=int(row.get("rounds", 1)),
        )

    def _base_metadata(self, dry_run: bool, mode: str) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        terminate_app_on_finish = bool(self.scenario.get("terminate_app_on_finish", True))
        run_id = make_run_id(
            self.experiment_id,
            device_name=str(get_config_value(self.device, "deviceName", "name")),
            app_label=str(self.app_config["app_label"]),
            scenario_name=str(self.scenario["name"]),
            now=started_at,
        )
        return {
            "run_id": run_id,
            "experiment_id": self.experiment_id,
            "mode": mode,
            "started_at": started_at.isoformat(),
            "environment": self.environment,
            "router": self.router,
            "device": self.device,
            "app": self.app_config,
            "scenario": self.scenario,
            "duration_sec": int(self.scenario["duration_sec"]),
            "random_seed": self.scenario["random_seed"],
            "rounds": self.rounds,
            "dry_run": dry_run,
            "terminate_app_on_finish": terminate_app_on_finish,
            "status": "planned" if dry_run else "running",
        }

    def _terminate_target_app(self, driver: Any, metadata: dict[str, Any]) -> None:
        if not metadata.get("terminate_app_on_finish", True):
            metadata["app_terminated_on_finish"] = False
            return

        app_package = str(get_config_value(self.app_config, "appPackage", "package"))
        try:
            driver.terminate_app(app_package)
            metadata["app_terminated_on_finish"] = True
        except Exception as exc:
            metadata["app_terminate_error"] = str(exc)

    def smoke(self, dry_run: bool = True, wait_sec: int = 5) -> dict[str, Any]:
        metadata = self._base_metadata(dry_run=dry_run, mode="smoke")
        metadata["smoke_wait_sec"] = wait_sec
        logger = RunLogger()
        logger.write(metadata)
        if dry_run:
            return metadata

        from appcollector.drivers.android import activate_android_app
        from appcollector.drivers.factory import create_driver

        driver = create_driver(self.device, self.app_config)
        try:
            activate_android_app(driver, self.app_config, self.device)
            sleep(wait_sec)
            metadata["status"] = "completed"
        except Exception:
            metadata["status"] = "failed"
            raise
        finally:
            try:
                self._terminate_target_app(driver, metadata)
                driver.quit()
            finally:
                metadata["finished_at"] = datetime.now(UTC).isoformat()
                logger.write(metadata)
        return metadata

    def run(self, dry_run: bool = True) -> dict[str, Any]:
        metadata = self._base_metadata(dry_run=dry_run, mode="collection")

        logger = RunLogger()
        logger.write(metadata)
        if dry_run:
            return metadata

        from appcollector.drivers.android import activate_android_app
        from appcollector.drivers.factory import create_driver
        from appcollector.flows import FLOW_REGISTRY
        from appcollector.rf.sync import DummyRfSync
        from appcollector.run_logger import MetadataEventLogger

        driver = create_driver(self.device, self.app_config)
        rf_sync = DummyRfSync()
        run_id = str(metadata["run_id"])
        rf_sync.start(run_id)
        run_error: Exception | None = None
        try:
            activate_android_app(driver, self.app_config, self.device)
            flow_cls = FLOW_REGISTRY[str(self.scenario["flow"])]
            flow = flow_cls(
                driver=driver,
                duration_sec=int(self.scenario["duration_sec"]),
                random_seed=self.scenario["random_seed"],
                logger=MetadataEventLogger(metadata),
                scenario=self.scenario,
                target_package=str(get_config_value(self.app_config, "appPackage", "package")),
            )
            flow.run()
            metadata["status"] = "completed"
        except Exception as exc:
            run_error = exc
            metadata["status"] = "failed"
            metadata["error"] = str(exc)
        finally:
            rf_sync.stop(run_id)
            try:
                self._terminate_target_app(driver, metadata)
                driver.quit()
            except Exception as exc:
                metadata["driver_quit_error"] = str(exc)
            metadata["finished_at"] = datetime.now(UTC).isoformat()
            logger.write(metadata)
        if run_error is not None:
            raise run_error
        return metadata
