from pathlib import Path
from typing import Any

import yaml

from appcollector.errors import ConfigError

CONFIG_FILES = {
    "devices": "devices.yaml",
    "apps": "apps.yaml",
    "scenarios": "scenarios.yaml",
    "experiment_matrix": "experiment_matrix.yaml",
}

OPTIONAL_CONFIG_FILES = {
    "device_app_overrides": "device_app_overrides.yaml",
}

REQUIRED_TOP_LEVEL_KEYS = {
    "devices": "devices",
    "apps": "apps",
    "scenarios": "scenarios",
    "experiment_matrix": "experiments",
}


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"Config file must contain a mapping: {path}")
    return data


def load_configs(config_dir: Path | str = "configs") -> dict[str, dict[str, Any]]:
    base = Path(config_dir)
    configs = {name: load_yaml(base / filename) for name, filename in CONFIG_FILES.items()}
    for name, filename in OPTIONAL_CONFIG_FILES.items():
        path = base / filename
        configs[name] = load_yaml(path) if path.exists() else {"overrides": {}}
    validate_configs(configs)
    return configs


def index_by(items: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for item in items:
        if key not in item:
            raise ConfigError(f"Missing required key '{key}' in item: {item}")
        indexed[str(item[key])] = item
    return indexed


def validate_configs(configs: dict[str, dict[str, Any]]) -> None:
    for config_name, top_level_key in REQUIRED_TOP_LEVEL_KEYS.items():
        if config_name not in configs:
            raise ConfigError(f"Missing config: {config_name}")
        value = configs[config_name].get(top_level_key)
        if not isinstance(value, list):
            raise ConfigError(f"{config_name} must contain a list at '{top_level_key}'")

    for scenario in configs["scenarios"]["scenarios"]:
        if "duration_sec" not in scenario:
            raise ConfigError(f"Scenario missing duration_sec: {scenario}")
        if "random_seed" not in scenario:
            raise ConfigError(f"Scenario missing random_seed: {scenario}")

    override_config = configs.get("device_app_overrides", {})
    overrides = override_config.get("overrides", {})
    if not isinstance(overrides, dict):
        raise ConfigError("device_app_overrides must contain a mapping at 'overrides'")
    for device_id, app_overrides in overrides.items():
        if not isinstance(app_overrides, dict):
            raise ConfigError(f"Device override for '{device_id}' must be a mapping")
        for app_id, override in app_overrides.items():
            if not isinstance(override, dict):
                raise ConfigError(f"App override for '{device_id}/{app_id}' must be a mapping")


def merge_device_app_override(
    app_config: dict[str, Any],
    configs: dict[str, dict[str, Any]],
    device_id: str,
    app_id: str,
) -> dict[str, Any]:
    """Return app config with device-specific override fields applied."""
    merged = dict(app_config)
    overrides = configs.get("device_app_overrides", {}).get("overrides", {})
    device_overrides = overrides.get(device_id, {})
    override = device_overrides.get(app_id, {})
    return _deep_merge(merged, override)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def get_config_value(config: dict[str, Any], *keys: str, required: bool = True) -> Any:
    for key in keys:
        value = config.get(key)
        if value not in (None, ""):
            return value
    if required:
        joined = " / ".join(keys)
        label = config.get("name") or config.get("app_label") or config
        raise ConfigError(f"Missing required config field '{joined}' in {label}")
    return None
