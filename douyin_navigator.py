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

from mobile_app_installer import AndroidAppInstaller, KNOWN_APPS


Runner = Callable[..., subprocess.CompletedProcess]
Sleeper = Callable[[float], None]

DOUYIN_PRIVACY_CONSENT_TAP = (640, 2000)
DOUYIN_FEED_SWIPE_START = (640, 2300)
DOUYIN_FEED_SWIPE_END = (640, 1000)
DOUYIN_SEARCH_ICON_TAP = (1188, 223)
DOUYIN_SEARCH_FIELD_TAP = (620, 223)
DOUYIN_SEARCH_BUTTON_TAP = (1179, 223)
DOUYIN_LIVE_TAB_TAP = (640, 364)
DOUYIN_FIRST_LIVE_CARD_TAP = (430, 1310)
DOUYIN_UI_DUMP_PATH = "/sdcard/douyin_nav.xml"
DOUYIN_CAPTURE_PATH = "/sdcard/douyin_capture.png"
DOUYIN_SEARCH_INPUT_ID = "com.ss.android.ugc.aweme:id/et_search_kw"
DOUYIN_SEARCH_BUTTON_ID = "com.ss.android.ugc.aweme:id/4_s"
ANDROID_PERMISSION_CONTROLLER_PACKAGE = "com.android.permissioncontroller"
ADB_KEYBOARD_IME = "com.android.adbkeyboard/.AdbIME"
ADB_KEYBOARD_B64_ACTION = "ADB_INPUT_B64"
TRANSIENT_ADB_ERRORS = (
    "daemon not running",
    "cannot connect to daemon",
    "adb server didn't ack",
    "device '",
    "device offline",
)
UI_DUMP_SUCCESS_MARKERS = (
    "ui hierchary dumped to:",
    "ui hierarchy dumped to:",
)
DELETE_TEXT_BATCH_SIZE = 12


class DouyinNavigationError(RuntimeError):
    """Raised when the navigator cannot complete the expected Douyin action."""


@dataclass(frozen=True)
class UiNode:
    resource_id: str
    text: str
    bounds: tuple[int, int, int, int]

    @property
    def center(self) -> tuple[int, int]:
        left, top, right, bottom = self.bounds
        return ((left + right) // 2, (top + bottom) // 2)


class DouyinNavigator:
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

    def _build_command(self, *args: str) -> list[str]:
        command = [self.adb_path]
        if self.serial:
            command.extend(["-s", self.serial])
        command.extend(args)
        return command

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

    def _run(
        self,
        *args: str,
        text: bool = True,
        retries: int = 2,
        retry_delay_seconds: float = 1.0,
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
            wait_result = self.runner(
                self._build_command("wait-for-device"),
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
            self._trace(
                "adb_wait_for_device",
                command=self._build_command("wait-for-device"),
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
            raise DouyinNavigationError(f"Invalid bounds: {raw_bounds}")
        return tuple(int(value) for value in match.groups())  # type: ignore[return-value]

    def dump_ui_xml(self) -> str:
        max_attempts = 3
        for attempt in range(max_attempts):
            self._trace("dump_ui_xml_attempt", attempt=attempt + 1, max_attempts=max_attempts)
            dump_result = self._run("shell", "uiautomator", "dump", DOUYIN_UI_DUMP_PATH, retries=0)
            dump_output = self._decode_output(dump_result.stdout).lower()
            dump_succeeded = any(marker in dump_output for marker in UI_DUMP_SUCCESS_MARKERS)
            if dump_result.returncode != 0 and not dump_succeeded and not self._is_transient_adb_error(dump_result):
                raise DouyinNavigationError(self._decode_output(dump_result.stderr) or "Failed to dump Douyin UI")
            self.sleeper(0.5)
            read_result = self._run(
                "exec-out",
                "cat",
                DOUYIN_UI_DUMP_PATH,
                text=False,
                accept_partial_bytes_prefix=b"<?xml",
            )
            if read_result.returncode != 0:
                raise DouyinNavigationError(
                    self._decode_output(read_result.stderr) or "Failed to read dumped Douyin UI XML"
                )
            ui_xml = self._decode_output(read_result.stdout).strip()
            if ui_xml.startswith("<?xml"):
                self._trace(
                    "dump_ui_xml_success",
                    attempt=attempt + 1,
                    is_search_page=self.is_search_page(ui_xml),
                    is_permission_prompt=self.is_permission_prompt(ui_xml),
                    is_ended_live_room=self.is_ended_live_room(ui_xml),
                    current_search_text=self.current_search_text(ui_xml),
                )
                return ui_xml
            if attempt == max_attempts - 1:
                break
            self.sleeper(0.5)
        self._trace("dump_ui_xml_failed", max_attempts=max_attempts)
        raise DouyinNavigationError("uiautomator dump did not return XML for Douyin")

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
        raise DouyinNavigationError(f"Could not find resource-id={resource_id}")

    def maybe_find_node(self, ui_xml: str, resource_id: str) -> UiNode | None:
        try:
            return self.find_node(ui_xml, resource_id)
        except DouyinNavigationError:
            return None

    def maybe_find_text_node(self, ui_xml: str, text: str) -> UiNode | None:
        root = ET.fromstring(ui_xml)
        for node in root.iter("node"):
            if node.attrib.get("text") != text:
                continue
            bounds = node.attrib.get("bounds")
            if not bounds:
                continue
            return UiNode(
                resource_id=node.attrib.get("resource-id", ""),
                text=text,
                bounds=self._parse_bounds(bounds),
            )
        return None

    def maybe_find_content_desc_node(self, ui_xml: str, content_desc: str) -> UiNode | None:
        root = ET.fromstring(ui_xml)
        for node in root.iter("node"):
            if node.attrib.get("content-desc") != content_desc:
                continue
            bounds = node.attrib.get("bounds")
            if not bounds:
                continue
            return UiNode(
                resource_id=node.attrib.get("resource-id", ""),
                text=node.attrib.get("text", ""),
                bounds=self._parse_bounds(bounds),
            )
        return None

    def is_search_page(self, ui_xml: str) -> bool:
        return (
            self.maybe_find_node(ui_xml, DOUYIN_SEARCH_INPUT_ID) is not None
            and self.maybe_find_node(ui_xml, DOUYIN_SEARCH_BUTTON_ID) is not None
        )

    def is_permission_prompt(self, ui_xml: str) -> bool:
        return ANDROID_PERMISSION_CONTROLLER_PACKAGE in ui_xml and (
            "拒绝" in ui_xml or "仅在使用中允许" in ui_xml or "本次使用允许" in ui_xml
        )

    def is_ended_live_room(self, ui_xml: str) -> bool:
        return "直播已结束" in ui_xml and "关闭" in ui_xml

    def current_search_text(self, ui_xml: str) -> str:
        search_input = self.maybe_find_node(ui_xml, DOUYIN_SEARCH_INPUT_ID)
        if search_input is None:
            return ""
        return search_input.text

    def tap(self, x: int, y: int) -> None:
        result = self._run("shell", "input", "tap", str(x), str(y))
        if result.returncode != 0:
            raise DouyinNavigationError(self._decode_output(result.stderr) or f"Failed to tap {x},{y}")

    def tap_node(self, node: UiNode) -> None:
        self.tap(*node.center)

    def swipe(self, start: tuple[int, int], end: tuple[int, int], duration_ms: int) -> None:
        result = self._run(
            "shell",
            "input",
            "swipe",
            str(start[0]),
            str(start[1]),
            str(end[0]),
            str(end[1]),
            str(duration_ms),
        )
        if result.returncode != 0:
            raise DouyinNavigationError(self._decode_output(result.stderr) or "Failed to swipe Douyin feed")

    def capture_screen(self, destination: str | Path) -> Path:
        target = Path(destination)
        direct_result = self._run(
            "exec-out",
            "screencap",
            "-p",
            text=False,
            retries=5,
            retry_delay_seconds=2.0,
            accept_partial_bytes_prefix=b"\x89PNG",
        )
        direct_payload = direct_result.stdout or b""
        if isinstance(direct_payload, str):
            direct_payload = direct_payload.encode()
        if direct_payload.startswith(b"\x89PNG") or (direct_result.returncode == 0 and direct_payload):
            target.write_bytes(direct_payload)
            return target
        return self.capture_screen_via_device_file(destination)

    def capture_screen_via_device_file(self, destination: str | Path) -> Path:
        target = Path(destination)
        capture_result = self._run(
            "shell",
            "screencap",
            "-p",
            DOUYIN_CAPTURE_PATH,
            retries=5,
            retry_delay_seconds=2.0,
        )
        if capture_result.returncode != 0:
            raise DouyinNavigationError(self._decode_output(capture_result.stderr) or "Fallback screenshot failed")
        read_result = self._run(
            "exec-out",
            "cat",
            DOUYIN_CAPTURE_PATH,
            text=False,
            retries=5,
            retry_delay_seconds=2.0,
            accept_partial_bytes_prefix=b"\x89PNG",
        )
        payload = read_result.stdout or b""
        if isinstance(payload, str):
            payload = payload.encode()
        if read_result.returncode != 0 or not payload:
            raise DouyinNavigationError(self._decode_output(read_result.stderr) or "Fallback screenshot read failed")
        target.write_bytes(payload)
        self._run("shell", "rm", "-f", DOUYIN_CAPTURE_PATH, retries=0)
        return target

    def list_input_methods(self) -> str:
        result = self._run("shell", "ime", "list", "-a")
        if result.returncode != 0:
            raise DouyinNavigationError(self._decode_output(result.stderr) or "Failed to list input methods")
        return self._decode_output(result.stdout)

    def get_default_input_method(self) -> str:
        result = self._run("shell", "settings", "get", "secure", "default_input_method")
        if result.returncode != 0:
            raise DouyinNavigationError(
                self._decode_output(result.stderr) or "Failed to get current default input method"
            )
        return self._decode_output(result.stdout).strip()

    def set_input_method(self, ime_id: str, *, enable: bool = False) -> None:
        if enable:
            enable_result = self._run("shell", "ime", "enable", ime_id)
            if enable_result.returncode != 0:
                raise DouyinNavigationError(
                    self._decode_output(enable_result.stderr) or f"Failed to enable input method {ime_id}"
                )
        result = self._run("shell", "ime", "set", ime_id)
        if result.returncode != 0:
            raise DouyinNavigationError(
                self._decode_output(result.stderr) or f"Failed to switch input method to {ime_id}"
            )

    def input_text(self, value: str) -> None:
        result = self._run("shell", "input", "text", value)
        if result.returncode != 0:
            raise DouyinNavigationError(self._decode_output(result.stderr) or f"Failed to input text: {value}")

    def keyevent(self, keycode: int) -> None:
        result = self._run("shell", "input", "keyevent", str(keycode))
        if result.returncode != 0:
            raise DouyinNavigationError(self._decode_output(result.stderr) or f"Failed to send keyevent {keycode}")

    def delete_text(self, characters: int) -> None:
        if characters <= 0:
            return
        remaining = characters
        while remaining > 0:
            batch_size = min(remaining, DELETE_TEXT_BATCH_SIZE)
            result = self._run(
                "shell",
                "sh",
                "-c",
                f'i=0; while [ "$i" -lt {batch_size} ]; do input keyevent 67; i=$((i+1)); done',
            )
            if result.returncode != 0:
                raise DouyinNavigationError(
                    self._decode_output(result.stderr) or "Failed to clear existing search text"
                )
            remaining -= batch_size

    def clear_existing_search_text(self, ui_xml: str) -> None:
        current_ui = ui_xml
        for _ in range(3):
            search_input = self.find_node(current_ui, DOUYIN_SEARCH_INPUT_ID)
            existing = search_input.text.strip()
            if not existing:
                return
            self.tap_node(search_input)
            self.sleeper(0.2)
            self.delete_text(max(len(existing) + 2, 6))
            self.sleeper(0.2)
            current_ui = self.dump_ui_xml()

    def force_clear_search_text(self, characters: int = 32) -> None:
        self.delete_text(characters)

    def dismiss_permission_prompt_if_present(self, ui_xml: str) -> bool:
        if not self.is_permission_prompt(ui_xml):
            return False
        self._trace("permission_prompt_detected")
        for label in ("拒绝", "仅在使用中允许", "本次使用允许"):
            button = self.maybe_find_text_node(ui_xml, label)
            if button is None:
                continue
            self.tap_node(button)
            self.sleeper(0.5)
            self._trace("permission_prompt_dismissed", label=label)
            return True
        return False

    def dismiss_live_room_if_present(self, ui_xml: str) -> bool:
        if not self.is_ended_live_room(ui_xml):
            return False
        self._trace("ended_live_room_detected")
        close_button = self.maybe_find_content_desc_node(ui_xml, "关闭")
        if close_button is None:
            close_button = self.maybe_find_text_node(ui_xml, "关闭")
        if close_button is None:
            return False
        self.tap_node(close_button)
        self.sleeper(0.5)
        self._trace("ended_live_room_dismissed")
        return True

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
                raise DouyinNavigationError(
                    self._decode_output(result.stderr) or "Failed to broadcast unicode text via ADBKeyBoard"
                )
        finally:
            if restore_ime is not None:
                self.set_input_method(restore_ime)

    def input_keyword(self, keyword: str, pinyin: str) -> None:
        ime_list = self.list_input_methods()
        if ADB_KEYBOARD_IME in ime_list:
            try:
                self.input_text_with_adb_keyboard(keyword)
                return
            except DouyinNavigationError:
                pass
        self.input_text(pinyin)
        self.sleeper(0.5)
        self.keyevent(62)

    def _open_search_flow(self) -> None:
        self.installer.ensure_app(KNOWN_APPS["douyin"], launch_after_install=True)
        self.sleeper(2)
        try:
            self.dismiss_permission_prompt_if_present(self.dump_ui_xml())
        except DouyinNavigationError:
            pass
        self.tap(*DOUYIN_PRIVACY_CONSENT_TAP)
        self.sleeper(1)
        self.swipe(DOUYIN_FEED_SWIPE_START, DOUYIN_FEED_SWIPE_END, 250)
        self.sleeper(0.5)
        self.swipe(DOUYIN_FEED_SWIPE_START, DOUYIN_FEED_SWIPE_END, 250)
        self.sleeper(0.5)
        self.tap(*DOUYIN_SEARCH_ICON_TAP)
        self.sleeper(1)

    def open_search(self, destination: str | Path) -> Path:
        self._open_search_flow()
        return self.capture_screen(destination)

    def search_keyword_on_search_page(
        self,
        keyword: str,
        pinyin: str,
        destination: str | Path,
    ) -> Path:
        self._trace("search_keyword_on_search_page_start", keyword=keyword, pinyin=pinyin, destination=destination)
        self.tap(*DOUYIN_SEARCH_FIELD_TAP)
        self.sleeper(0.5)
        try:
            ui_xml = self.dump_ui_xml()
        except DouyinNavigationError:
            ui_xml = None
        if ui_xml is not None and self.dismiss_live_room_if_present(ui_xml):
            self.tap(*DOUYIN_SEARCH_FIELD_TAP)
            self.sleeper(0.5)
            ui_xml = self.dump_ui_xml()
        if ui_xml is not None and self.dismiss_permission_prompt_if_present(ui_xml):
            ui_xml = self.dump_ui_xml()
        if ui_xml is not None and self.is_search_page(ui_xml):
            if self.current_search_text(ui_xml).strip() != keyword.strip():
                self.clear_existing_search_text(ui_xml)
        else:
            self.force_clear_search_text()
            self.tap(*DOUYIN_SEARCH_FIELD_TAP)
        self.sleeper(0.5)
        if ui_xml is None or not self.is_search_page(ui_xml) or self.current_search_text(ui_xml).strip() != keyword.strip():
            self.input_keyword(keyword=keyword, pinyin=pinyin)
            self.sleeper(0.5)
        search_button = self.maybe_find_node(ui_xml, DOUYIN_SEARCH_BUTTON_ID) if ui_xml is not None else None
        if search_button is not None:
            self.tap_node(search_button)
        else:
            self.tap(*DOUYIN_SEARCH_BUTTON_TAP)
        self.sleeper(1)
        self._trace("search_keyword_on_search_page_submit", keyword=keyword)
        return self.capture_screen(destination)

    def search_keyword(
        self,
        keyword: str,
        pinyin: str,
        destination: str | Path,
    ) -> Path:
        self._trace("search_keyword_start", keyword=keyword, pinyin=pinyin, destination=destination)
        try:
            ui_xml = self.dump_ui_xml()
        except DouyinNavigationError:
            try:
                return self.search_keyword_on_search_page(
                    keyword=keyword,
                    pinyin=pinyin,
                    destination=destination,
                )
            except DouyinNavigationError:
                self._open_search_flow()
                return self.search_keyword_on_search_page(
                    keyword=keyword,
                    pinyin=pinyin,
                    destination=destination,
                )
        if self.dismiss_live_room_if_present(ui_xml):
            ui_xml = self.dump_ui_xml()
        if self.dismiss_permission_prompt_if_present(ui_xml):
            ui_xml = self.dump_ui_xml()
        if not self.is_search_page(ui_xml):
            try:
                return self.search_keyword_on_search_page(
                    keyword=keyword,
                    pinyin=pinyin,
                    destination=destination,
                )
            except DouyinNavigationError:
                self._open_search_flow()
        written = self.search_keyword_on_search_page(keyword=keyword, pinyin=pinyin, destination=destination)
        self._trace("search_keyword_complete", keyword=keyword, destination=destination)
        return written

    def open_live_results(self, destination: str | Path) -> Path:
        self._trace("open_live_results_start", destination=destination)
        self.tap(*DOUYIN_LIVE_TAB_TAP)
        self.sleeper(2)
        written = self.capture_screen(destination)
        self._trace("open_live_results_complete", destination=destination)
        return written

    def enter_first_live_room(self, destination: str | Path) -> Path:
        self._trace("enter_first_live_room_start", destination=destination)
        self.tap(*DOUYIN_FIRST_LIVE_CARD_TAP)
        self.sleeper(2)
        written = self.capture_screen(destination)
        self._trace("enter_first_live_room_complete", destination=destination)
        return written

    def search_live_results(
        self,
        keyword: str,
        pinyin: str,
        destination: str | Path,
    ) -> Path:
        self.search_keyword(keyword=keyword, pinyin=pinyin, destination=destination)
        return self.open_live_results(destination)

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
    parser = argparse.ArgumentParser(description="Open Douyin search and capture a screenshot.")
    parser.add_argument("--serial", help="ADB serial to target a specific device.")
    parser.add_argument("--output", default="/tmp/douyin-search.png", help="Destination screenshot path.")
    parser.add_argument("--query", help="Search keyword to submit on Douyin.")
    parser.add_argument("--pinyin", help="Latin input used when ADBKeyBoard is unavailable.")
    parser.add_argument(
        "--open-live-results",
        action="store_true",
        help="After search, switch to the public livestream results tab and capture it.",
    )
    parser.add_argument(
        "--enter-first-live-room",
        action="store_true",
        help="After search, switch to livestream results and enter the first public live room.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    navigator = DouyinNavigator(serial=args.serial)
    if args.query:
        if not args.pinyin:
            raise SystemExit("--query requires --pinyin")
        if args.enter_first_live_room:
            output = navigator.search_and_enter_first_live_room(
                keyword=args.query,
                pinyin=args.pinyin,
                destination=args.output,
            )
        elif args.open_live_results:
            output = navigator.search_live_results(
                keyword=args.query,
                pinyin=args.pinyin,
                destination=args.output,
            )
        else:
            output = navigator.search_keyword(
                keyword=args.query,
                pinyin=args.pinyin,
                destination=args.output,
            )
    else:
        if args.open_live_results or args.enter_first_live_room:
            raise SystemExit("--open-live-results/--enter-first-live-room require --query and --pinyin")
        output = navigator.open_search(args.output)
    print(f"Douyin search screenshot saved to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
