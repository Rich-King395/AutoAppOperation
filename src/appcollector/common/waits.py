from time import sleep
from typing import Any

from selenium.webdriver.support.ui import WebDriverWait


def sleep_seconds(seconds: float) -> None:
    sleep(max(0.0, seconds))


def wait_until(driver: Any, condition, timeout_seconds: float = 10):
    return WebDriverWait(driver, timeout_seconds).until(condition)
