from appcollector.common.app_state import guarded_open_and_back
from appcollector.common.gestures import swipe_down_jittered, swipe_up_jittered, tap_relative_jittered
from appcollector.common.popups import dismiss_known_popups
from appcollector.flows.base import Flow


class FeedRandomWalk(Flow):
    def step(self, iteration: int) -> str:
        scenario = self.scenario or {}
        popup_every = int((self.scenario or {}).get("popup_check_every_iterations", 4))
        if popup_every > 0 and iteration % popup_every == 1:
            dismiss_known_popups(self.driver)

        allow_open_content = bool(scenario.get("allow_open_content", False))
        choices = [
            ("wait", 0.28),
            ("swipe_up", 0.55),
            ("swipe_down", 0.17),
        ]
        if allow_open_content:
            choices.append(("open_and_back", 0.12))

        action = self.randomizer.weighted_choice(
            choices
        )
        if action == "wait":
            self.wait_random(1.2, 4.0)
        elif action == "swipe_down":
            swipe_down_jittered(self.driver, self.randomizer)
            self.wait_random(0.8, 2.0)
        elif action == "open_and_back":
            result = guarded_open_and_back(
                self.driver,
                self.target_package,
                open_action=lambda: tap_relative_jittered(self.driver, self.randomizer, 0.5, 0.48, jitter=0.08),
                dwell_sec=self.randomizer.uniform(2.0, 5.0),
            )
            action = f"{action}:{result}"
            self.wait_random(0.8, 2.0)
        else:
            swipe_up_jittered(self.driver, self.randomizer)
            self.wait_random(0.8, 2.4)
        return action
