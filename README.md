# AppCollector

AppCollector is a Python + Appium framework for app-level mobile data collection with synchronized voltage/RF recording. The current system collects app-level experiment data only; it does not perform activity-level labeling or behavior classification.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
```

## System Structure

The top-level automated experiment flow is split into three integration layers:

- `MobileAutomationClient`
  Wraps the existing Android/Appium automation module. It checks the phone/Appium state, launches the target app, runs the configured app-level flow, stops the app, and cleans up the driver.

- `RFCollectorClient`
  Wraps the voltage/RF collection backend. It talks to the RFEH Web Live Monitor HTTP API, starts recording for each run, waits for recording completion, and reports RF status.

- `ExperimentOrchestrator`
  Coordinates batch experiments. It reads the experiment config, generates run plans, calls mobile automation and RF collection in order, and writes per-run metadata.

The per-run execution order is:

```text
check phone/Appium
check RF collector
launch app
wait for app_warmup_sec without RF recording
start RF recording
run app-level flow
wait for RF recording
stop app
save metadata
```

## Prepare Config

The top-level experiment config is `configs/experiment.yaml`. It describes one batch experiment:

```yaml
experiment_id: social_media_s10_rfeh_demo
device_id: samsung_galaxy_S10
hardware_id: arduino_vcap_com3
environment_id: lab
router_id: router_01
duration_sec: 180
app_warmup_sec: 60
repetitions: 1
output_root: data/raw/social_media_s10_rfeh_demo

apps:
  - app_id: twitter_android
    app_label: twitter_android
```

Device details come from `configs/devices.yaml`, app package/activity details come from `configs/apps.yaml`, and flow behavior comes from `configs/scenarios.yaml`.

`app_warmup_sec` is the wait time after launching the app and before starting RF recording. Use it to let the voltage waveform settle; no RF data is recorded during this warm-up window.

## Dry Run

Dry-run only parses the config and prints the planned runs. It does not connect to the phone, Appium, or RF hardware.

```powershell
python -m appcollector.cli run-matrix --config configs/experiment.yaml --dry-run
```

## Run Experiment

Formal execution runs the planned apps in sequence and starts RF recording for each run.

```powershell
python -m appcollector.cli run-matrix --config configs/experiment.yaml
```

To continue after a failed run:

```powershell
python -m appcollector.cli run-matrix --config configs/experiment.yaml --continue-on-error
```

Each run writes metadata under its run output directory.

The run output directory is grouped by experiment, router, device, and app:

```text
<output_root>/
  <router_id>/
      <device_id>/
        <app_label>/
        <app_label>_metadata.json
```

The RF backend uses the same grouping under `RFEHDataCollection/Data`:

```text
RFEHDataCollection/Data/
  <experiment_id>/
    <router_id>/
      <device_id>/
        <app_label>/
          <app_label>.csv
          <app_label>.png
          <app_label>_meta.json
```

`run_id` is still written inside metadata for traceability, but it is not used as the RF data folder name.

## Required Manual Checks

Before formal execution, confirm:

- Android phone is connected to the computer.
- Android phone is connected to the target Wi-Fi.
- Voltage collection hardware is connected.
- Web Live Monitor or RF backend is running.
- Appium server is running.

Start Appium:

```powershell
appium
```

Start the RFEH Live Monitor:

```powershell
cd RFEHDataCollection
python LiveServer.py
```

The monitor is available at:

```text
http://127.0.0.1:8000
```

## App-Level Scope

Current flows are app-level browsing flows. They generate natural, randomized, reproducible interactions within the configured duration, but they do not create activity-level labels.

The automation avoids sending messages, liking, commenting, purchasing, following, sharing, or bypassing verification screens.

## TODO / Stubs

- `RFCollectorClient` currently uses the Web Live Monitor HTTP API; direct hardware adapters can be added later if needed.
- iOS/XCUITest driver support is stubbed and not fully implemented.
- App-specific flows can be expanded with safer element-based locators where available.
- RF output is saved by the RFEH backend under `RFEHDataCollection/Data` using the same experiment/router/device/app grouping as AppCollector metadata.
- More validation can be added for hardware IDs, router IDs, and environment IDs.
