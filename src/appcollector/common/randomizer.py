from random import Random
from typing import Iterable, Sequence, TypeVar

T = TypeVar("T")


def make_rng(seed: int | str | None = None) -> Random:
    return Random(seed)


class SeededRandom:
    def __init__(self, seed: int | str | None = None) -> None:
        self.seed = seed
        self.rng = make_rng(seed)

    def choice(self, values: Iterable[T]) -> T:
        return self.rng.choice(list(values))

    def probability(self) -> float:
        return self.rng.random()

    def chance(self, probability: float) -> bool:
        return self.rng.random() < probability

    def uniform(self, low: float, high: float) -> float:
        return self.rng.uniform(low, high)

    def randint(self, low: int, high: int) -> int:
        return self.rng.randint(low, high)

    def jitter(self, value: float, radius: float, low: float = 0.0, high: float = 1.0) -> float:
        return min(high, max(low, value + self.uniform(-radius, radius)))

    def weighted_choice(self, choices: Sequence[tuple[T, float]]) -> T:
        total = sum(weight for _, weight in choices)
        if total <= 0:
            raise ValueError("Total weight must be positive")
        threshold = self.uniform(0, total)
        cumulative = 0.0
        for value, weight in choices:
            cumulative += weight
            if threshold <= cumulative:
                return value
        return choices[-1][0]

    def sequence(self, count: int) -> list[float]:
        return [self.rng.random() for _ in range(count)]
