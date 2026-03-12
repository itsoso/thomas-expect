from __future__ import annotations

from pathlib import Path

from test_douyin_navigator import FakeCompletedProcess, FakeInstaller, RecordingRunner


def test_open_discovery_launches_xiaohongshu_accepts_privacy_and_captures_screen(tmp_path: Path) -> None:
    from xiaohongshu_navigator import XiaohongshuNavigator

    installer = FakeInstaller()
    runner = RecordingRunner(
        [
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout=b"\x89PNGDATA"),
        ]
    )

    navigator = XiaohongshuNavigator(
        serial="deec9116",
        installer=installer,
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    target = tmp_path / "xhs-discovery.png"
    written = navigator.open_discovery(target)

    assert written == target
    assert target.read_bytes() == b"\x89PNGDATA"
    assert installer.calls == [("com.xingin.xhs", False)]
    assert runner.calls[0]["cmd"] == [
        "adb",
        "-s",
        "deec9116",
        "shell",
        "monkey",
        "-p",
        "com.xingin.xhs",
        "-c",
        "android.intent.category.LAUNCHER",
        "1",
    ]
    assert runner.calls[1]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "640", "1885"]
    assert runner.calls[2]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "screencap", "-p"]
    assert runner.calls[2]["text"] is False


def test_enter_first_feed_note_taps_first_note_card_and_captures_screen(tmp_path: Path) -> None:
    from xiaohongshu_navigator import XiaohongshuNavigator

    runner = RecordingRunner(
        [
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout=b"\x89PNGDATA"),
        ]
    )

    navigator = XiaohongshuNavigator(
        serial="deec9116",
        installer=FakeInstaller(),
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    target = tmp_path / "xhs-note.png"
    written = navigator.enter_first_feed_note(target)

    assert written == target
    assert target.read_bytes() == b"\x89PNGDATA"
    assert runner.calls[0]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "970", "640"]
    assert runner.calls[1]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "screencap", "-p"]
    assert runner.calls[1]["text"] is False


def test_open_first_feed_note_runs_discovery_then_note_flow(tmp_path: Path) -> None:
    from xiaohongshu_navigator import XiaohongshuNavigator

    class FlowNavigator(XiaohongshuNavigator):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.actions: list[tuple[str, str]] = []

        def open_discovery(self, destination: str | Path) -> Path:
            self.actions.append(("open-discovery", str(destination)))
            target = Path(destination)
            target.write_bytes(b"DISCOVERY")
            return target

        def enter_first_feed_note(self, destination: str | Path) -> Path:
            self.actions.append(("enter-note", str(destination)))
            target = Path(destination)
            target.write_bytes(b"NOTE")
            return target

    navigator = FlowNavigator(
        serial="deec9116",
        installer=FakeInstaller(),
        runner=RecordingRunner([]),
        sleeper=lambda _seconds: None,
    )

    target = tmp_path / "xhs-final.png"
    written = navigator.open_first_feed_note(target)

    assert written == target
    assert target.read_bytes() == b"NOTE"
    assert navigator.actions == [
        ("open-discovery", str(target)),
        ("enter-note", str(target)),
    ]


def test_capture_screen_accepts_valid_png_when_adb_returns_negative_15(tmp_path: Path) -> None:
    from xiaohongshu_navigator import XiaohongshuNavigator

    runner = RecordingRunner(
        [
            FakeCompletedProcess(returncode=-15, stdout=b"\x89PNGDATA"),
        ]
    )

    navigator = XiaohongshuNavigator(
        serial="deec9116",
        installer=FakeInstaller(),
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    target = tmp_path / "xhs-capture.png"
    written = navigator.capture_screen(target)

    assert written == target
    assert target.read_bytes() == b"\x89PNGDATA"
    assert runner.calls == [
        {
            "cmd": ["adb", "-s", "deec9116", "exec-out", "screencap", "-p"],
            "capture_output": True,
            "text": False,
            "check": False,
        }
    ]
