class AppCollectorError(Exception):
    """Base exception for user-facing AppCollector errors."""


class ConfigError(AppCollectorError):
    """Raised when required config is missing or inconsistent."""


class DriverError(AppCollectorError):
    """Raised when Appium driver creation or startup fails."""
