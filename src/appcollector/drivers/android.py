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
    if launch_strategy not in {"monkey", "container"}:
        options.app_package = str(app_package)
    if app_activity and launch_strategy not in {"monkey", "container"}:
        options.app_activity = str(app_activity)
    if launch_strategy in {"monkey", "container"}:
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
    if launch_strategy == "container":
        _launch_with_container(driver, app_config, device)
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


def _launch_with_container(driver: Any, app_config: dict[str, Any], device: dict[str, Any] | None = None) -> None:
    container = app_config.get("container") or {}
    if not isinstance(container, dict):
        raise DriverError(f"Container launch config for '{app_config.get('app_label')}' must be a mapping")

    container_package = str(container.get("packageName") or container.get("package") or "com.easy.abroad")
    app_names = _container_app_names(app_config, container)
    target_package = str(get_config_value(app_config, "appPackage", "package"))

    try:
        driver.activate_app(container_package)
    except Exception:
        _launch_with_monkey(driver, container_package, device)

    _wait_seconds(float(container.get("startupWaitSec", 5)))
    if bool(container.get("openAllApps") or container.get("open_all_apps")):
        _open_container_all_apps_page(driver, container, device)
        _scroll_container_list_to_top(driver, device)
    element = _find_container_app_element(
        driver,
        app_names,
        timeout_sec=float(container.get("findTimeoutSec", 25)),
        device=device,
        scroll=True,
    )
    if element is not None:
        _tap_container_app_tile(driver, element, container, device)
    elif _tap_container_fallback(driver, container):
        pass
    else:
        names = ", ".join(app_names)
        raise DriverError(
            f"Container app '{container_package}' opened, but could not find target app icon for '{names}'. "
            "Add container.tapPoints in configs/device_app_overrides.yaml or verify the app is visible in Chujingyi."
        )

    target_wait_sec = float(container.get("targetWaitSec", 30))
    if not (
        _wait_for_target_package(driver, target_package, timeout_sec=target_wait_sec)
        or _wait_for_container_proxy_activity(driver, container, timeout_sec=target_wait_sec)
    ):
        current_package = _safe_current_package(driver)
        current_activity = _safe_current_activity(driver)
        raise DriverError(
            f"Tapped container app icon for '{app_config.get('app_label')}', but target package "
            f"'{target_package}' did not become foreground. Current package/activity: "
            f"{current_package}/{current_activity}"
        )


def _open_container_all_apps_page(
    driver: Any,
    container: dict[str, Any],
    device: dict[str, Any] | None = None,
) -> None:
    activity_name = str(container.get("allAppsActivity") or "com.easy.abroad.activities.SecondPageActivity")
    if _is_container_all_apps_page(driver, activity_name):
        return

    labels = container.get("allAppsLabels") or container.get("all_apps_labels") or ["全部"]
    if not isinstance(labels, list):
        labels = [labels]
    element = _find_container_app_element(driver, [str(label) for label in labels], timeout_sec=10)
    if element is None:
        if _is_container_all_apps_page(driver, activity_name):
            return
        raise DriverError("Container app opened, but could not find the '全部' entry for the all-apps page.")

    _tap_element_center(driver, element, device)
    deadline = _monotonic() + float(container.get("allAppsWaitSec", 10))
    while _monotonic() < deadline:
        if _is_container_all_apps_page(driver, activity_name):
            return
        _wait_seconds(0.5)

    current_activity = _safe_current_activity(driver)
    raise DriverError(
        f"Tapped container all-apps entry, but '{activity_name}' did not become foreground. "
        f"Current activity: {current_activity}"
    )


def _container_app_names(app_config: dict[str, Any], container: dict[str, Any]) -> list[str]:
    configured = container.get("appNames") or container.get("app_names")
    if isinstance(configured, list):
        names = [str(name).strip() for name in configured if str(name).strip()]
    elif configured:
        names = [str(configured).strip()]
    else:
        names = []
    app_name = app_config.get("app_name")
    if app_name:
        names.append(str(app_name).strip())
    app_label = app_config.get("app_label")
    if app_label:
        names.append(str(app_label).replace("_android", "").replace("_", " ").strip())
    return list(dict.fromkeys(name for name in names if name))


def _find_container_app_element(
    driver: Any,
    app_names: list[str],
    timeout_sec: float,
    device: dict[str, Any] | None = None,
    scroll: bool = False,
) -> Any | None:
    from appium.webdriver.common.appiumby import AppiumBy

    deadline = _monotonic() + timeout_sec
    while _monotonic() < deadline:
        for name in app_names:
            escaped = _escape_uiautomator_string(name)
            xpath_name = _escape_xpath_string(name)
            selectors = [
                (
                    AppiumBy.ANDROID_UIAUTOMATOR,
                    f'new UiSelector().resourceId("com.easy.abroad:id/tv_name").text("{escaped}")',
                ),
                (
                    AppiumBy.ANDROID_UIAUTOMATOR,
                    f'new UiSelector().text("{escaped}")',
                ),
                (
                    AppiumBy.ANDROID_UIAUTOMATOR,
                    f'new UiSelector().description("{escaped}")',
                ),
                (
                    AppiumBy.XPATH,
                    f'//*[@text="{xpath_name}" or @content-desc="{xpath_name}"]',
                ),
                (
                    AppiumBy.ANDROID_UIAUTOMATOR,
                    f'new UiSelector().textContains("{escaped}")',
                ),
                (
                    AppiumBy.ANDROID_UIAUTOMATOR,
                    f'new UiSelector().descriptionContains("{escaped}")',
                ),
                (
                    AppiumBy.XPATH,
                    f'//*[contains(@text, "{xpath_name}") or contains(@content-desc, "{xpath_name}")]',
                ),
            ]
            for by, value in selectors:
                try:
                    elements = driver.find_elements(by, value)
                except Exception:
                    elements = []
                for element in elements:
                    try:
                        if element.is_displayed():
                            return element
                    except Exception:
                        return element
        if scroll:
            _scroll_container_list_down(driver, device)
            _wait_seconds(0.5)
        else:
            _wait_seconds(1)
    return None


def _scroll_container_list_to_top(driver: Any, device: dict[str, Any] | None = None) -> None:
    for _ in range(4):
        if not _swipe_container_list(driver, device, direction="down"):
            return
        _wait_seconds(0.2)


def _scroll_container_list_down(driver: Any, device: dict[str, Any] | None = None) -> bool:
    return _swipe_container_list(driver, device, direction="up")


def _swipe_container_list(driver: Any, device: dict[str, Any] | None, direction: str) -> bool:
    try:
        size = driver.get_window_size()
        width = int(size["width"])
        height = int(size["height"])
    except Exception:
        width, height = 1080, 2265

    x = int(width * 0.5)
    if direction == "down":
        start_y, end_y = int(height * 0.35), int(height * 0.78)
    else:
        start_y, end_y = int(height * 0.78), int(height * 0.35)

    if _adb_input_swipe(x, start_y, x, end_y, device):
        return True
    try:
        driver.swipe(x, start_y, x, end_y, 350)
        return True
    except Exception:
        return False


def _tap_container_fallback(driver: Any, container: dict[str, Any]) -> bool:
    tap_points = container.get("tapPoints") or container.get("tap_points") or []
    if not isinstance(tap_points, list):
        return False
    for point in tap_points:
        if not isinstance(point, list | tuple) or len(point) != 2:
            continue
        try:
            x_ratio = float(point[0])
            y_ratio = float(point[1])
            size = driver.get_window_size()
            driver.tap([(int(size["width"] * x_ratio), int(size["height"] * y_ratio))], 200)
            _wait_seconds(float(container.get("afterTapWaitSec", 5)))
            return True
        except Exception:
            continue
    return False


def _tap_container_app_tile(
    driver: Any,
    element: Any,
    container: dict[str, Any],
    device: dict[str, Any] | None = None,
) -> None:
    try:
        rect = element.rect
        center_x = int(rect["x"] + rect["width"] / 2)
        label_center_y = int(rect["y"] + rect["height"] / 2)
        icon_offset_y = int(container.get("iconTapOffsetY", -120))
        center_y = max(1, label_center_y + icon_offset_y)
        if not _adb_input_tap(center_x, center_y, device):
            driver.tap([(center_x, center_y)], 200)
    except Exception:
        element.click()
    _wait_seconds(float(container.get("afterTapWaitSec", 5)))


def _tap_element_center(driver: Any, element: Any, device: dict[str, Any] | None = None) -> None:
    rect = element.rect
    center_x = int(rect["x"] + rect["width"] / 2)
    center_y = int(rect["y"] + rect["height"] / 2)
    if not _adb_input_tap(center_x, center_y, device):
        driver.tap([(center_x, center_y)], 200)


def _adb_input_tap(x: int, y: int, device: dict[str, Any] | None = None) -> bool:
    adb = _adb_executable(device)
    udid = str((device or {}).get("udid", "")).strip()
    if not adb or not udid:
        return False
    try:
        subprocess.run(
            [adb, "-s", udid, "shell", "input", "tap", str(x), str(y)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
        return True
    except Exception:
        return False


def _adb_input_swipe(
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    device: dict[str, Any] | None = None,
) -> bool:
    adb = _adb_executable(device)
    udid = str((device or {}).get("udid", "")).strip()
    if not adb or not udid:
        return False
    try:
        subprocess.run(
            [
                adb,
                "-s",
                udid,
                "shell",
                "input",
                "swipe",
                str(start_x),
                str(start_y),
                str(end_x),
                str(end_y),
                "350",
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
        return True
    except Exception:
        return False


def _wait_for_target_package(driver: Any, target_package: str, timeout_sec: float) -> bool:
    deadline = _monotonic() + timeout_sec
    while _monotonic() < deadline:
        if _safe_current_package(driver) == target_package:
            return True
        _wait_seconds(1)
    return False


def _wait_for_container_proxy_activity(driver: Any, container: dict[str, Any], timeout_sec: float) -> bool:
    container_package = str(container.get("packageName") or container.get("package") or "com.easy.abroad")
    page_activities = {
        "com.easy.abroad.activities.MainActivity",
        "com.easy.abroad.activities.SecondPageActivity",
        ".activities.MainActivity",
        ".activities.SecondPageActivity",
    }

    deadline = _monotonic() + timeout_sec
    while _monotonic() < deadline:
        current_package = _safe_current_package(driver)
        current_activity = _safe_current_activity(driver) or ""
        if current_package == container_package:
            if "com.vlite.sdk.proxy" in current_activity:
                return True
            if current_activity and current_activity not in page_activities and "easy.abroad.activities" not in current_activity:
                return True
        _wait_seconds(1)
    return False


def _safe_current_package(driver: Any) -> str | None:
    try:
        package = driver.current_package
    except Exception:
        return None
    return str(package) if package else None


def _safe_current_activity(driver: Any) -> str | None:
    try:
        activity = driver.current_activity
    except Exception:
        return None
    return str(activity) if activity else None


def _activity_matches(current_activity: str | None, expected_activity: str) -> bool:
    if not current_activity:
        return False
    current = current_activity.strip()
    expected = expected_activity.strip()
    return current == expected or current.endswith(expected) or expected.endswith(current.lstrip("."))


def _is_container_all_apps_page(driver: Any, activity_name: str) -> bool:
    from appium.webdriver.common.appiumby import AppiumBy

    if _activity_matches(_safe_current_activity(driver), activity_name):
        return True

    has_title = False
    selectors = [
        (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("我的应用")'),
        (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().resourceId("com.easy.abroad:id/tv_title_bar_title").text("我的应用")'),
    ]
    for by, value in selectors:
        try:
            elements = driver.find_elements(by, value)
        except Exception:
            elements = []
        if elements:
            has_title = True
            break
    if not has_title:
        return False

    try:
        app_lists = driver.find_elements(
            AppiumBy.ANDROID_UIAUTOMATOR,
            'new UiSelector().resourceId("com.easy.abroad:id/installed_app")',
        )
    except Exception:
        app_lists = []
    return any(_safe_is_displayed(element) for element in app_lists)


def _safe_is_displayed(element: Any) -> bool:
    try:
        return bool(element.is_displayed())
    except Exception:
        return True


def _escape_uiautomator_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _escape_xpath_string(value: str) -> str:
    return value.replace('"', '\\"')


def _wait_seconds(seconds: float) -> None:
    import time

    time.sleep(max(0.0, seconds))


def _monotonic() -> float:
    import time

    return time.monotonic()


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
