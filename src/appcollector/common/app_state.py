from time import sleep
from typing import Any


def current_package(driver: Any) -> str | None:
    try:
        package = driver.current_package
    except Exception:
        return None
    return str(package) if package else None


def ensure_app_foreground(driver: Any, app_package: str | None) -> bool:
    if not app_package:
        return True
    package = current_package(driver)
    if package == app_package:
        return True
    driver.activate_app(app_package)
    sleep(0.8)
    return False


def guarded_back(driver: Any, app_package: str | None) -> bool:
    driver.back()
    sleep(0.8)
    return ensure_app_foreground(driver, app_package)


def guarded_open_and_back(
    driver: Any,
    app_package: str | None,
    open_action,
    dwell_sec: float,
    after_back_sec: float = 0.8,
    sleeper=sleep,
) -> str:
    open_action()
    sleeper(dwell_sec)
    if not ensure_app_foreground(driver, app_package):
        return "recovered_after_open"
    driver.back()
    sleeper(after_back_sec)
    if not ensure_app_foreground(driver, app_package):
        return "recovered_after_back"
    return "opened_and_returned"
