from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import time
from typing import Callable

from mobile_app_installer import AndroidAppInstaller, KNOWN_APPS


Runner = Callable[..., subprocess.CompletedProcess]
Sleeper = Callable[[float], None]

XHS_PRIVACY_CONSENT_TAP = (640, 1885)
XHS_FIRST_FEED_NOTE_TAP = (970, 640)
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
            wait_result = self.runner(
                self._build_command("wait-for-device"),
                capture_output=True,
                text=True,
                check=False,
            )
            if wait_result.returncode != 0 and attempt == retries:
                return wait_result
            self.sleeper(retry_delay_seconds)
        return last_result  # pragma: no cover

    def tap(self, x: int, y: int) -> None:
        result = self._run("shell", "input", "tap", str(x), str(y))
        if result.returncode != 0:
            raise XiaohongshuNavigationError(self._decode_output(result.stderr) or f"Failed to tap {x},{y}")

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

    def capture_screen(self, destination: str | Path) -> Path:
        target = Path(destination)
        last_error = "Xiaohongshu screenshot payload is not a PNG"
        for attempt in range(6):
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
            if not self._is_transient_adb_error(capture_result) or attempt == 5:
                break
            wait_result = self.runner(
                self._build_command("wait-for-device"),
                capture_output=True,
                text=True,
                check=False,
            )
            if wait_result.returncode != 0:
                last_error = self._decode_output(wait_result.stderr) or last_error
                break
            self.sleeper(2.0)
        raise XiaohongshuNavigationError(last_error or "Xiaohongshu screenshot failed")

    def open_discovery(self, destination: str | Path) -> Path:
        self.installer.ensure_app(KNOWN_APPS["xiaohongshu"], launch_after_install=False)
        self.launch_app()
        self.sleeper(2)
        self.tap(*XHS_PRIVACY_CONSENT_TAP)
        self.sleeper(2)
        return self.capture_screen(destination)

    def enter_first_feed_note(self, destination: str | Path) -> Path:
        self.tap(*XHS_FIRST_FEED_NOTE_TAP)
        self.sleeper(2)
        return self.capture_screen(destination)

    def open_first_feed_note(self, destination: str | Path) -> Path:
        self.open_discovery(destination)
        return self.enter_first_feed_note(destination)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Open Xiaohongshu discovery feed and capture screenshots.")
    parser.add_argument("--serial", help="ADB serial to target a specific device.")
    parser.add_argument("--output", default="/tmp/xhs-discovery.png", help="Destination screenshot path.")
    parser.add_argument(
        "--enter-first-note",
        action="store_true",
        help="After opening discovery, enter the first visible public note and capture it.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    navigator = XiaohongshuNavigator(serial=args.serial)
    if args.enter_first_note:
        output = navigator.open_first_feed_note(args.output)
    else:
        output = navigator.open_discovery(args.output)
    print(f"Xiaohongshu screenshot saved to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
