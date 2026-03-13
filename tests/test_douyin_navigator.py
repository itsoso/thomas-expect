from __future__ import annotations

import subprocess
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

    def __call__(
        self,
        cmd: list[str],
        capture_output: bool = True,
        text: bool = True,
        check: bool = False,
        timeout: float | None = None,
    ):
        self.calls.append(
            {
                "cmd": cmd,
                "capture_output": capture_output,
                "text": text,
                "check": check,
                "timeout": timeout,
            }
        )
        if not self.responses:
            raise AssertionError(f"Missing fake response for command: {cmd}")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeInstaller:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []
        self.launch_calls: list[tuple[str, str | None]] = []
        self.launch_failures: list[Exception] = []

    def ensure_app(self, spec, launch_after_install: bool = True, **_kwargs):
        self.calls.append((spec.package_name, launch_after_install))

    def launch_app(self, package_name: str, launcher_activity: str | None = None):
        self.launch_calls.append((package_name, launcher_activity))
        if self.launch_failures:
            raise self.launch_failures.pop(0)


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

PERMISSION_PROMPT_XML = """\
<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node
    index="0"
    text=""
    resource-id=""
    class="android.widget.FrameLayout"
    package="com.android.permissioncontroller"
    bounds="[0,0][1280,2772]">
    <node
      index="0"
      text="允许“抖音”获取位置信息？"
      resource-id="com.android.permissioncontroller:id/alertTitle"
      class="android.widget.TextView"
      package="com.android.permissioncontroller"
      bounds="[168,1353][1111,1430]" />
    <node
      index="1"
      text="拒绝"
      resource-id=""
      class="android.widget.Button"
      package="com.android.permissioncontroller"
      bounds="[129,2249][1150,2408]" />
  </node>
</hierarchy>
"""

ENDED_LIVE_ROOM_XML = """\
<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node
    index="0"
    text=""
    resource-id=""
    class="android.widget.FrameLayout"
    package="com.ss.android.ugc.aweme"
    bounds="[0,0][1280,2772]">
    <node
      index="0"
      text=""
      resource-id=""
      class="android.view.ViewGroup"
      package="com.ss.android.ugc.aweme"
      content-desc="直播已结束"
      bounds="[478,224][803,315]" />
    <node
      index="1"
      text=""
      resource-id=""
      class="android.widget.ImageView"
      package="com.ss.android.ugc.aweme"
      content-desc="关闭"
      bounds="[1121,231][1199,309]" />
  </node>
</hierarchy>
"""

NON_STANDARD_SEARCH_PAGE_XML = """\
<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node
    index="0"
    text=""
    resource-id=""
    class="android.widget.FrameLayout"
    package="com.ss.android.ugc.aweme"
    bounds="[0,0][1280,2772]">
    <node
      index="0"
      text=""
      resource-id=""
      class="android.widget.EditText"
      package="com.ss.android.ugc.aweme"
      bounds="[120,152][1050,295]" />
    <node
      index="1"
      text="搜索"
      resource-id=""
      class="android.widget.TextView"
      package="com.ss.android.ugc.aweme"
      bounds="[1110,152][1230,295]" />
  </node>
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
            FakeCompletedProcess(stdout=SEARCH_PAGE_XML_WITH_EXISTING_TEXT),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout=b"PNGDATA"),
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
    assert installer.calls == []
    assert installer.launch_calls == [("com.ss.android.ugc.aweme", None)]
    assert runner.calls[0]["cmd"] == ["adb", "-s", "deec9116", "shell", "uiautomator", "dump", "/sdcard/douyin_nav.xml"]
    assert runner.calls[1]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "cat", "/sdcard/douyin_nav.xml"]
    assert runner.calls[1]["text"] is False
    assert runner.calls[2]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "640", "2000"]
    assert runner.calls[3]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "swipe", "640", "2300", "640", "1000", "250"]
    assert runner.calls[4]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "swipe", "640", "2300", "640", "1000", "250"]
    assert runner.calls[5]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "1188", "223"]
    assert runner.calls[6]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "screencap", "-p"]
    assert runner.calls[6]["text"] is False
    assert len(runner.calls) == 7


def test_open_search_falls_back_to_install_check_when_direct_launch_fails(tmp_path: Path) -> None:
    from douyin_navigator import DouyinNavigator
    from mobile_app_installer import AppInstallError

    installer = FakeInstaller()
    installer.launch_failures = [AppInstallError("launch failed")]
    runner = RecordingRunner(
        [
            FakeCompletedProcess(stdout=SEARCH_PAGE_XML_WITH_EXISTING_TEXT),
            FakeCompletedProcess(stdout=SEARCH_PAGE_XML_WITH_EXISTING_TEXT),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout=b"PNGDATA"),
        ]
    )

    navigator = DouyinNavigator(
        serial="deec9116",
        installer=installer,
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    target = tmp_path / "douyin-search-fallback.png"
    written = navigator.open_search(target)

    assert written == target
    assert target.read_bytes() == b"PNGDATA"
    assert installer.calls == [("com.ss.android.ugc.aweme", False)]
    assert installer.launch_calls == [
        ("com.ss.android.ugc.aweme", None),
        ("com.ss.android.ugc.aweme", None),
    ]


def test_capture_screen_prefers_direct_exec_out_strategy(tmp_path: Path) -> None:
    from douyin_navigator import DouyinNavigator

    installer = FakeInstaller()
    runner = RecordingRunner(
        [
            FakeCompletedProcess(stdout=b"PNGDATA"),
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
        "exec-out",
        "screencap",
        "-p",
    ]
    assert runner.calls[0]["text"] is False


def test_capture_screen_falls_back_to_device_file_when_direct_exec_out_fails(tmp_path: Path) -> None:
    from douyin_navigator import DouyinNavigator

    runner = RecordingRunner(
        [
            FakeCompletedProcess(returncode=1, stdout=b"", stderr="direct screencap failed"),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout=b"PNGDATA"),
            FakeCompletedProcess(),
        ]
    )

    navigator = DouyinNavigator(
        serial="deec9116",
        installer=FakeInstaller(),
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    target = tmp_path / "douyin-fallback-shot.png"
    written = navigator.capture_screen(target)

    assert written == target
    assert target.read_bytes() == b"PNGDATA"
    assert runner.calls[0]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "screencap", "-p"]
    assert runner.calls[1]["cmd"] == [
        "adb",
        "-s",
        "deec9116",
        "shell",
        "screencap",
        "-p",
        "/sdcard/douyin_capture.png",
    ]
    assert runner.calls[2]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "cat", "/sdcard/douyin_capture.png"]
    assert runner.calls[3]["cmd"] == ["adb", "-s", "deec9116", "shell", "rm", "-f", "/sdcard/douyin_capture.png"]


def test_capture_screen_retries_after_timeout_then_succeeds_directly(tmp_path: Path) -> None:
    from douyin_navigator import DouyinNavigator

    runner = RecordingRunner(
        [
            subprocess.TimeoutExpired(cmd=["adb", "exec-out", "screencap", "-p"], timeout=15),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout=b"PNGDATA"),
        ]
    )

    navigator = DouyinNavigator(
        serial="deec9116",
        installer=FakeInstaller(),
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    target = tmp_path / "douyin-timeout-retry-shot.png"
    written = navigator.capture_screen(target)

    assert written == target
    assert target.read_bytes() == b"PNGDATA"
    assert runner.calls[0]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "screencap", "-p"]
    assert runner.calls[0]["timeout"] == 15.0
    assert runner.calls[1]["cmd"] == ["adb", "-s", "deec9116", "wait-for-device"]
    assert runner.calls[2]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "screencap", "-p"]


def test_capture_screen_accepts_valid_png_when_adb_returns_negative_15(tmp_path: Path) -> None:
    from douyin_navigator import DouyinNavigator

    runner = RecordingRunner(
        [
            FakeCompletedProcess(returncode=-15, stdout=b"\x89PNGDATA"),
        ]
    )

    navigator = DouyinNavigator(
        serial="deec9116",
        installer=FakeInstaller(),
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    target = tmp_path / "douyin-negative-15-valid-png.png"
    written = navigator.capture_screen(target)

    assert written == target
    assert target.read_bytes() == b"\x89PNGDATA"
    assert runner.calls == [
        {
            "cmd": ["adb", "-s", "deec9116", "exec-out", "screencap", "-p"],
            "capture_output": True,
            "text": False,
            "check": False,
            "timeout": 15.0,
        }
    ]


def test_dump_ui_xml_retries_after_exec_out_cat_timeout() -> None:
    from douyin_navigator import DouyinNavigator

    runner = RecordingRunner(
        [
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/douyin_nav.xml\n"),
            subprocess.TimeoutExpired(cmd=["adb", "exec-out", "cat", "/sdcard/douyin_nav.xml"], timeout=15),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout=b"<?xml version='1.0' encoding='UTF-8'?><hierarchy />"),
        ]
    )

    navigator = DouyinNavigator(
        serial="deec9116",
        installer=FakeInstaller(),
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    ui_xml = navigator.dump_ui_xml()

    assert ui_xml.startswith("<?xml")
    assert runner.calls[0]["cmd"] == ["adb", "-s", "deec9116", "shell", "uiautomator", "dump", "/sdcard/douyin_nav.xml"]
    assert runner.calls[1]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "cat", "/sdcard/douyin_nav.xml"]
    assert runner.calls[1]["text"] is False
    assert runner.calls[1]["timeout"] == 15.0
    assert runner.calls[2]["cmd"] == ["adb", "-s", "deec9116", "wait-for-device"]
    assert runner.calls[3]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "cat", "/sdcard/douyin_nav.xml"]
    assert runner.calls[3]["text"] is False


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
            FakeCompletedProcess(stdout=b"PNGDATA"),
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
    assert runner.calls[2]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "cat", "/sdcard/douyin_nav.xml"]
    assert runner.calls[2]["text"] is False
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
    assert runner.calls[6]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "cat", "/sdcard/douyin_nav.xml"]
    assert runner.calls[6]["text"] is False
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
    assert runner.calls[14]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "screencap", "-p"]
    assert runner.calls[14]["text"] is False


def test_search_keyword_on_search_page_skips_retyping_when_keyword_already_matches(tmp_path: Path) -> None:
    from douyin_navigator import DouyinNavigator

    current_keyword_xml = build_search_page_xml("美女直播")
    runner = RecordingRunner(
        [
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout=current_keyword_xml),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout=b"PNGDATA"),
        ]
    )

    navigator = DouyinNavigator(
        serial="deec9116",
        installer=FakeInstaller(),
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    target = tmp_path / "douyin-search-already-matched.png"
    written = navigator.search_keyword_on_search_page(
        keyword="美女直播",
        pinyin="meinvzhibo",
        destination=target,
    )

    assert written == target
    assert target.read_bytes() == b"PNGDATA"
    assert runner.calls[0]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "620", "223"]
    assert runner.calls[1]["cmd"] == ["adb", "-s", "deec9116", "shell", "uiautomator", "dump", "/sdcard/douyin_nav.xml"]
    assert runner.calls[2]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "cat", "/sdcard/douyin_nav.xml"]
    assert runner.calls[3]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "1179", "223"]
    assert runner.calls[4]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "screencap", "-p"]
    assert len(runner.calls) == 5


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
            FakeCompletedProcess(stdout=b"PNGDATA"),
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
    assert runner.calls[14]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "screencap", "-p"]
    assert runner.calls[14]["text"] is False


def test_search_keyword_on_search_page_dismisses_permission_prompt_before_editing_text(tmp_path: Path) -> None:
    from douyin_navigator import DouyinNavigator

    class PermissionPromptNavigator(DouyinNavigator):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.dump_payloads = [
                PERMISSION_PROMPT_XML,
                SEARCH_PAGE_XML_WITH_EXISTING_TEXT,
                build_search_page_xml(""),
            ]

        def dump_ui_xml(self) -> str:
            if not self.dump_payloads:
                raise AssertionError("Unexpected extra dump_ui_xml call")
            return self.dump_payloads.pop(0)

        def capture_screen(self, destination: str | Path) -> Path:
            target = Path(destination)
            target.write_bytes(b"PNGDATA")
            return target

    installer = FakeInstaller()
    runner = RecordingRunner(
        [
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout=ADB_KEYBOARD_LIST_OUTPUT),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
        ]
    )

    navigator = PermissionPromptNavigator(
        serial="deec9116",
        installer=installer,
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    target = tmp_path / "douyin-search-after-permission.png"
    written = navigator.search_keyword_on_search_page(
        keyword="直播带货",
        pinyin="zhibodaihuo",
        destination=target,
    )

    assert written == target
    assert target.read_bytes() == b"PNGDATA"
    assert runner.calls[0]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "620", "223"]
    assert runner.calls[1]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "639", "2328"]
    assert runner.calls[2]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "617", "223"]


def test_search_keyword_on_search_page_closes_ended_live_room_and_uses_coordinate_clear(tmp_path: Path) -> None:
    from douyin_navigator import DouyinNavigator

    class EndedLiveRoomNavigator(DouyinNavigator):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.dump_payloads = [
                ENDED_LIVE_ROOM_XML,
                NON_STANDARD_SEARCH_PAGE_XML,
            ]
            self.force_clear_calls: list[int] = []
            self.input_calls: list[tuple[str, str]] = []

        def dump_ui_xml(self) -> str:
            if not self.dump_payloads:
                raise AssertionError("Unexpected extra dump_ui_xml call")
            return self.dump_payloads.pop(0)

        def force_clear_search_text(self, characters: int = 32) -> None:
            self.force_clear_calls.append(characters)

        def input_keyword(self, keyword: str, pinyin: str) -> None:
            self.input_calls.append((keyword, pinyin))

        def capture_screen(self, destination: str | Path) -> Path:
            target = Path(destination)
            target.write_bytes(b"PNGDATA")
            return target

    runner = RecordingRunner(
        [
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
        ]
    )

    navigator = EndedLiveRoomNavigator(
        serial="deec9116",
        installer=FakeInstaller(),
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    target = tmp_path / "douyin-search-after-ended-room.png"
    written = navigator.search_keyword_on_search_page(
        keyword="直播带货",
        pinyin="zhibodaihuo",
        destination=target,
    )

    assert written == target
    assert target.read_bytes() == b"PNGDATA"
    assert navigator.force_clear_calls == [32]
    assert navigator.input_calls == [("直播带货", "zhibodaihuo")]
    assert runner.calls[0]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "620", "223"]
    assert runner.calls[1]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "1160", "270"]
    assert runner.calls[2]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "620", "223"]
    assert runner.calls[3]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "620", "223"]
    assert runner.calls[4]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "1179", "223"]


def test_search_keyword_tries_current_page_search_flow_before_reopening_home(tmp_path: Path) -> None:
    from douyin_navigator import DouyinNavigator

    class ReuseCurrentPageNavigator(DouyinNavigator):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.search_calls: list[tuple[str, str, str]] = []

        def dump_ui_xml(self) -> str:
            return NON_STANDARD_SEARCH_PAGE_XML

        def search_keyword_on_search_page(self, keyword: str, pinyin: str, destination: str | Path) -> Path:
            self.search_calls.append((keyword, pinyin, str(destination)))
            target = Path(destination)
            target.write_bytes(b"PNGDATA")
            return target

        def _open_search_flow(self) -> None:
            raise AssertionError("Should reuse the current page before reopening Douyin home")

    navigator = ReuseCurrentPageNavigator(
        serial="deec9116",
        installer=FakeInstaller(),
        runner=RecordingRunner([]),
        sleeper=lambda _seconds: None,
    )

    target = tmp_path / "douyin-search-reuse-current-page.png"
    written = navigator.search_keyword(
        keyword="直播带货",
        pinyin="zhibodaihuo",
        destination=target,
    )

    assert written == target
    assert target.read_bytes() == b"PNGDATA"
    assert navigator.search_calls == [("直播带货", "zhibodaihuo", str(target))]


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


def test_search_keyword_on_search_page_falls_back_to_coordinate_clear_when_dump_fails(tmp_path: Path) -> None:
    from douyin_navigator import DouyinNavigationError, DouyinNavigator

    class DumpFailNavigator(DouyinNavigator):
        def dump_ui_xml(self) -> str:
            raise DouyinNavigationError("ui dump failed")

    runner = RecordingRunner(
        [
            FakeCompletedProcess(),
            FakeCompletedProcess(),
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
            FakeCompletedProcess(stdout=b"PNGDATA"),
        ]
    )

    navigator = DumpFailNavigator(
        serial="deec9116",
        installer=FakeInstaller(),
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    target = tmp_path / "douyin-search-coordinate-fallback.png"
    written = navigator.search_keyword_on_search_page(
        keyword="直播带货",
        pinyin="zhibodaihuo",
        destination=target,
    )

    assert written == target
    assert target.read_bytes() == b"PNGDATA"
    assert runner.calls[0]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "620", "223"]
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
    assert runner.calls[3]["cmd"] == [
        "adb",
        "-s",
        "deec9116",
        "shell",
        "sh",
        "-c",
        'i=0; while [ "$i" -lt 8 ]; do input keyevent 67; i=$((i+1)); done',
    ]
    assert runner.calls[4]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "620", "223"]
    assert runner.calls[5]["cmd"] == ["adb", "-s", "deec9116", "shell", "ime", "list", "-a"]
    assert runner.calls[6]["cmd"] == ["adb", "-s", "deec9116", "shell", "settings", "get", "secure", "default_input_method"]
    assert runner.calls[11]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "1179", "223"]


def test_open_live_results_taps_live_tab_and_captures_screen(tmp_path: Path) -> None:
    from douyin_navigator import DouyinNavigator

    runner = RecordingRunner(
        [
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout=b"PNGDATA"),
        ]
    )

    navigator = DouyinNavigator(
        serial="deec9116",
        installer=FakeInstaller(),
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    target = tmp_path / "douyin-live-results.png"
    written = navigator.open_live_results(target)

    assert written == target
    assert target.read_bytes() == b"PNGDATA"
    assert runner.calls[0]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "640", "364"]
    assert runner.calls[1]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "screencap", "-p"]
    assert runner.calls[1]["text"] is False


def test_enter_first_live_room_taps_first_card_and_captures_screen(tmp_path: Path) -> None:
    from douyin_navigator import DouyinNavigator

    runner = RecordingRunner(
        [
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout=b"PNGDATA"),
        ]
    )

    navigator = DouyinNavigator(
        serial="deec9116",
        installer=FakeInstaller(),
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    target = tmp_path / "douyin-live-room.png"
    written = navigator.enter_first_live_room(target)

    assert written == target
    assert target.read_bytes() == b"PNGDATA"
    assert runner.calls[0]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "430", "1310"]
    assert runner.calls[1]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "screencap", "-p"]
    assert runner.calls[1]["text"] is False


def test_search_and_enter_first_live_room_runs_full_public_live_flow(tmp_path: Path) -> None:
    from douyin_navigator import DouyinNavigator

    class FlowNavigator(DouyinNavigator):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.actions: list[tuple[str, str, str, str]] = []

        def search_keyword(self, keyword: str, pinyin: str, destination: str | Path) -> Path:
            self.actions.append(("search", keyword, pinyin, str(destination)))
            target = Path(destination)
            target.write_bytes(b"SEARCH")
            return target

        def open_live_results(self, destination: str | Path) -> Path:
            self.actions.append(("live-results", "", "", str(destination)))
            target = Path(destination)
            target.write_bytes(b"LIVE")
            return target

        def enter_first_live_room(self, destination: str | Path) -> Path:
            self.actions.append(("enter-live-room", "", "", str(destination)))
            target = Path(destination)
            target.write_bytes(b"ROOM")
            return target

    navigator = FlowNavigator(
        serial="deec9116",
        installer=FakeInstaller(),
        runner=RecordingRunner([]),
        sleeper=lambda _seconds: None,
    )

    target = tmp_path / "douyin-live-room-final.png"
    written = navigator.search_and_enter_first_live_room(
        keyword="直播带货",
        pinyin="zhibodaihuo",
        destination=target,
    )

    assert written == target
    assert target.read_bytes() == b"ROOM"
    assert navigator.actions == [
        ("search", "直播带货", "zhibodaihuo", str(target)),
        ("live-results", "", "", str(target)),
        ("enter-live-room", "", "", str(target)),
    ]


def test_delete_text_waits_for_device_after_transient_adb_restart() -> None:
    from douyin_navigator import DouyinNavigator

    runner = RecordingRunner(
        [
            FakeCompletedProcess(returncode=1, stderr="* daemon not running; starting now at tcp:5037\n"),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
        ]
    )

    navigator = DouyinNavigator(
        serial="deec9116",
        installer=FakeInstaller(),
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    navigator.delete_text(6)

    assert runner.calls == [
        {
            "cmd": [
                "adb",
                "-s",
                "deec9116",
                "shell",
                "sh",
                "-c",
                'i=0; while [ "$i" -lt 6 ]; do input keyevent 67; i=$((i+1)); done',
            ],
            "capture_output": True,
            "text": True,
            "check": False,
            "timeout": 15.0,
        },
        {
            "cmd": ["adb", "-s", "deec9116", "wait-for-device"],
            "capture_output": True,
            "text": True,
            "check": False,
            "timeout": 15.0,
        },
        {
            "cmd": [
                "adb",
                "-s",
                "deec9116",
                "shell",
                "sh",
                "-c",
                'i=0; while [ "$i" -lt 6 ]; do input keyevent 67; i=$((i+1)); done',
            ],
            "capture_output": True,
            "text": True,
            "check": False,
            "timeout": 15.0,
        },
    ]


def test_delete_text_waits_for_device_after_device_not_found() -> None:
    from douyin_navigator import DouyinNavigator

    runner = RecordingRunner(
        [
            FakeCompletedProcess(returncode=1, stderr="adb: device 'deec9116' not found"),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
        ]
    )

    navigator = DouyinNavigator(
        serial="deec9116",
        installer=FakeInstaller(),
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    navigator.delete_text(6)

    assert runner.calls[0]["cmd"] == [
        "adb",
        "-s",
        "deec9116",
        "shell",
        "sh",
        "-c",
        'i=0; while [ "$i" -lt 6 ]; do input keyevent 67; i=$((i+1)); done',
    ]
    assert runner.calls[1]["cmd"] == ["adb", "-s", "deec9116", "wait-for-device"]
    assert runner.calls[2]["cmd"] == [
        "adb",
        "-s",
        "deec9116",
        "shell",
        "sh",
        "-c",
        'i=0; while [ "$i" -lt 6 ]; do input keyevent 67; i=$((i+1)); done',
    ]


def test_delete_text_splits_large_clear_requests_into_small_batches() -> None:
    from douyin_navigator import DouyinNavigator

    runner = RecordingRunner(
        [
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
        ]
    )

    navigator = DouyinNavigator(
        serial="deec9116",
        installer=FakeInstaller(),
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    navigator.delete_text(32)

    assert runner.calls == [
        {
            "cmd": [
                "adb",
                "-s",
                "deec9116",
                "shell",
                "sh",
                "-c",
                'i=0; while [ "$i" -lt 12 ]; do input keyevent 67; i=$((i+1)); done',
            ],
            "capture_output": True,
            "text": True,
            "check": False,
            "timeout": 15.0,
        },
        {
            "cmd": [
                "adb",
                "-s",
                "deec9116",
                "shell",
                "sh",
                "-c",
                'i=0; while [ "$i" -lt 12 ]; do input keyevent 67; i=$((i+1)); done',
            ],
            "capture_output": True,
            "text": True,
            "check": False,
            "timeout": 15.0,
        },
        {
            "cmd": [
                "adb",
                "-s",
                "deec9116",
                "shell",
                "sh",
                "-c",
                'i=0; while [ "$i" -lt 8 ]; do input keyevent 67; i=$((i+1)); done',
            ],
            "capture_output": True,
            "text": True,
            "check": False,
            "timeout": 15.0,
        },
    ]
