from appcollector.common.app_state import guarded_back
from appcollector.common.gestures import swipe_down_jittered, swipe_up_jittered, tap_relative_jittered
from appcollector.common.popups import dismiss_known_popups
from appcollector.flows.base import Flow


class ShoppingBrowse(Flow):
    def step(self, iteration: int) -> str:
        popup_every = int((self.scenario or {}).get("popup_check_every_iterations", 5))
        if popup_every > 0 and iteration % popup_every == 1:
            dismiss_known_popups(self.driver)

        action = self.randomizer.weighted_choice(
            [
                ("browse_list", 0.52),
                ("open_detail", 0.28),
                ("swipe_down", 0.1),
                ("wait", 0.1),
            ]
        )
        if action == "open_detail":
            tap_relative_jittered(self.driver, self.randomizer, 0.5, 0.52, jitter=0.1)
            self.wait_random(1.5, 3.5)
            if not self.ensure_foreground():
                return "open_detail:recovered_after_open"
            for _ in range(self.randomizer.randint(1, 4)):
                swipe_up_jittered(self.driver, self.randomizer, duration_ms=self.randomizer.randint(700, 1200))
                self.wait_random(0.8, 2.0)
            guarded_back(self.driver, self.target_package, foreground_guard=self.foreground_guard)
            self.wait_random(0.8, 2.0)
        elif action == "swipe_down":
            swipe_down_jittered(self.driver, self.randomizer)
            self.wait_random(0.7, 1.8)
        elif action == "wait":
            self.wait_random(1.5, 4.0)
        else:
            swipe_up_jittered(self.driver, self.randomizer)
            self.wait_random(0.7, 2.0)
        return action
