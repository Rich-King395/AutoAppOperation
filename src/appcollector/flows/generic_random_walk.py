from appcollector.common.app_state import guarded_back
from appcollector.common.gestures import swipe_down_jittered, swipe_up_jittered
from appcollector.flows.base import Flow


class GenericRandomWalk(Flow):
    def step(self, iteration: int) -> str:
        allow_back = bool((self.scenario or {}).get("allow_back_navigation", False))
        choices = [("wait", 0.22), ("swipe_up", 0.6), ("swipe_down", 0.18)]
        if allow_back:
            choices.append(("back", 0.12))
        action = self.randomizer.weighted_choice(choices)
        if action == "back":
            guarded_back(self.driver, self.target_package, foreground_guard=self.foreground_guard)
            self.wait_random(0.8, 2.0)
        elif action == "swipe_down":
            swipe_down_jittered(self.driver, self.randomizer)
            self.wait_random(0.8, 2.0)
        elif action == "wait":
            self.wait_random(1.0, 4.0)
        else:
            swipe_up_jittered(self.driver, self.randomizer)
            self.wait_random(0.8, 2.0)
        return action
