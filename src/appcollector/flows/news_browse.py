from appcollector.common.app_state import ensure_app_foreground, guarded_back
from appcollector.common.gestures import slow_swipe_up_jittered, swipe_up_jittered, tap_relative_jittered
from appcollector.common.popups import dismiss_known_popups
from appcollector.flows.base import Flow


class NewsBrowse(Flow):
    def step(self, iteration: int) -> str:
        popup_every = int((self.scenario or {}).get("popup_check_every_iterations", 5))
        if popup_every > 0 and iteration % popup_every == 1:
            dismiss_known_popups(self.driver)

        action = self.randomizer.weighted_choice(
            [
                ("browse_home", 0.6),
                ("open_article", 0.3),
                ("wait", 0.1),
            ]
        )
        if action == "open_article":
            tap_relative_jittered(self.driver, self.randomizer, 0.5, 0.45, jitter=0.1)
            self.wait_random(1.5, 3.0)
            if not ensure_app_foreground(self.driver, self.target_package):
                return "open_article:recovered_after_open"
            for _ in range(self.randomizer.randint(1, 3)):
                slow_swipe_up_jittered(self.driver, self.randomizer)
                self.wait_random(1.0, 2.5)
            guarded_back(self.driver, self.target_package)
            self.wait_random(0.8, 1.8)
        elif action == "wait":
            self.wait_random(2.0, 5.0)
        else:
            swipe_up_jittered(self.driver, self.randomizer)
            self.wait_random(0.8, 2.2)
        return action
