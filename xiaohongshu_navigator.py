from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import time
import subprocess
from typing import Callable

from mobile_app_installer import AndroidAppInstaller, KNOWN_APPS


Runner = Callable[..., subprocess.CompletedProcess]
Sleeper = Callable[[float], None]

XHS_PRIVACY_CONSENT_TAP = (640, 1885)
XHS_SEARCH_ICON_TAP = (1180, 210)
XHS_SEARCH_FIELD_TAP = (260, 170)
XHS_FIRST_SUGGESTION_TAP = (180, 360)
XHS_FIRST_FEED_NOTE_TAP = (970, 640)
XHS_FIRST_SEARCH_NOTE_TAP = (250, 760)
XHS_CAPTURE_PATH = "/sdcard/xhs_nav.png"
ADB_KEYBOARD_IME = "com.android.adbkeyboard/.AdbIME"
ADB_KEYBOARD_B64_ACTION = "ADB_INPUT_B64"
DELETE_TEXT_BATCH_SIZE = 12
XHS_LAUNCH_SETTLE_SECONDS = 0.5
XHS_DISCOVERY_TAP_SETTLE_SECONDS = 0.5
XHS_PRIVACY_TAP_SETTLE_SECONDS = 0.2
XHS_SEARCH_ICON_SETTLE_SECONDS = 0.5
TRANSIENT_ADB_ERRORS = (
    "daemon not running",
    "cannot connect to daemon",
    "adb server didn't ack",
)


class XiaohongshuNavigationError(RuntimeError):
    """Raised when Xiaohongshu navigation cannot complete the expected action."""


class XiaohongshuNavigator:
    def __init__(
        self,
        serial: str | None = None,
        installer: AndroidAppInstaller | None = None,
        adb_path: str = "adb",
        runner: Runner | None = None,
        sleeper: Sleeper | None = None,
        trace_dir: str | Path | None = None,
    ) -> None:
        self.serial = serial
        self.adb_path = adb_path
        self.runner = runner or subprocess.run
        self.sleeper = sleeper or time.sleep
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
        sanitized: dict[str, object] = {"event": event, "timestamp": round(time.time(), 3)}
        sanitized.update(payload)
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
        return result.returncode == -15 or any(marker in combined_output for marker in TRANSIENT_ADB_ERRORS)

    def _run(
        self,
        *args: str,
        text: bool = True,
        retries: int = 2,
        retry_delay_seconds: float = 0.0,
    ) -> subprocess.CompletedProcess:
        last_result: subprocess.CompletedProcess | None = None
        for attempt in range(retries + 1):
            command = self._build_command(*args)
            self._trace(
                "adb_command_start",
                command=command,
                attempt=attempt + 1,
                max_attempts=retries + 1,
                text=text,
            )
            last_result = self.runner(
                command,
                capture_output=True,
                text=text,
                check=False,
            )
            self._trace(
                "adb_command_result",
                command=command,
                attempt=attempt + 1,
                returncode=last_result.returncode,
                stdout=self._decode_output(last_result.stdout)[:300],
                stderr=self._decode_output(last_result.stderr)[:300],
            )
            if last_result.returncode == 0:
                return last_result
            if not self._is_transient_adb_error(last_result) or attempt == retries:
                return last_result
            wait_result = self.runner(
                self._build_command("wait-for-device"),
                capture_output=True,
                text=True,
                check=False,
            )
            self._trace(
                "adb_wait_for_device",
                command=self._build_command("wait-for-device"),
                attempt=attempt + 1,
                returncode=wait_result.returncode,
                stderr=self._decode_output(wait_result.stderr)[:300],
            )
            if wait_result.returncode != 0 and attempt == retries:
                return wait_result
            self.sleeper(retry_delay_seconds)
        return last_result  # pragma: no cover

    def tap(self, x: int, y: int) -> None:
        result = self._run("shell", "input", "tap", str(x), str(y))
        if result.returncode != 0:
            raise XiaohongshuNavigationError(self._decode_output(result.stderr) or f"Failed to tap {x},{y}")

    def force_stop_app(self) -> None:
        result = self._run("shell", "am", "force-stop", KNOWN_APPS["xiaohongshu"].package_name)
        if result.returncode != 0:
            raise XiaohongshuNavigationError(
                self._decode_output(result.stderr) or f"Failed to force-stop {KNOWN_APPS['xiaohongshu'].package_name}"
            )

    def input_text(self, value: str) -> None:
        result = self._run("shell", "input", "text", value)
        if result.returncode != 0:
            raise XiaohongshuNavigationError(self._decode_output(result.stderr) or f"Failed to input text: {value}")

    def list_input_methods(self) -> str:
        result = self._run("shell", "ime", "list", "-a")
        if result.returncode != 0:
            raise XiaohongshuNavigationError(self._decode_output(result.stderr) or "Failed to list input methods")
        return self._decode_output(result.stdout)

    def get_default_input_method(self) -> str:
        result = self._run("shell", "settings", "get", "secure", "default_input_method")
        if result.returncode != 0:
            raise XiaohongshuNavigationError(
                self._decode_output(result.stderr) or "Failed to get current default input method"
            )
        return self._decode_output(result.stdout).strip()

    def set_input_method(self, ime_id: str, *, enable: bool = False) -> None:
        if enable:
            enable_result = self._run("shell", "ime", "enable", ime_id)
            if enable_result.returncode != 0:
                raise XiaohongshuNavigationError(
                    self._decode_output(enable_result.stderr) or f"Failed to enable input method {ime_id}"
                )
        result = self._run("shell", "ime", "set", ime_id)
        if result.returncode != 0:
            raise XiaohongshuNavigationError(
                self._decode_output(result.stderr) or f"Failed to switch input method to {ime_id}"
            )

    def input_text_with_adb_keyboard(self, value: str) -> None:
        current_ime = self.get_default_input_method()
        restore_ime = current_ime if current_ime and current_ime != ADB_KEYBOARD_IME else None
        try:
            self.set_input_method(ADB_KEYBOARD_IME, enable=True)
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
                raise XiaohongshuNavigationError(
                    self._decode_output(result.stderr) or "Failed to broadcast unicode text via ADBKeyBoard"
                )
        finally:
            if restore_ime:
                self.set_input_method(restore_ime)

    def enter_search_text(self, keyword: str) -> None:
        ime_list = self.list_input_methods()
        if ADB_KEYBOARD_IME in ime_list:
            self.input_text_with_adb_keyboard(keyword)
            return
        self.input_text(keyword)

    def keyevent(self, keycode: int) -> None:
        result = self._run("shell", "input", "keyevent", str(keycode))
        if result.returncode != 0:
            raise XiaohongshuNavigationError(self._decode_output(result.stderr) or f"Failed to send keyevent {keycode}")

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
                raise XiaohongshuNavigationError(
                    self._decode_output(result.stderr) or "Failed to clear existing Xiaohongshu search text"
                )
            remaining -= batch_size

    def launch_app(self) -> None:
        result = self._run(
            "shell",
            "monkey",
            "-p",
            KNOWN_APPS["xiaohongshu"].package_name,
            "-c",
            "android.intent.category.LAUNCHER",
            "1",
        )
        if result.returncode != 0:
            raise XiaohongshuNavigationError(
                self._decode_output(result.stderr) or f"Failed to launch {KNOWN_APPS['xiaohongshu'].package_name}"
            )

    def launch_app_with_install_fallback(self) -> None:
        try:
            self.launch_app()
            return
        except XiaohongshuNavigationError as exc:
            self._trace("launch_app_fallback_to_install", error=str(exc))
        self.installer.ensure_app(KNOWN_APPS["xiaohongshu"], launch_after_install=False)
        self.launch_app()

    def capture_screen(self, destination: str | Path) -> Path:
        target = Path(destination)
        last_error = "Xiaohongshu screenshot payload is not a PNG"
        capture_result = self.runner(
            self._build_command("exec-out", "screencap", "-p"),
            capture_output=True,
            text=False,
            check=False,
        )
        payload = capture_result.stdout or b""
        if isinstance(payload, str):
            payload = payload.encode()
        if payload.startswith(b"\x89PNG"):
            target.write_bytes(payload)
            return target
        last_error = self._decode_output(capture_result.stderr) or last_error
        self._trace(
            "capture_screen_direct_fallback",
            returncode=capture_result.returncode,
            stderr=last_error[:300],
        )
        return self.capture_screen_via_device_file(destination, last_error=last_error)

    def capture_screen_via_device_file(self, destination: str | Path, last_error: str | None = None) -> Path:
        target = Path(destination)
        capture_result = self._run(
            "shell",
            "screencap",
            "-p",
            XHS_CAPTURE_PATH,
            text=True,
            retries=5,
            retry_delay_seconds=2.0,
        )
        if capture_result.returncode != 0:
            raise XiaohongshuNavigationError(
                self._decode_output(capture_result.stderr) or last_error or "Fallback screenshot failed"
            )

        read_result = self._run(
            "exec-out",
            "cat",
            XHS_CAPTURE_PATH,
            text=False,
            retries=5,
            retry_delay_seconds=2.0,
        )
        payload = read_result.stdout or b""
        if isinstance(payload, str):
            payload = payload.encode()
        if read_result.returncode != 0 or not payload.startswith(b"\x89PNG"):
            raise XiaohongshuNavigationError(
                self._decode_output(read_result.stderr) or last_error or "Fallback screenshot read failed"
            )
        target.write_bytes(payload)
        return target

    def open_discovery(self, destination: str | Path) -> Path:
        self._trace("open_discovery_start", destination=str(destination))
        self._trace("open_discovery_launch_start")
        self.launch_app_with_install_fallback()
        self.sleeper(XHS_LAUNCH_SETTLE_SECONDS)
        self._trace("open_discovery_launch_complete")
        self._trace("open_discovery_privacy_tap_start")
        self.tap(*XHS_PRIVACY_CONSENT_TAP)
        self.sleeper(XHS_DISCOVERY_TAP_SETTLE_SECONDS)
        self._trace("open_discovery_privacy_tap_complete")
        self._trace("open_discovery_capture_start", destination=str(destination))
        output = self.capture_screen(destination)
        self._trace("open_discovery_capture_complete", destination=str(output))
        self._trace("open_discovery_complete", destination=str(output))
        return output

    def open_search(self, destination: str | Path) -> Path:
        self._trace("open_search_start", destination=str(destination))
        self._trace("open_search_force_stop_start")
        self.force_stop_app()
        self._trace("open_search_force_stop_complete")
        self._trace("open_search_launch_start")
        self.launch_app_with_install_fallback()
        self.sleeper(XHS_LAUNCH_SETTLE_SECONDS)
        self._trace("open_search_launch_complete")
        self._trace("open_search_privacy_tap_start")
        self.tap(*XHS_PRIVACY_CONSENT_TAP)
        self.sleeper(XHS_PRIVACY_TAP_SETTLE_SECONDS)
        self._trace("open_search_privacy_tap_complete")
        self._trace("open_search_search_icon_tap_start")
        self.tap(*XHS_SEARCH_ICON_TAP)
        self.sleeper(XHS_SEARCH_ICON_SETTLE_SECONDS)
        self._trace("open_search_search_icon_tap_complete")
        self._trace("open_search_capture_start", destination=str(destination))
        output = self.capture_screen(destination)
        self._trace("open_search_capture_complete", destination=str(output))
        self._trace("open_search_complete", destination=str(output))
        return output

    def enter_first_feed_note(self, destination: str | Path) -> Path:
        self.tap(*XHS_FIRST_FEED_NOTE_TAP)
        self.sleeper(2)
        return self.capture_screen(destination)

    def search_keyword_on_search_page(self, keyword: str, destination: str | Path) -> Path:
        self.tap(*XHS_SEARCH_FIELD_TAP)
        self.sleeper(0.2)
        self.delete_text(24)
        self.sleeper(0.2)
        self.enter_search_text(keyword)
        self.sleeper(1)
        self.tap(*XHS_FIRST_SUGGESTION_TAP)
        self.sleeper(4)
        return self.capture_screen(destination)

    def search_keyword(self, keyword: str, destination: str | Path) -> Path:
        self.open_search(destination)
        return self.search_keyword_on_search_page(keyword=keyword, destination=destination)

    def enter_first_search_note(self, destination: str | Path) -> Path:
        self.tap(*XHS_FIRST_SEARCH_NOTE_TAP)
        self.sleeper(2)
        return self.capture_screen(destination)

    def search_and_open_first_note(self, keyword: str, destination: str | Path) -> Path:
        self.search_keyword(keyword=keyword, destination=destination)
        return self.enter_first_search_note(destination)

    def open_first_feed_note(self, destination: str | Path) -> Path:
        self.open_discovery(destination)
        return self.enter_first_feed_note(destination)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Open Xiaohongshu discovery feed and capture screenshots.")
    parser.add_argument("--serial", help="ADB serial to target a specific device.")
    parser.add_argument("--output", default="/tmp/xhs-discovery.png", help="Destination screenshot path.")
    parser.add_argument("--trace-dir", help="Optional trace directory for Xiaohongshu navigation.")
    parser.add_argument(
        "--enter-first-note",
        action="store_true",
        help="After opening discovery, enter the first visible public note and capture it.",
    )
    parser.add_argument("--open-search", action="store_true", help="Open the Xiaohongshu search page and capture it.")
    parser.add_argument("--query", help="Search keyword to run on Xiaohongshu.")
    parser.add_argument(
        "--open-first-search-note",
        action="store_true",
        help="After searching, open the first visible public search result note and capture it.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    navigator = XiaohongshuNavigator(serial=args.serial, trace_dir=args.trace_dir)
    if args.open_first_search_note:
        if not args.query:
            raise XiaohongshuNavigationError("--open-first-search-note requires --query")
        output = navigator.search_and_open_first_note(keyword=args.query, destination=args.output)
    elif args.query:
        output = navigator.search_keyword(keyword=args.query, destination=args.output)
    elif args.open_search:
        output = navigator.open_search(args.output)
    elif args.enter_first_note:
        output = navigator.open_first_feed_note(args.output)
    else:
        output = navigator.open_discovery(args.output)
    print(f"Xiaohongshu screenshot saved to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
