from appcollector.common.randomizer import SeededRandom, make_rng


def test_make_rng_is_deterministic() -> None:
    first = [make_rng(42).random() for _ in range(1)]
    second = [make_rng(42).random() for _ in range(1)]
    assert first == second


def test_seeded_random_choice_is_deterministic() -> None:
    left = SeededRandom(7).choice(["a", "b", "c"])
    right = SeededRandom(7).choice(["a", "b", "c"])
    assert left == right


def test_seeded_random_sequence_is_deterministic() -> None:
    assert SeededRandom(99).sequence(5) == SeededRandom(99).sequence(5)


def test_seeded_random_weighted_choice_is_deterministic() -> None:
    choices = [("wait", 0.2), ("swipe", 0.7), ("back", 0.1)]
    left = [SeededRandom(123).weighted_choice(choices) for _ in range(1)]
    right = [SeededRandom(123).weighted_choice(choices) for _ in range(1)]
    assert left == right


def test_seeded_random_jitter_is_deterministic_and_bounded() -> None:
    left = SeededRandom(77).jitter(0.5, 0.2, low=0.4, high=0.6)
    right = SeededRandom(77).jitter(0.5, 0.2, low=0.4, high=0.6)
    assert left == right
    assert 0.4 <= left <= 0.6
