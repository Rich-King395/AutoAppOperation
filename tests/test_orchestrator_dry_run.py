from pathlib import Path

from appcollector.integration.experiment_orchestrator import ExperimentOrchestrator


class FakeMobileClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def check_ready(self, run_context) -> None:
        self.calls.append("check_ready")

    def launch_app(self, app_id: str) -> None:
        self.calls.append(f"launch_app:{app_id}")

    def run_app_flow(self, app_id: str, duration_sec: int, run_context=None):
        self.calls.append(f"run_app_flow:{app_id}:{duration_sec}")
        return {"status": "completed", "flow": "fake"}

    def stop_app(self, app_id: str) -> None:
        self.calls.append(f"stop_app:{app_id}")

    def cleanup(self, run_context) -> None:
        self.calls.append("cleanup")


class FailingMobileClient(FakeMobileClient):
    def run_app_flow(self, app_id: str, duration_sec: int, run_context=None):
        self.calls.append(f"run_app_flow:{app_id}:{duration_sec}")
        raise RuntimeError("mobile flow failed")


class FakeRFClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def check_ready(self):
        self.calls.append("check_ready")
        return {"status": {"connected": True}}

    def start_recording(self, run_id: str, output_dir: str, duration_sec: int, run_context=None):
        self.calls.append(f"start_recording:{run_id}:{duration_sec}")
        return {"active": True, "folderName": run_id}

    def wait_until_finished(self, run_id: str, duration_sec: int | None = None):
        self.calls.append(f"wait_until_finished:{run_id}:{duration_sec}")
        return {"completed": True, "folderName": run_id}

    def stop_recording(self):
        self.calls.append("stop_recording")
        return {"completed": True}


def test_orchestrator_generates_dry_run_plan_from_yaml() -> None:
    orchestrator = ExperimentOrchestrator.from_config_file(Path("configs/experiment.yaml"))
    plan = orchestrator.dry_run_plan()

    assert plan["mode"] == "dry_run"
    assert plan["experiment_id"] == "social_media_s10_rfeh_demo"
    assert plan["run_count"] == 4
    assert plan["runs"][0]["device_id"] == "samsung_galaxy_S10"
    assert plan["runs"][0]["hardware_id"] == "arduino_vcap_com3"
    assert plan["runs"][0]["duration_sec"] == 180
    assert plan["runs"][0]["app_warmup_sec"] == 60
    assert plan["runs"][0]["dry_run"] is True
    assert plan["runs"][0]["app_label"] == "twitter_android"
    assert plan["runs"][0]["repetition_id"] == 1
    router_id = plan["runs"][0]["router_id"]
    assert plan["runs"][0]["output_group"] == str(Path("social_media_s10_rfeh_demo") / router_id / "samsung_galaxy_S10")
    assert plan["runs"][0]["output_dir"].endswith(
        str(Path("social_media_s10_rfeh_demo") / router_id / "samsung_galaxy_S10" / "twitter_android")
    )
    assert plan["runs"][0]["file_stem"] == "twitter_android"
    assert plan["runs"][0]["run_id"].startswith("social-media-s10-rfeh-demo-")


def test_orchestrator_simulated_run_writes_metadata(tmp_path: Path) -> None:
    config = {
        "experiment_id": "demo",
        "device_id": "phone_01",
        "hardware_id": "arduino_01",
        "environment_id": "lab",
        "router_id": "router_01",
        "apps": [{"app_id": "reddit_android", "app_label": "Reddit"}],
        "duration_sec": 12,
        "repetitions": 1,
        "output_root": str(tmp_path),
    }
    fake_mobile = FakeMobileClient()
    fake_rf = FakeRFClient()
    orchestrator = ExperimentOrchestrator(config=config, mobile_client=fake_mobile, rf_client=fake_rf)

    results = orchestrator.run_matrix()

    assert len(results) == 1
    metadata = results[0]
    assert metadata["environment_id"] == "lab"
    assert metadata["device_id"] == "phone_01"
    assert metadata["router_id"] == "router_01"
    assert metadata["app_id"] == "reddit_android"
    assert metadata["app_label"] == "Reddit"
    assert metadata["duration_sec"] == 12
    assert metadata["app_warmup_sec"] == 0
    assert metadata["file_stem"] == "Reddit"
    assert metadata["repetition_id"] == 1
    assert metadata["status"] == "completed"
    assert metadata["mobile_result"] == {"status": "completed", "flow": "fake"}
    assert metadata["rf_start"]["active"] is True
    assert metadata["rf_finished"]["completed"] is True
    assert metadata["start_time"]
    assert metadata["end_time"]
    assert metadata["error"] is None
    assert Path(metadata["metadata_path"]).exists()
    assert Path(metadata["metadata_path"]).name.endswith("_metadata.json")
    assert fake_mobile.calls == [
        "check_ready",
        "launch_app:reddit_android",
        "run_app_flow:reddit_android:12",
        "stop_app:reddit_android",
        "cleanup",
    ]
    assert fake_rf.calls[0] == "check_ready"
    assert fake_rf.calls[1].startswith("start_recording:")
    assert fake_rf.calls[2].startswith("wait_until_finished:")


def test_orchestrator_failure_updates_metadata(tmp_path: Path) -> None:
    config = {
        "experiment_id": "demo",
        "device_id": "phone_01",
        "hardware_id": "arduino_01",
        "environment_id": "lab",
        "router_id": "router_01",
        "apps": ["reddit_android"],
        "duration_sec": 12,
        "repetitions": 1,
        "output_root": str(tmp_path),
    }
    fake_mobile = FailingMobileClient()
    fake_rf = FakeRFClient()
    orchestrator = ExperimentOrchestrator(config=config, mobile_client=fake_mobile, rf_client=fake_rf)

    metadata = orchestrator.run_matrix()[0]

    assert metadata["status"] == "failed"
    assert metadata["error"] == "mobile flow failed"
    assert Path(metadata["metadata_path"]).exists()
    assert fake_mobile.calls == [
        "check_ready",
        "launch_app:reddit_android",
        "run_app_flow:reddit_android:12",
        "stop_app:reddit_android",
        "cleanup",
    ]
    assert fake_rf.calls[-1].startswith("wait_until_finished:")
    assert "rf_finished_after_mobile_error" in metadata
