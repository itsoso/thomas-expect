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


def test_run_retries_transient_adb_startup_error() -> None:
    from kuaishou_navigator import KuaishouNavigator

    runner = RecordingRunner(
        [
            FakeCompletedProcess(returncode=-15, stderr="* daemon not running; starting now at tcp:5037"),
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
    assert len(runner.calls) == 2
    assert runner.calls[0]["cmd"] == ["adb", "-s", "deec9116", "get-state"]
    assert runner.calls[1]["cmd"] == ["adb", "-s", "deec9116", "get-state"]


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
    assert runner.calls[3]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "553", "223"]
    assert runner.calls[4]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "text", "zhibodaihuo"]
    assert runner.calls[5]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "keyevent", "62"]
    assert runner.calls[6]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "1169", "223"]
    assert runner.calls[7]["cmd"] == ["adb", "-s", "deec9116", "exec-out", "screencap", "-p"]
    assert runner.calls[7]["text"] is False


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
    assert runner.calls[5]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "1186", "223"]
    assert runner.calls[8]["cmd"] == ["adb", "-s", "deec9116", "shell", "input", "tap", "1010", "223"]
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
