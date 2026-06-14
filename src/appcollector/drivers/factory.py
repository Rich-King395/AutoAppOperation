from typing import Any

from appcollector.config import get_config_value
from appcollector.drivers.android import create_android_driver
from appcollector.drivers.ios import create_ios_driver
from appcollector.errors import ConfigError


def create_driver(device: dict[str, Any], app_config: dict[str, Any]):
    platform = str(get_config_value(device, "platformName", "platform")).lower()
    if platform == "android":
        return create_android_driver(device, app_config)
    if platform == "ios":
        return create_ios_driver(device, app_config)
    raise ConfigError(f"Unsupported platformName/platform: {platform}")
