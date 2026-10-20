import asyncio
import math
from itertools import pairwise
from types import SimpleNamespace

import pytest

from tests.wait_fakes import runtime, view
from ultralight_py import ErrorCode, UltralightError
from ultralight_py.integrations.asyncio import install
from ultralight_py.scripting import ScriptDriver

pytestmark = pytest.mark.asyncio


async def test_host_controls_steps_and_immediate_results_do_not_drive():
    rt = runtime()
    page = view(rt)
    entered = asyncio.Event()
    release = asyncio.Event()
    requests = []

    async def step(*, render=False):
        requests.append(render)
        entered.set()
        await release.wait()
        rt.update()
        rt.refresh_display()
        page._native.emit("dom_ready")
        if render:
            rt.render()

    async with ScriptDriver(rt, step=step) as driver:
        script = driver.page(page)
        assert await script.wait_until(lambda: "ready") == "ready"
        assert not requests
        job = asyncio.create_task(script.navigate("https://example.test"))
        await entered.wait()
        assert rt._native.updates == 0
        await asyncio.sleep(0.01)
        assert not job.done() and requests == [False]
        release.set()
        await job
    assert not page.closed and not rt.closed
    rt.close()


@pytest.mark.parametrize("clock_resolution", [None, 0.016])
async def test_auto_is_on_demand_shared_rate_limited_and_renders_only_when_needed(
    monkeypatch, clock_resolution
):
    if clock_resolution is not None:
        # Reproduce early timer wakeups on Windows even on a high-resolution host.
        loop = asyncio.get_running_loop()
        time = loop.time
        monkeypatch.setattr(loop, "_clock_resolution", clock_resolution)
        monkeypatch.setattr(
            loop, "time", lambda: math.floor(time() / clock_resolution) * clock_resolution
        )
    rt = runtime()
    left, right = view(rt), view(rt)
    for page in (left, right):
        page.load_html("<body>")
    updates = []

    def update():
        updates.append(asyncio.get_running_loop().time())
        if rt._native.updates >= 3:
            for page in (left, right):
                page._native.emit("dom_ready")

    rt._native.on_update = update
    async with ScriptDriver.auto(rt, update_interval=0.01) as driver:
        with pytest.raises(RuntimeError, match="already"):
            install(rt)
        await asyncio.sleep(0.02)
        assert rt._native.updates == 0
        start = driver.loop.time()
        await asyncio.gather(driver.page(left).wait_ready(), driver.page(right).wait_ready())
        assert driver.loop.time() - start >= 0.018
        assert rt._native.updates == 3 and rt._native.renders == 0
        assert all(later - earlier >= 0.01 for earlier, later in pairwise(updates))
        count = rt._native.updates
        await asyncio.sleep(0.025)
        assert rt._native.updates == count
        rt._native.on_render = lambda: left._native.emit("page_settled")
        await driver.page(left).wait_settled()
        assert rt._native.renders == 1
    assert rt._async_driver is None and rt._script_driver is None
    assert not rt._async_work
    rt.close()


async def test_navigation_follows_engine_chain_but_new_explicit_load_supersedes():
    rt = runtime()
    page = view(rt)

    async def redirect(*, render=False):
        page._native.emit("begin_loading", url="https://redirect.test")
        page._native.emit("dom_ready", url="https://redirect.test")
        rt.update()

    async with ScriptDriver(rt, step=redirect) as driver:
        await driver.page(page).navigate("https://example.test")
        passive = asyncio.create_task(page.wait_until(lambda: False))
        await asyncio.sleep(0)
        page._native.emit("begin_loading")
        with pytest.raises(UltralightError) as error:
            await passive
        assert error.value.code == ErrorCode.PageGone
        started = asyncio.Event()

        async def paused(*, render=False):
            started.set()
            await asyncio.Future()

        driver._step = paused
        job = asyncio.create_task(driver.page(page).navigate("old"))
        await started.wait()
        page.load_url("new")
        page._native.emit("dom_ready")
        with pytest.raises(UltralightError) as error:
            await job
        assert error.value.code == ErrorCode.PageGone
    rt.close()


async def test_ready_callback_navigation_is_not_mistaken_for_final_ready():
    rt = runtime()
    page = view(rt)
    seen = []

    def ready(event):
        if not seen:
            seen.append("redirect")
            page._native.emit("begin_loading")

    page.on("dom_ready", ready)

    async def step(*, render=False):
        rt.update()
        page._native.emit("dom_ready")

    async with ScriptDriver(rt, step=step) as driver:
        await driver.page(page).navigate("initial")
        assert rt._native.updates == 2 and page.is_ready
    rt.close()


async def test_promise_result_rejection_timeout_and_cancellation_cleanup():
    rt = runtime()
    page = view(rt)
    cancelled = asyncio.Event()

    async def evaluate(source, *, copy=False):
        if source == "42":
            return 42
        if source == "reject":
            raise ValueError("rejected")
        try:
            await asyncio.Future()
        finally:
            cancelled.set()

    page.evaluate_async = evaluate
    async with ScriptDriver.auto(rt, update_interval=0.005) as driver:
        script = driver.page(page)
        assert await script.evaluate("42") == 42
        assert rt._native.updates == 0
        with pytest.raises(ValueError, match="rejected"):
            await script.evaluate("reject")
        with pytest.raises(TimeoutError):
            await script.evaluate("pending", timeout=0.01)
        assert cancelled.is_set() and not driver._demands
        cancelled.clear()
        job = asyncio.create_task(script.evaluate("pending"))
        await asyncio.sleep(0.01)
        job.cancel()
        with pytest.raises(asyncio.CancelledError):
            await job
        assert cancelled.is_set() and not driver._demands
        count = rt._native.updates
        await asyncio.sleep(0.01)
        assert rt._native.updates == count
    rt.close()


async def test_one_cancelled_wait_does_not_cancel_shared_request():
    rt = runtime()
    left, right = view(rt), view(rt)
    for page in (left, right):
        page.load_html("<body>")
    started, release = asyncio.Event(), asyncio.Event()
    requests = []

    async def step(*, render=False):
        requests.append(render)
        started.set()
        await release.wait()
        rt.update()
        right._native.emit("dom_ready")

    async with ScriptDriver(rt, step=step) as driver:
        first = asyncio.create_task(driver.page(left).wait_ready())
        second = asyncio.create_task(driver.page(right).wait_ready())
        await started.wait()
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        assert not second.done() and requests == [False]
        release.set()
        await second
    rt.close()


async def test_failures_close_and_ownership_checks():
    rt = runtime()
    page = view(rt)
    page.load_html("<body>")

    async def fail(*, render=False):
        raise RuntimeError("host failed")

    async with ScriptDriver(rt, step=fail) as driver:
        with pytest.raises(ValueError, match="another"):
            driver.page(SimpleNamespace(_runtime=runtime()))
        with pytest.raises(RuntimeError, match="already"):
            ScriptDriver(rt, step=fail)
        errors = await asyncio.gather(
            driver.page(page).wait_ready(), driver.page(page).wait_settled(), return_exceptions=True
        )
        assert all(
            isinstance(error, RuntimeError) and str(error) == "host failed" for error in errors
        )
        assert not page._state.waiters
    async with ScriptDriver.auto(rt) as driver:
        job = asyncio.create_task(driver.page(page).wait_ready())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        rt.close()
        with pytest.raises(UltralightError) as error:
            await job
        assert error.value.code == ErrorCode.Closed


async def test_existing_driver_and_invalid_requests():
    rt = runtime()
    page = view(rt)
    with install(rt), pytest.raises(RuntimeError, match="already"):
        ScriptDriver.auto(rt)
    async with ScriptDriver.auto(rt) as driver:
        script = driver.page(page)
        for timeout in [0, True, "5", float("inf")]:
            with pytest.raises(ValueError, match="timeout"):
                await script.evaluate("42", timeout)
        with pytest.raises(TypeError, match="render"):
            await script.wait_until(lambda: True, render="yes")
        with pytest.raises(ValueError, match="wait_until"):
            await script.navigate("https://example.test", wait_until="networkidle")
        assert rt._native.updates == 0 and page.navigation_id == 0
    rt.close()


async def test_expect_navigation_arms_before_action_and_follows_engine_chain():
    rt = runtime()
    page = view(rt)
    page.load_html("old")
    page._native.emit("dom_ready")
    stages = []

    async def step(*, render=False):
        stages.append(render)
        if len(stages) == 1:
            page._native.emit("begin_loading")
        page._native.emit("dom_ready")
        if render:
            page._native.emit("page_settled")

    async with ScriptDriver(rt, step=step) as driver:
        script = driver.page(page)
        async with script.expect_navigation(wait_until="settled"):
            assert page._state.waiters
            # Native action emits synchronously, before __aexit__ starts pumping.
            page._native.emit("begin_loading")
            page._native.emit("dom_ready")
        assert page.is_settled and stages and all(stages)
        assert not page._state.waiters and not driver._demands
    rt.close()


async def test_expect_navigation_timeout_includes_action_and_cleans_up():
    rt = runtime()
    page = view(rt)
    page.load_html("old")
    page._native.emit("dom_ready")
    async with ScriptDriver.auto(rt, update_interval=0.001) as driver:
        script = driver.page(page)
        for action in (False, True):
            with pytest.raises(TimeoutError):
                async with script.expect_navigation(timeout=0.01):
                    if action:
                        await asyncio.Future()
            assert not page._state.waiters and not driver._demands
        # A scope exception must not turn into a no-navigation timeout.
        with pytest.raises(ValueError, match="action failed"):
            async with script.expect_navigation():
                raise ValueError("action failed")
        assert not page._state.waiters
        assert getattr(asyncio.current_task(), "cancelling", lambda: 0)() == 0
    assert not rt._async_work
    rt.close()


async def test_expect_navigation_action_and_wait_share_deadline():
    rt = runtime()
    page = view(rt)
    async with ScriptDriver.auto(rt, update_interval=0.001) as driver:
        start = driver.loop.time()
        with pytest.raises(TimeoutError):
            async with driver.page(page).expect_navigation(timeout=0.08):
                await asyncio.sleep(0.06)
                page._native.emit("begin_loading")
        assert driver.loop.time() - start < 0.12
        assert not page._state.waiters and not driver._demands
    rt.close()


async def test_expect_navigation_close_and_loading_failure_clean_up():
    from ultralight_py import PageLoadError

    rt = runtime()
    page = view(rt)
    async with ScriptDriver.auto(rt) as driver:
        with pytest.raises(PageLoadError):
            async with driver.page(page).expect_navigation():
                page._native.emit("begin_loading")
                page._state.emit(
                    "fail_loading",
                    SimpleNamespace(
                        frame=SimpleNamespace(is_main_frame=True),
                        description="failed",
                        domain="http",
                        code=500,
                    ),
                )
        assert not page._state.waiters
        # A failure from the old document does not block a new navigation.
        async with driver.page(page).expect_navigation():
            page.load_html("replacement")
            page._native.emit("dom_ready")
        with pytest.raises(UltralightError) as error:
            async with driver.page(page).expect_navigation():
                page.close()
        assert error.value.code == ErrorCode.Closed
        assert not page._state.waiters
    rt.close()


@pytest.mark.parametrize("in_action", [False, True])
async def test_expect_navigation_external_cancel_cleans_up(in_action):
    rt = runtime()
    page = view(rt)
    entered = asyncio.Event()
    async with ScriptDriver.auto(rt, update_interval=0.001) as driver:

        async def action():
            async with driver.page(page).expect_navigation():
                entered.set()
                if in_action:
                    await asyncio.Future()

        job = asyncio.create_task(action())
        await entered.wait()
        await asyncio.sleep(0)
        job.cancel()
        with pytest.raises(asyncio.CancelledError):
            await job
        assert not page._state.waiters and not driver._demands
    assert not rt._async_work
    rt.close()


async def test_expect_navigation_rejects_explicit_supersession_after_native_action():
    rt = runtime()
    page = view(rt)
    async with ScriptDriver.auto(rt) as driver:
        with pytest.raises(UltralightError) as error:
            async with driver.page(page).expect_navigation():
                page._native.emit("begin_loading")
                page.load_url("other")
                page._native.emit("dom_ready")
        assert error.value.code == ErrorCode.PageGone
        assert not page._state.waiters
    rt.close()
