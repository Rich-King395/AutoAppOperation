from datetime import UTC, datetime

from appcollector.run_logger import make_run_id


def test_make_run_id_is_stable_and_contains_key_fields() -> None:
    now = datetime(2026, 6, 14, 7, 0, 0, tzinfo=UTC)
    run_id = make_run_id("demo", "android_01", "sample_app", "feed_random_walk", now=now)
    assert run_id == make_run_id("demo", "android_01", "sample_app", "feed_random_walk", now=now)
    assert run_id == "demo-android-01-sample-app-feed-random-walk-20260614T070000000000Z"
