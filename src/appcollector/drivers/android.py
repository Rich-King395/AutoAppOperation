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

    options = UiAutomator2Options()
    options.platform_name = str(platform_name)
    options.automation_name = str(automation_name)
    options.udid = str(udid)
    options.device_name = str(device_name)
    if platform_version:
        options.platform_version = str(platform_version)
    options.app_package = str(app_package)
    if app_activity:
        options.app_activity = str(app_activity)
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


def activate_android_app(driver: Any, app_config: dict[str, Any]) -> None:
    app_package = get_config_value(app_config, "appPackage", "package")
    try:
        driver.activate_app(str(app_package))
    except Exception as exc:
        raise DriverError(f"Driver connected, but failed to activate appPackage '{app_package}': {exc}") from exc
