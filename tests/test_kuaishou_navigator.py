from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest


@dataclass
class FakeCompletedProcess:
    returncode: int = 0
    stdout: str | bytes = ""
    stderr: str = ""


class RecordingRunner:
    def __init__(self, responses: list[FakeCompletedProcess]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def __call__(self, cmd: list[str], capture_output: bool = True, text: bool = True, check: bool = False):
        self.calls.append(
            {
                "cmd": cmd,
                "capture_output": capture_output,
                "text": text,
                "check": check,
            }
        )
        if not self.responses:
            raise AssertionError(f"Missing fake response for command: {cmd}")
        return self.responses.pop(0)


class FakeInstaller:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []

    def ensure_app(self, spec, launch_after_install: bool = True, **_kwargs):
        self.calls.append((spec.package_name, launch_after_install))


def test_current_activity_reads_resumed_activity_line() -> None:
    from kuaishou_navigator import KuaishouNavigator

    runner = RecordingRunner(
        [
            FakeCompletedProcess(
                stdout=(
                    "  ResumedActivity: ActivityRecord{123 u0 "
                    "com.smile.gifmaker/com.yxcorp.gifshow.HomeActivity t61}\n"
                )
            )
        ]
    )

    navigator = KuaishouNavigator(serial="deec9116", runner=runner)

    assert navigator.current_activity() == "com.smile.gifmaker/com.yxcorp.gifshow.HomeActivity"
    assert runner.calls[0]["cmd"] == ["adb", "-s", "deec9116", "shell", "dumpsys", "activity", "activities"]


def test_open_search_launches_app_taps_search_and_writes_screenshot(tmp_path: Path) -> None:
    from kuaishou_navigator import KuaishouNavigator

    installer = FakeInstaller()
    runner = RecordingRunner(
        [
            FakeCompletedProcess(
                stdout=(
                    "  ResumedActivity: ActivityRecord{123 u0 "
                    "com.smile.gifmaker/com.yxcorp.gifshow.HomeActivity t61}\n"
                )
            ),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout=b"PNGDATA"),
        ]
    )

    navigator = KuaishouNavigator(
        serial="deec9116",
        installer=installer,
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    target = tmp_path / "search.png"
    written = navigator.open_search(target)

    assert written == target
    assert target.read_bytes() == b"PNGDATA"
    assert installer.calls == [("com.smile.gifmaker", True)]
    assert runner.calls[0]["cmd"] == ["adb", "-s", "deec9116", "shell", "dumpsys", "activity", "activities"]
    assert runner.calls[1]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "1188", "212"]
    assert runner.calls[2]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "screencap", "-p"]
    assert runner.calls[2]["text"] is False


def test_open_search_raises_when_not_on_home_activity() -> None:
    from kuaishou_navigator import KuaishouNavigator, KuaishouNavigationError

    installer = FakeInstaller()
    runner = RecordingRunner(
        [
            FakeCompletedProcess(
                stdout=(
                    "  ResumedActivity: ActivityRecord{123 u0 "
                    "com.smile.gifmaker/com.yxcorp.gifshow.LoginActivity t61}\n"
                )
            )
        ]
    )

    navigator = KuaishouNavigator(
        serial="deec9116",
        installer=installer,
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    with pytest.raises(KuaishouNavigationError, match="Expected 快手首页"):
        navigator.open_search(Path("/tmp/ignored.png"))
