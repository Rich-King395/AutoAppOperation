from typing import Any


def build_ios_options(device: dict[str, Any], app_config: dict[str, Any]):
    from appium.options.ios import XCUITestOptions

    options = XCUITestOptions()
    options.platform_name = "iOS"
    options.automation_name = "XCUITest"
    options.udid = device.get("udid")
    options.platform_version = device.get("platform_version")
    options.bundle_id = app_config.get("bundle_id")
    options.no_reset = True
    return options


def create_ios_driver(device: dict[str, Any], app_config: dict[str, Any]):
    from appium import webdriver

    server_url = device.get("appium_server_url", "http://127.0.0.1:4723")
    return webdriver.Remote(server_url, options=build_ios_options(device, app_config))
