import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from appcollector.config import get_config_value
from appcollector.errors import DriverError


def _short_error(exc: Exception) -> str:
    message = str(exc).strip()
    return message if len(message) <= 1200 else f"{message[:1200]}..."


def build_android_options(device: dict[str, Any], app_config: dict[str, Any]):
    from appium.options.android import UiAutomator2Options

    platform_name = get_config_value(device, "platformName", "platform")
    automation_name = get_config_value(device, "automationName")
    udid = get_config_value(device, "udid")
    device_name = get_config_value(device, "deviceName", "name")
    platform_version = get_config_value(device, "platformVersion", "platform_version", required=False)
    app_package = get_config_value(app_config, "appPackage", "package")
    app_activity = get_config_value(app_config, "appActivity", "activity", required=False)
    launch_strategy = str(app_config.get("launchStrategy") or app_config.get("launch_strategy") or "").lower()

    options = UiAutomator2Options()
    options.platform_name = str(platform_name)
    options.automation_name = str(automation_name)
    options.udid = str(udid)
    options.device_name = str(device_name)
    if platform_version:
        options.platform_version = str(platform_version)
    if launch_strategy != "monkey":
        options.app_package = str(app_package)
    if app_activity and launch_strategy != "monkey":
        options.app_activity = str(app_activity)
    if launch_strategy == "monkey":
        options.set_capability("autoLaunch", False)
    options.no_reset = True
    options.uiautomator2_server_launch_timeout = 120000
    options.uiautomator2_server_install_timeout = 120000
    options.adb_exec_timeout = 120000
    options.new_command_timeout = 300
    return options


def create_android_driver(device: dict[str, Any], app_config: dict[str, Any]):
    from appium import webdriver

    server_url = get_config_value(
        device,
        "appiumServerUrl",
        "appium_server_url",
        required=False,
    ) or "http://127.0.0.1:4723"
    try:
        return webdriver.Remote(str(server_url), options=build_android_options(device, app_config))
    except Exception as exc:
        message = _short_error(exc)
        lowered = message.lower()
        if "Connection refused" in message or "Max retries exceeded" in message or "WinError 10061" in message:
            raise DriverError(f"Could not connect to Appium server at {server_url}. Start it with: appium") from exc
        if "uiautomator2" in lowered and ("not installed" in lowered or "not found" in lowered):
            raise DriverError("UiAutomator2 driver is not installed. Run: appium driver install uiautomator2") from exc
        if "adb" in lowered and ("not found" in lowered or "could not find" in lowered):
            raise DriverError(
                "Appium could not find adb. Make sure Android SDK platform-tools is installed and adb is on PATH "
                "in the same terminal where you start Appium."
            ) from exc
        if "device" in lowered or "udid" in lowered:
            raise DriverError(
                f"Could not start Android session for udid '{device.get('udid')}'. "
                "Check USB debugging, adb devices, and the udid in configs/devices.yaml.\n"
                f"Appium detail: {message}"
            ) from exc
        raise DriverError(f"Could not create Android UiAutomator2 driver: {message}") from exc


def activate_android_app(driver: Any, app_config: dict[str, Any], device: dict[str, Any] | None = None) -> None:
    app_package = get_config_value(app_config, "appPackage", "package")
    launch_strategy = str(app_config.get("launchStrategy") or app_config.get("launch_strategy") or "").lower()
    if launch_strategy == "monkey":
        _launch_with_monkey(driver, str(app_package), device)
        return
    try:
        driver.activate_app(str(app_package))
    except Exception as exc:
        raise DriverError(f"Driver connected, but failed to activate appPackage '{app_package}': {exc}") from exc


def _launch_with_monkey(driver: Any, app_package: str, device: dict[str, Any] | None = None) -> None:
    args = ["-p", app_package, "-c", "android.intent.category.LAUNCHER", "1"]
    try:
        driver.execute_script("mobile: shell", {"command": "monkey", "args": args})
        return
    except Exception as appium_exc:
        if _launch_with_adb_monkey(app_package, device):
            return
        raise DriverError(
            f"Driver connected, but failed to launch appPackage '{app_package}' with monkey: {appium_exc}"
        ) from appium_exc


def _launch_with_adb_monkey(app_package: str, device: dict[str, Any] | None = None) -> bool:
    adb = _adb_executable(device)
    udid = str((device or {}).get("udid", "")).strip()
    if not adb or not udid:
        return False
    try:
        subprocess.run(
            [adb, "-s", udid, "shell", "monkey", "-p", app_package, "-c", "android.intent.category.LAUNCHER", "1"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
        )
        return True
    except Exception:
        return False


def _adb_executable(device: dict[str, Any] | None = None) -> str | None:
    for key in ("adbPath", "adb_path"):
        configured = str((device or {}).get(key, "")).strip()
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
