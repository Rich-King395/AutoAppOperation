# AppCollector

AppCollector is a Python + Appium framework skeleton for app-level mobile data collection experiments inspired by AppListener reproduction work. It does not implement activity-level behavior classification.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
```

## Start Appium

Install Appium and the Android driver:

```powershell
npm install -g appium
appium driver install uiautomator2
appium
```

For iOS, install and configure the XCUITest driver on a macOS host.

## Android Real Device Setup

1. Enable Developer Options and USB debugging on the Android phone.
2. Connect the phone by USB and accept the RSA debugging prompt on the phone.
3. Confirm ADB sees the device:

```powershell
adb devices -l
```

Use the device id from that output as `udid` in `configs/devices.yaml`.

4. Fill Android device config:

```yaml
devices:
  - name: samsung_galaxy_S10
    platformName: Android
    automationName: UiAutomator2
    deviceName: samsung_galaxy_S10
    udid: YOUR_ADB_DEVICE_ID
    platformVersion: "14"
    appiumServerUrl: http://127.0.0.1:4723
```

5. Fill Android app config:

```yaml
apps:
  - app_label: target_app
    platformName: Android
    appPackage: com.example.android
    appActivity: .MainActivity
```

You can inspect the foreground package/activity after manually opening the app:

```powershell
adb shell dumpsys window | findstr mCurrentFocus
```

Keep `noReset=true` behavior by default so Appium does not clear app data or remove login state.

## Validate And Smoke Test

These commands run in dry-run mode by default, so they do not require a phone or Appium server:

```powershell
appcollector validate-config
appcollector smoke
pytest
```

Real Android smoke test:

```powershell
appium
appcollector smoke smoke_android_feed --no-dry-run
```

The smoke command creates an Android UiAutomator2 driver, activates the configured app, waits 5 seconds, writes `logs/runs/<run_id>.json`, and quits the driver.

## Run One Collection

Dry-run:

```powershell
appcollector run smoke_android_feed
```

Real Appium run:

```powershell
appcollector run smoke_android_feed --no-dry-run
```

Each run writes metadata to `logs/runs/<run_id>.json`.

## Safety Scope

Flows are limited to browsing-style app-level interactions such as passive waiting, safe taps, back navigation, and feed scrolling. The framework intentionally avoids sending messages, liking, commenting, purchasing, following, sharing, or bypassing verification screens. For real device operations, flows should prefer Appium element locators and use relative coordinates only as a fallback.
