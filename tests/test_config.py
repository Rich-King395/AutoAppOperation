from pathlib import Path

from appcollector.config import load_configs


def test_load_configs() -> None:
    configs = load_configs(Path("configs"))
    assert "devices" in configs
    assert configs["devices"]["devices"]
    assert configs["devices"]["devices"][0]["platformName"] == "Android"
    assert configs["devices"]["devices"][0]["automationName"] == "UiAutomator2"
    assert "appPackage" in configs["apps"]["apps"][0]
    assert configs["scenarios"]["scenarios"][0]["duration_sec"] > 0
    assert "random_seed" in configs["scenarios"]["scenarios"][0]
    assert configs["experiment_matrix"]["experiments"][0]["experiment_id"] == "smoke_android_feed"
