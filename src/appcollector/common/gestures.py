from typing import Any

from appcollector.common.randomizer import SeededRandom


def _window_size(driver: Any) -> tuple[int, int]:
    size = driver.get_window_size()
    return int(size["width"]), int(size["height"])


def tap_relative(driver: Any, x_ratio: float, y_ratio: float) -> None:
    width, height = _window_size(driver)
    driver.tap([(int(width * x_ratio), int(height * y_ratio))])


def tap_relative_jittered(
    driver: Any,
    randomizer: SeededRandom,
    x_ratio: float,
    y_ratio: float,
    jitter: float = 0.04,
) -> None:
    tap_relative(
        driver,
        randomizer.jitter(x_ratio, jitter, low=0.05, high=0.95),
        randomizer.jitter(y_ratio, jitter, low=0.05, high=0.95),
    )


def tap_first_available(
    driver: Any,
    locators: list[tuple[str, str]],
    fallback: tuple[float, float] | None = None,
) -> bool:
    for by, value in locators:
        elements = driver.find_elements(by, value)
        if elements:
            elements[0].click()
            return True
    if fallback is not None:
        tap_relative(driver, fallback[0], fallback[1])
        return True
    return False


def tap_center(driver: Any) -> None:
    tap_relative(driver, 0.5, 0.5)


def swipe_relative(
    driver: Any,
    start_x: float,
    start_y: float,
    end_x: float,
    end_y: float,
    duration_ms: int = 500,
) -> None:
    width, height = _window_size(driver)
    driver.swipe(
        int(width * start_x),
        int(height * start_y),
        int(width * end_x),
        int(height * end_y),
        duration_ms,
    )


def swipe_relative_jittered(
    driver: Any,
    randomizer: SeededRandom,
    start_x: float,
    start_y: float,
    end_x: float,
    end_y: float,
    jitter: float = 0.035,
    duration_ms: int = 650,
) -> None:
    swipe_relative(
        driver,
        randomizer.jitter(start_x, jitter, low=0.1, high=0.9),
        randomizer.jitter(start_y, jitter, low=0.1, high=0.9),
        randomizer.jitter(end_x, jitter, low=0.1, high=0.9),
        randomizer.jitter(end_y, jitter, low=0.1, high=0.9),
        duration_ms=duration_ms,
    )


def swipe_up(driver: Any) -> None:
    swipe_relative(driver, 0.5, 0.8, 0.5, 0.2)


def swipe_up_jittered(driver: Any, randomizer: SeededRandom, duration_ms: int = 650) -> None:
    swipe_relative_jittered(driver, randomizer, 0.5, 0.82, 0.5, 0.24, duration_ms=duration_ms)


def swipe_down_jittered(driver: Any, randomizer: SeededRandom, duration_ms: int = 650) -> None:
    swipe_relative_jittered(driver, randomizer, 0.5, 0.28, 0.5, 0.76, duration_ms=duration_ms)


def slow_swipe_up_jittered(driver: Any, randomizer: SeededRandom) -> None:
    swipe_up_jittered(driver, randomizer, duration_ms=randomizer.randint(900, 1500))


def go_back(driver: Any) -> None:
    driver.back()
