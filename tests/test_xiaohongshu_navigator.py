from __future__ import annotations

import json
from pathlib import Path

from test_douyin_navigator import ADB_KEYBOARD_LIST_OUTPUT, FakeCompletedProcess, FakeInstaller, RecordingRunner


def test_open_search_launches_xiaohongshu_and_captures_search_page(tmp_path: Path) -> None:
    from xiaohongshu_navigator import XiaohongshuNavigator

    installer = FakeInstaller()
    runner = RecordingRunner(
        [
            FakeCompletedProcess(),
            FakeCompletedProcess(),
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

    target = tmp_path / "xhs-search.png"
    written = navigator.open_search(target)

    assert written == target
    assert target.read_bytes() == b"\x89PNGDATA"
    assert installer.calls == []
    assert runner.calls[0]["cmd"] == ["adb", "-s", "deec9116", "shell", "am", "force-stop", "com.xingin.xhs"]
    assert runner.calls[1]["cmd"] == [
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
    assert runner.calls[2]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "640", "1885"]
    assert runner.calls[3]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "1180", "210"]
    assert runner.calls[4]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "screencap", "-p"]
    assert runner.calls[4]["text"] is False


def test_open_search_falls_back_to_install_check_when_launch_fails(tmp_path: Path) -> None:
    from xiaohongshu_navigator import XiaohongshuNavigator

    installer = FakeInstaller()
    runner = RecordingRunner(
        [
            FakeCompletedProcess(),
            FakeCompletedProcess(returncode=1, stderr="launch failed"),
            FakeCompletedProcess(),
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

    target = tmp_path / "xhs-search-fallback.png"
    written = navigator.open_search(target)

    assert written == target
    assert target.read_bytes() == b"\x89PNGDATA"
    assert installer.calls == [("com.xingin.xhs", False)]
    assert runner.calls[0]["cmd"] == ["adb", "-s", "deec9116", "shell", "am", "force-stop", "com.xingin.xhs"]
    assert runner.calls[1]["cmd"] == [
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
    assert runner.calls[2]["cmd"] == [
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


def test_open_search_writes_trace_file_when_trace_dir_is_provided(tmp_path: Path) -> None:
    from xiaohongshu_navigator import XiaohongshuNavigator

    installer = FakeInstaller()
    runner = RecordingRunner(
        [
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout=b"\x89PNGDATA"),
        ]
    )
    trace_dir = tmp_path / "trace"

    navigator = XiaohongshuNavigator(
        serial="deec9116",
        installer=installer,
        runner=runner,
        sleeper=lambda _seconds: None,
        trace_dir=trace_dir,
    )

    target = tmp_path / "xhs-search-trace.png"
    navigator.open_search(target)

    trace_file = trace_dir / "trace.jsonl"
    assert trace_file.exists()
    trace_rows = [json.loads(line) for line in trace_file.read_text(encoding="utf-8").splitlines()]
    assert any(row["event"] == "open_search_start" for row in trace_rows)
    assert any(row["event"] == "open_search_force_stop_start" for row in trace_rows)
    assert any(row["event"] == "open_search_force_stop_complete" for row in trace_rows)
    assert any(row["event"] == "open_search_launch_start" for row in trace_rows)
    assert any(row["event"] == "open_search_launch_complete" for row in trace_rows)
    assert any(row["event"] == "open_search_privacy_tap_start" for row in trace_rows)
    assert any(row["event"] == "open_search_privacy_tap_complete" for row in trace_rows)
    assert any(row["event"] == "open_search_search_icon_tap_start" for row in trace_rows)
    assert any(row["event"] == "open_search_search_icon_tap_complete" for row in trace_rows)
    assert any(row["event"] == "open_search_capture_start" for row in trace_rows)
    assert any(row["event"] == "open_search_capture_complete" for row in trace_rows)
    assert any(row["event"] == "adb_command_start" for row in trace_rows)
    assert any(row["event"] == "open_search_complete" for row in trace_rows)


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
    assert installer.calls == []
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


def test_capture_screen_waits_for_device_after_transient_adb_restart(tmp_path: Path) -> None:
    from xiaohongshu_navigator import XiaohongshuNavigator

    runner = RecordingRunner(
        [
            FakeCompletedProcess(returncode=1, stderr="* daemon not running; starting now at tcp:5037\n"),
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

    target = tmp_path / "xhs-retry.png"
    written = navigator.capture_screen(target)

    assert written == target
    assert target.read_bytes() == b"\x89PNGDATA"
    assert runner.calls[0]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "screencap", "-p"]
    assert runner.calls[0]["text"] is False
    assert runner.calls[1]["cmd"] == ["adb", "-s", "deec9116", "wait-for-device"]
    assert runner.calls[2]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "screencap", "-p"]
    assert runner.calls[2]["text"] is False


def test_tap_accepts_zero_returncode_even_when_daemon_restart_noise_is_present() -> None:
    from xiaohongshu_navigator import XiaohongshuNavigator

    runner = RecordingRunner(
        [
            FakeCompletedProcess(
                returncode=0,
                stderr="* daemon not running; starting now at tcp:5037\n* daemon started successfully\n",
            ),
        ]
    )

    navigator = XiaohongshuNavigator(
        serial="deec9116",
        installer=FakeInstaller(),
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    navigator.tap(640, 1885)

    assert runner.calls == [
        {
            "cmd": ["adb", "-s", "deec9116", "shell", "input", "tap", "640", "1885"],
            "capture_output": True,
            "text": True,
            "check": False,
            "timeout": None,
        }
    ]


def test_capture_screen_falls_back_to_device_file_when_direct_capture_keeps_failing(tmp_path: Path) -> None:
    from xiaohongshu_navigator import XiaohongshuNavigator

    runner = RecordingRunner(
        [
            FakeCompletedProcess(returncode=1, stderr="* daemon not running; starting now at tcp:5037\n"),
            FakeCompletedProcess(),
            FakeCompletedProcess(returncode=1, stderr="* daemon not running; starting now at tcp:5037\n"),
            FakeCompletedProcess(),
            FakeCompletedProcess(returncode=1, stderr="* daemon not running; starting now at tcp:5037\n"),
            FakeCompletedProcess(),
            FakeCompletedProcess(returncode=1, stderr="* daemon not running; starting now at tcp:5037\n"),
            FakeCompletedProcess(),
            FakeCompletedProcess(returncode=1, stderr="* daemon not running; starting now at tcp:5037\n"),
            FakeCompletedProcess(),
            FakeCompletedProcess(returncode=1, stderr="* daemon not running; starting now at tcp:5037\n"),
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

    target = tmp_path / "xhs-fallback.png"
    written = navigator.capture_screen(target)

    assert written == target
    assert target.read_bytes() == b"\x89PNGDATA"
    assert runner.calls[11]["cmd"] == ["adb", "-s", "deec9116", "shell", "screencap", "-p", "/sdcard/xhs_nav.png"]
    assert runner.calls[12]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "cat", "/sdcard/xhs_nav.png"]
    assert runner.calls[12]["text"] is False


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


def test_search_keyword_on_search_page_clears_field_inputs_keyword_and_taps_first_suggestion(
    tmp_path: Path,
) -> None:
    from xiaohongshu_navigator import XiaohongshuNavigator

    runner = RecordingRunner(
        [
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout=""),
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

    target = tmp_path / "xhs-results.png"
    written = navigator.search_keyword_on_search_page(keyword="hanfu", destination=target)

    assert written == target
    assert target.read_bytes() == b"\x89PNGDATA"
    assert runner.calls[0]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "260", "170"]
    assert runner.calls[1]["cmd"] == [
        "adb",
        "-s",
        "deec9116",
        "shell",
        "sh",
        "-c",
        'i=0; while [ "$i" -lt 12 ]; do input keyevent 67; i=$((i+1)); done',
    ]
    assert runner.calls[2]["cmd"] == [
        "adb",
        "-s",
        "deec9116",
        "shell",
        "sh",
        "-c",
        'i=0; while [ "$i" -lt 12 ]; do input keyevent 67; i=$((i+1)); done',
    ]
    assert runner.calls[3]["cmd"] == ["adb", "-s", "deec9116", "shell", "ime", "list", "-a"]
    assert runner.calls[4]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "text", "hanfu"]
    assert runner.calls[5]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "180", "360"]
    assert runner.calls[6]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "screencap", "-p"]


def test_search_keyword_on_search_page_prefers_adb_keyboard_when_available(tmp_path: Path) -> None:
    from xiaohongshu_navigator import ADB_KEYBOARD_B64_ACTION, ADB_KEYBOARD_IME, XiaohongshuNavigator

    runner = RecordingRunner(
        [
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout=ADB_KEYBOARD_LIST_OUTPUT),
            FakeCompletedProcess(stdout="com.tencent.wetype/.plugin.hld.WxHldService\n"),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
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

    target = tmp_path / "xhs-results-adb-keyboard.png"
    written = navigator.search_keyword_on_search_page(keyword="hanfu", destination=target)

    assert written == target
    assert target.read_bytes() == b"\x89PNGDATA"
    assert runner.calls[0]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "260", "170"]
    assert runner.calls[1]["cmd"][:6] == ["adb", "-s", "deec9116", "shell", "sh", "-c"]
    assert runner.calls[2]["cmd"][:6] == ["adb", "-s", "deec9116", "shell", "sh", "-c"]
    assert runner.calls[3]["cmd"] == ["adb", "-s", "deec9116", "shell", "ime", "list", "-a"]
    assert runner.calls[4]["cmd"] == ["adb", "-s", "deec9116", "shell", "settings", "get", "secure", "default_input_method"]
    assert runner.calls[5]["cmd"] == ["adb", "-s", "deec9116", "shell", "ime", "enable", ADB_KEYBOARD_IME]
    assert runner.calls[6]["cmd"] == ["adb", "-s", "deec9116", "shell", "ime", "set", ADB_KEYBOARD_IME]
    assert runner.calls[7]["cmd"] == [
        "adb",
        "-s",
        "deec9116",
        "shell",
        "am",
        "broadcast",
        "-a",
        ADB_KEYBOARD_B64_ACTION,
        "--es",
        "msg",
        "aGFuZnU=",
    ]
    assert runner.calls[8]["cmd"] == [
        "adb",
        "-s",
        "deec9116",
        "shell",
        "ime",
        "set",
        "com.tencent.wetype/.plugin.hld.WxHldService",
    ]
    assert runner.calls[9]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "180", "360"]
    assert runner.calls[10]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "screencap", "-p"]


def test_search_and_open_first_note_runs_search_then_enters_first_result(tmp_path: Path) -> None:
    from xiaohongshu_navigator import XiaohongshuNavigator

    class FlowNavigator(XiaohongshuNavigator):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.actions: list[tuple[str, str, str]] = []

        def search_keyword(self, keyword: str, destination: str | Path) -> Path:
            self.actions.append(("search", keyword, str(destination)))
            target = Path(destination)
            target.write_bytes(b"RESULTS")
            return target

        def enter_first_search_note(self, destination: str | Path) -> Path:
            self.actions.append(("enter-first-result", "", str(destination)))
            target = Path(destination)
            target.write_bytes(b"NOTE")
            return target

    navigator = FlowNavigator(
        serial="deec9116",
        installer=FakeInstaller(),
        runner=RecordingRunner([]),
        sleeper=lambda _seconds: None,
    )

    target = tmp_path / "xhs-first-search-note.png"
    written = navigator.search_and_open_first_note(keyword="hanfu", destination=target)

    assert written == target
    assert target.read_bytes() == b"NOTE"
    assert navigator.actions == [
        ("search", "hanfu", str(target)),
        ("enter-first-result", "", str(target)),
    ]


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
            "timeout": None,
        }
    ]


def test_enter_first_search_note_taps_first_result_card_and_captures_screen(tmp_path: Path) -> None:
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

    target = tmp_path / "xhs-search-note.png"
    written = navigator.enter_first_search_note(target)

    assert written == target
    assert target.read_bytes() == b"\x89PNGDATA"
    assert runner.calls[0]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "250", "760"]
    assert runner.calls[1]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "screencap", "-p"]
