from dataclasses import dataclass
from time import monotonic, sleep
from typing import Any, Callable

from appcollector.common.app_state import ensure_app_foreground
from appcollector.common.randomizer import SeededRandom


@dataclass
class Flow:
    driver: Any
    duration_sec: int
    random_seed: int | str | None
    logger: Any
    scenario: dict[str, Any] | None = None
    target_package: str | None = None
    foreground_guard: Callable[[], bool] | None = None

    def __post_init__(self) -> None:
        self.randomizer = SeededRandom(self.random_seed)

    @property
    def flow_name(self) -> str:
        return self.__class__.__name__

    def log_event(self, event: str, **fields: Any) -> None:
        if hasattr(self.logger, "event"):
            self.logger.event(event, flow=self.flow_name, **fields)

    def run(self) -> None:
        deadline = monotonic() + max(0, self.duration_sec)
        iteration = 0
        consecutive_errors = 0
        stay_in_app = bool((self.scenario or {}).get("stay_in_app", True))
        self.log_event(
            "flow_start",
            duration_sec=self.duration_sec,
            random_seed=self.random_seed,
            stay_in_app=stay_in_app,
        )
        if stay_in_app:
            recovered = self.ensure_foreground()
            if not recovered:
                self.log_event("app_foreground_recovery", phase="flow_start")
        while monotonic() < deadline:
            iteration += 1
            try:
                action = self.step(iteration)
                consecutive_errors = 0
            except Exception as exc:
                consecutive_errors += 1
                action = f"step_error:{exc.__class__.__name__}"
                self.log_event(
                    "flow_step_error",
                    iteration=iteration,
                    error=str(exc),
                    consecutive_errors=consecutive_errors,
                )
                if stay_in_app:
                    recovered = self.ensure_foreground()
                    if not recovered:
                        action = f"{action}:recovery_failed"
                remaining = deadline - monotonic()
                if remaining <= 0:
                    break
                sleep(min(3.0, remaining))
                self.log_event("loop_iteration", iteration=iteration, action=action)
                continue
            if stay_in_app:
                stayed = self.ensure_foreground()
                if not stayed:
                    action = f"{action}:recovered_app_foreground"
            self.log_event("loop_iteration", iteration=iteration, action=action)
        self.log_event("flow_end", iterations=iteration)

    def ensure_foreground(self) -> bool:
        return ensure_app_foreground(
            self.driver,
            self.target_package,
            foreground_guard=self.foreground_guard,
        )

    def wait_random(self, min_sec: float, max_sec: float) -> None:
        sleep(self.randomizer.uniform(min_sec, max_sec))

    def step(self, iteration: int) -> str:
        raise NotImplementedError
