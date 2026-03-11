from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import time
from typing import Callable
import xml.etree.ElementTree as ET

from mobile_app_installer import AndroidAppInstaller, KNOWN_APPS


Runner = Callable[..., subprocess.CompletedProcess]
Sleeper = Callable[[float], None]

KUAISHOU_HOME_ACTIVITY = "com.smile.gifmaker/com.yxcorp.gifshow.HomeActivity"
KUAISHOU_SEARCH_TAP = (1188, 212)
KUAISHOU_UI_DUMP_PATH = "/sdcard/kuaishou_nav.xml"
KUAISHOU_EDITOR_ID = "com.smile.gifmaker:id/editor"
KUAISHOU_CLEAR_ID = "com.smile.gifmaker:id/clear_layout"
KUAISHOU_SEARCH_BUTTON_ID = "com.smile.gifmaker:id/right_tv"
KUAISHOU_HOME_SEARCH_BUTTON_ID = "com.smile.gifmaker:id/search_btn"
KUAISHOU_TEEN_MODE_DISMISS_ID = "com.smile.gifmaker:id/positive"
TRANSIENT_ADB_ERRORS = (
    "daemon not running",
    "cannot connect to daemon",
    "adb server didn't ack",
)
UI_DUMP_SUCCESS_MARKERS = (
    "ui hierchary dumped to:",
    "ui hierarchy dumped to:",
)


class KuaishouNavigationError(RuntimeError):
    """Raised when the navigator cannot reach the expected Kuaishou page."""


@dataclass(frozen=True)
class UiNode:
    resource_id: str
    text: str
    bounds: tuple[int, int, int, int]

    @property
    def center(self) -> tuple[int, int]:
        left, top, right, bottom = self.bounds
        return ((left + right) // 2, (top + bottom) // 2)


class KuaishouNavigator:
    def __init__(
        self,
        serial: str | None = None,
        installer: AndroidAppInstaller | None = None,
        adb_path: str = "adb",
        runner: Runner | None = None,
        sleeper: Sleeper | None = None,
    ) -> None:
        self.serial = serial
        self.adb_path = adb_path
        self.runner = runner or subprocess.run
        self.sleeper = sleeper or time.sleep
        self.installer = installer or AndroidAppInstaller(
            serial=serial,
            adb_path=adb_path,
            runner=self.runner,
            sleeper=self.sleeper,
        )

    @staticmethod
    def _decode_output(value: str | bytes | None) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="ignore")
        return value

    @classmethod
    def _is_transient_adb_error(cls, result: subprocess.CompletedProcess) -> bool:
        combined_output = (cls._decode_output(result.stdout) + "\n" + cls._decode_output(result.stderr)).lower()
        if any(marker in combined_output for marker in UI_DUMP_SUCCESS_MARKERS):
            return False
        return result.returncode == -15 or any(marker in combined_output for marker in TRANSIENT_ADB_ERRORS)

    def _build_command(self, *args: str) -> list[str]:
        command = [self.adb_path]
        if self.serial:
            command.extend(["-s", self.serial])
        command.extend(args)
        return command

    def _run(
        self,
        *args: str,
        text: bool = True,
        retries: int = 2,
        retry_delay_seconds: float = 1.0,
    ) -> subprocess.CompletedProcess:
        last_result: subprocess.CompletedProcess | None = None
        for attempt in range(retries + 1):
            last_result = self.runner(
                self._build_command(*args),
                capture_output=True,
                text=text,
                check=False,
            )
            if not self._is_transient_adb_error(last_result) or attempt == retries:
                return last_result
            self.sleeper(retry_delay_seconds)
        return last_result  # pragma: no cover

    @staticmethod
    def _parse_bounds(raw_bounds: str) -> tuple[int, int, int, int]:
        match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", raw_bounds)
        if not match:
            raise KuaishouNavigationError(f"Invalid bounds: {raw_bounds}")
        return tuple(int(value) for value in match.groups())  # type: ignore[return-value]

    def dump_ui_xml(self) -> str:
        for attempt in range(3):
            dump_result = self._run("shell", "uiautomator", "dump", KUAISHOU_UI_DUMP_PATH, retries=0)
            dump_output = self._decode_output(dump_result.stdout).lower()
            dump_succeeded = any(marker in dump_output for marker in UI_DUMP_SUCCESS_MARKERS)
            if dump_result.returncode != 0 and not dump_succeeded and not self._is_transient_adb_error(dump_result):
                raise KuaishouNavigationError(self._decode_output(dump_result.stderr) or "Failed to dump current UI")
            self.sleeper(0.5)
            result = self._run("shell", "cat", KUAISHOU_UI_DUMP_PATH)
            if result.returncode != 0:
                raise KuaishouNavigationError(self._decode_output(result.stderr) or "Failed to read dumped UI XML")
            ui_xml = self._decode_output(result.stdout).strip()
            if ui_xml.startswith("<?xml"):
                return ui_xml
            if attempt == 2:
                raise KuaishouNavigationError("uiautomator dump did not return XML")
            self.sleeper(0.5)
        raise KuaishouNavigationError("uiautomator dump did not return XML")  # pragma: no cover

    def find_node(self, ui_xml: str, resource_id: str) -> UiNode:
        root = ET.fromstring(ui_xml)
        for node in root.iter("node"):
            if node.attrib.get("resource-id") != resource_id:
                continue
            bounds = node.attrib.get("bounds")
            if not bounds:
                continue
            return UiNode(
                resource_id=resource_id,
                text=node.attrib.get("text", ""),
                bounds=self._parse_bounds(bounds),
            )
        raise KuaishouNavigationError(f"Could not find resource-id={resource_id}")

    def maybe_find_node(self, ui_xml: str, resource_id: str) -> UiNode | None:
        try:
            return self.find_node(ui_xml, resource_id)
        except KuaishouNavigationError:
            return None

    def current_activity(self) -> str:
        result = self._run("shell", "dumpsys", "activity", "activities")
        output = self._decode_output(result.stdout) + "\n" + self._decode_output(result.stderr)
        match = re.search(r"ResumedActivity: ActivityRecord\{[^ ]+ u\d+ ([^ ]+)", output)
        if not match:
            match = re.search(r"topResumedActivity=ActivityRecord\{[^ ]+ u\d+ ([^ ]+)", output)
        if not match:
            raise KuaishouNavigationError("Could not determine current foreground activity")
        return match.group(1)

    def tap(self, x: int, y: int) -> None:
        result = self._run("shell", "input", "tap", str(x), str(y))
        if result.returncode != 0:
            raise KuaishouNavigationError(self._decode_output(result.stderr) or f"Failed to tap {x},{y}")

    def input_text(self, value: str) -> None:
        result = self._run("shell", "input", "text", value)
        if result.returncode != 0:
            raise KuaishouNavigationError(self._decode_output(result.stderr) or f"Failed to input text: {value}")

    def keyevent(self, keycode: int) -> None:
        result = self._run("shell", "input", "keyevent", str(keycode))
        if result.returncode != 0:
            raise KuaishouNavigationError(self._decode_output(result.stderr) or f"Failed to send keyevent {keycode}")

    def capture_screen(self, destination: str | Path) -> Path:
        target = Path(destination)
        result = self._run("exec-out", "screencap", "-p", text=False)
        if result.returncode != 0:
            raise KuaishouNavigationError(self._decode_output(result.stderr) or "Screenshot failed")
        payload = result.stdout or b""
        if isinstance(payload, str):
            payload = payload.encode()
        target.write_bytes(payload)
        return target

    def open_search(self, destination: str | Path) -> Path:
        self.installer.ensure_app(KNOWN_APPS["kuaishou"], launch_after_install=True)
        self.sleeper(2)
        activity = self.current_activity()
        if activity != KUAISHOU_HOME_ACTIVITY:
            raise KuaishouNavigationError(f"Expected 快手首页, got {activity}")
        self.tap(*KUAISHOU_SEARCH_TAP)
        self.sleeper(2)
        return self.capture_screen(destination)

    def _is_search_page(self, ui_xml: str) -> bool:
        return self.maybe_find_node(ui_xml, KUAISHOU_EDITOR_ID) is not None and self.maybe_find_node(
            ui_xml,
            KUAISHOU_SEARCH_BUTTON_ID,
        ) is not None

    def ensure_search_page_ui(self) -> str:
        self.installer.ensure_app(KNOWN_APPS["kuaishou"], launch_after_install=True)
        self.sleeper(2)
        ui_xml = self.dump_ui_xml()
        if self._is_search_page(ui_xml):
            return ui_xml

        dismiss_node = self.maybe_find_node(ui_xml, KUAISHOU_TEEN_MODE_DISMISS_ID)
        if dismiss_node is not None:
            self.tap(*dismiss_node.center)
            self.sleeper(1)
            ui_xml = self.dump_ui_xml()
            if self._is_search_page(ui_xml):
                return ui_xml

        search_btn = self.maybe_find_node(ui_xml, KUAISHOU_HOME_SEARCH_BUTTON_ID)
        if search_btn is not None:
            self.tap(*search_btn.center)
            self.sleeper(2)
            ui_xml = self.dump_ui_xml()
            if self._is_search_page(ui_xml):
                return ui_xml

        raise KuaishouNavigationError("Could not reach 快手搜索页 from the current app state")

    def _submit_search_on_search_page(
        self,
        ui_xml: str,
        keyword: str,
        pinyin: str,
        destination: str | Path,
    ) -> Path:
        _ = keyword  # Reserved for future result-page assertions.
        clear_node = self.find_node(ui_xml, KUAISHOU_CLEAR_ID)
        editor_node = self.find_node(ui_xml, KUAISHOU_EDITOR_ID)
        search_button = self.find_node(ui_xml, KUAISHOU_SEARCH_BUTTON_ID)

        self.tap(*clear_node.center)
        self.sleeper(0.5)
        self.tap(*editor_node.center)
        self.sleeper(0.5)
        self.input_text(pinyin)
        self.sleeper(0.5)
        self.keyevent(62)
        self.sleeper(0.5)
        self.tap(*search_button.center)
        self.sleeper(2)
        return self.capture_screen(destination)

    def search_keyword_on_search_page(
        self,
        keyword: str,
        pinyin: str,
        destination: str | Path,
    ) -> Path:
        self.installer.ensure_app(KNOWN_APPS["kuaishou"], launch_after_install=True)
        self.sleeper(2)
        ui_xml = self.dump_ui_xml()
        return self._submit_search_on_search_page(ui_xml, keyword=keyword, pinyin=pinyin, destination=destination)

    def search_keyword(
        self,
        keyword: str,
        pinyin: str,
        destination: str | Path,
    ) -> Path:
        ui_xml = self.ensure_search_page_ui()
        return self._submit_search_on_search_page(ui_xml, keyword=keyword, pinyin=pinyin, destination=destination)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Open Kuaishou search and capture a screenshot.")
    parser.add_argument("--serial", help="ADB serial to target a specific device.")
    parser.add_argument(
        "--output",
        default="/tmp/kuaishou-search.png",
        help="Destination file for the captured screenshot.",
    )
    parser.add_argument("--query", help="Search keyword to submit on an already opened Kuaishou search page.")
    parser.add_argument(
        "--pinyin",
        help="Latin input used to compose the keyword with the current Chinese IME, for example zhibodaihuo.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    navigator = KuaishouNavigator(serial=args.serial)
    if args.query:
        if not args.pinyin:
            raise SystemExit("--query requires --pinyin")
        output = navigator.search_keyword(
            keyword=args.query,
            pinyin=args.pinyin,
            destination=args.output,
        )
    else:
        output = navigator.open_search(args.output)
    print(f"Kuaishou search screenshot saved to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
