from time import sleep
from typing import Any, Callable

from appcollector.common.app_state import ensure_app_foreground
from appcollector.common.gestures import swipe_up_jittered, tap_relative
from appcollector.common.popups import dismiss_known_popups
from appcollector.common.randomizer import SeededRandom


DEFAULT_VIDEO_TAP_POINTS = [
    (0.50, 0.42),
    (0.50, 0.58),
    (0.50, 0.72),
]

DEFAULT_MUSIC_TAP_POINTS = [
    (0.50, 0.55),
    (0.50, 0.72),
    (0.86, 0.92),
]


def prepare_playback(
    driver: Any,
    app_config: dict[str, Any],
    logger: Any | None = None,
    target_package: str | None = None,
    foreground_guard: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Try to put video/music apps into playback before RF collection starts."""
    category = str(app_config.get("category", "")).lower()
    if category not in {"video", "music"}:
        return {"skipped": True, "reason": f"category:{category or 'unknown'}"}

    profile = app_config.get("playback_profile") or {}
    max_attempts = int(profile.get("max_attempts", 3))
    startup_wait_sec = float(profile.get("startup_wait_sec", 3.0))
    after_tap_wait_sec = float(profile.get("after_tap_wait_sec", 5.0))
    tap_points = _tap_points(profile, category)
    randomizer = SeededRandom(profile.get("random_seed", app_config.get("app_label")))

    _event(logger, "playback_prepare_start", category=category, max_attempts=max_attempts)
    dismissed = _safe_dismiss_popups(driver)
    sleep(startup_wait_sec)

    actions: list[dict[str, Any]] = []
    for attempt in range(1, max_attempts + 1):
        if not ensure_app_foreground(driver, target_package, foreground_guard=foreground_guard):
            actions.append({"attempt": attempt, "action": "recover_foreground"})
            sleep(1.0)

        point = tap_points[(attempt - 1) % len(tap_points)]
        try:
            tap_relative(driver, point[0], point[1])
            actions.append({"attempt": attempt, "action": "tap", "point": point})
        except Exception as exc:
            actions.append({"attempt": attempt, "action": "tap_error", "error": str(exc)})

        sleep(after_tap_wait_sec)
        foreground = ensure_app_foreground(driver, target_package, foreground_guard=foreground_guard)
        if foreground and attempt >= 1:
            _event(
                logger,
                "playback_prepare_attempt",
                attempt=attempt,
                action="tap",
                foreground=foreground,
            )

        if attempt < max_attempts:
            try:
                swipe_up_jittered(driver, randomizer, duration_ms=randomizer.randint(500, 900))
                actions.append({"attempt": attempt, "action": "gentle_swipe"})
                sleep(1.5)
            except Exception as exc:
                actions.append({"attempt": attempt, "action": "swipe_error", "error": str(exc)})

    final_foreground = ensure_app_foreground(driver, target_package, foreground_guard=foreground_guard)
    result = {
        "skipped": False,
        "category": category,
        "dismissed_popups": dismissed,
        "attempts": max_attempts,
        "final_foreground": final_foreground,
        "actions": actions,
    }
    _event(logger, "playback_prepare_end", category=category, final_foreground=final_foreground)
    return result


def _tap_points(profile: dict[str, Any], category: str) -> list[tuple[float, float]]:
    configured = profile.get("tap_points") or profile.get("startup_taps")
    if configured:
        points = [(float(point[0]), float(point[1])) for point in configured]
        if points:
            return points
    return DEFAULT_MUSIC_TAP_POINTS if category == "music" else DEFAULT_VIDEO_TAP_POINTS


def _safe_dismiss_popups(driver: Any) -> int:
    try:
        return dismiss_known_popups(driver)
    except Exception:
        return 0


def _event(logger: Any | None, event: str, **fields: Any) -> None:
    if hasattr(logger, "event"):
        logger.event(event, flow="PlaybackPrepare", **fields)
