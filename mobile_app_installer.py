from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import subprocess
import time
from typing import Callable


Runner = Callable[..., subprocess.CompletedProcess]
Sleeper = Callable[[float], None]
Clock = Callable[[], float]


class AppInstallError(RuntimeError):
    """Raised when the installer cannot make the requested app available."""


@dataclass(frozen=True)
class AppSpec:
    name: str
    package_name: str
    market_id: str | None = None
    install_tap_points: list[tuple[int, int]] | None = None
    launcher_activity: str | None = None


@dataclass(frozen=True)
class EnsureResult:
    status: str
    package_name: str


KNOWN_APPS: dict[str, AppSpec] = {
    "alipay": AppSpec(
        name="支付宝",
        package_name="com.eg.android.AlipayGphone",
        market_id="com.eg.android.AlipayGphone",
        install_tap_points=[(640, 2610)],
    ),
    "wechat": AppSpec(
        name="微信",
        package_name="com.tencent.mm",
        market_id="com.tencent.mm",
        install_tap_points=[(640, 2610)],
    ),
    "douyin": AppSpec(
        name="抖音",
        package_name="com.ss.android.ugc.aweme",
        market_id="com.ss.android.ugc.aweme",
        install_tap_points=[(640, 2610)],
    ),
    "kuaishou": AppSpec(
        name="快手",
        package_name="com.smile.gifmaker",
        market_id="com.smile.gifmaker",
        install_tap_points=[(640, 2610)],
        launcher_activity="com.smile.gifmaker/com.yxcorp.gifshow.HomeActivity",
    ),
    "xiaohongshu": AppSpec(
        name="小红书",
        package_name="com.xingin.xhs",
        market_id="com.xingin.xhs",
        install_tap_points=[(640, 2610)],
    ),
}


class AndroidAppInstaller:
    def __init__(
        self,
        serial: str | None = None,
        adb_path: str = "adb",
        runner: Runner | None = None,
        sleeper: Sleeper | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.serial = serial
        self.adb_path = adb_path
        self.runner = runner or subprocess.run
        self.sleeper = sleeper or time.sleep
        self.clock = clock or time.monotonic

    def _build_command(self, *args: str) -> list[str]:
        command = [self.adb_path]
        if self.serial:
            command.extend(["-s", self.serial])
        command.extend(args)
        return command

    def _run(self, *args: str, text: bool = True) -> subprocess.CompletedProcess:
        result = self.runner(
            self._build_command(*args),
            capture_output=True,
            text=text,
            check=False,
        )
        if result.returncode != 0 and "daemon not running" in (result.stderr or ""):
            self.sleeper(1)
            result = self.runner(
                self._build_command(*args),
                capture_output=True,
                text=text,
                check=False,
            )
        return result

    def ensure_connected(self) -> None:
        result = self._run("get-state")
        state = (result.stdout or "").strip()
        if result.returncode != 0 and "daemon not running" in (result.stderr or ""):
            self.sleeper(1)
            result = self._run("get-state")
            state = (result.stdout or "").strip()
        if result.returncode != 0 or state != "device":
            raise AppInstallError(result.stderr or f"Unexpected adb state: {state}")

    def is_installed(self, package_name: str) -> bool:
        result = self._run("shell", "pm", "path", package_name)
        return result.returncode == 0 and "package:" in (result.stdout or "")

    @staticmethod
    def _parse_resolved_launcher_activity(output: str) -> str | None:
        for line in reversed(output.splitlines()):
            candidate = line.strip()
            if "/" not in candidate:
                continue
            return candidate
        return None

    def resolve_launcher_activity(self, package_name: str) -> str | None:
        result = self._run("shell", "cmd", "package", "resolve-activity", "--brief", package_name)
        if result.returncode != 0:
            return None
        return self._parse_resolved_launcher_activity(result.stdout or "")

    def launch_app(self, package_name: str, launcher_activity: str | None = None) -> None:
        if launcher_activity:
            result = self._run("shell", "am", "start", "-W", "-n", launcher_activity)
            if result.returncode != 0:
                raise AppInstallError(result.stderr or f"Failed to launch {package_name}")
            return
        result = self._run(
            "shell",
            "monkey",
            "-p",
            package_name,
            "-c",
            "android.intent.category.LAUNCHER",
            "1",
        )
        if result.returncode == 0:
            return
        resolved_activity = self.resolve_launcher_activity(package_name)
        if resolved_activity:
            fallback_result = self._run("shell", "am", "start", "-W", "-n", resolved_activity)
            if fallback_result.returncode == 0:
                return
            raise AppInstallError(fallback_result.stderr or f"Failed to launch {package_name}")
        raise AppInstallError(result.stderr or f"Failed to launch {package_name}")

    def tap(self, x: int, y: int) -> None:
        result = self._run("shell", "input", "tap", str(x), str(y))
        if result.returncode != 0:
            raise AppInstallError(result.stderr or f"Failed to tap {x},{y}")

    def open_market_details(self, market_id: str) -> None:
        result = self._run(
            "shell",
            "am",
            "start",
            "-W",
            "-a",
            "android.intent.action.VIEW",
            "-d",
            f"market://details?id={market_id}",
            "com.xiaomi.market",
        )
        if result.returncode != 0:
            raise AppInstallError(result.stderr or f"Failed to open market page for {market_id}")

    def wait_for_install(
        self,
        spec: AppSpec,
        timeout_seconds: int,
        poll_interval_seconds: int,
    ) -> None:
        deadline = self.clock() + timeout_seconds
        tap_points = spec.install_tap_points or []
        while self.clock() < deadline:
            for x, y in tap_points:
                self.tap(x, y)
            if self.is_installed(spec.package_name):
                return
            self.sleeper(poll_interval_seconds)
        raise AppInstallError(f"Timed out waiting for 小米应用商店安装 {spec.name}")

    def ensure_app(
        self,
        spec: AppSpec,
        timeout_seconds: int = 180,
        poll_interval_seconds: int = 3,
        launch_after_install: bool = True,
    ) -> EnsureResult:
        self.ensure_connected()
        already_installed = self.is_installed(spec.package_name)
        status = "already-installed" if already_installed else "installed"
        if not already_installed:
            if not spec.market_id:
                raise AppInstallError(f"{spec.name} 缺少 market_id，无法自动拉起商店安装")
            self.open_market_details(spec.market_id)
            self.wait_for_install(spec, timeout_seconds, poll_interval_seconds)
        if launch_after_install:
            self.launch_app(spec.package_name, spec.launcher_activity)
            if not already_installed and not self.is_installed(spec.package_name):
                raise AppInstallError(f"{spec.name} 安装后校验失败")
        return EnsureResult(status=status, package_name=spec.package_name)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ensure an Android app is installed and launchable.")
    parser.add_argument(
        "target",
        help="Known alias (alipay/wechat/douyin/kuaishou/xiaohongshu) or an Android package name.",
    )
    parser.add_argument("--name", help="Display name when target is a raw package name.")
    parser.add_argument("--market-id", help="Xiaomi market package id. Defaults to the package name.")
    parser.add_argument("--serial", help="ADB serial to target a specific device.")
    parser.add_argument("--timeout", type=int, default=180, help="Install timeout in seconds.")
    parser.add_argument("--poll-interval", type=int, default=3, help="Polling interval in seconds.")
    parser.add_argument(
        "--skip-launch",
        action="store_true",
        help="Only ensure installation without launching the app.",
    )
    return parser


def resolve_app_spec(target: str, name: str | None, market_id: str | None) -> AppSpec:
    target_key = target.lower()
    if target_key in KNOWN_APPS:
        known = KNOWN_APPS[target_key]
        return AppSpec(
            name=known.name,
            package_name=known.package_name,
            market_id=market_id or known.market_id,
            install_tap_points=list(known.install_tap_points or []),
            launcher_activity=known.launcher_activity,
        )
    display_name = name or target
    return AppSpec(
        name=display_name,
        package_name=target,
        market_id=market_id or target,
        install_tap_points=[(640, 2610)],
        launcher_activity=None,
    )


def main() -> int:
    args = build_parser().parse_args()
    spec = resolve_app_spec(args.target, args.name, args.market_id)
    installer = AndroidAppInstaller(serial=args.serial)
    result = installer.ensure_app(
        spec,
        timeout_seconds=args.timeout,
        poll_interval_seconds=args.poll_interval,
        launch_after_install=not args.skip_launch,
    )
    print(f"{spec.name}: {result.status} ({result.package_name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
