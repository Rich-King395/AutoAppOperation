from typing import Any


ANDROID_PERMISSION_ALLOW_IDS = [
    "com.android.permissioncontroller:id/permission_allow_button",
    "com.android.permissioncontroller:id/permission_allow_foreground_only_button",
]


def dismiss_android_permissions(driver: Any) -> int:
    dismissed = 0
    for element_id in ANDROID_PERMISSION_ALLOW_IDS:
        elements = driver.find_elements("id", element_id)
        for element in elements:
            element.click()
            dismissed += 1
    return dismissed


def dismiss_known_popups(driver: Any) -> int:
    return dismiss_android_permissions(driver)
