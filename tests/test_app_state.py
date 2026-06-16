from appcollector.common.app_state import ensure_app_foreground, guarded_open_and_back


class FakeDriver:
    def __init__(self) -> None:
        self.current_package = "com.twitter.android"
        self.activated: list[str] = []
        self.back_calls = 0

    def activate_app(self, package: str) -> None:
        self.activated.append(package)
        self.current_package = package

    def back(self) -> None:
        self.back_calls += 1


def test_guarded_open_and_back_recovers_when_ad_opens_browser() -> None:
    driver = FakeDriver()

    def open_ad() -> None:
        driver.current_package = "com.android.chrome"

    result = guarded_open_and_back(
        driver,
        "com.twitter.android",
        open_action=open_ad,
        dwell_sec=0,
        sleeper=lambda _: None,
    )

    assert result == "recovered_after_open"
    assert driver.current_package == "com.twitter.android"
    assert driver.activated == ["com.twitter.android"]
    assert driver.back_calls == 0


def test_guarded_open_and_back_recovers_when_back_exits_target_app() -> None:
    class BackExitsDriver(FakeDriver):
        def back(self) -> None:
            self.back_calls += 1
            self.current_package = "com.sec.android.app.launcher"

    driver = BackExitsDriver()

    result = guarded_open_and_back(
        driver,
        "com.twitter.android",
        open_action=lambda: None,
        dwell_sec=0,
        sleeper=lambda _: None,
    )

    assert result == "recovered_after_back"
    assert driver.current_package == "com.twitter.android"
    assert driver.activated == ["com.twitter.android"]
    assert driver.back_calls == 1


def test_ensure_app_foreground_returns_false_when_activation_fails() -> None:
    class ActivationFailsDriver(FakeDriver):
        def activate_app(self, package: str) -> None:
            self.activated.append(package)
            raise RuntimeError("activation failed")

    driver = ActivationFailsDriver()
    driver.current_package = "com.android.chrome"

    assert ensure_app_foreground(driver, "com.twitter.android") is False
    assert driver.current_package == "com.android.chrome"
