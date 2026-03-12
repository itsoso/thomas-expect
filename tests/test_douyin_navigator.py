from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


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


ADB_KEYBOARD_LIST_OUTPUT = """\
mId=com.android.adbkeyboard/.AdbIME mSettingsActivityName=null mIsVrOnly=false mSupportsSwitchingToNextInputMethod=true
mId=com.tencent.wetype/.plugin.hld.WxHldService mSettingsActivityName=null mIsVrOnly=false mSupportsSwitchingToNextInputMethod=true
"""

SEARCH_PAGE_XML_WITH_EXISTING_TEXT = """\
<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node
    index="0"
    text="辛夷死鬼"
    resource-id="com.ss.android.ugc.aweme:id/et_search_kw"
    class="android.widget.EditText"
    package="com.ss.android.ugc.aweme"
    content-desc=""
    bounds="[156,165][1078,282]" />
  <node
    index="1"
    text="搜索"
    resource-id="com.ss.android.ugc.aweme:id/4_s"
    class="android.widget.TextView"
    package="com.ss.android.ugc.aweme"
    content-desc=""
    bounds="[1078,152][1280,295]" />
</hierarchy>
"""


def build_search_page_xml(text: str) -> str:
    return f"""\
<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node
    index="0"
    text="{text}"
    resource-id="com.ss.android.ugc.aweme:id/et_search_kw"
    class="android.widget.EditText"
    package="com.ss.android.ugc.aweme"
    content-desc=""
    bounds="[156,165][1078,282]" />
  <node
    index="1"
    text="搜索"
    resource-id="com.ss.android.ugc.aweme:id/4_s"
    class="android.widget.TextView"
    package="com.ss.android.ugc.aweme"
    content-desc=""
    bounds="[1078,152][1280,295]" />
</hierarchy>
"""


def test_open_search_launches_douyin_and_captures_search_page(tmp_path: Path) -> None:
    from douyin_navigator import DouyinNavigator

    installer = FakeInstaller()
    runner = RecordingRunner(
        [
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout=b"PNGDATA"),
            FakeCompletedProcess(),
        ]
    )

    navigator = DouyinNavigator(
        serial="deec9116",
        installer=installer,
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    target = tmp_path / "douyin-search.png"
    written = navigator.open_search(target)

    assert written == target
    assert target.read_bytes() == b"PNGDATA"
    assert installer.calls == [("com.ss.android.ugc.aweme", True)]
    assert runner.calls[0]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "640", "2000"]
    assert runner.calls[1]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "swipe", "640", "2300", "640", "1000", "250"]
    assert runner.calls[2]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "swipe", "640", "2300", "640", "1000", "250"]
    assert runner.calls[3]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "1188", "223"]
    assert runner.calls[4]["cmd"] == [
        "adb",
        "-s",
        "deec9116",
        "shell",
        "screencap",
        "-p",
        "/sdcard/douyin_capture.png",
    ]
    assert runner.calls[5]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "cat", "/sdcard/douyin_capture.png"]
    assert runner.calls[5]["text"] is False
    assert runner.calls[6]["cmd"] == ["adb", "-s", "deec9116", "shell", "rm", "-f", "/sdcard/douyin_capture.png"]


def test_capture_screen_uses_remote_file_strategy(tmp_path: Path) -> None:
    from douyin_navigator import DouyinNavigator

    installer = FakeInstaller()
    runner = RecordingRunner(
        [
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout=b"PNGDATA"),
            FakeCompletedProcess(),
        ]
    )

    navigator = DouyinNavigator(
        serial="deec9116",
        installer=installer,
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    target = tmp_path / "douyin-fallback-shot.png"
    written = navigator.capture_screen(target)

    assert written == target
    assert target.read_bytes() == b"PNGDATA"
    assert runner.calls[0]["cmd"] == [
        "adb",
        "-s",
        "deec9116",
        "shell",
        "screencap",
        "-p",
        "/sdcard/douyin_capture.png",
    ]
    assert runner.calls[1]["cmd"] == [
        "adb",
        "-s",
        "deec9116",
        "exec-out",
        "cat",
        "/sdcard/douyin_capture.png",
    ]
    assert runner.calls[2]["cmd"] == ["adb", "-s", "deec9116", "shell", "rm", "-f", "/sdcard/douyin_capture.png"]


def test_clear_existing_search_text_retries_until_the_input_is_empty() -> None:
    from douyin_navigator import DouyinNavigator

    class RetryingClearNavigator(DouyinNavigator):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.dump_payloads = [
                build_search_page_xml("辛夷直"),
                build_search_page_xml(""),
            ]

        def dump_ui_xml(self) -> str:
            if not self.dump_payloads:
                raise AssertionError("Unexpected extra dump_ui_xml call")
            return self.dump_payloads.pop(0)

    runner = RecordingRunner(
        [
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
        ]
    )
    navigator = RetryingClearNavigator(
        serial="deec9116",
        installer=FakeInstaller(),
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    navigator.clear_existing_search_text(build_search_page_xml("辛夷直播带货bab"))

    assert runner.calls[0]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "617", "223"]
    assert runner.calls[1]["cmd"] == [
        "adb",
        "-s",
        "deec9116",
        "shell",
        "sh",
        "-c",
        'i=0; while [ "$i" -lt 11 ]; do input keyevent 67; i=$((i+1)); done',
    ]
    assert runner.calls[2]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "617", "223"]
    assert runner.calls[3]["cmd"] == [
        "adb",
        "-s",
        "deec9116",
        "shell",
        "sh",
        "-c",
        'i=0; while [ "$i" -lt 6 ]; do input keyevent 67; i=$((i+1)); done',
    ]


def test_search_keyword_on_search_page_prefers_adb_keyboard_and_replaces_existing_text(tmp_path: Path) -> None:
    from douyin_navigator import ADB_KEYBOARD_IME, DouyinNavigator

    installer = FakeInstaller()
    runner = RecordingRunner(
        [
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout=SEARCH_PAGE_XML_WITH_EXISTING_TEXT),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout=build_search_page_xml("")),
            FakeCompletedProcess(stdout=ADB_KEYBOARD_LIST_OUTPUT),
            FakeCompletedProcess(stdout="com.tencent.wetype/.plugin.hld.WxHldService\n"),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout=b"PNGDATA"),
            FakeCompletedProcess(),
        ]
    )

    navigator = DouyinNavigator(
        serial="deec9116",
        installer=installer,
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    target = tmp_path / "douyin-search-result.png"
    written = navigator.search_keyword_on_search_page(
        keyword="直播带货",
        pinyin="zhibodaihuo",
        destination=target,
    )

    assert written == target
    assert target.read_bytes() == b"PNGDATA"
    assert installer.calls == []
    assert runner.calls[0]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "620", "223"]
    assert runner.calls[1]["cmd"] == ["adb", "-s", "deec9116", "shell", "uiautomator", "dump", "/sdcard/douyin_nav.xml"]
    assert runner.calls[2]["cmd"] == ["adb", "-s", "deec9116", "shell", "cat", "/sdcard/douyin_nav.xml"]
    assert runner.calls[3]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "617", "223"]
    assert runner.calls[4]["cmd"] == [
        "adb",
        "-s",
        "deec9116",
        "shell",
        "sh",
        "-c",
        'i=0; while [ "$i" -lt 6 ]; do input keyevent 67; i=$((i+1)); done',
    ]
    assert runner.calls[5]["cmd"] == ["adb", "-s", "deec9116", "shell", "uiautomator", "dump", "/sdcard/douyin_nav.xml"]
    assert runner.calls[6]["cmd"] == ["adb", "-s", "deec9116", "shell", "cat", "/sdcard/douyin_nav.xml"]
    assert runner.calls[7]["cmd"] == ["adb", "-s", "deec9116", "shell", "ime", "list", "-a"]
    assert runner.calls[8]["cmd"] == ["adb", "-s", "deec9116", "shell", "settings", "get", "secure", "default_input_method"]
    assert runner.calls[9]["cmd"] == ["adb", "-s", "deec9116", "shell", "ime", "enable", ADB_KEYBOARD_IME]
    assert runner.calls[10]["cmd"] == ["adb", "-s", "deec9116", "shell", "ime", "set", ADB_KEYBOARD_IME]
    assert runner.calls[11]["cmd"][:8] == [
        "adb",
        "-s",
        "deec9116",
        "shell",
        "am",
        "broadcast",
        "-a",
        "ADB_INPUT_B64",
    ]
    assert runner.calls[12]["cmd"] == [
        "adb",
        "-s",
        "deec9116",
        "shell",
        "ime",
        "set",
        "com.tencent.wetype/.plugin.hld.WxHldService",
    ]
    assert runner.calls[13]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "1179", "223"]
    assert runner.calls[14]["cmd"] == [
        "adb",
        "-s",
        "deec9116",
        "shell",
        "screencap",
        "-p",
        "/sdcard/douyin_capture.png",
    ]
    assert runner.calls[15]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "cat", "/sdcard/douyin_capture.png"]
    assert runner.calls[16]["cmd"] == ["adb", "-s", "deec9116", "shell", "rm", "-f", "/sdcard/douyin_capture.png"]


def test_search_keyword_on_search_page_falls_back_to_pinyin_when_adb_keyboard_switch_fails(tmp_path: Path) -> None:
    from douyin_navigator import DouyinNavigator

    installer = FakeInstaller()
    runner = RecordingRunner(
        [
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout=SEARCH_PAGE_XML_WITH_EXISTING_TEXT),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout=build_search_page_xml("")),
            FakeCompletedProcess(stdout=ADB_KEYBOARD_LIST_OUTPUT),
            FakeCompletedProcess(stdout="com.tencent.wetype/.plugin.hld.WxHldService\n"),
            FakeCompletedProcess(),
            FakeCompletedProcess(returncode=1, stderr="ime set failed"),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout=b"PNGDATA"),
            FakeCompletedProcess(),
        ]
    )

    navigator = DouyinNavigator(
        serial="deec9116",
        installer=installer,
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    target = tmp_path / "douyin-search-fallback.png"
    written = navigator.search_keyword_on_search_page(
        keyword="直播带货",
        pinyin="zhibodaihuo",
        destination=target,
    )

    assert written == target
    assert target.read_bytes() == b"PNGDATA"
    assert runner.calls[4]["cmd"] == [
        "adb",
        "-s",
        "deec9116",
        "shell",
        "sh",
        "-c",
        'i=0; while [ "$i" -lt 6 ]; do input keyevent 67; i=$((i+1)); done',
    ]
    assert runner.calls[11]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "text", "zhibodaihuo"]
    assert runner.calls[12]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "keyevent", "62"]
    assert runner.calls[13]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "1179", "223"]
    assert runner.calls[14]["cmd"] == [
        "adb",
        "-s",
        "deec9116",
        "shell",
        "screencap",
        "-p",
        "/sdcard/douyin_capture.png",
    ]
    assert runner.calls[15]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "cat", "/sdcard/douyin_capture.png"]
    assert runner.calls[16]["cmd"] == ["adb", "-s", "deec9116", "shell", "rm", "-f", "/sdcard/douyin_capture.png"]


def test_search_keyword_retries_search_page_flow_before_reopening_home(tmp_path: Path) -> None:
    from douyin_navigator import DouyinNavigationError, DouyinNavigator

    class FlakyDumpNavigator(DouyinNavigator):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.dump_calls = 0

        def dump_ui_xml(self) -> str:
            self.dump_calls += 1
            if self.dump_calls == 1:
                raise DouyinNavigationError("transient dump failure")
            return SEARCH_PAGE_XML_WITH_EXISTING_TEXT

        def capture_screen(self, destination: str | Path) -> Path:
            target = Path(destination)
            target.write_bytes(b"PNGDATA")
            return target

    installer = FakeInstaller()
    runner = RecordingRunner([FakeCompletedProcess() for _ in range(20)])

    navigator = FlakyDumpNavigator(
        serial="deec9116",
        installer=installer,
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    target = tmp_path / "douyin-search-retry.png"
    written = navigator.search_keyword(
        keyword="直播带货",
        pinyin="zhibodaihuo",
        destination=target,
    )

    assert written == target
    assert target.read_bytes() == b"PNGDATA"
    assert runner.calls[0]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "620", "223"]


def test_search_keyword_reuses_existing_search_page_without_relaunching_app(tmp_path: Path) -> None:
    from douyin_navigator import DouyinNavigator

    class SearchPageNavigator(DouyinNavigator):
        def dump_ui_xml(self) -> str:
            return SEARCH_PAGE_XML_WITH_EXISTING_TEXT

        def capture_screen(self, destination: str | Path) -> Path:
            target = Path(destination)
            target.write_bytes(b"PNGDATA")
            return target

    installer = FakeInstaller()
    runner = RecordingRunner([FakeCompletedProcess() for _ in range(20)])

    navigator = SearchPageNavigator(
        serial="deec9116",
        installer=installer,
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    target = tmp_path / "douyin-search-existing-page.png"
    written = navigator.search_keyword(
        keyword="直播带货",
        pinyin="zhibodaihuo",
        destination=target,
    )

    assert written == target
    assert target.read_bytes() == b"PNGDATA"
    assert installer.calls == []
