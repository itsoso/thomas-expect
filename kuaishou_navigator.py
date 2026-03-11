from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import time
from typing import Callable

from mobile_app_installer import AndroidAppInstaller, KNOWN_APPS


Runner = Callable[..., subprocess.CompletedProcess]
Sleeper = Callable[[float], None]

KUAISHOU_HOME_ACTIVITY = "com.smile.gifmaker/com.yxcorp.gifshow.HomeActivity"
KUAISHOU_SEARCH_TAP = (1188, 212)


class KuaishouNavigationError(RuntimeError):
    """Raised when the navigator cannot reach the expected Kuaishou page."""


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

    def _build_command(self, *args: str) -> list[str]:
        command = [self.adb_path]
        if self.serial:
            command.extend(["-s", self.serial])
        command.extend(args)
        return command

    def _run(self, *args: str, text: bool = True) -> subprocess.CompletedProcess:
        return self.runner(
            self._build_command(*args),
            capture_output=True,
            text=text,
            check=False,
        )

    def current_activity(self) -> str:
        result = self._run("shell", "dumpsys", "activity", "activities")
        output = (result.stdout or "") + "\n" + (result.stderr or "")
        match = re.search(r"ResumedActivity: ActivityRecord\{[^ ]+ u\d+ ([^ ]+)", output)
        if not match:
            match = re.search(r"topResumedActivity=ActivityRecord\{[^ ]+ u\d+ ([^ ]+)", output)
        if not match:
            raise KuaishouNavigationError("Could not determine current foreground activity")
        return match.group(1)

    def tap(self, x: int, y: int) -> None:
        result = self._run("shell", "input", "tap", str(x), str(y))
        if result.returncode != 0:
            raise KuaishouNavigationError(result.stderr or f"Failed to tap {x},{y}")

    def capture_screen(self, destination: str | Path) -> Path:
        target = Path(destination)
        result = self._run("exec-out", "screencap", "-p", text=False)
        if result.returncode != 0:
            raise KuaishouNavigationError(result.stderr or "Screenshot failed")
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Open Kuaishou search and capture a screenshot.")
    parser.add_argument("--serial", help="ADB serial to target a specific device.")
    parser.add_argument(
        "--output",
        default="/tmp/kuaishou-search.png",
        help="Destination file for the captured screenshot.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    navigator = KuaishouNavigator(serial=args.serial)
    output = navigator.open_search(args.output)
    print(f"Kuaishou search screenshot saved to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
