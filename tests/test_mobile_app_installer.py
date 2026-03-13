from __future__ import annotations

from dataclasses import dataclass

import pytest


@dataclass
class FakeCompletedProcess:
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


class RecordingRunner:
    def __init__(self, responses: list[FakeCompletedProcess]) -> None:
        self.responses = list(responses)
        self.calls: list[list[str]] = []

    def __call__(self, cmd: list[str], capture_output: bool = True, text: bool = True, check: bool = False):
        self.calls.append(cmd)
        if not self.responses:
            raise AssertionError(f"Missing fake response for command: {cmd}")
        return self.responses.pop(0)


class IncrementingClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        current = self.value
        self.value += 1.0
        return current


def test_ensure_app_when_already_installed_only_launches_once() -> None:
    from mobile_app_installer import AndroidAppInstaller, AppSpec

    runner = RecordingRunner(
        [
            FakeCompletedProcess(stdout="device\n"),
            FakeCompletedProcess(returncode=0, stdout="package:/data/app/base.apk\n"),
            FakeCompletedProcess(returncode=0, stdout="Events injected: 1\n"),
        ]
    )

    installer = AndroidAppInstaller(runner=runner)
    result = installer.ensure_app(AppSpec(name="支付宝", package_name="com.eg.android.AlipayGphone"))

    assert result.status == "already-installed"
    assert result.package_name == "com.eg.android.AlipayGphone"
    assert runner.calls == [
        ["adb", "get-state"],
        ["adb", "shell", "pm", "path", "com.eg.android.AlipayGphone"],
        [
            "adb",
            "shell",
            "monkey",
            "-p",
            "com.eg.android.AlipayGphone",
            "-c",
            "android.intent.category.LAUNCHER",
            "1",
        ],
    ]


def test_ensure_app_uses_explicit_launcher_activity_when_provided() -> None:
    from mobile_app_installer import AndroidAppInstaller, AppSpec

    runner = RecordingRunner(
        [
            FakeCompletedProcess(stdout="device\n"),
            FakeCompletedProcess(returncode=0, stdout="package:/data/app/base.apk\n"),
            FakeCompletedProcess(returncode=0, stdout="Starting: Intent"),
        ]
    )

    installer = AndroidAppInstaller(runner=runner)
    result = installer.ensure_app(
        AppSpec(
            name="快手",
            package_name="com.smile.gifmaker",
            launcher_activity="com.smile.gifmaker/com.yxcorp.gifshow.HomeActivity",
        )
    )

    assert result.status == "already-installed"
    assert runner.calls == [
        ["adb", "get-state"],
        ["adb", "shell", "pm", "path", "com.smile.gifmaker"],
        [
            "adb",
            "shell",
            "am",
            "start",
            "-W",
            "-n",
            "com.smile.gifmaker/com.yxcorp.gifshow.HomeActivity",
        ],
    ]


def test_ensure_app_retries_explicit_launcher_after_device_not_found() -> None:
    from mobile_app_installer import AndroidAppInstaller, AppSpec

    runner = RecordingRunner(
        [
            FakeCompletedProcess(stdout="device\n"),
            FakeCompletedProcess(returncode=0, stdout="package:/data/app/base.apk\n"),
            FakeCompletedProcess(returncode=1, stderr="adb: device 'deec9116' not found"),
            FakeCompletedProcess(returncode=0, stdout=""),
            FakeCompletedProcess(returncode=0, stdout="Starting: Intent"),
        ]
    )

    installer = AndroidAppInstaller(serial="deec9116", runner=runner, sleeper=lambda _seconds: None)
    result = installer.ensure_app(
        AppSpec(
            name="快手",
            package_name="com.smile.gifmaker",
            launcher_activity="com.smile.gifmaker/com.yxcorp.gifshow.HomeActivity",
        )
    )

    assert result.status == "already-installed"
    assert runner.calls == [
        ["adb", "-s", "deec9116", "get-state"],
        ["adb", "-s", "deec9116", "shell", "pm", "path", "com.smile.gifmaker"],
        [
            "adb",
            "-s",
            "deec9116",
            "shell",
            "am",
            "start",
            "-W",
            "-n",
            "com.smile.gifmaker/com.yxcorp.gifshow.HomeActivity",
        ],
        ["adb", "-s", "deec9116", "wait-for-device"],
        [
            "adb",
            "-s",
            "deec9116",
            "shell",
            "am",
            "start",
            "-W",
            "-n",
            "com.smile.gifmaker/com.yxcorp.gifshow.HomeActivity",
        ],
    ]


def test_ensure_app_missing_opens_market_and_waits_until_installed() -> None:
    from mobile_app_installer import AndroidAppInstaller, AppSpec

    runner = RecordingRunner(
        [
            FakeCompletedProcess(stdout="device\n"),
            FakeCompletedProcess(returncode=1, stderr="package not found"),
            FakeCompletedProcess(returncode=0, stdout="Starting: Intent"),
            FakeCompletedProcess(returncode=0),
            FakeCompletedProcess(returncode=1, stderr="package not found"),
            FakeCompletedProcess(returncode=0),
            FakeCompletedProcess(returncode=0, stdout="package:/data/app/base.apk\n"),
            FakeCompletedProcess(returncode=0, stdout="Events injected: 1\n"),
            FakeCompletedProcess(returncode=0, stdout="package:/data/app/base.apk\n"),
        ]
    )

    installer = AndroidAppInstaller(runner=runner, sleeper=lambda _seconds: None, clock=IncrementingClock())
    result = installer.ensure_app(
        AppSpec(
            name="微信",
            package_name="com.tencent.mm",
            market_id="com.tencent.mm",
            install_tap_points=[(640, 2610)],
        ),
        timeout_seconds=10,
        poll_interval_seconds=1,
    )

    assert result.status == "installed"
    assert result.package_name == "com.tencent.mm"
    assert runner.calls == [
        ["adb", "get-state"],
        ["adb", "shell", "pm", "path", "com.tencent.mm"],
        [
            "adb",
            "shell",
            "am",
            "start",
            "-W",
            "-a",
            "android.intent.action.VIEW",
            "-d",
            "market://details?id=com.tencent.mm",
            "com.xiaomi.market",
        ],
        ["adb", "shell", "input", "tap", "640", "2610"],
        ["adb", "shell", "pm", "path", "com.tencent.mm"],
        ["adb", "shell", "input", "tap", "640", "2610"],
        ["adb", "shell", "pm", "path", "com.tencent.mm"],
        [
            "adb",
            "shell",
            "monkey",
            "-p",
            "com.tencent.mm",
            "-c",
            "android.intent.category.LAUNCHER",
            "1",
        ],
        ["adb", "shell", "pm", "path", "com.tencent.mm"],
    ]


def test_ensure_app_raises_when_market_install_times_out() -> None:
    from mobile_app_installer import AndroidAppInstaller, AppInstallError, AppSpec

    runner = RecordingRunner(
        [
            FakeCompletedProcess(stdout="device\n"),
            FakeCompletedProcess(returncode=1, stderr="package not found"),
            FakeCompletedProcess(returncode=0, stdout="Starting: Intent"),
            FakeCompletedProcess(returncode=1, stderr="package not found"),
            FakeCompletedProcess(returncode=1, stderr="package not found"),
            FakeCompletedProcess(returncode=1, stderr="package not found"),
        ]
    )

    installer = AndroidAppInstaller(runner=runner, sleeper=lambda _seconds: None, clock=IncrementingClock())

    with pytest.raises(AppInstallError, match="Timed out waiting for 小米应用商店安装"):
        installer.ensure_app(
            AppSpec(name="抖音", package_name="com.ss.android.ugc.aweme", market_id="com.ss.android.ugc.aweme"),
            timeout_seconds=3,
            poll_interval_seconds=1,
        )


def test_ensure_connected_tolerates_adb_daemon_bootstrap_noise() -> None:
    from mobile_app_installer import AndroidAppInstaller

    runner = RecordingRunner(
        [
            FakeCompletedProcess(
                returncode=0,
                stdout="device\n",
                stderr="* daemon not running; starting now at tcp:5037\n* daemon started successfully\n",
            )
        ]
    )

    installer = AndroidAppInstaller(serial="deec9116", runner=runner)

    installer.ensure_connected()


def test_ensure_connected_retries_when_get_state_returns_empty_during_daemon_bootstrap() -> None:
    from mobile_app_installer import AndroidAppInstaller

    sleep_calls: list[float] = []
    runner = RecordingRunner(
        [
            FakeCompletedProcess(
                returncode=0,
                stdout="",
                stderr="* daemon not running; starting now at tcp:5037\n* daemon started successfully\n",
            ),
            FakeCompletedProcess(returncode=0, stdout=""),
            FakeCompletedProcess(returncode=0, stdout="device\n"),
        ]
    )

    installer = AndroidAppInstaller(
        serial="deec9116",
        runner=runner,
        sleeper=sleep_calls.append,
    )

    installer.ensure_connected()

    assert runner.calls == [
        ["adb", "-s", "deec9116", "get-state"],
        ["adb", "-s", "deec9116", "wait-for-device"],
        ["adb", "-s", "deec9116", "get-state"],
    ]
    assert sleep_calls == [0.0]


def test_ensure_connected_retries_once_when_adb_daemon_is_bootstrapping() -> None:
    from mobile_app_installer import AndroidAppInstaller

    sleep_calls: list[float] = []
    runner = RecordingRunner(
        [
            FakeCompletedProcess(
                returncode=1,
                stdout="",
                stderr="* daemon not running; starting now at tcp:5037\n",
            ),
            FakeCompletedProcess(returncode=0, stdout=""),
            FakeCompletedProcess(returncode=0, stdout="device\n"),
        ]
    )

    installer = AndroidAppInstaller(serial="deec9116", runner=runner, sleeper=sleep_calls.append)

    installer.ensure_connected()

    assert runner.calls == [
        ["adb", "-s", "deec9116", "get-state"],
        ["adb", "-s", "deec9116", "wait-for-device"],
        ["adb", "-s", "deec9116", "get-state"],
    ]
    assert sleep_calls == [0.0]


def test_ensure_app_falls_back_to_resolved_launcher_when_monkey_launch_fails() -> None:
    from mobile_app_installer import AndroidAppInstaller, AppSpec

    runner = RecordingRunner(
        [
            FakeCompletedProcess(stdout="device\n"),
            FakeCompletedProcess(returncode=0, stdout="package:/data/app/base.apk\n"),
            FakeCompletedProcess(returncode=1, stderr="monkey launch failed"),
            FakeCompletedProcess(
                returncode=0,
                stdout=(
                    "priority=0 preferredOrder=0 match=0x108000 specificIndex=-1 isDefault=true\n"
                    "com.ss.android.ugc.aweme/.splash.SplashActivity\n"
                ),
            ),
            FakeCompletedProcess(returncode=0, stdout="Starting: Intent"),
        ]
    )

    installer = AndroidAppInstaller(runner=runner)
    result = installer.ensure_app(AppSpec(name="抖音", package_name="com.ss.android.ugc.aweme"))

    assert result.status == "already-installed"
    assert result.package_name == "com.ss.android.ugc.aweme"
    assert runner.calls == [
        ["adb", "get-state"],
        ["adb", "shell", "pm", "path", "com.ss.android.ugc.aweme"],
        [
            "adb",
            "shell",
            "monkey",
            "-p",
            "com.ss.android.ugc.aweme",
            "-c",
            "android.intent.category.LAUNCHER",
            "1",
        ],
        [
            "adb",
            "shell",
            "cmd",
            "package",
            "resolve-activity",
            "--brief",
            "com.ss.android.ugc.aweme",
        ],
        [
            "adb",
            "shell",
            "am",
            "start",
            "-W",
            "-n",
            "com.ss.android.ugc.aweme/.splash.SplashActivity",
        ],
    ]


def test_parse_resolved_launcher_activity_uses_last_component_line() -> None:
    from mobile_app_installer import AndroidAppInstaller

    installer = AndroidAppInstaller()

    resolved_activity = installer._parse_resolved_launcher_activity(
        (
            "priority=0 preferredOrder=0 match=0x108000 specificIndex=-1 isDefault=true\n"
            "com.ss.android.ugc.aweme/.LauncherActivity\n"
        )
    )

    assert resolved_activity == "com.ss.android.ugc.aweme/.LauncherActivity"


def test_prepare_device_wakes_dismisses_keyguard_and_goes_home() -> None:
    from mobile_app_installer import AndroidAppInstaller

    runner = RecordingRunner(
        [
            FakeCompletedProcess(stdout="device\n"),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
            FakeCompletedProcess(),
        ]
    )

    installer = AndroidAppInstaller(serial="deec9116", runner=runner)
    installer.prepare_device()

    assert runner.calls == [
        ["adb", "-s", "deec9116", "get-state"],
        ["adb", "-s", "deec9116", "shell", "input", "keyevent", "224"],
        ["adb", "-s", "deec9116", "shell", "wm", "dismiss-keyguard"],
        ["adb", "-s", "deec9116", "shell", "input", "keyevent", "3"],
    ]
