from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from douyin_navigator import DouyinNavigator
from kuaishou_navigator import KuaishouNavigator
from mobile_app_installer import AndroidAppInstaller
from xiaohongshu_navigator import XiaohongshuNavigator


DouyinFactory = Callable[..., DouyinNavigator]
KuaishouFactory = Callable[..., KuaishouNavigator]
XiaohongshuFactory = Callable[..., XiaohongshuNavigator]
DevicePreparerFactory = Callable[..., AndroidAppInstaller]

SUPPORTED_ACTIONS: dict[str, tuple[str, ...]] = {
    "douyin": ("open-search", "search", "open-first-result"),
    "kuaishou": ("open-search", "search", "open-first-result"),
    "xiaohongshu": ("open-search", "search", "open-first-result"),
}


class PublicBrowseRouterError(RuntimeError):
    """Raised when a public browsing request is invalid or unsupported."""


@dataclass(frozen=True)
class PublicBrowseRequest:
    platform: str
    action: str
    output: str | Path
    query: str | None = None
    pinyin: str | None = None
    serial: str | None = None
    trace_dir: str | Path | None = None


class PublicBrowseRouter:
    def __init__(
        self,
        douyin_factory: DouyinFactory = DouyinNavigator,
        kuaishou_factory: KuaishouFactory = KuaishouNavigator,
        xiaohongshu_factory: XiaohongshuFactory = XiaohongshuNavigator,
        device_preparer_factory: DevicePreparerFactory = AndroidAppInstaller,
    ) -> None:
        self.douyin_factory = douyin_factory
        self.kuaishou_factory = kuaishou_factory
        self.xiaohongshu_factory = xiaohongshu_factory
        self.device_preparer_factory = device_preparer_factory

    def _validate(self, request: PublicBrowseRequest) -> None:
        if request.platform not in SUPPORTED_ACTIONS:
            raise PublicBrowseRouterError(f"Unsupported platform: {request.platform}")
        if request.action not in SUPPORTED_ACTIONS[request.platform]:
            raise PublicBrowseRouterError(
                f"Platform {request.platform} does not support action {request.action}"
            )
        if request.action != "open-search" and not request.query:
            raise PublicBrowseRouterError(f"Action {request.action} requires query")
        if request.platform in {"douyin", "kuaishou"} and request.action != "open-search" and not request.pinyin:
            raise PublicBrowseRouterError(f"Platform {request.platform} action {request.action} requires pinyin")

    def execute(self, request: PublicBrowseRequest) -> Path:
        self._validate(request)
        target = Path(request.output)
        self.device_preparer_factory(serial=request.serial).prepare_device()

        if request.platform == "douyin":
            navigator = self.douyin_factory(serial=request.serial, trace_dir=request.trace_dir)
            if request.action == "open-search":
                return navigator.open_search(target)
            if request.action == "search":
                return navigator.search_keyword(keyword=request.query or "", pinyin=request.pinyin or "", destination=target)
            return navigator.search_and_enter_first_live_room(
                keyword=request.query or "",
                pinyin=request.pinyin or "",
                destination=target,
            )

        if request.platform == "kuaishou":
            navigator = self.kuaishou_factory(serial=request.serial, trace_dir=request.trace_dir)
            if request.action == "open-search":
                return navigator.open_search(target)
            if request.action == "search":
                return navigator.search_keyword(
                    keyword=request.query or "",
                    pinyin=request.pinyin or "",
                    destination=target,
                )
            return navigator.search_and_enter_first_live_room(
                keyword=request.query or "",
                pinyin=request.pinyin or "",
                destination=target,
            )

        navigator = self.xiaohongshu_factory(serial=request.serial, trace_dir=request.trace_dir)
        if request.action == "open-search":
            return navigator.open_search(target)
        if request.action == "search":
            return navigator.search_keyword(keyword=request.query or "", destination=target)
        return navigator.search_and_open_first_note(keyword=request.query or "", destination=target)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Route a safe public mobile browsing action to a platform navigator.")
    parser.add_argument("--platform", required=True, choices=tuple(SUPPORTED_ACTIONS.keys()))
    parser.add_argument("--action", required=True, choices=("open-search", "search", "open-first-result"))
    parser.add_argument("--query", help="Public search keyword.")
    parser.add_argument("--pinyin", help="Latin fallback input for Douyin and Kuaishou.")
    parser.add_argument("--output", default="/tmp/public-browse.png", help="Destination screenshot path.")
    parser.add_argument("--serial", help="ADB serial for the target device.")
    parser.add_argument("--trace-dir", help="Optional trace directory for Kuaishou.")
    return parser


def main(argv: list[str] | None = None, router: PublicBrowseRouter | None = None) -> int:
    args = build_parser().parse_args(argv)
    active_router = router or PublicBrowseRouter()
    output = active_router.execute(
        PublicBrowseRequest(
            platform=args.platform,
            action=args.action,
            query=args.query,
            pinyin=args.pinyin,
            output=args.output,
            serial=args.serial,
            trace_dir=args.trace_dir,
        )
    )
    print(f"Public browse screenshot saved to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
