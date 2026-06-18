"""High-level client boundary for mobile automation.

This module is intentionally thin.  It defines the orchestration-facing
interface for the existing Appium-based mobile automation module without
duplicating app operation logic, gestures, flows, or driver setup.

The implementation acts as an adapter around existing modules such as
``drivers.factory.create_driver``, ``drivers.android.activate_android_app``,
and registered flows.  It does not define app-specific click, swipe, or browse
logic.
"""

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from appcollector.config import get_config_value, index_by, load_configs
from appcollector.drivers.android import activate_android_app
from appcollector.drivers.factory import create_driver
from appcollector.errors import ConfigError
from appcollector.flows import FLOW_REGISTRY
from appcollector.run_logger import MetadataEventLogger


CATEGORY_FLOW_DEFAULTS = {
    "social_media": "feed_random_walk",
    "news": "news_browse",
    "shopping": "shopping_browse",
    "video": "passive_media",
    "music": "passive_media",
}

PROTECTED_ANDROID_PACKAGES = {
    "com.android.systemui",
    "com.sec.android.app.launcher",
    "com.google.android.apps.nexuslauncher",
    "com.android.launcher",
    "com.android.launcher3",
}


def _copy_scenario_with_duration(scenario: dict[str, Any], duration_sec: int) -> dict[str, Any]:
    copied = dict(scenario)
    copied["duration_sec"] = duration_sec
    return copied


@dataclass
class MobileAutomationClient:
    """Facade for app-level mobile automation.

    The orchestrator should use this class to start, run, and clean up mobile
    app automation for a single experiment.  Concrete behavior is still owned
    by the existing mobile automation modules.
    """

    config: dict[str, Any] | None = None
    config_dir: Path | str = Path("configs")
    driver: Any | None = None
    device: dict[str, Any] | None = None
    app_config: dict[str, Any] | None = None
    scenario: dict[str, Any] | None = None

    def check_ready(self, run_context: dict[str, Any]) -> None:
        """Resolve device, app, and scenario config for a planned run."""
        configs = load_configs(self.config_dir)
        devices = index_by(configs["devices"].get("devices", []), "name")
        apps = index_by(configs["apps"].get("apps", []), "app_label")

        device_id = str(run_context["device_id"])
        app_id = str(run_context["app_id"])
        if device_id not in devices:
            raise ConfigError(f"Device '{device_id}' was not found in configs/devices.yaml")
        if app_id not in apps:
            raise ConfigError(f"App '{app_id}' was not found in configs/apps.yaml")

        self.device = devices[device_id]
        self.app_config = apps[app_id]
        self.scenario = self._resolve_scenario(configs, run_context, self.app_config)

    def launch_app(self, app_id: str) -> None:
        """Create the Appium driver and launch the configured app."""
        if self.device is None or self.app_config is None:
            raise ConfigError("MobileAutomationClient.check_ready() must run before launch_app().")
        if app_id != self.app_config.get("app_label"):
            raise ConfigError(f"Run app_id '{app_id}' does not match resolved app config.")
        self.driver = create_driver(self.device, self.app_config)
        activate_android_app(self.driver, self.app_config, self.device)

    def run_app_flow(self, app_id: str, duration_sec: int, run_context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run the existing app-level flow for the configured duration."""
        if self.driver is None or self.app_config is None or self.scenario is None:
            raise ConfigError("MobileAutomationClient.launch_app() must run before run_app_flow().")
        if app_id != self.app_config.get("app_label"):
            raise ConfigError(f"Run app_id '{app_id}' does not match resolved app config.")

        scenario = _copy_scenario_with_duration(self.scenario, duration_sec)
        flow_name = str(scenario["flow"])
        if flow_name not in FLOW_REGISTRY:
            raise ConfigError(f"Unsupported flow '{flow_name}' for app '{app_id}'")

        metadata = (run_context or {}).get("metadata", {})
        logger = MetadataEventLogger(metadata)
        flow = FLOW_REGISTRY[flow_name](
            driver=self.driver,
            duration_sec=duration_sec,
            random_seed=scenario["random_seed"],
            logger=logger,
            scenario=scenario,
            target_package=str(get_config_value(self.app_config, "appPackage", "package")),
        )
        flow.run()
        return {"status": "completed", "flow": flow_name, "events": metadata.get("events", [])}

    def stop_app(self, app_id: str) -> dict[str, Any] | None:
        """Terminate the target app and any foreground external app without clearing app data.

        ``terminate_app`` is not always enough for apps that keep media or
        notification services alive in the background.  After the Appium-level
        termination attempt, this method also tries Android ``am force-stop``
        through Appium's mobile shell extension or a configured/local adb
        executable.  This preserves app data and login state, but stops the app
        process and its background services before the next run starts.
        """
        if self.driver is None or self.app_config is None:
            return None
        if app_id != self.app_config.get("app_label"):
            raise ConfigError(f"Run app_id '{app_id}' does not match resolved app config.")
        app_package = str(get_config_value(self.app_config, "appPackage", "package"))
        current_package = self._current_package()
        results: list[dict[str, Any]] = []

        if current_package and current_package != app_package:
            results.append(self._stop_android_package(current_package, reason="foreground_external_app"))
        results.append(self._stop_android_package(app_package, reason="target_app"))
        self._press_home()
        return {
            "target_package": app_package,
            "foreground_package_before_stop": current_package,
            "packages": results,
        }

    def prepare(self, run_context: dict[str, Any]) -> None:
        """Prepare the target device/app session before collection starts."""
        self.check_ready(run_context)

    def run(self, run_context: dict[str, Any]) -> dict[str, Any]:
        """Run app-level automation for the configured duration."""
        app_id = str(run_context["app_id"])
        self.launch_app(app_id)
        return self.run_app_flow(app_id, int(run_context["duration_sec"]), run_context=run_context)

    def cleanup(self, run_context: dict[str, Any]) -> None:
        """Release driver/session resources after ``stop_app`` has run."""
        if self.driver is not None:
            self.driver.quit()
        self.driver = None
        self.device = None
        self.app_config = None
        self.scenario = None

    def _current_package(self) -> str | None:
        if self.driver is None:
            return None
        try:
            package = self.driver.current_package
        except Exception:
            return None
        return str(package) if package else None

    def _press_home(self) -> None:
        if self.driver is None:
            return
        try:
            self.driver.press_keycode(3)
        except Exception:
            pass

    def _stop_android_package(self, package: str, reason: str) -> dict[str, Any]:
        result: dict[str, Any] = {
            "package": package,
            "reason": reason,
            "protected": package in PROTECTED_ANDROID_PACKAGES,
            "methods": [],
            "errors": [],
        }
        if result["protected"]:
            result["skipped"] = True
            return result

        if self.driver is not None:
            try:
                self.driver.terminate_app(package)
                result["methods"].append("appium_terminate_app")
            except Exception as exc:
                result["errors"].append(f"appium_terminate_app: {exc}")

        if self._force_stop_with_appium_shell(package):
            result["methods"].append("appium_mobile_shell_force_stop")
        if self._force_stop_with_adb(package):
            result["methods"].append("adb_force_stop")
        if "appium_mobile_shell_force_stop" not in result["methods"] and "adb_force_stop" not in result["methods"]:
            result["errors"].append("force_stop_unavailable")

        result["pid_after_stop"] = self._pidof_package(package)
        result["stopped"] = bool(result["methods"])
        return result

    def _force_stop_with_appium_shell(self, package: str) -> bool:
        if self.driver is None:
            return False
        try:
            self.driver.execute_script("mobile: shell", {"command": "am", "args": ["force-stop", package]})
            return True
        except Exception:
            return False

    def _force_stop_with_adb(self, package: str) -> bool:
        adb = self._adb_executable()
        udid = str((self.device or {}).get("udid", "")).strip()
        if not adb or not udid:
            return False
        try:
            subprocess.run(
                [adb, "-s", udid, "shell", "am", "force-stop", package],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10,
            )
            return True
        except Exception:
            return False

    def _pidof_package(self, package: str) -> str | None:
        adb = self._adb_executable()
        udid = str((self.device or {}).get("udid", "")).strip()
        if not adb or not udid:
            return None
        try:
            completed = subprocess.run(
                [adb, "-s", udid, "shell", "pidof", package],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10,
            )
        except Exception:
            return None
        pid = completed.stdout.strip()
        return pid or None

    def _adb_executable(self) -> str | None:
        for key in ("adbPath", "adb_path"):
            configured = str((self.device or {}).get(key, "")).strip()
            if configured:
                return configured

        adb_name = "adb.exe" if os.name == "nt" else "adb"
        for env_name in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
            sdk_root = os.environ.get(env_name)
            if not sdk_root:
                continue
            candidate = Path(sdk_root) / "platform-tools" / adb_name
            if candidate.exists():
                return str(candidate)

        found = shutil.which("adb")
        if found:
            return found

        windows_default = Path("D:/Android/Sdk/platform-tools/adb.exe")
        if windows_default.exists():
            return str(windows_default)
        return None

    def _resolve_scenario(
        self,
        configs: dict[str, dict[str, Any]],
        run_context: dict[str, Any],
        app_config: dict[str, Any],
    ) -> dict[str, Any]:
        scenarios = index_by(configs["scenarios"].get("scenarios", []), "name")
        scenario_id = run_context.get("scenario_id") or run_context.get("scenario")
        if scenario_id:
            scenario_name = str(scenario_id)
        else:
            scenario_name = self._scenario_from_existing_matrix(configs, run_context)
            if scenario_name is None:
                category = str(app_config.get("category", "")).lower()
                scenario_name = CATEGORY_FLOW_DEFAULTS.get(category, "generic_random_walk")

        if scenario_name not in scenarios:
            raise ConfigError(f"Scenario '{scenario_name}' was not found in configs/scenarios.yaml")
        return scenarios[scenario_name]

    def _scenario_from_existing_matrix(
        self,
        configs: dict[str, dict[str, Any]],
        run_context: dict[str, Any],
    ) -> str | None:
        device_id = str(run_context["device_id"])
        app_id = str(run_context["app_id"])
        for row in configs["experiment_matrix"].get("experiments", []):
            if row.get("device") == device_id and row.get("app") == app_id:
                return str(row.get("scenario"))
        return None
