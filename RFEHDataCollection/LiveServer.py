from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import threading
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from serial_utils import parse_sample_line, sanitize_run_name


DEFAULT_SERIAL_PORT = "COM3"
DEFAULT_BAUD_RATE = 115200
DEFAULT_HOST = "127.0.0.1"
DEFAULT_HTTP_PORT = 8000
MAX_BUFFER_SECONDS = 300
MAX_EXPECTED_SAMPLE_RATE = 500
MAX_BUFFER_SAMPLES = MAX_BUFFER_SECONDS * MAX_EXPECTED_SAMPLE_RATE
ROOT_DIR = Path(__file__).resolve().parent
WEB_DIR = ROOT_DIR / "web"
DATA_DIR = ROOT_DIR / "Data"
RAW_CSV_HEADER = ["Time(ms)", "ADC", "Voltage(V)"]


def normalize_smooth_window(value: Any) -> int:
    try:
        window = int(value)
    except (TypeError, ValueError):
        window = 11

    window = max(1, min(window, 501))
    if window % 2 == 0:
        window += 1
    return min(window, 501)


class RecordingManager:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self._lock = threading.RLock()
        self._active = False
        self._completed = False
        self._saving = False
        self._error = ""
        self._folder_name = ""
        self._duration_s = 0.0
        self._smooth = True
        self._show_raw = True
        self._smooth_window = 11
        self._started_at = 0.0
        self._sample_count = 0
        self._samples: list[dict[str, Any]] = []
        self._run_dir: Path | None = None
        self._raw_csv_path: Path | None = None
        self._png_path: Path | None = None
        self._meta_path: Path | None = None
        self._experiment_context: dict[str, Any] = {}
        self._csv_file = None
        self._writer: csv.writer | None = None
        self._result: dict[str, Any] = {}

    def start(self, config: dict[str, Any], serial_connected: bool) -> dict[str, Any]:
        if not serial_connected:
            raise ValueError("Serial port is not connected.")

        file_stem = sanitize_run_name(str(config.get("fileStem") or config.get("folderName", "")))
        relative_output_dir = str(config.get("relativeOutputDir", "")).strip()
        folder_name = relative_output_dir or file_stem
        try:
            duration_s = float(config.get("durationSeconds", 0))
        except (TypeError, ValueError) as exc:
            raise ValueError("Duration must be a number.") from exc

        if duration_s <= 0:
            raise ValueError("Duration must be greater than 0 seconds.")

        smooth = bool(config.get("smooth", True))
        show_raw = bool(config.get("showRaw", True))
        if not smooth and not show_raw:
            raise ValueError("At least one of smooth or raw plotting must be enabled.")

        smooth_window = normalize_smooth_window(config.get("smoothWindow", 11))
        experiment_context = config.get("experimentContext", {})
        if not isinstance(experiment_context, dict):
            experiment_context = {}
        run_dir = self._resolve_output_dir(relative_output_dir) if relative_output_dir else self.data_dir / file_stem
        raw_csv_path = run_dir / f"{file_stem}.csv"
        png_path = run_dir / f"{file_stem}.png"
        meta_path = run_dir / f"{file_stem}_meta.json"

        with self._lock:
            if self._active or self._saving:
                raise RuntimeError("A recording is already active.")
            existing_paths = [path for path in (raw_csv_path, png_path, meta_path) if path.exists()]
            if existing_paths:
                raise FileExistsError(f"Output file already exists: {existing_paths[0]}")

            run_dir.mkdir(parents=True, exist_ok=True)
            self._reset_locked()
            self._active = True
            self._completed = False
            self._folder_name = folder_name
            self._duration_s = duration_s
            self._smooth = smooth
            self._show_raw = show_raw
            self._smooth_window = smooth_window
            self._started_at = time.monotonic()
            self._run_dir = run_dir
            self._raw_csv_path = raw_csv_path
            self._png_path = png_path
            self._meta_path = meta_path
            self._experiment_context = dict(experiment_context)
            self._csv_file = raw_csv_path.open("w", encoding="utf-8", newline="")
            self._writer = csv.writer(self._csv_file)
            self._writer.writerow(RAW_CSV_HEADER)
            self._csv_file.flush()

            self._write_meta_locked(status="recording")
            return self.status()

    def append_sample(self, sample: dict[str, Any]) -> None:
        should_finish = False

        with self._lock:
            if not self._active or not self._writer or not self._csv_file:
                return

            elapsed_ms = (time.monotonic() - self._started_at) * 1000.0
            row = [
                f"{elapsed_ms:.3f}",
                sample["adc"],
                f"{sample['voltage']:.3f}",
            ]
            self._writer.writerow(row)
            self._sample_count += 1
            self._samples.append(
                {
                    "arduinoTimeMs": sample["arduinoTimeMs"],
                    "pcElapsedMs": elapsed_ms,
                    "adc": sample["adc"],
                    "voltage": sample["voltage"],
                }
            )

            if self._sample_count % 100 == 0:
                self._csv_file.flush()

            should_finish = elapsed_ms >= self._duration_s * 1000.0

        if should_finish:
            self.stop(reason="duration reached")

    def stop(self, reason: str = "manual stop") -> dict[str, Any]:
        with self._lock:
            if not self._active and not self._saving:
                return self.status()
            if self._saving:
                return self.status()

            self._active = False
            self._saving = True
            self._close_raw_csv_locked()

        try:
            self._finalize(reason)
        except Exception as exc:
            with self._lock:
                self._error = str(exc)
                self._completed = False
        finally:
            with self._lock:
                self._saving = False
                self._write_meta_locked(status="completed" if self._completed else "error")
                return self.status()

    def status(self) -> dict[str, Any]:
        with self._lock:
            elapsed_s = 0.0
            if self._active or self._saving or self._completed:
                elapsed_s = time.monotonic() - self._started_at if self._started_at else 0.0
                elapsed_s = min(elapsed_s, self._duration_s) if self._duration_s else elapsed_s

            return {
                "active": self._active,
                "saving": self._saving,
                "completed": self._completed,
                "folderName": self._folder_name,
                "durationSeconds": self._duration_s,
                "elapsedSeconds": elapsed_s,
                "sampleCount": self._sample_count,
                "smooth": self._smooth,
                "showRaw": self._show_raw,
                "smoothWindow": self._smooth_window,
                "experimentContext": self._experiment_context,
                "error": self._error,
                "outputDir": self._relative_path(self._run_dir),
                "csvPath": self._relative_path(self._raw_csv_path),
                "pngPath": self._relative_path(self._png_path),
                "metaPath": self._relative_path(self._meta_path),
                "result": self._result,
            }

    def _finalize(self, reason: str) -> None:
        with self._lock:
            if self._sample_count == 0:
                raise RuntimeError("No samples were recorded.")

            raw_csv_path = self._raw_csv_path
            png_path = self._png_path
            smooth = self._smooth
            show_raw = self._show_raw
            smooth_window = self._smooth_window

        if raw_csv_path is None or png_path is None:
            raise RuntimeError("Recording paths were not initialized.")

        from DataVisualization import plot_voltage_csv

        plot_voltage_csv(
            csv_path=raw_csv_path,
            output_path=png_path,
            window_size=smooth_window,
            smooth=smooth,
            show_raw=show_raw,
        )

        with self._lock:
            self._completed = True
            self._active = False
            self._saving = False
            self._error = ""
            self._result = {
                "reason": reason,
                "completedAt": datetime.now().isoformat(timespec="seconds"),
                "sampleCount": self._sample_count,
                "csvPath": self._relative_path(self._raw_csv_path),
                "pngPath": self._relative_path(self._png_path),
            }

    def _write_meta_locked(self, status: str) -> None:
        if self._meta_path is None:
            return

        meta = {
            "status": status,
            "folderName": self._folder_name,
            "createdAt": datetime.now().isoformat(timespec="seconds"),
            "durationSeconds": self._duration_s,
            "sampleCount": self._sample_count,
            "smooth": self._smooth,
            "showRaw": self._show_raw,
            "smoothWindow": self._smooth_window,
            "experimentContext": self._experiment_context,
            "rawHeader": RAW_CSV_HEADER,
            "files": {
                "rawCsv": self._relative_path(self._raw_csv_path),
                "plot": self._relative_path(self._png_path),
            },
            "error": self._error,
            "result": self._result,
        }

        self._meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    def _close_raw_csv_locked(self) -> None:
        if self._csv_file:
            self._csv_file.flush()
            self._csv_file.close()
        self._csv_file = None
        self._writer = None

    def _reset_locked(self) -> None:
        self._close_raw_csv_locked()
        self._active = False
        self._completed = False
        self._saving = False
        self._error = ""
        self._folder_name = ""
        self._duration_s = 0.0
        self._smooth = True
        self._show_raw = True
        self._smooth_window = 11
        self._started_at = 0.0
        self._sample_count = 0
        self._samples = []
        self._run_dir = None
        self._raw_csv_path = None
        self._png_path = None
        self._meta_path = None
        self._experiment_context = {}
        self._result = {}

    def _relative_path(self, path: Path | None) -> str | None:
        if path is None:
            return None
        try:
            return str(path.relative_to(ROOT_DIR))
        except ValueError:
            return str(path)

    def _resolve_output_dir(self, relative_output_dir: str) -> Path:
        parts = [
            sanitize_run_name(part)
            for part in re.split(r"[\\/]+", relative_output_dir)
            if part.strip()
        ]
        if not parts:
            raise ValueError("relativeOutputDir cannot be empty.")
        return self.data_dir.joinpath(*parts)


class SerialMonitor:
    def __init__(self, port: str, baud_rate: int, recorder: RecordingManager | None = None) -> None:
        self.port = port
        self.baud_rate = baud_rate
        self.recorder = recorder
        self._samples: deque[dict[str, Any]] = deque(maxlen=MAX_BUFFER_SAMPLES)
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._started_at = time.monotonic()
        self._sequence = 0
        self._latest_error = ""
        self._connected = False
        self._total_samples = 0
        self._invalid_lines = 0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="serial-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)

    def status(self) -> dict[str, Any]:
        with self._lock:
            sample_rate = self._sample_rate_locked()
            latest = self._samples[-1] if self._samples else None
            return {
                "connected": self._connected,
                "port": self.port,
                "baudRate": self.baud_rate,
                "sampleRate": sample_rate,
                "totalSamples": self._total_samples,
                "invalidLines": self._invalid_lines,
                "latestError": self._latest_error,
                "latest": latest,
            }

    def samples_after(self, sequence: int) -> list[dict[str, Any]]:
        with self._lock:
            return [sample for sample in self._samples if sample["sequence"] > sequence]

    def recent_samples(self, seconds: float) -> list[dict[str, Any]]:
        cutoff_ms = (time.monotonic() - self._started_at - seconds) * 1000.0
        with self._lock:
            return [sample for sample in self._samples if sample["pcTimeMs"] >= cutoff_ms]

    def _run(self) -> None:
        try:
            import serial
        except ModuleNotFoundError:
            with self._lock:
                self._latest_error = "pyserial is not installed. Run: pip install pyserial"
            return

        while not self._stop_event.is_set():
            try:
                with serial.Serial(self.port, self.baud_rate, timeout=1) as ser:
                    time.sleep(2)
                    ser.reset_input_buffer()
                    with self._lock:
                        self._connected = True
                        self._latest_error = ""

                    while not self._stop_event.is_set():
                        raw_line = ser.readline()
                        if not raw_line:
                            continue

                        line = raw_line.decode("utf-8", errors="ignore").strip()
                        sample_parts = parse_sample_line(line)
                        if sample_parts is None:
                            with self._lock:
                                self._invalid_lines += 1
                            continue

                        self._append_sample(sample_parts)

            except Exception as exc:
                with self._lock:
                    self._connected = False
                    self._latest_error = str(exc)
                self._stop_event.wait(2)

    def _append_sample(self, sample_parts: list[str]) -> None:
        now_ms = (time.monotonic() - self._started_at) * 1000.0
        arduino_time_ms = float(sample_parts[0])
        adc = int(sample_parts[1])
        voltage = float(sample_parts[2])

        sample = {
            "sequence": 0,
            "arduinoTimeMs": arduino_time_ms,
            "pcTimeMs": now_ms,
            "adc": adc,
            "voltage": voltage,
        }

        with self._lock:
            self._sequence += 1
            self._total_samples += 1
            sample["sequence"] = self._sequence
            self._samples.append(sample)

        if self.recorder:
            self.recorder.append_sample(sample)

    def _sample_rate_locked(self) -> float:
        if len(self._samples) < 2:
            return 0.0

        latest_ms = self._samples[-1]["pcTimeMs"]
        cutoff_ms = latest_ms - 1000.0
        count = sum(1 for sample in reversed(self._samples) if sample["pcTimeMs"] >= cutoff_ms)
        return float(count)


def create_app(monitor: SerialMonitor, recorder: RecordingManager) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        monitor.start()
        try:
            yield
        finally:
            recorder.stop(reason="server shutdown")
            monitor.stop()

    app = FastAPI(title="VCAP Live Monitor", lifespan=lifespan)

    @app.get("/")
    async def index() -> FileResponse:
        response = FileResponse(WEB_DIR / "index.html")
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/status")
    async def api_status() -> dict[str, Any]:
        return {
            "status": monitor.status(),
            "recording": recorder.status(),
        }

    @app.get("/api/samples")
    async def api_samples(seconds: float = 60.0) -> dict[str, Any]:
        return {
            "status": monitor.status(),
            "recording": recorder.status(),
            "samples": monitor.recent_samples(seconds),
        }

    @app.get("/api/recording/status")
    async def recording_status() -> dict[str, Any]:
        return recorder.status()

    @app.post("/api/recording/start")
    async def recording_start(config: dict[str, Any]) -> dict[str, Any]:
        try:
            return recorder.start(config=config, serial_connected=monitor.status()["connected"])
        except (ValueError, FileExistsError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/recording/stop")
    async def recording_stop() -> dict[str, Any]:
        return recorder.stop(reason="manual stop")

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        last_sequence = 0

        try:
            while True:
                try:
                    await asyncio.wait_for(websocket.receive_text(), timeout=0.001)
                except (asyncio.TimeoutError, json.JSONDecodeError, ValueError):
                    pass

                samples = monitor.samples_after(last_sequence)
                if samples:
                    last_sequence = samples[-1]["sequence"]

                await websocket.send_text(
                    json.dumps(
                        {
                            "status": monitor.status(),
                            "recording": recorder.status(),
                            "samples": samples,
                        }
                    )
                )
                await asyncio.sleep(0.1)
        except WebSocketDisconnect:
            return

    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
    return app


default_recorder = RecordingManager(DATA_DIR)
default_monitor = SerialMonitor(port=DEFAULT_SERIAL_PORT, baud_rate=DEFAULT_BAUD_RATE, recorder=default_recorder)
app = create_app(default_monitor, default_recorder)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start the local VCAP live monitor.")
    parser.add_argument("--serial-port", default=DEFAULT_SERIAL_PORT, help="Arduino serial port.")
    parser.add_argument("--baud-rate", type=int, default=DEFAULT_BAUD_RATE, help="Arduino serial baud rate.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="HTTP host.")
    parser.add_argument("--http-port", type=int, default=DEFAULT_HTTP_PORT, help="HTTP port.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    recorder = RecordingManager(DATA_DIR)
    monitor = SerialMonitor(port=args.serial_port, baud_rate=args.baud_rate, recorder=recorder)
    app = create_app(monitor, recorder)

    try:
        import uvicorn
    except ModuleNotFoundError as exc:
        raise RuntimeError("uvicorn is not installed. Run: pip install fastapi uvicorn") from exc

    print(f"Live monitor: http://{args.host}:{args.http_port}")
    print(f"Serial input: {args.serial_port} @ {args.baud_rate} baud")
    uvicorn.run(app, host=args.host, port=args.http_port)


if __name__ == "__main__":
    main()
