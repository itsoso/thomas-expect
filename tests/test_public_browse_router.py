from __future__ import annotations

from pathlib import Path

import pytest


class FakeDevicePreparer:
    instances: list["FakeDevicePreparer"] = []

    def __init__(self, serial: str | None = None, **_kwargs) -> None:
        self.serial = serial
        self.prepare_calls = 0
        type(self).instances.append(self)

    def prepare_device(self) -> None:
        self.prepare_calls += 1


class FakeDouyinNavigator:
    instances: list["FakeDouyinNavigator"] = []

    def __init__(self, serial: str | None = None, trace_dir: str | Path | None = None, **_kwargs) -> None:
        self.serial = serial
        self.trace_dir = None if trace_dir is None else str(trace_dir)
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        type(self).instances.append(self)

    def open_search(self, destination: str | Path) -> Path:
        self.calls.append(("open_search", (str(destination),)))
        target = Path(destination)
        target.write_bytes(b"DOUYIN-SEARCH")
        return target

    def search_keyword(self, keyword: str, pinyin: str, destination: str | Path) -> Path:
        self.calls.append(("search_keyword", (keyword, pinyin, str(destination))))
        target = Path(destination)
        target.write_bytes(b"DOUYIN-RESULT")
        return target

    def search_and_enter_first_live_room(self, keyword: str, pinyin: str, destination: str | Path) -> Path:
        self.calls.append(("search_and_enter_first_live_room", (keyword, pinyin, str(destination))))
        target = Path(destination)
        target.write_bytes(b"DOUYIN-LIVE")
        return target


class FakeKuaishouNavigator:
    instances: list["FakeKuaishouNavigator"] = []

    def __init__(self, serial: str | None = None, trace_dir: str | Path | None = None, **_kwargs) -> None:
        self.serial = serial
        self.trace_dir = None if trace_dir is None else str(trace_dir)
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        type(self).instances.append(self)

    def open_search(self, destination: str | Path) -> Path:
        self.calls.append(("open_search", (str(destination),)))
        target = Path(destination)
        target.write_bytes(b"KUAISHOU-SEARCH")
        return target

    def search_keyword(self, keyword: str, pinyin: str, destination: str | Path) -> Path:
        self.calls.append(("search_keyword", (keyword, pinyin, str(destination))))
        target = Path(destination)
        target.write_bytes(b"KUAISHOU-RESULT")
        return target

    def search_and_enter_first_live_room(self, keyword: str, pinyin: str, destination: str | Path) -> Path:
        self.calls.append(("search_and_enter_first_live_room", (keyword, pinyin, str(destination))))
        target = Path(destination)
        target.write_bytes(b"KUAISHOU-LIVE")
        return target


class FakeXiaohongshuNavigator:
    instances: list["FakeXiaohongshuNavigator"] = []

    def __init__(self, serial: str | None = None, trace_dir: str | Path | None = None, **_kwargs) -> None:
        self.serial = serial
        self.trace_dir = None if trace_dir is None else str(trace_dir)
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        type(self).instances.append(self)

    def open_search(self, destination: str | Path) -> Path:
        self.calls.append(("open_search", (str(destination),)))
        target = Path(destination)
        target.write_bytes(b"XHS-SEARCH")
        return target

    def search_keyword(self, keyword: str, destination: str | Path) -> Path:
        self.calls.append(("search_keyword", (keyword, str(destination))))
        target = Path(destination)
        target.write_bytes(b"XHS-RESULT")
        return target

    def search_and_open_first_note(self, keyword: str, destination: str | Path) -> Path:
        self.calls.append(("search_and_open_first_note", (keyword, str(destination))))
        target = Path(destination)
        target.write_bytes(b"XHS-NOTE")
        return target


def reset_fake_navigators() -> None:
    FakeDouyinNavigator.instances.clear()
    FakeKuaishouNavigator.instances.clear()
    FakeXiaohongshuNavigator.instances.clear()
    FakeDevicePreparer.instances.clear()


def test_router_routes_douyin_open_first_result_to_live_room(tmp_path: Path) -> None:
    from public_browse_router import PublicBrowseRequest, PublicBrowseRouter

    reset_fake_navigators()
    router = PublicBrowseRouter(
        douyin_factory=FakeDouyinNavigator,
        kuaishou_factory=FakeKuaishouNavigator,
        xiaohongshu_factory=FakeXiaohongshuNavigator,
        device_preparer_factory=FakeDevicePreparer,
    )

    target = tmp_path / "douyin-live.png"
    trace_dir = tmp_path / "trace"
    written = router.execute(
        PublicBrowseRequest(
            platform="douyin",
            action="open-first-result",
            query="直播带货",
            pinyin="zhibodaihuo",
            output=target,
            serial="device-1",
            trace_dir=trace_dir,
        )
    )

    assert written == target
    assert target.read_bytes() == b"DOUYIN-LIVE"
    assert len(FakeDouyinNavigator.instances) == 1
    assert len(FakeDevicePreparer.instances) == 1
    assert FakeDevicePreparer.instances[0].serial == "device-1"
    assert FakeDevicePreparer.instances[0].prepare_calls == 1
    assert FakeDouyinNavigator.instances[0].serial == "device-1"
    assert FakeDouyinNavigator.instances[0].trace_dir == str(trace_dir)
    assert FakeDouyinNavigator.instances[0].calls == [
        ("search_and_enter_first_live_room", ("直播带货", "zhibodaihuo", str(target)))
    ]


def test_router_routes_kuaishou_search_and_passes_trace_dir(tmp_path: Path) -> None:
    from public_browse_router import PublicBrowseRequest, PublicBrowseRouter

    reset_fake_navigators()
    router = PublicBrowseRouter(
        douyin_factory=FakeDouyinNavigator,
        kuaishou_factory=FakeKuaishouNavigator,
        xiaohongshu_factory=FakeXiaohongshuNavigator,
        device_preparer_factory=FakeDevicePreparer,
    )

    target = tmp_path / "kuaishou-search.png"
    trace_dir = tmp_path / "trace"
    written = router.execute(
        PublicBrowseRequest(
            platform="kuaishou",
            action="search",
            query="直播带货",
            pinyin="zhibodaihuo",
            output=target,
            serial="device-2",
            trace_dir=trace_dir,
        )
    )

    assert written == target
    assert target.read_bytes() == b"KUAISHOU-RESULT"
    assert len(FakeKuaishouNavigator.instances) == 1
    assert len(FakeDevicePreparer.instances) == 1
    assert FakeDevicePreparer.instances[0].serial == "device-2"
    assert FakeDevicePreparer.instances[0].prepare_calls == 1
    assert FakeKuaishouNavigator.instances[0].serial == "device-2"
    assert FakeKuaishouNavigator.instances[0].trace_dir == str(trace_dir)
    assert FakeKuaishouNavigator.instances[0].calls == [
        ("search_keyword", ("直播带货", "zhibodaihuo", str(target)))
    ]


def test_router_routes_kuaishou_open_first_result_to_live_room(tmp_path: Path) -> None:
    from public_browse_router import PublicBrowseRequest, PublicBrowseRouter

    reset_fake_navigators()
    router = PublicBrowseRouter(
        douyin_factory=FakeDouyinNavigator,
        kuaishou_factory=FakeKuaishouNavigator,
        xiaohongshu_factory=FakeXiaohongshuNavigator,
        device_preparer_factory=FakeDevicePreparer,
    )

    target = tmp_path / "kuaishou-live.png"
    trace_dir = tmp_path / "trace"
    written = router.execute(
        PublicBrowseRequest(
            platform="kuaishou",
            action="open-first-result",
            query="美女直播",
            pinyin="meinvzhibo",
            output=target,
            serial="device-4",
            trace_dir=trace_dir,
        )
    )

    assert written == target
    assert target.read_bytes() == b"KUAISHOU-LIVE"
    assert len(FakeKuaishouNavigator.instances) == 1
    assert len(FakeDevicePreparer.instances) == 1
    assert FakeDevicePreparer.instances[0].serial == "device-4"
    assert FakeDevicePreparer.instances[0].prepare_calls == 1
    assert FakeKuaishouNavigator.instances[0].serial == "device-4"
    assert FakeKuaishouNavigator.instances[0].trace_dir == str(trace_dir)
    assert FakeKuaishouNavigator.instances[0].calls == [
        ("search_and_enter_first_live_room", ("美女直播", "meinvzhibo", str(target)))
    ]


def test_router_routes_xiaohongshu_open_first_result(tmp_path: Path) -> None:
    from public_browse_router import PublicBrowseRequest, PublicBrowseRouter

    reset_fake_navigators()
    router = PublicBrowseRouter(
        douyin_factory=FakeDouyinNavigator,
        kuaishou_factory=FakeKuaishouNavigator,
        xiaohongshu_factory=FakeXiaohongshuNavigator,
        device_preparer_factory=FakeDevicePreparer,
    )

    target = tmp_path / "xhs-note.png"
    trace_dir = tmp_path / "trace"
    written = router.execute(
        PublicBrowseRequest(
            platform="xiaohongshu",
            action="open-first-result",
            query="hanfu",
            output=target,
            serial="device-3",
            trace_dir=trace_dir,
        )
    )

    assert written == target
    assert target.read_bytes() == b"XHS-NOTE"
    assert len(FakeXiaohongshuNavigator.instances) == 1
    assert len(FakeDevicePreparer.instances) == 1
    assert FakeDevicePreparer.instances[0].serial == "device-3"
    assert FakeDevicePreparer.instances[0].prepare_calls == 1
    assert FakeXiaohongshuNavigator.instances[0].serial == "device-3"
    assert FakeXiaohongshuNavigator.instances[0].trace_dir == str(trace_dir)
    assert FakeXiaohongshuNavigator.instances[0].calls == [
        ("search_and_open_first_note", ("hanfu", str(target)))
    ]


def test_router_requires_query_for_search_actions(tmp_path: Path) -> None:
    from public_browse_router import PublicBrowseRequest, PublicBrowseRouter, PublicBrowseRouterError

    router = PublicBrowseRouter(
        douyin_factory=FakeDouyinNavigator,
        kuaishou_factory=FakeKuaishouNavigator,
        xiaohongshu_factory=FakeXiaohongshuNavigator,
        device_preparer_factory=FakeDevicePreparer,
    )

    with pytest.raises(PublicBrowseRouterError, match="requires query"):
        router.execute(
            PublicBrowseRequest(
                platform="xiaohongshu",
                action="search",
                output=tmp_path / "ignored.png",
            )
        )


def test_router_requires_pinyin_for_douyin_and_kuaishou_search(tmp_path: Path) -> None:
    from public_browse_router import PublicBrowseRequest, PublicBrowseRouter, PublicBrowseRouterError

    router = PublicBrowseRouter(
        douyin_factory=FakeDouyinNavigator,
        kuaishou_factory=FakeKuaishouNavigator,
        xiaohongshu_factory=FakeXiaohongshuNavigator,
        device_preparer_factory=FakeDevicePreparer,
    )

    with pytest.raises(PublicBrowseRouterError, match="requires pinyin"):
        router.execute(
            PublicBrowseRequest(
                platform="douyin",
                action="search",
                query="直播带货",
                output=tmp_path / "ignored.png",
            )
        )


def test_main_executes_router_request_and_prints_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from public_browse_router import PublicBrowseRouter, main

    reset_fake_navigators()
    router = PublicBrowseRouter(
        douyin_factory=FakeDouyinNavigator,
        kuaishou_factory=FakeKuaishouNavigator,
        xiaohongshu_factory=FakeXiaohongshuNavigator,
        device_preparer_factory=FakeDevicePreparer,
    )

    target = tmp_path / "cli-xhs.png"
    exit_code = main(
        [
            "--platform",
            "xiaohongshu",
            "--action",
            "search",
            "--query",
            "hanfu",
            "--output",
            str(target),
            "--serial",
            "device-9",
        ],
        router=router,
    )

    assert exit_code == 0
    assert target.read_bytes() == b"XHS-RESULT"
    assert len(FakeDevicePreparer.instances) == 1
    assert FakeDevicePreparer.instances[0].serial == "device-9"
    assert FakeDevicePreparer.instances[0].prepare_calls == 1
    assert "Public browse screenshot saved to" in capsys.readouterr().out
