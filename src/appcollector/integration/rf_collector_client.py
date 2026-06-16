"""High-level client boundary for voltage/RF data collection.

This module defines the orchestration-facing interface for the existing
``RFEHDataCollection`` subsystem.  It adapts the existing Web Live Monitor
HTTP API and intentionally does not implement serial protocols, plotting, or
browser automation.

The expected backend is ``RFEHDataCollection/LiveServer.py``.
"""

import json
from dataclasses import dataclass
from time import monotonic, sleep
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from appcollector.errors import ConfigError


@dataclass
class RFCollectorClient:
    """Facade for voltage/RF collection used by the orchestrator.

    By default this client calls the existing RFEH Web Live Monitor API.  For
    tests or offline planning, inject a fake client into ``ExperimentOrchestrator``.
    """

    config: dict[str, Any] | None = None

    @property
    def base_url(self) -> str:
        """Base URL for the RFEH live monitor HTTP API."""
        return str((self.config or {}).get("base_url", "http://127.0.0.1:8000")).rstrip("/")

    def check_ready(self) -> dict[str, Any]:
        """Validate that the Live Monitor is reachable and serial is connected."""
        status = self.status()
        serial_status = status.get("status", {})
        if not serial_status.get("connected"):
            latest_error = serial_status.get("latestError") or "serial port is not connected"
            raise ConfigError(f"RF collector is not ready: {latest_error}")
        return status

    def start_recording(
        self,
        run_id: str,
        output_dir: str,
        duration_sec: int,
        run_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Start recording through the RFEH Live Monitor API."""
        context = dict(run_context or {})
        file_stem = str(context.get("file_stem") or run_id)
        relative_output_dir = self._relative_output_dir(context)
        payload = {
            "folderName": file_stem,
            "fileStem": file_stem,
            "relativeOutputDir": relative_output_dir,
            "durationSeconds": int(duration_sec),
            "smooth": bool((self.config or {}).get("smooth", True)),
            "showRaw": bool((self.config or {}).get("show_raw", True)),
            "smoothWindow": int((self.config or {}).get("smooth_window", 11)),
            "experimentContext": self._experiment_context(run_id, output_dir, run_context),
        }
        return self._post_json("/api/recording/start", payload)

    def wait_until_finished(self, run_id: str, duration_sec: int | None = None) -> dict[str, Any]:
        """Poll recording status until the requested recording finishes."""
        poll_interval = float((self.config or {}).get("poll_interval_sec", 1.0))
        margin = float((self.config or {}).get("wait_margin_sec", 120.0))
        timeout = float(duration_sec or 0) + margin
        deadline = monotonic() + timeout

        while True:
            status = self.recording_status()
            if status.get("completed"):
                return status
            if status.get("error"):
                raise ConfigError(f"RF recording failed for {run_id}: {status['error']}")
            if not status.get("active") and not status.get("saving") and status.get("sampleCount", 0) == 0:
                raise ConfigError(f"RF recording is not active for {run_id}.")
            if monotonic() >= deadline:
                raise ConfigError(f"Timed out waiting for RF recording to finish for {run_id}.")
            sleep(poll_interval)

    def stop_recording(self) -> dict[str, Any]:
        """Request recording stop through the RFEH Live Monitor API."""
        return self._post_json("/api/recording/stop", {})

    def recording_status(self) -> dict[str, Any]:
        """Return RFEH recording status."""
        return self._get_json("/api/recording/status")

    def prepare(self, run_context: dict[str, Any]) -> None:
        """Backward-compatible alias for ``check_ready``."""
        self.check_ready()

    def start(self, run_context: dict[str, Any]) -> dict[str, Any]:
        """Backward-compatible alias for ``start_recording``."""
        return self.start_recording(
            run_id=str(run_context["run_id"]),
            output_dir=str(run_context["output_dir"]),
            duration_sec=int(run_context["duration_sec"]),
            run_context=run_context,
        )

    def stop(self, run_context: dict[str, Any]) -> dict[str, Any]:
        """Backward-compatible alias for ``stop_recording``."""
        return self.stop_recording()

    def status(self) -> dict[str, Any]:
        """Return collector/service status."""
        return self._get_json("/api/status")

    def _get_json(self, path: str) -> dict[str, Any]:
        try:
            with urlopen(f"{self.base_url}{path}", timeout=float((self.config or {}).get("timeout_sec", 5.0))) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError) as exc:
            raise ConfigError(f"Could not reach RF collector at {self.base_url}: {exc}") from exc

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=float((self.config or {}).get("timeout_sec", 5.0))) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            try:
                detail = json.loads(body).get("detail", body)
            except json.JSONDecodeError:
                detail = body or str(exc)
            raise ConfigError(f"RF collector request failed at {path}: {detail}") from exc
        except (URLError, TimeoutError) as exc:
            raise ConfigError(f"Could not reach RF collector at {self.base_url}: {exc}") from exc

    def _experiment_context(
        self,
        run_id: str,
        output_dir: str,
        run_context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        context = dict(run_context or {})
        return {
            "runId": run_id,
            "experimentId": context.get("experiment_id"),
            "environmentId": context.get("environment_id"),
            "deviceId": context.get("device_id"),
            "hardwareId": context.get("hardware_id"),
            "routerId": context.get("router_id"),
            "appId": context.get("app_id"),
            "appLabel": context.get("app_label"),
            "durationSec": context.get("duration_sec"),
            "appWarmupSec": context.get("app_warmup_sec"),
            "repetitionId": context.get("repetition_id") or context.get("repetition"),
            "outputDir": output_dir,
        }

    def _relative_output_dir(self, context: dict[str, Any]) -> str:
        output_group = context.get("output_group")
        app_label = context.get("app_label") or context.get("app_id") or "unknown_app"
        if output_group:
            return f"{output_group}/{app_label}"

        experiment_id = context.get("experiment_id") or "unknown_experiment"
        router_id = context.get("router_id") or "unknown_router"
        device_id = context.get("device_id") or "unknown_device"
        return f"{experiment_id}/{router_id}/{device_id}/{app_label}"
