from appcollector.common.gestures import swipe_up_jittered, tap_relative_jittered
from appcollector.flows.base import Flow


class PassiveMedia(Flow):
    def step(self, iteration: int) -> str:
        action = self.randomizer.weighted_choice(
            [
                ("long_wait", 0.78),
                ("keep_alive_tap", 0.12),
                ("gentle_swipe", 0.1),
            ]
        )
        if action == "keep_alive_tap":
            tap_relative_jittered(self.driver, self.randomizer, 0.5, 0.5, jitter=0.03)
            self.wait_random(8.0, 18.0)
        elif action == "gentle_swipe":
            swipe_up_jittered(self.driver, self.randomizer, duration_ms=self.randomizer.randint(500, 900))
            self.wait_random(10.0, 24.0)
        else:
            self.wait_random(12.0, 30.0)
        return action
