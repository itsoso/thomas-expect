from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess

import pytest


@dataclass
class FakeCompletedProcess:
    returncode: int = 0
    stdout: str | bytes = ""
    stderr: str = ""


class RecordingRunner:
    def __init__(self, responses: list[FakeCompletedProcess | BaseException]) -> None:
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
        next_response = self.responses.pop(0)
        if isinstance(next_response, BaseException):
            raise next_response
        return next_response


class FakeInstaller:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []
        self.launch_calls: list[str] = []

    def ensure_app(self, spec, launch_after_install: bool = True, **_kwargs):
        self.calls.append((spec.package_name, launch_after_install))

    def launch_app(self, package_name: str) -> None:
        self.launch_calls.append(package_name)


SEARCH_PAGE_XML = """\
<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="">
    <node index="0" text="" resource-id="com.smile.gifmaker:id/search_field_container" bounds="[136,152][1082,295]" clickable="true">
      <node index="0" text="直播带货qwen3.5-plus" resource-id="com.smile.gifmaker:id/editor" bounds="[175,181][932,266]" clickable="true" />
      <node index="1" text="" resource-id="com.smile.gifmaker:id/clear_layout" bounds="[965,178][1056,269]" clickable="true" />
    </node>
    <node index="1" text="搜索" resource-id="com.smile.gifmaker:id/right_tv" bounds="[1120,190][1218,256]" clickable="true" />
  </node>
</hierarchy>
"""

SEARCH_PAGE_NO_CLEAR_XML = """\
<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="">
    <node index="0" text="" resource-id="com.smile.gifmaker:id/search_field_container" bounds="[136,152][1082,295]" clickable="true">
      <node index="0" text="" resource-id="com.smile.gifmaker:id/search_layout" bounds="[136,165][1082,282]">
        <node index="0" text="" resource-id="com.smile.gifmaker:id/inside_editor_hint_layout" bounds="[175,165][932,282]" />
        <node index="1" text="" resource-id="com.smile.gifmaker:id/search_switcher" bounds="[175,165][932,282]" />
        <node index="2" text="" resource-id="com.smile.gifmaker:id/editor" bounds="[175,181][932,266]" clickable="true" />
      </node>
      <node index="1" text="" resource-id="com.smile.gifmaker:id/layout_right_icons" bounds="[965,165][1082,282]">
        <node index="0" text="" resource-id="com.smile.gifmaker:id/qrcode_layout" bounds="[965,165][1082,282]" clickable="true">
          <node index="0" text="" resource-id="com.smile.gifmaker:id/qr_code_btn" bounds="[978,191][1043,256]" clickable="true" />
        </node>
      </node>
    </node>
    <node index="1" text="搜索" resource-id="com.smile.gifmaker:id/right_tv" bounds="[1120,190][1218,256]" clickable="true" />
  </node>
</hierarchy>
"""

SEARCH_PAGE_WITH_EXPECTED_KEYWORD_XML = SEARCH_PAGE_XML.replace("直播带货qwen3.5-plus", "直播带货")
SEARCH_PAGE_WITH_MISMATCHED_KEYWORD_XML = SEARCH_PAGE_XML.replace("直播带货qwen3.5-plus", "董卿惊艳高清照片")

HOME_PAGE_WITH_PROMPT_XML = """\
<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="">
    <node index="0" text="不再提示" resource-id="com.smile.gifmaker:id/positive" bounds="[114,2460][1166,2616]" clickable="true" />
    <node index="1" text="" resource-id="com.smile.gifmaker:id/search_btn" bounds="[1121,158][1251,289]" clickable="true" />
  </node>
</hierarchy>
"""

HOME_PAGE_XML = """\
<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="">
    <node index="0" text="" resource-id="com.smile.gifmaker:id/search_btn" bounds="[1121,158][1251,289]" clickable="true" />
  </node>
</hierarchy>
"""

HOME_FEED_XML = """\
<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="">
    <node index="0" text="" resource-id="com.smile.gifmaker:id/home_activity_root" bounds="[0,0][1280,2772]">
      <node index="1" text="" resource-id="com.smile.gifmaker:id/home_fragment_container" bounds="[0,0][1280,2772]" />
      <node index="2" text="" resource-id="com.smile.gifmaker:id/swipe" bounds="[0,0][1280,2772]" />
      <node index="3" text="" resource-id="com.smile.gifmaker:id/nasa_groot_view_pager" bounds="[0,0][1280,2772]" />
    </node>
  </node>
</hierarchy>
"""

HOME_ACTIVITY_OUTPUT = (
    "  ResumedActivity: ActivityRecord{123 u0 "
    "com.smile.gifmaker/com.yxcorp.gifshow.HomeActivity t61}\n"
)

SEARCH_ACTIVITY_OUTPUT = (
    "  ResumedActivity: ActivityRecord{123 u0 "
    "com.smile.gifmaker/com.yxcorp.plugin.search.SearchActivity t61}\n"
)

SEARCH_GROUP_RESULT_XML = """\
<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="">
    <node index="0" text="" resource-id="com.smile.gifmaker:id/left_btn" bounds="[26,152][169,295]" clickable="true" />
    <node index="1" text="包含“null”的群聊" resource-id="com.smile.gifmaker:id/title_tv" bounds="[195,152][1085,295]" clickable="false" />
    <node index="2" text="" resource-id="com.smile.gifmaker:id/search_web_view" bounds="[0,295][1280,2772]" clickable="false" />
    <node index="3" text="点击重试" resource-id="com.smile.gifmaker:id/retry_btn" bounds="[458,1732][822,1862]" clickable="true" />
  </node>
</hierarchy>
"""

SEARCH_MULTIQ_XML = """\
<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="">
    <node index="0" text="" resource-id="com.smile.gifmaker:id/search_layout" bounds="[137,165][1081,282]" clickable="false">
      <node index="0" text="小莫哥" resource-id="com.smile.gifmaker:id/search_result_text" bounds="[176,171][1032,275]" clickable="true" />
      <node index="1" text="" resource-id="com.smile.gifmaker:id/clear_layout" bounds="[912,174][1081,272]" clickable="false" />
    </node>
    <node index="1" text="搜索" resource-id="com.smile.gifmaker:id/right_tv" bounds="[1081,152][1280,295]" clickable="true" />
  </node>
</hierarchy>
"""

SEARCH_RESULTS_XML = """\
<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="">
    <node index="0" text="" resource-id="com.smile.gifmaker:id/search_result_view" bounds="[0,0][1280,2772]">
      <node index="0" text="" resource-id="com.smile.gifmaker:id/top_container" bounds="[0,0][1280,440]">
        <node index="0" text="" resource-id="com.smile.gifmaker:id/result_bar" bounds="[0,0][1280,295]">
          <node index="0" text="" resource-id="com.smile.gifmaker:id/title_root" bounds="[0,152][1280,295]">
            <node index="0" text="" resource-id="com.smile.gifmaker:id/search_layout" bounds="[137,165][1081,282]">
              <node index="0" text="" resource-id="com.smile.gifmaker:id/inside_editor_hint_layout" bounds="[176,165][1048,282]" />
              <node index="1" text="233乐园游戏下载" resource-id="com.smile.gifmaker:id/search_result_text" bounds="[176,171][1032,275]" clickable="true" />
              <node index="2" text="" resource-id="com.smile.gifmaker:id/clear_layout" bounds="[912,174][1081,272]">
                <node index="0" text="" resource-id="com.smile.gifmaker:id/clear_button" bounds="[977,190][1042,255]" clickable="true" />
              </node>
            </node>
            <node index="1" text="搜索" resource-id="com.smile.gifmaker:id/right_tv" bounds="[1081,152][1280,295]" clickable="true" />
          </node>
        </node>
        <node index="1" text="" resource-id="com.smile.gifmaker:id/tab_container" bounds="[0,295][1280,438]" />
      </node>
      <node index="1" text="" resource-id="com.smile.gifmaker:id/view_pager" bounds="[0,440][1280,2772]">
        <node index="0" text="" resource-id="com.smile.gifmaker:id/search_web_view" bounds="[0,602][1280,2772]" />
        <node index="1" text="" resource-id="com.smile.gifmaker:id/recycler_view" bounds="[0,602][1280,2772]" />
      </node>
    </node>
  </node>
</hierarchy>
"""

ADB_KEYBOARD_LIST_OUTPUT = """\
mId=com.android.adbkeyboard/.AdbIME mSettingsActivityName=null mIsVrOnly=false mSupportsSwitchingToNextInputMethod=true
mId=com.sohu.inputmethod.sogou.xiaomi/.SogouIME mSettingsActivityName=com.sohu.inputmethod.sogou.SogouIMESettingsLaunchActivity mIsVrOnly=false mSupportsSwitchingToNextInputMethod=true
"""

NO_ADB_KEYBOARD_LIST_OUTPUT = """\
mId=com.sohu.inputmethod.sogou.xiaomi/.SogouIME mSettingsActivityName=com.sohu.inputmethod.sogou.SogouIMESettingsLaunchActivity mIsVrOnly=false mSupportsSwitchingToNextInputMethod=true
"""


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
    assert installer.calls == []
    assert installer.launch_calls == ["com.smile.gifmaker"]
    assert runner.calls[0]["cmd"] == ["adb", "-s", "deec9116", "shell", "dumpsys", "activity", "activities"]
    assert runner.calls[1]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "1186", "223"]
    assert runner.calls[2]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "screencap", "-p"]
    assert runner.calls[2]["text"] is False


def test_open_search_falls_back_to_install_check_when_direct_launch_fails(tmp_path: Path) -> None:
    from kuaishou_navigator import KuaishouNavigator
    from mobile_app_installer import AppInstallError

    installer = FakeInstaller()
    failed_once = False

    def launch_once_then_succeed(package_name: str) -> None:
        nonlocal failed_once
        installer.launch_calls.append(package_name)
        if not failed_once:
            failed_once = True
            raise AppInstallError("launch failed")

    installer.launch_app = launch_once_then_succeed  # type: ignore[method-assign]
    runner = RecordingRunner(
        [
            FakeCompletedProcess(stdout=HOME_ACTIVITY_OUTPUT),
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

    target = tmp_path / "search-fallback.png"
    written = navigator.open_search(target)

    assert written == target
    assert target.read_bytes() == b"PNGDATA"
    assert installer.calls == [("com.smile.gifmaker", False)]
    assert installer.launch_calls == ["com.smile.gifmaker", "com.smile.gifmaker"]


def test_capture_screen_retries_when_first_screencap_is_empty(tmp_path: Path) -> None:
    from kuaishou_navigator import KuaishouNavigator

    runner = RecordingRunner(
        [
            FakeCompletedProcess(stdout=b""),
            FakeCompletedProcess(stdout=b"PNGDATA"),
        ]
    )

    navigator = KuaishouNavigator(
        serial="deec9116",
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    target = tmp_path / "capture.png"
    written = navigator.capture_screen(target)

    assert written == target
    assert target.read_bytes() == b"PNGDATA"
    assert runner.calls[0]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "screencap", "-p"]
    assert runner.calls[1]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "screencap", "-p"]


def test_capture_screen_falls_back_to_device_file_when_direct_exec_out_fails(tmp_path: Path) -> None:
    from kuaishou_navigator import KuaishouNavigator

    runner = RecordingRunner(
        [
            FakeCompletedProcess(returncode=1, stdout=b"", stderr="direct screencap failed"),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout=b"PNGDATA"),
            FakeCompletedProcess(),
        ]
    )

    navigator = KuaishouNavigator(
        serial="deec9116",
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    target = tmp_path / "kuaishou-fallback-shot.png"
    written = navigator.capture_screen(target)

    assert written == target
    assert target.read_bytes() == b"PNGDATA"
    assert runner.calls[0]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "screencap", "-p"]
    assert runner.calls[1]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "screencap", "-p"]
    assert runner.calls[2]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "screencap", "-p"]
    assert runner.calls[3]["cmd"] == [
        "adb",
        "-s",
        "deec9116",
        "shell",
        "screencap",
        "-p",
        "/sdcard/kuaishou_capture.png",
    ]
    assert runner.calls[4]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "cat", "/sdcard/kuaishou_capture.png"]
    assert runner.calls[5]["cmd"] == ["adb", "-s", "deec9116", "shell", "rm", "-f", "/sdcard/kuaishou_capture.png"]


def test_capture_screen_accepts_partial_png_payload_even_with_transient_returncode(tmp_path: Path) -> None:
    from kuaishou_navigator import KuaishouNavigator

    runner = RecordingRunner(
        [
            FakeCompletedProcess(returncode=-15, stdout=b"\x89PNG\r\n\x1a\nPNGDATA"),
        ]
    )

    navigator = KuaishouNavigator(
        serial="deec9116",
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    target = tmp_path / "partial-png.png"
    written = navigator.capture_screen(target)

    assert written == target
    assert target.read_bytes() == b"\x89PNG\r\n\x1a\nPNGDATA"
    assert len(runner.calls) == 1
    assert runner.calls[0]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "screencap", "-p"]


def test_capture_screen_via_device_file_accepts_transient_screencap_when_file_exists(tmp_path: Path) -> None:
    from kuaishou_navigator import KuaishouNavigator

    navigator = KuaishouNavigator(
        serial="deec9116",
        runner=RecordingRunner([]),
        sleeper=lambda _seconds: None,
    )

    responses = [
        FakeCompletedProcess(returncode=-15, stderr="* daemon not running; starting now at tcp:5037"),
        FakeCompletedProcess(
            returncode=0,
            stdout="-rw-rw---- 1 u0_a241 media_rw 2173569 2026-03-12 14:25 /sdcard/kuaishou_capture.png\n",
        ),
        FakeCompletedProcess(stdout=b"PNGDATA"),
        FakeCompletedProcess(),
    ]
    commands: list[tuple[str, ...]] = []

    def fake_run(*args: str, **_kwargs):
        commands.append(args)
        if not responses:
            raise AssertionError(f"Missing fake response for command: {args}")
        return responses.pop(0)

    navigator._run = fake_run  # type: ignore[method-assign]

    target = tmp_path / "kuaishou-existing-file-shot.png"
    written = navigator.capture_screen_via_device_file(target)

    assert written == target
    assert target.read_bytes() == b"PNGDATA"
    assert commands == [
        ("shell", "screencap", "-p", "/sdcard/kuaishou_capture.png"),
        ("shell", "ls", "-l", "/sdcard/kuaishou_capture.png"),
        ("exec-out", "cat", "/sdcard/kuaishou_capture.png"),
        ("shell", "rm", "-f", "/sdcard/kuaishou_capture.png"),
    ]


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


def test_run_retries_transient_adb_startup_error() -> None:
    from kuaishou_navigator import KuaishouNavigator

    runner = RecordingRunner(
        [
            FakeCompletedProcess(returncode=-15, stderr="* daemon not running; starting now at tcp:5037"),
            FakeCompletedProcess(stdout=""),
            FakeCompletedProcess(stdout="device"),
        ]
    )

    navigator = KuaishouNavigator(
        serial="deec9116",
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    result = navigator._run("get-state")

    assert result.stdout == "device"
    assert len(runner.calls) == 3
    assert runner.calls[0]["cmd"] == ["adb", "-s", "deec9116", "get-state"]
    assert runner.calls[1]["cmd"] == ["adb", "-s", "deec9116", "wait-for-device"]
    assert runner.calls[2]["cmd"] == ["adb", "-s", "deec9116", "get-state"]


def test_run_accepts_success_even_with_daemon_startup_stderr() -> None:
    from kuaishou_navigator import KuaishouNavigator

    runner = RecordingRunner(
        [
            FakeCompletedProcess(returncode=0, stdout="device", stderr="* daemon started successfully\n"),
        ]
    )

    navigator = KuaishouNavigator(
        serial="deec9116",
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    result = navigator._run("get-state")

    assert result.stdout == "device"
    assert len(runner.calls) == 1
    assert runner.calls[0]["cmd"] == ["adb", "-s", "deec9116", "get-state"]


def test_run_retries_timeout_expired_after_waiting_for_device() -> None:
    from kuaishou_navigator import KuaishouNavigator

    runner = RecordingRunner(
        [
            subprocess.TimeoutExpired(cmd=["adb", "-s", "deec9116", "get-state"], timeout=15.0),
            FakeCompletedProcess(stdout=""),
            FakeCompletedProcess(stdout="device"),
        ]
    )

    navigator = KuaishouNavigator(
        serial="deec9116",
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    result = navigator._run("get-state")

    assert result.stdout == "device"
    assert len(runner.calls) == 3
    assert runner.calls[0]["cmd"] == ["adb", "-s", "deec9116", "get-state"]
    assert runner.calls[0]["timeout"] == 15.0
    assert runner.calls[1]["cmd"] == ["adb", "-s", "deec9116", "wait-for-device"]
    assert runner.calls[2]["cmd"] == ["adb", "-s", "deec9116", "get-state"]


def test_search_keyword_on_search_page_clears_inputs_and_submits(tmp_path: Path) -> None:
    from kuaishou_navigator import KuaishouNavigator

    installer = FakeInstaller()
    runner = RecordingRunner(
        [
            FakeCompletedProcess(
                returncode=-15,
                stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n",
                stderr="* daemon not running; starting now at tcp:5037\n* daemon started successfully\n",
            ),
            FakeCompletedProcess(stdout=SEARCH_PAGE_XML),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout=NO_ADB_KEYBOARD_LIST_OUTPUT),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
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

    target = tmp_path / "kuaishou-search-result.png"
    written = navigator.search_keyword_on_search_page(
        keyword="直播带货",
        pinyin="zhibodaihuo",
        destination=target,
    )

    assert written == target
    assert target.read_bytes() == b"PNGDATA"
    assert installer.calls == [("com.smile.gifmaker", True)]
    assert runner.calls[0]["cmd"] == ["adb", "-s", "deec9116", "shell", "uiautomator", "dump", "/sdcard/kuaishou_nav.xml"]
    assert runner.calls[1]["cmd"] == ["adb", "-s", "deec9116", "shell", "cat", "/sdcard/kuaishou_nav.xml"]
    assert runner.calls[2]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "1010", "223"]
    assert runner.calls[3]["cmd"] == ["adb", "-s", "deec9116", "shell", "ime", "list", "-a"]
    assert runner.calls[4]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "text", "zhibodaihuo"]
    assert runner.calls[5]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "keyevent", "62"]
    assert runner.calls[6]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "1169", "223"]
    assert runner.calls[7]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "screencap", "-p"]
    assert runner.calls[7]["text"] is False


def test_search_keyword_on_search_page_prefers_adb_keyboard_for_unicode_text(tmp_path: Path) -> None:
    from kuaishou_navigator import ADB_KEYBOARD_IME, KuaishouNavigator

    installer = FakeInstaller()
    runner = RecordingRunner(
        [
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=SEARCH_PAGE_XML),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout=ADB_KEYBOARD_LIST_OUTPUT),
            FakeCompletedProcess(stdout="com.sohu.inputmethod.sogou.xiaomi/.SogouIME\n"),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=SEARCH_PAGE_WITH_EXPECTED_KEYWORD_XML),
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

    target = tmp_path / "kuaishou-search-result.png"
    written = navigator.search_keyword_on_search_page(
        keyword="直播带货",
        pinyin="zhibodaihuo",
        destination=target,
    )

    assert written == target
    assert target.read_bytes() == b"PNGDATA"
    assert installer.calls == [("com.smile.gifmaker", True)]
    assert runner.calls[3]["cmd"] == ["adb", "-s", "deec9116", "shell", "ime", "list", "-a"]
    assert runner.calls[4]["cmd"] == ["adb", "-s", "deec9116", "shell", "settings", "get", "secure", "default_input_method"]
    assert runner.calls[5]["cmd"] == ["adb", "-s", "deec9116", "shell", "ime", "enable", ADB_KEYBOARD_IME]
    assert runner.calls[6]["cmd"] == ["adb", "-s", "deec9116", "shell", "ime", "set", ADB_KEYBOARD_IME]
    assert runner.calls[7]["cmd"][:8] == [
        "adb",
        "-s",
        "deec9116",
        "shell",
        "am",
        "broadcast",
        "-a",
        "ADB_INPUT_B64",
    ]
    assert runner.calls[7]["cmd"][8:10] == ["--es", "msg"]
    assert runner.calls[8]["cmd"] == [
        "adb",
        "-s",
        "deec9116",
        "shell",
        "ime",
        "set",
        "com.sohu.inputmethod.sogou.xiaomi/.SogouIME",
    ]
    assert runner.calls[9]["cmd"] == ["adb", "-s", "deec9116", "shell", "uiautomator", "dump", "/sdcard/kuaishou_nav.xml"]
    assert runner.calls[10]["cmd"] == ["adb", "-s", "deec9116", "shell", "cat", "/sdcard/kuaishou_nav.xml"]
    assert runner.calls[11]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "1169", "223"]
    assert runner.calls[12]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "screencap", "-p"]


def test_search_keyword_on_search_page_skips_retyping_when_keyword_already_matches(tmp_path: Path) -> None:
    from kuaishou_navigator import KuaishouNavigator

    installer = FakeInstaller()
    runner = RecordingRunner(
        [
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=SEARCH_PAGE_WITH_EXPECTED_KEYWORD_XML),
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

    target = tmp_path / "kuaishou-search-already-matched.png"
    written = navigator.search_keyword_on_search_page(
        keyword="直播带货",
        pinyin="zhibodaihuo",
        destination=target,
    )

    assert written == target
    assert target.read_bytes() == b"PNGDATA"
    assert runner.calls[0]["cmd"] == ["adb", "-s", "deec9116", "shell", "uiautomator", "dump", "/sdcard/kuaishou_nav.xml"]
    assert runner.calls[1]["cmd"] == ["adb", "-s", "deec9116", "shell", "cat", "/sdcard/kuaishou_nav.xml"]
    assert runner.calls[2]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "1169", "223"]
    assert runner.calls[3]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "screencap", "-p"]
    assert len(runner.calls) == 4


def test_search_keyword_on_search_page_falls_back_to_pinyin_when_adb_keyboard_switch_fails(tmp_path: Path) -> None:
    from kuaishou_navigator import KuaishouNavigator

    installer = FakeInstaller()
    runner = RecordingRunner(
        [
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=SEARCH_PAGE_NO_CLEAR_XML),
            FakeCompletedProcess(stdout=ADB_KEYBOARD_LIST_OUTPUT),
            FakeCompletedProcess(stdout="com.tencent.wetype/.plugin.hld.WxHldService\n"),
            FakeCompletedProcess(),
            FakeCompletedProcess(returncode=1, stderr="Failed to switch input method"),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
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

    target = tmp_path / "kuaishou-search-fallback.png"
    written = navigator.search_keyword_on_search_page(
        keyword="直播带货",
        pinyin="zhibodaihuo",
        destination=target,
    )

    assert written == target
    assert target.read_bytes() == b"PNGDATA"
    assert runner.calls[2]["cmd"] == ["adb", "-s", "deec9116", "shell", "ime", "list", "-a"]
    assert runner.calls[3]["cmd"] == ["adb", "-s", "deec9116", "shell", "settings", "get", "secure", "default_input_method"]
    assert runner.calls[4]["cmd"] == ["adb", "-s", "deec9116", "shell", "ime", "enable", "com.android.adbkeyboard/.AdbIME"]
    assert runner.calls[5]["cmd"] == ["adb", "-s", "deec9116", "shell", "ime", "set", "com.android.adbkeyboard/.AdbIME"]
    assert runner.calls[6]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "text", "zhibodaihuo"]
    assert runner.calls[7]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "keyevent", "62"]


def test_search_keyword_on_search_page_retries_with_pinyin_when_adb_keyboard_text_is_wrong(tmp_path: Path) -> None:
    from kuaishou_navigator import KuaishouNavigator

    installer = FakeInstaller()
    runner = RecordingRunner(
        [
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=SEARCH_PAGE_XML),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout=ADB_KEYBOARD_LIST_OUTPUT),
            FakeCompletedProcess(stdout="com.sohu.inputmethod.sogou.xiaomi/.SogouIME\n"),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=SEARCH_PAGE_WITH_MISMATCHED_KEYWORD_XML),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
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

    target = tmp_path / "kuaishou-search-retry.png"
    written = navigator.search_keyword_on_search_page(
        keyword="直播带货",
        pinyin="zhibodaihuo",
        destination=target,
    )

    assert written == target
    assert target.read_bytes() == b"PNGDATA"
    assert runner.calls[9]["cmd"] == ["adb", "-s", "deec9116", "shell", "uiautomator", "dump", "/sdcard/kuaishou_nav.xml"]
    assert runner.calls[10]["cmd"] == ["adb", "-s", "deec9116", "shell", "cat", "/sdcard/kuaishou_nav.xml"]
    assert runner.calls[11]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "1010", "223"]
    assert runner.calls[12]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "text", "zhibodaihuo"]
    assert runner.calls[13]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "keyevent", "62"]
    assert runner.calls[14]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "1169", "223"]


def test_search_keyword_on_search_page_uses_search_result_text_when_editor_is_missing(tmp_path: Path) -> None:
    from kuaishou_navigator import KuaishouNavigator

    installer = FakeInstaller()
    runner = RecordingRunner(
        [
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=SEARCH_MULTIQ_XML),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout=NO_ADB_KEYBOARD_LIST_OUTPUT),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
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

    target = tmp_path / "kuaishou-search-result.png"
    written = navigator.search_keyword_on_search_page(
        keyword="直播带货",
        pinyin="zhibodaihuo",
        destination=target,
    )

    assert written == target
    assert target.read_bytes() == b"PNGDATA"
    assert runner.calls[2]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "996", "223"]
    assert runner.calls[3]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "604", "223"]


def test_search_keyword_on_search_page_submits_when_clear_button_is_missing(tmp_path: Path) -> None:
    from kuaishou_navigator import KuaishouNavigator

    installer = FakeInstaller()
    runner = RecordingRunner(
        [
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=SEARCH_PAGE_NO_CLEAR_XML),
            FakeCompletedProcess(stdout=NO_ADB_KEYBOARD_LIST_OUTPUT),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
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

    target = tmp_path / "kuaishou-search-no-clear.png"
    written = navigator.search_keyword_on_search_page(
        keyword="直播带货",
        pinyin="zhibodaihuo",
        destination=target,
    )

    assert written == target
    assert target.read_bytes() == b"PNGDATA"
    assert runner.calls[2]["cmd"] == ["adb", "-s", "deec9116", "shell", "ime", "list", "-a"]
    assert runner.calls[5]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "1169", "223"]


def test_is_search_page_returns_false_for_search_results_surface() -> None:
    from kuaishou_navigator import KuaishouNavigator

    navigator = KuaishouNavigator(runner=RecordingRunner([]))

    assert navigator._is_search_page(SEARCH_RESULTS_XML) is False


def test_ensure_search_page_recovers_from_search_results_surface() -> None:
    from kuaishou_navigator import KuaishouNavigator

    installer = FakeInstaller()
    runner = RecordingRunner(
        [
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=SEARCH_RESULTS_XML),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=SEARCH_PAGE_XML),
        ]
    )

    navigator = KuaishouNavigator(
        serial="deec9116",
        installer=installer,
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    ui_xml = navigator.ensure_search_page_ui()

    assert ui_xml.strip() == SEARCH_PAGE_XML.strip()
    assert installer.calls == [("com.smile.gifmaker", True)]
    assert runner.calls[2]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "604", "223"]


def test_dump_ui_xml_falls_back_to_cat_after_transient_dump_failure() -> None:
    from kuaishou_navigator import KuaishouNavigator

    runner = RecordingRunner(
        [
            FakeCompletedProcess(
                returncode=1,
                stderr="* daemon not running; starting now at tcp:5037\n* daemon started successfully\n",
            ),
            FakeCompletedProcess(stdout=SEARCH_PAGE_XML),
        ]
    )

    navigator = KuaishouNavigator(
        serial="deec9116",
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    xml = navigator.dump_ui_xml()

    assert xml.strip() == SEARCH_PAGE_XML.strip()
    assert runner.calls[0]["cmd"] == ["adb", "-s", "deec9116", "shell", "uiautomator", "dump", "/sdcard/kuaishou_nav.xml"]
    assert runner.calls[1]["cmd"] == ["adb", "-s", "deec9116", "shell", "cat", "/sdcard/kuaishou_nav.xml"]


def test_search_keyword_dismisses_home_prompt_and_opens_search_page(tmp_path: Path) -> None:
    from kuaishou_navigator import KuaishouNavigator

    installer = FakeInstaller()
    runner = RecordingRunner(
        [
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=HOME_PAGE_WITH_PROMPT_XML),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=HOME_PAGE_XML),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=SEARCH_PAGE_XML),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout=NO_ADB_KEYBOARD_LIST_OUTPUT),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
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

    target = tmp_path / "kuaishou-search-opened.png"
    written = navigator.search_keyword(
        keyword="直播带货",
        pinyin="zhibodaihuo",
        destination=target,
    )

    assert written == target
    assert target.read_bytes() == b"PNGDATA"
    assert installer.calls == [("com.smile.gifmaker", True)]
    assert runner.calls[2]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "640", "2538"]
    assert runner.calls[5]["cmd"] == [
        "adb",
        "-s",
        "deec9116",
        "shell",
        "am",
        "start",
        "-W",
        "-n",
        "com.smile.gifmaker/com.yxcorp.plugin.search.SearchActivity",
    ]
    assert runner.calls[8]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "1010", "223"]
    assert runner.calls[12]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "1169", "223"]
    assert runner.calls[13]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "screencap", "-p"]


def test_dump_ui_xml_retries_when_cat_returns_non_xml() -> None:
    from kuaishou_navigator import KuaishouNavigator

    runner = RecordingRunner(
        [
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=""),
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=SEARCH_PAGE_XML),
        ]
    )

    navigator = KuaishouNavigator(
        serial="deec9116",
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    xml = navigator.dump_ui_xml()

    assert xml.strip() == SEARCH_PAGE_XML.strip()
    assert runner.calls[0]["cmd"] == ["adb", "-s", "deec9116", "shell", "uiautomator", "dump", "/sdcard/kuaishou_nav.xml"]
    assert runner.calls[1]["cmd"] == ["adb", "-s", "deec9116", "shell", "cat", "/sdcard/kuaishou_nav.xml"]
    assert runner.calls[2]["cmd"] == ["adb", "-s", "deec9116", "shell", "uiautomator", "dump", "/sdcard/kuaishou_nav.xml"]
    assert runner.calls[3]["cmd"] == ["adb", "-s", "deec9116", "shell", "cat", "/sdcard/kuaishou_nav.xml"]


def test_dump_ui_xml_survives_three_empty_reads_before_success() -> None:
    from kuaishou_navigator import KuaishouNavigator

    runner = RecordingRunner(
        [
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=""),
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=""),
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=""),
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=SEARCH_PAGE_XML),
        ]
    )

    navigator = KuaishouNavigator(
        serial="deec9116",
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    xml = navigator.dump_ui_xml()

    assert xml.strip() == SEARCH_PAGE_XML.strip()
    assert len(runner.calls) == 8


def test_dump_ui_xml_retries_when_cat_temporarily_loses_device() -> None:
    from kuaishou_navigator import KuaishouNavigator

    runner = RecordingRunner(
        [
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(returncode=1, stderr="adb: device 'deec9116' not found\n"),
            FakeCompletedProcess(stdout=""),
            FakeCompletedProcess(stdout=SEARCH_PAGE_XML),
        ]
    )

    navigator = KuaishouNavigator(
        serial="deec9116",
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    xml = navigator.dump_ui_xml()

    assert xml.strip() == SEARCH_PAGE_XML.strip()
    assert runner.calls[0]["cmd"] == ["adb", "-s", "deec9116", "shell", "uiautomator", "dump", "/sdcard/kuaishou_nav.xml"]
    assert runner.calls[1]["cmd"] == ["adb", "-s", "deec9116", "shell", "cat", "/sdcard/kuaishou_nav.xml"]
    assert runner.calls[2]["cmd"] == ["adb", "-s", "deec9116", "wait-for-device"]
    assert runner.calls[3]["cmd"] == ["adb", "-s", "deec9116", "shell", "cat", "/sdcard/kuaishou_nav.xml"]


def test_search_keyword_writes_trace_file_when_trace_dir_is_enabled(tmp_path: Path) -> None:
    from kuaishou_navigator import KuaishouNavigator

    installer = FakeInstaller()
    runner = RecordingRunner(
        [
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=HOME_PAGE_WITH_PROMPT_XML),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=HOME_PAGE_XML),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=SEARCH_PAGE_XML),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout=NO_ADB_KEYBOARD_LIST_OUTPUT),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout=b"PNGDATA"),
        ]
    )

    trace_dir = tmp_path / "trace"
    navigator = KuaishouNavigator(
        serial="deec9116",
        installer=installer,
        runner=runner,
        sleeper=lambda _seconds: None,
        trace_dir=trace_dir,
    )

    navigator.search_keyword(
        keyword="直播带货",
        pinyin="zhibodaihuo",
        destination=tmp_path / "result.png",
    )

    trace_file = trace_dir / "trace.jsonl"
    assert trace_file.exists()
    events = [json.loads(line)["event"] for line in trace_file.read_text().splitlines()]
    assert "search_keyword.start" in events
    assert "ui_state" in events
    assert "search_keyword.submit" in events


def test_search_keyword_falls_back_to_home_search_when_activity_launch_is_denied(tmp_path: Path) -> None:
    from kuaishou_navigator import KuaishouNavigator

    installer = FakeInstaller()
    runner = RecordingRunner(
        [
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=HOME_PAGE_XML),
            FakeCompletedProcess(returncode=255, stderr="SecurityException"),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=SEARCH_PAGE_XML),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout=NO_ADB_KEYBOARD_LIST_OUTPUT),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
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

    written = navigator.search_keyword(
        keyword="直播带货",
        pinyin="zhibodaihuo",
        destination=tmp_path / "result.png",
    )

    assert written == tmp_path / "result.png"
    assert installer.calls == [("com.smile.gifmaker", True)]
    assert runner.calls[2]["cmd"] == [
        "adb",
        "-s",
        "deec9116",
        "shell",
        "am",
        "start",
        "-W",
        "-n",
        "com.smile.gifmaker/com.yxcorp.plugin.search.SearchActivity",
    ]
    assert runner.calls[3]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "1186", "223"]


def test_search_keyword_taps_default_home_search_hotspot_when_feed_has_no_search_id(tmp_path: Path) -> None:
    from kuaishou_navigator import KuaishouNavigator

    installer = FakeInstaller()
    runner = RecordingRunner(
        [
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=HOME_FEED_XML),
            FakeCompletedProcess(returncode=255, stderr="SecurityException"),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=SEARCH_PAGE_XML),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout=NO_ADB_KEYBOARD_LIST_OUTPUT),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
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

    written = navigator.search_keyword(
        keyword="直播带货",
        pinyin="zhibodaihuo",
        destination=tmp_path / "result.png",
    )

    assert written == tmp_path / "result.png"
    assert installer.calls == [("com.smile.gifmaker", True)]
    assert runner.calls[2]["cmd"] == [
        "adb",
        "-s",
        "deec9116",
        "shell",
        "am",
        "start",
        "-W",
        "-n",
        "com.smile.gifmaker/com.yxcorp.plugin.search.SearchActivity",
    ]
    assert runner.calls[3]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "1186", "223"]


def test_search_keyword_force_stops_when_launch_starts_in_search_group_result(tmp_path: Path) -> None:
    from kuaishou_navigator import KuaishouNavigator

    installer = FakeInstaller()
    runner = RecordingRunner(
        [
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=SEARCH_GROUP_RESULT_XML),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=HOME_PAGE_XML),
            FakeCompletedProcess(returncode=255, stderr="SecurityException"),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=SEARCH_PAGE_XML),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout=NO_ADB_KEYBOARD_LIST_OUTPUT),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
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

    written = navigator.search_keyword(
        keyword="直播带货",
        pinyin="zhibodaihuo",
        destination=tmp_path / "result.png",
    )

    assert written == tmp_path / "result.png"
    assert installer.calls == [("com.smile.gifmaker", True)]
    assert installer.launch_calls == ["com.smile.gifmaker"]
    assert runner.calls[2]["cmd"] == ["adb", "-s", "deec9116", "shell", "am", "force-stop", "com.smile.gifmaker"]
    assert runner.calls[5]["cmd"] == [
        "adb",
        "-s",
        "deec9116",
        "shell",
        "am",
        "start",
        "-W",
        "-n",
        "com.smile.gifmaker/com.yxcorp.plugin.search.SearchActivity",
    ]
    assert runner.calls[6]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "1186", "223"]


def test_search_keyword_uses_home_activity_fallback_when_initial_dump_is_empty(tmp_path: Path) -> None:
    from kuaishou_navigator import KuaishouNavigator

    installer = FakeInstaller()
    runner = RecordingRunner(
        [
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=""),
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=""),
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=""),
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=""),
            FakeCompletedProcess(stdout=HOME_ACTIVITY_OUTPUT),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=SEARCH_PAGE_XML),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout=NO_ADB_KEYBOARD_LIST_OUTPUT),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
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

    written = navigator.search_keyword(
        keyword="直播带货",
        pinyin="zhibodaihuo",
        destination=tmp_path / "result.png",
    )

    assert written == tmp_path / "result.png"
    assert installer.calls == [("com.smile.gifmaker", True)]
    assert runner.calls[8]["cmd"] == ["adb", "-s", "deec9116", "shell", "dumpsys", "activity", "activities"]
    assert runner.calls[9]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "1186", "223"]


def test_search_keyword_uses_activity_only_search_fallback_when_search_activity_has_no_xml(tmp_path: Path) -> None:
    from kuaishou_navigator import KuaishouNavigator

    installer = FakeInstaller()
    runner = RecordingRunner(
        [
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=""),
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=""),
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=""),
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=""),
            FakeCompletedProcess(stdout=HOME_ACTIVITY_OUTPUT),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=""),
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=""),
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=""),
            FakeCompletedProcess(stdout="UI hierchary dumped to: /sdcard/kuaishou_nav.xml\n"),
            FakeCompletedProcess(stdout=""),
            FakeCompletedProcess(stdout=SEARCH_ACTIVITY_OUTPUT),
            FakeCompletedProcess(stdout=NO_ADB_KEYBOARD_LIST_OUTPUT),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
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

    written = navigator.search_keyword(
        keyword="直播带货",
        pinyin="zhibodaihuo",
        destination=tmp_path / "result.png",
    )

    assert written == tmp_path / "result.png"
    assert installer.calls == [("com.smile.gifmaker", True)]
    assert runner.calls[18]["cmd"] == ["adb", "-s", "deec9116", "shell", "dumpsys", "activity", "activities"]
    assert runner.calls[19]["cmd"] == ["adb", "-s", "deec9116", "shell", "ime", "list", "-a"]
    assert runner.calls[20]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "text", "zhibodaihuo"]
    assert runner.calls[21]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "keyevent", "62"]
    assert runner.calls[22]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "keyevent", "66"]


def test_open_live_results_taps_live_tab_and_captures_screen(tmp_path: Path) -> None:
    from kuaishou_navigator import KuaishouNavigator

    runner = RecordingRunner(
        [
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout=b"PNGDATA"),
        ]
    )

    navigator = KuaishouNavigator(
        serial="deec9116",
        installer=FakeInstaller(),
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    target = tmp_path / "kuaishou-live-results.png"
    written = navigator.open_live_results(target)

    assert written == target
    assert target.read_bytes() == b"PNGDATA"
    assert runner.calls[0]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "246", "366"]
    assert runner.calls[1]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "screencap", "-p"]
    assert runner.calls[1]["text"] is False


def test_enter_first_live_room_taps_first_card_and_captures_screen(tmp_path: Path) -> None:
    from kuaishou_navigator import KuaishouNavigator

    runner = RecordingRunner(
        [
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(stdout=b"PNGDATA"),
        ]
    )

    navigator = KuaishouNavigator(
        serial="deec9116",
        installer=FakeInstaller(),
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    target = tmp_path / "kuaishou-live-room.png"
    written = navigator.enter_first_live_room(target)

    assert written == target
    assert target.read_bytes() == b"PNGDATA"
    assert runner.calls[0]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "420", "960"]
    assert runner.calls[1]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "930", "1030"]
    assert runner.calls[2]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "screencap", "-p"]
    assert runner.calls[2]["text"] is False


def test_search_and_enter_first_live_room_runs_full_public_live_flow(tmp_path: Path) -> None:
    from kuaishou_navigator import KuaishouNavigator

    class FlowNavigator(KuaishouNavigator):
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

    target = tmp_path / "kuaishou-live-room-final.png"
    written = navigator.search_and_enter_first_live_room(
        keyword="美女直播",
        pinyin="meinvzhibo",
        destination=target,
    )

    assert written == target
    assert target.read_bytes() == b"ROOM"
    assert navigator.actions == [
        ("search", "美女直播", "meinvzhibo", str(target)),
        ("live-results", "", "", str(target)),
        ("enter-live-room", "", "", str(target)),
    ]
