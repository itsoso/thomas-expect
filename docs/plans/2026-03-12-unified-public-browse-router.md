# Unified Public Browse Router Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a single entrypoint that routes safe public-browsing actions to the existing Douyin, Kuaishou, and Xiaohongshu navigators.

**Architecture:** Keep the existing navigator classes unchanged except where the router needs a stable call surface. Add a thin router module that validates `platform + action + query/pinyin` and delegates to the already tested navigator methods. Cover the router with focused unit tests that use fake navigator factories.

**Tech Stack:** Python 3, argparse, pathlib, pytest

---

### Task 1: Add failing router tests

**Files:**
- Create: `/Users/liqiuhua/work/personal/claw-creator/thomas-expect/tests/test_public_browse_router.py`

**Step 1: Write the failing test for routing Douyin open-first-result**

Test a request like `platform=douyin`, `action=open-first-result`, `query=直播带货`, `pinyin=zhibodaihuo`, and assert the router calls `search_and_enter_first_live_room()`.

**Step 2: Run the test to verify it fails**

Run: `pytest -q /Users/liqiuhua/work/personal/claw-creator/thomas-expect/tests/test_public_browse_router.py`

Expected: FAIL because `public_browse_router.py` does not exist yet.

**Step 3: Add more failing tests**

Add:
- Kuaishou `search` routes to `search_keyword()`
- Xiaohongshu `open-first-result` routes to `search_and_open_first_note()`
- Unsupported `platform + action` combinations raise a router error
- Missing `query` or `pinyin` validation errors are raised when required

**Step 4: Run the test file again**

Run: `pytest -q /Users/liqiuhua/work/personal/claw-creator/thomas-expect/tests/test_public_browse_router.py`

Expected: FAIL with missing imports or missing attributes, not test syntax errors.

### Task 2: Implement the minimal router

**Files:**
- Create: `/Users/liqiuhua/work/personal/claw-creator/thomas-expect/public_browse_router.py`

**Step 1: Add request model and router error**

Define a small dataclass for:
- `platform`
- `action`
- `query`
- `pinyin`
- `output`
- `serial`
- `trace_dir`

Add a `PublicBrowseRouterError`.

**Step 2: Add router class with injected navigator factories**

Use constructor-injected factories for:
- `DouyinNavigator`
- `KuaishouNavigator`
- `XiaohongshuNavigator`

This keeps tests isolated from real `adb`.

**Step 3: Implement action validation**

Support only:
- Douyin: `open-search`, `search`, `open-first-result`
- Kuaishou: `open-search`, `search`
- Xiaohongshu: `open-search`, `search`, `open-first-result`

Require:
- `query` for `search` and `open-first-result`
- `pinyin` for Douyin/Kuaishou search actions

**Step 4: Implement delegation**

Map requests to existing navigator methods:
- Douyin `open-first-result` -> `search_and_enter_first_live_room()`
- Kuaishou `search` -> `search_keyword()`
- Xiaohongshu `open-first-result` -> `search_and_open_first_note()`

**Step 5: Run focused tests**

Run: `pytest -q /Users/liqiuhua/work/personal/claw-creator/thomas-expect/tests/test_public_browse_router.py`

Expected: PASS

### Task 3: Add CLI entrypoint

**Files:**
- Modify: `/Users/liqiuhua/work/personal/claw-creator/thomas-expect/public_browse_router.py`

**Step 1: Add argparse wrapper**

Support:
- `--platform`
- `--action`
- `--query`
- `--pinyin`
- `--output`
- `--serial`
- `--trace-dir`

**Step 2: Wire CLI into router execution**

Return the output path and print a short success line.

**Step 3: Add or extend tests for CLI parsing if needed**

Keep tests small. Do not test `adb`; only validate argument handling and router call selection.

### Task 4: Verify and publish

**Files:**
- Verify: `/Users/liqiuhua/work/personal/claw-creator/thomas-expect/public_browse_router.py`
- Verify: `/Users/liqiuhua/work/personal/claw-creator/thomas-expect/tests/test_public_browse_router.py`

**Step 1: Run full suite**

Run:
`pytest -q /Users/liqiuhua/work/personal/claw-creator/thomas-expect/tests/test_mobile_app_installer.py /Users/liqiuhua/work/personal/claw-creator/thomas-expect/tests/test_kuaishou_navigator.py /Users/liqiuhua/work/personal/claw-creator/thomas-expect/tests/test_douyin_navigator.py /Users/liqiuhua/work/personal/claw-creator/thomas-expect/tests/test_xiaohongshu_navigator.py /Users/liqiuhua/work/personal/claw-creator/thomas-expect/tests/test_public_browse_router.py`

Expected: PASS

**Step 2: Run syntax verification**

Run:
`python3 -m py_compile /Users/liqiuhua/work/personal/claw-creator/thomas-expect/public_browse_router.py /Users/liqiuhua/work/personal/claw-creator/thomas-expect/tests/test_public_browse_router.py`

Expected: PASS

**Step 3: Commit**

```bash
git -C /Users/liqiuhua/work/personal/claw-creator add thomas-expect/public_browse_router.py thomas-expect/tests/test_public_browse_router.py thomas-expect/docs/plans/2026-03-12-unified-public-browse-router.md
git -C /Users/liqiuhua/work/personal/claw-creator commit -m "feat(thomas-expect): add unified public browse router"
```

**Step 4: Push subtree**

```bash
git -C /Users/liqiuhua/work/personal/claw-creator subtree split --prefix thomas-expect -b codex/thomas-expect-export-20260312-public-browse-router
git -C /Users/liqiuhua/work/personal/claw-creator push thomas-expect codex/thomas-expect-export-20260312-public-browse-router:main
```
