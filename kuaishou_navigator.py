from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
import time
from typing import Callable
import xml.etree.ElementTree as ET

from mobile_app_installer import AndroidAppInstaller, AppInstallError, KNOWN_APPS


Runner = Callable[..., subprocess.CompletedProcess]
Sleeper = Callable[[float], None]

KUAISHOU_HOME_ACTIVITY = "com.smile.gifmaker/com.yxcorp.gifshow.HomeActivity"
KUAISHOU_SEARCH_ACTIVITY = "com.smile.gifmaker/com.yxcorp.plugin.search.SearchActivity"
KUAISHOU_SEARCH_TAP = (1186, 223)
KUAISHOU_LIVE_TAB_TAP = (246, 366)
KUAISHOU_FIRST_LIVE_RESULT_TAP = (420, 960)
KUAISHOU_LIVE_ENTRY_POPUP_CLOSE_TAP = (930, 1030)
KUAISHOU_UI_DUMP_PATH = "/sdcard/kuaishou_nav.xml"
KUAISHOU_CAPTURE_PATH = "/sdcard/kuaishou_capture.png"
KUAISHOU_EDITOR_ID = "com.smile.gifmaker:id/editor"
KUAISHOU_SEARCH_RESULT_TEXT_ID = "com.smile.gifmaker:id/search_result_text"
KUAISHOU_CLEAR_ID = "com.smile.gifmaker:id/clear_layout"
KUAISHOU_SEARCH_BUTTON_ID = "com.smile.gifmaker:id/right_tv"
KUAISHOU_HOME_SEARCH_BUTTON_ID = "com.smile.gifmaker:id/search_btn"
KUAISHOU_TEEN_MODE_DISMISS_ID = "com.smile.gifmaker:id/positive"
KUAISHOU_SEARCH_GROUP_WEBVIEW_ID = "com.smile.gifmaker:id/search_web_view"
KUAISHOU_SEARCH_GROUP_BACK_ID = "com.smile.gifmaker:id/left_btn"
KUAISHOU_SEARCH_RESULTS_ROOT_ID = "com.smile.gifmaker:id/search_result_view"
KUAISHOU_SEARCH_RESULTS_TAB_ID = "com.smile.gifmaker:id/tab_container"
KUAISHOU_SEARCH_RESULTS_VIEW_PAGER_ID = "com.smile.gifmaker:id/view_pager"
KUAISHOU_HOME_ROOT_ID = "com.smile.gifmaker:id/home_activity_root"
ADB_KEYBOARD_IME = "com.android.adbkeyboard/.AdbIME"
ADB_KEYBOARD_B64_ACTION = "ADB_INPUT_B64"
TRANSIENT_ADB_ERRORS = (
    "daemon not running",
    "cannot connect to daemon",
    "adb server didn't ack",
    "device '",
)
UI_DUMP_SUCCESS_MARKERS = (
    "ui hierchary dumped to:",
    "ui hierarchy dumped to:",
)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
KUAISHOU_LAUNCH_SETTLE_SECONDS = 0.5
KUAISHOU_SEARCH_TAP_SETTLE_SECONDS = 0.5


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
        command_timeout_seconds: float = 15.0,
        trace_dir: str | Path | None = None,
    ) -> None:
        self.serial = serial
        self.adb_path = adb_path
        self.runner = runner or subprocess.run
        self.sleeper = sleeper or time.sleep
        self.command_timeout_seconds = command_timeout_seconds
        self.trace_dir = Path(trace_dir) if trace_dir else None
        if self.trace_dir is not None:
            self.trace_dir.mkdir(parents=True, exist_ok=True)
            self.trace_file = self.trace_dir / "trace.jsonl"
        else:
            self.trace_file = None
        self.installer = installer or AndroidAppInstaller(
            serial=serial,
            adb_path=adb_path,
            runner=self.runner,
            sleeper=self.sleeper,
        )

    def _trace(self, event: str, **payload: object) -> None:
        if self.trace_file is None:
            return
        sanitized: dict[str, object] = {
            "ts": round(time.time(), 3),
            "event": event,
        }
        for key, value in payload.items():
            if isinstance(value, Path):
                sanitized[key] = str(value)
            else:
                sanitized[key] = value
        with self.trace_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(sanitized, ensure_ascii=False) + "\n")

    def _summarize_ui_state(self, ui_xml: str) -> dict[str, object]:
        root = ET.fromstring(ui_xml)
        resource_ids: list[str] = []
        seen: set[str] = set()
        for node in root.iter("node"):
            resource_id = node.attrib.get("resource-id") or ""
            if not resource_id or resource_id in seen:
                continue
            seen.add(resource_id)
            resource_ids.append(resource_id)
            if len(resource_ids) == 20:
                break
        return {
            "has_search_editor": self._find_search_input_node(ui_xml) is not None,
            "has_search_submit": self.maybe_find_node(ui_xml, KUAISHOU_SEARCH_BUTTON_ID) is not None,
            "has_home_search": self.maybe_find_node(ui_xml, KUAISHOU_HOME_SEARCH_BUTTON_ID) is not None,
            "has_teen_prompt": self.maybe_find_node(ui_xml, KUAISHOU_TEEN_MODE_DISMISS_ID) is not None,
            "has_search_results_surface": self._is_search_results_page(ui_xml),
            "resource_ids": resource_ids,
        }

    def _trace_ui_state(self, label: str, ui_xml: str) -> None:
        self._trace("ui_state", label=label, **self._summarize_ui_state(ui_xml))

    @staticmethod
    def _decode_output(value: str | bytes | None) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="ignore")
        return value

    @classmethod
    def _is_transient_adb_error(cls, result: subprocess.CompletedProcess) -> bool:
        if result.returncode == 0:
            return False
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
        retry_delay_seconds: float = 0.0,
        timeout_seconds: float | None = None,
        accept_partial_bytes_prefix: bytes | None = None,
    ) -> subprocess.CompletedProcess:
        last_result: subprocess.CompletedProcess | None = None
        timeout = self.command_timeout_seconds if timeout_seconds is None else timeout_seconds
        for attempt in range(retries + 1):
            command = self._build_command(*args)
            self._trace(
                "adb_command_start",
                command=command,
                attempt=attempt + 1,
                retries=retries,
                timeout=timeout,
                text=text,
            )
            try:
                last_result = self.runner(
                    command,
                    capture_output=True,
                    text=text,
                    check=False,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired as exc:
                self._trace(
                    "adb_command_timeout",
                    command=command,
                    attempt=attempt + 1,
                    timeout=timeout,
                )
                stderr = exc.stderr
                if stderr is None:
                    stderr = f"Command timed out after {timeout:.1f}s"
                elif isinstance(stderr, bytes):
                    stderr = stderr.decode("utf-8", errors="ignore")
                stdout: str | bytes
                if exc.stdout is None:
                    stdout = b"" if not text else ""
                else:
                    stdout = exc.stdout
                last_result = subprocess.CompletedProcess(
                    command,
                    returncode=-15,
                    stdout=stdout,
                    stderr=stderr,
                )
            self._trace(
                "adb_command_result",
                command=command,
                attempt=attempt + 1,
                returncode=last_result.returncode,
                stdout_preview=self._decode_output(last_result.stdout)[:200],
                stderr_preview=self._decode_output(last_result.stderr)[:200],
            )
            if accept_partial_bytes_prefix is not None:
                payload = last_result.stdout or b""
                if isinstance(payload, str):
                    payload = payload.encode()
                if payload.startswith(accept_partial_bytes_prefix):
                    return last_result
            if not self._is_transient_adb_error(last_result) or attempt == retries:
                return last_result
            wait_command = self._build_command("wait-for-device")
            wait_result = self.runner(
                wait_command,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
            self._trace(
                "adb_wait_for_device",
                command=wait_command,
                attempt=attempt + 1,
                returncode=wait_result.returncode,
                stdout_preview=self._decode_output(wait_result.stdout)[:200],
                stderr_preview=self._decode_output(wait_result.stderr)[:200],
            )
            if wait_result.returncode != 0 and attempt == retries:
                return wait_result
            self.sleeper(retry_delay_seconds)
        return last_result  # pragma: no cover

    @staticmethod
    def _parse_bounds(raw_bounds: str) -> tuple[int, int, int, int]:
        match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", raw_bounds)
        if not match:
            raise KuaishouNavigationError(f"Invalid bounds: {raw_bounds}")
        return tuple(int(value) for value in match.groups())  # type: ignore[return-value]

    def dump_ui_xml(self) -> str:
        max_attempts = 4
        for attempt in range(max_attempts):
            dump_result = self._run("shell", "uiautomator", "dump", KUAISHOU_UI_DUMP_PATH, retries=0)
            dump_output = self._decode_output(dump_result.stdout).lower()
            dump_succeeded = any(marker in dump_output for marker in UI_DUMP_SUCCESS_MARKERS)
            self._trace(
                "dump_ui_xml.dump",
                attempt=attempt + 1,
                returncode=dump_result.returncode,
                stdout=self._decode_output(dump_result.stdout)[:240],
                stderr=self._decode_output(dump_result.stderr)[:240],
            )
            if dump_result.returncode != 0 and not dump_succeeded and not self._is_transient_adb_error(dump_result):
                raise KuaishouNavigationError(self._decode_output(dump_result.stderr) or "Failed to dump current UI")
            self.sleeper(0.5)
            result = self._run("shell", "cat", KUAISHOU_UI_DUMP_PATH)
            self._trace(
                "dump_ui_xml.cat",
                attempt=attempt + 1,
                returncode=result.returncode,
                stdout=self._decode_output(result.stdout)[:240],
                stderr=self._decode_output(result.stderr)[:240],
            )
            if result.returncode != 0:
                raise KuaishouNavigationError(self._decode_output(result.stderr) or "Failed to read dumped UI XML")
            ui_xml = self._decode_output(result.stdout).strip()
            if ui_xml.startswith("<?xml"):
                return ui_xml
            if attempt == max_attempts - 1:
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

    def _find_search_input_node(self, ui_xml: str) -> UiNode | None:
        return self.maybe_find_node(ui_xml, KUAISHOU_EDITOR_ID) or self.maybe_find_node(
            ui_xml,
            KUAISHOU_SEARCH_RESULT_TEXT_ID,
        )

    def _current_search_text(self, ui_xml: str) -> str:
        node = self._find_search_input_node(ui_xml)
        if node is None:
            return ""
        return node.text

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

    def list_input_methods(self) -> str:
        result = self._run("shell", "ime", "list", "-a")
        if result.returncode != 0:
            raise KuaishouNavigationError(self._decode_output(result.stderr) or "Failed to list input methods")
        return self._decode_output(result.stdout)

    def get_default_input_method(self) -> str:
        result = self._run("shell", "settings", "get", "secure", "default_input_method")
        if result.returncode != 0:
            raise KuaishouNavigationError(
                self._decode_output(result.stderr) or "Failed to get current default input method"
            )
        return self._decode_output(result.stdout).strip()

    def set_input_method(self, ime_id: str, *, enable: bool = False) -> None:
        if enable:
            enable_result = self._run("shell", "ime", "enable", ime_id)
            if enable_result.returncode != 0:
                raise KuaishouNavigationError(
                    self._decode_output(enable_result.stderr) or f"Failed to enable input method {ime_id}"
                )
        result = self._run("shell", "ime", "set", ime_id)
        if result.returncode != 0:
            raise KuaishouNavigationError(
                self._decode_output(result.stderr) or f"Failed to switch input method to {ime_id}"
            )

    def input_text_with_adb_keyboard(self, value: str) -> None:
        current_ime = self.get_default_input_method()
        restore_ime = current_ime if current_ime and current_ime != ADB_KEYBOARD_IME else None
        if restore_ime is not None:
            self.set_input_method(ADB_KEYBOARD_IME, enable=True)
        try:
            payload = base64.b64encode(value.encode("utf-8")).decode("ascii")
            result = self._run(
                "shell",
                "am",
                "broadcast",
                "-a",
                ADB_KEYBOARD_B64_ACTION,
                "--es",
                "msg",
                payload,
            )
            if result.returncode != 0:
                raise KuaishouNavigationError(
                    self._decode_output(result.stderr) or "Failed to broadcast unicode text via ADBKeyBoard"
                )
        finally:
            if restore_ime is not None:
                self.set_input_method(restore_ime)

    def input_keyword(self, keyword: str, pinyin: str) -> str:
        ime_list = self.list_input_methods()
        if ADB_KEYBOARD_IME in ime_list:
            self._trace("input_keyword.adb_keyboard", keyword=keyword)
            try:
                self.input_text_with_adb_keyboard(keyword)
                return "adb_keyboard"
            except KuaishouNavigationError as exc:
                self._trace("input_keyword.adb_keyboard_failed", keyword=keyword, error=str(exc))
        self._trace("input_keyword.pinyin", keyword=keyword, pinyin=pinyin)
        self.input_text(pinyin)
        self.sleeper(0.5)
        self.keyevent(62)
        return "pinyin"

    def start_search_activity(self) -> None:
        result = self._run("shell", "am", "start", "-W", "-n", KUAISHOU_SEARCH_ACTIVITY)
        if result.returncode != 0:
            raise KuaishouNavigationError(self._decode_output(result.stderr) or "Failed to launch 快手搜索页")

    def force_stop_app(self, package_name: str) -> None:
        result = self._run("shell", "am", "force-stop", package_name)
        if result.returncode != 0:
            raise KuaishouNavigationError(self._decode_output(result.stderr) or f"Failed to force-stop {package_name}")

    def capture_screen(self, destination: str | Path) -> Path:
        target = Path(destination)
        for attempt in range(3):
            direct_result = self._run(
                "exec-out",
                "screencap",
                "-p",
                text=False,
                retries=5,
                retry_delay_seconds=2.0,
                accept_partial_bytes_prefix=PNG_SIGNATURE,
            )
            payload = direct_result.stdout or b""
            if isinstance(payload, str):
                payload = payload.encode()
            if payload:
                target.write_bytes(payload)
                return target
            if attempt < 2:
                self.sleeper(0.5)
        return self.capture_screen_via_device_file(destination)

    def capture_screen_via_device_file(self, destination: str | Path) -> Path:
        target = Path(destination)
        capture_result = self._run(
            "shell",
            "screencap",
            "-p",
            KUAISHOU_CAPTURE_PATH,
            retries=5,
            retry_delay_seconds=2.0,
        )
        if capture_result.returncode != 0 and not self._device_file_exists(KUAISHOU_CAPTURE_PATH):
            raise KuaishouNavigationError(self._decode_output(capture_result.stderr) or "Fallback screenshot failed")
        read_result = self._run(
            "exec-out",
            "cat",
            KUAISHOU_CAPTURE_PATH,
            text=False,
            retries=5,
            retry_delay_seconds=2.0,
            accept_partial_bytes_prefix=PNG_SIGNATURE,
        )
        payload = read_result.stdout or b""
        if isinstance(payload, str):
            payload = payload.encode()
        if read_result.returncode != 0 or not payload:
            raise KuaishouNavigationError(
                self._decode_output(read_result.stderr) or "Fallback screenshot read failed"
            )
        target.write_bytes(payload)
        self._run("shell", "rm", "-f", KUAISHOU_CAPTURE_PATH, retries=0)
        return target

    def _device_file_exists(self, path: str) -> bool:
        result = self._run("shell", "ls", "-l", path, retries=2, retry_delay_seconds=1.0)
        return result.returncode == 0 and bool(self._decode_output(result.stdout).strip())

    def launch_app_with_install_fallback(self) -> None:
        package_name = KNOWN_APPS["kuaishou"].package_name
        try:
            self.installer.launch_app(package_name)
            return
        except AppInstallError as exc:
            self._trace("launch_app_fallback_to_install", error=str(exc))
        self.installer.ensure_app(KNOWN_APPS["kuaishou"], launch_after_install=False)
        self.installer.launch_app(package_name)

    def open_search(self, destination: str | Path) -> Path:
        self.launch_app_with_install_fallback()
        self.sleeper(KUAISHOU_LAUNCH_SETTLE_SECONDS)
        activity = self.current_activity()
        if activity != KUAISHOU_HOME_ACTIVITY:
            raise KuaishouNavigationError(f"Expected 快手首页, got {activity}")
        self.tap(*KUAISHOU_SEARCH_TAP)
        self.sleeper(KUAISHOU_SEARCH_TAP_SETTLE_SECONDS)
        return self.capture_screen(destination)

    def _is_search_page(self, ui_xml: str) -> bool:
        return not self._is_search_results_page(ui_xml) and self._find_search_input_node(ui_xml) is not None and self.maybe_find_node(
            ui_xml,
            KUAISHOU_SEARCH_BUTTON_ID,
        ) is not None

    def _is_search_group_result_page(self, ui_xml: str) -> bool:
        return self.maybe_find_node(ui_xml, KUAISHOU_SEARCH_GROUP_WEBVIEW_ID) is not None and self.maybe_find_node(
            ui_xml,
            KUAISHOU_SEARCH_GROUP_BACK_ID,
        ) is not None

    def _is_search_results_page(self, ui_xml: str) -> bool:
        return (
            self.maybe_find_node(ui_xml, KUAISHOU_SEARCH_RESULT_TEXT_ID) is not None
            and self.maybe_find_node(ui_xml, KUAISHOU_SEARCH_GROUP_WEBVIEW_ID) is not None
            and (
                self.maybe_find_node(ui_xml, KUAISHOU_SEARCH_RESULTS_ROOT_ID) is not None
                or self.maybe_find_node(ui_xml, KUAISHOU_SEARCH_RESULTS_TAB_ID) is not None
                or self.maybe_find_node(ui_xml, KUAISHOU_SEARCH_RESULTS_VIEW_PAGER_ID) is not None
            )
        )

    def _is_home_feed_page(self, ui_xml: str) -> bool:
        return self.maybe_find_node(ui_xml, KUAISHOU_HOME_ROOT_ID) is not None

    def _recover_from_search_group_result(self) -> str:
        package_name = KNOWN_APPS["kuaishou"].package_name
        self._trace("ensure_search_page.force_stop_relaunch", package_name=package_name)
        self.force_stop_app(package_name)
        self.sleeper(1)
        self.installer.launch_app(package_name)
        self.sleeper(3)
        ui_xml = self.dump_ui_xml()
        self._trace_ui_state("after_force_stop_relaunch", ui_xml)
        return ui_xml

    def _recover_from_search_results_page(self, ui_xml: str) -> str:
        query_node = self.find_node(ui_xml, KUAISHOU_SEARCH_RESULT_TEXT_ID)
        self._trace("ensure_search_page.tap_result_query", center=query_node.center)
        self.tap(*query_node.center)
        self.sleeper(1)
        recovered_ui = self.dump_ui_xml()
        self._trace_ui_state("after_tap_result_query", recovered_ui)
        return recovered_ui

    def ensure_search_page_ui(self) -> str:
        self.installer.ensure_app(KNOWN_APPS["kuaishou"], launch_after_install=True)
        self.sleeper(2)
        try:
            ui_xml = self.dump_ui_xml()
        except KuaishouNavigationError as exc:
            self._trace("ensure_search_page.initial_dump_failed", error=str(exc))
            activity = self.current_activity()
            self._trace("ensure_search_page.activity_after_initial_dump_failed", activity=activity)
            if activity == KUAISHOU_HOME_ACTIVITY:
                self._trace("ensure_search_page.tap_home_search_without_ui_dump", center=KUAISHOU_SEARCH_TAP)
                self.tap(*KUAISHOU_SEARCH_TAP)
                self.sleeper(2)
                ui_xml = self.dump_ui_xml()
                self._trace_ui_state("after_tap_home_search_without_ui_dump", ui_xml)
                if self._is_search_page(ui_xml):
                    return ui_xml
            raise
        self._trace_ui_state("launch", ui_xml)
        if self._is_search_page(ui_xml):
            return ui_xml

        if self._is_search_group_result_page(ui_xml):
            ui_xml = self._recover_from_search_group_result()
            if self._is_search_page(ui_xml):
                return ui_xml

        if self._is_search_results_page(ui_xml):
            ui_xml = self._recover_from_search_results_page(ui_xml)
            if self._is_search_page(ui_xml):
                return ui_xml

        dismiss_node = self.maybe_find_node(ui_xml, KUAISHOU_TEEN_MODE_DISMISS_ID)
        if dismiss_node is not None:
            self._trace("ensure_search_page.dismiss_teen_prompt", center=dismiss_node.center)
            self.tap(*dismiss_node.center)
            self.sleeper(1)
            ui_xml = self.dump_ui_xml()
            self._trace_ui_state("after_dismiss_teen_prompt", ui_xml)
            if self._is_search_results_page(ui_xml):
                ui_xml = self._recover_from_search_results_page(ui_xml)
            if self._is_search_page(ui_xml):
                return ui_xml

        self._trace("ensure_search_page.start_search_activity", activity=KUAISHOU_SEARCH_ACTIVITY)
        try:
            self.start_search_activity()
            self.sleeper(2)
            ui_xml = self.dump_ui_xml()
            self._trace_ui_state("after_start_search_activity", ui_xml)
            if self._is_search_results_page(ui_xml):
                ui_xml = self._recover_from_search_results_page(ui_xml)
            if self._is_search_page(ui_xml):
                return ui_xml
        except KuaishouNavigationError as exc:
            self._trace("ensure_search_page.start_search_activity_failed", error=str(exc))

        search_btn = self.maybe_find_node(ui_xml, KUAISHOU_HOME_SEARCH_BUTTON_ID)
        if search_btn is not None:
            self._trace("ensure_search_page.tap_home_search", center=search_btn.center)
            self.tap(*search_btn.center)
            self.sleeper(2)
            ui_xml = self.dump_ui_xml()
            self._trace_ui_state("after_tap_home_search", ui_xml)
            if self._is_search_results_page(ui_xml):
                ui_xml = self._recover_from_search_results_page(ui_xml)
            if self._is_search_page(ui_xml):
                return ui_xml

        if self._is_home_feed_page(ui_xml):
            self._trace("ensure_search_page.tap_home_search_hotspot", center=KUAISHOU_SEARCH_TAP)
            self.tap(*KUAISHOU_SEARCH_TAP)
            self.sleeper(2)
            ui_xml = self.dump_ui_xml()
            self._trace_ui_state("after_tap_home_search_hotspot", ui_xml)
            if self._is_search_results_page(ui_xml):
                ui_xml = self._recover_from_search_results_page(ui_xml)
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
        clear_node = self.maybe_find_node(ui_xml, KUAISHOU_CLEAR_ID)
        editor_node = self._find_search_input_node(ui_xml)
        if editor_node is None:
            raise KuaishouNavigationError("Could not find search input node on the current 快手 page")
        search_button = self.find_node(ui_xml, KUAISHOU_SEARCH_BUTTON_ID)
        self._trace(
            "search_keyword.submit",
            keyword=keyword,
            clear_center=clear_node.center if clear_node is not None else None,
            editor_center=editor_node.center,
            search_center=search_button.center,
            destination=destination,
        )

        current_keyword = editor_node.text.strip()
        if current_keyword == keyword.strip():
            self._trace("search_keyword.skip_retype", keyword=keyword)
        else:
            if clear_node is not None:
                self.tap(*clear_node.center)
                self.sleeper(0.5)
            if editor_node.resource_id != KUAISHOU_EDITOR_ID:
                self.tap(*editor_node.center)
                self.sleeper(0.5)
            input_strategy = self.input_keyword(keyword=keyword, pinyin=pinyin)
            if input_strategy == "adb_keyboard":
                verified_ui = self.dump_ui_xml()
                observed_keyword = self._current_search_text(verified_ui)
                if observed_keyword != keyword:
                    self._trace(
                        "search_keyword.retry_with_pinyin",
                        expected=keyword,
                        observed=observed_keyword,
                    )
                    retry_clear_node = self.maybe_find_node(verified_ui, KUAISHOU_CLEAR_ID)
                    if retry_clear_node is not None:
                        self.tap(*retry_clear_node.center)
                        self.sleeper(0.5)
                    self.input_text(pinyin)
                    self.sleeper(0.5)
                    self.keyevent(62)
        self.sleeper(0.5)
        self.tap(*search_button.center)
        self.sleeper(2)
        return self.capture_screen(destination)

    def _submit_search_on_search_activity_without_ui(
        self,
        keyword: str,
        pinyin: str,
        destination: str | Path,
    ) -> Path:
        self._trace(
            "search_keyword.activity_only_submit",
            keyword=keyword,
            pinyin=pinyin,
            destination=destination,
        )
        self.input_keyword(keyword=keyword, pinyin=pinyin)
        self.sleeper(0.5)
        self.keyevent(66)
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
        self._trace("search_keyword.start", keyword=keyword, pinyin=pinyin, destination=destination)
        try:
            ui_xml = self.ensure_search_page_ui()
            return self._submit_search_on_search_page(ui_xml, keyword=keyword, pinyin=pinyin, destination=destination)
        except KuaishouNavigationError as exc:
            self._trace("search_keyword.error", error=str(exc))
            try:
                activity = self.current_activity()
            except KuaishouNavigationError:
                raise
            self._trace("search_keyword.error_activity", activity=activity)
            if activity == KUAISHOU_SEARCH_ACTIVITY:
                return self._submit_search_on_search_activity_without_ui(
                    keyword=keyword,
                    pinyin=pinyin,
                    destination=destination,
                )
            raise

    def open_live_results(self, destination: str | Path) -> Path:
        self._trace("open_live_results_start", destination=destination)
        self.tap(*KUAISHOU_LIVE_TAB_TAP)
        self.sleeper(2)
        self._trace("open_live_results_complete", destination=destination)
        return self.capture_screen(destination)

    def enter_first_live_room(self, destination: str | Path) -> Path:
        self._trace("enter_first_live_room_start", destination=destination)
        self.tap(*KUAISHOU_FIRST_LIVE_RESULT_TAP)
        self.sleeper(3)
        self._trace("dismiss_live_entry_popup", center=KUAISHOU_LIVE_ENTRY_POPUP_CLOSE_TAP)
        self.tap(*KUAISHOU_LIVE_ENTRY_POPUP_CLOSE_TAP)
        self.sleeper(1)
        self._trace("enter_first_live_room_complete", destination=destination)
        return self.capture_screen(destination)

    def search_and_enter_first_live_room(
        self,
        keyword: str,
        pinyin: str,
        destination: str | Path,
    ) -> Path:
        self.search_keyword(keyword=keyword, pinyin=pinyin, destination=destination)
        self.open_live_results(destination)
        return self.enter_first_live_room(destination)


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
    parser.add_argument(
        "--trace-dir",
        help="Optional directory for structured diagnostic traces, for example /tmp/kuaishou-trace.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    navigator = KuaishouNavigator(serial=args.serial, trace_dir=args.trace_dir)
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
