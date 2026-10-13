import asyncio
from types import SimpleNamespace

import pytest

from tests.wait_fakes import runtime, view
from ultralight_py import ErrorCode, PageLoadError, UltralightError

pytestmark = pytest.mark.asyncio


async def test_wait_is_passive_and_callbacks_do_not_replace_it():
    rt = runtime()
    page = view(rt)
    seen = []
    page.set_callbacks(dom_ready=lambda event: seen.append("legacy"))
    first = page.on("dom_ready", lambda event: seen.append("first"))
    second = page.on("dom_ready", lambda event: seen.append("second"))
    page.load_html("<body>")
    waiting = asyncio.create_task(page.wait_ready())
    other = asyncio.create_task(page.wait_ready())
    await asyncio.sleep(0)
    await asyncio.sleep(0.01)
    assert rt._native.updates == rt._native.renders == 0
    page.set_callbacks(console=lambda event: None)
    first.close()
    page._native.emit("dom_ready", main=False)
    assert not waiting.done()
    page._native.emit("dom_ready")
    await asyncio.gather(waiting, other)
    assert seen == ["second", "second"]
    assert page.is_ready
    page.close()
    assert second.closed
    rt.close()


async def test_callback_failures_and_subscription_changes_are_isolated():
    rt = runtime()
    page = view(rt)
    seen = []
    late = []

    def legacy(event):
        assert page.is_ready
        late.append(page.on("dom_ready", lambda event: seen.append("late")))
        removed.close()
        raise ValueError("bad listener")

    page.set_callbacks(dom_ready=legacy)
    removed = page.on("dom_ready", lambda event: seen.append("removed"))
    page.on("dom_ready", lambda event: seen.append("kept"))
    page.load_html("<body>")
    waiting = asyncio.create_task(page.wait_ready())
    await asyncio.sleep(0)
    page._native.emit("dom_ready")
    await waiting
    assert seen == ["kept"]
    assert rt.errors[0].code == ErrorCode.HostException
    assert "bad listener" in str(rt.errors[0])
    page._native.emit("dom_ready")
    assert seen == ["kept", "kept", "late"]
    rt.close()


async def test_load_resets_ready_before_delayed_begin_and_invalidates_old_waits():
    rt = runtime()
    page = view(rt)
    page.load_url("same")
    page._native.emit("dom_ready")
    old_id = page.navigation_id
    old = asyncio.create_task(page.wait_until(lambda: False))
    await asyncio.sleep(0)
    page._native.begin_inline = False
    page.load_url("same")
    assert not page.is_ready and page.navigation_id == old_id + 1
    with pytest.raises(UltralightError) as failure:
        await old
    assert failure.value.code == ErrorCode.PageGone
    waiting = asyncio.create_task(page.wait_ready())
    await asyncio.sleep(0)
    page._native.emit("begin_loading")
    assert page.navigation_id == old_id + 1
    page._native.emit("page_settled")
    assert not page.is_settled
    page._native.emit("window_ready")
    assert page.navigation_id == old_id + 1
    assert not waiting.done()
    page._native.emit("dom_ready")
    await waiting
    rt.close()


async def test_page_navigation_invalidates_document_waits_but_not_iframes():
    rt = runtime()
    page = view(rt)
    page.load_html("<body>")
    waiting = asyncio.create_task(page.wait_ready())
    await asyncio.sleep(0)
    page._native.emit("begin_loading", main=False)
    assert not waiting.done()
    page._native.emit("begin_loading")
    with pytest.raises(UltralightError) as error:
        await waiting
    assert error.value.code == ErrorCode.PageGone
    rt.close()


async def test_failure_timeout_cancel_and_close_release_waiters():
    rt = runtime()
    page = view(rt)
    page.load_html("<body>")
    waiting = asyncio.create_task(page.wait_ready())
    await asyncio.sleep(0)
    failure = SimpleNamespace(
        frame=SimpleNamespace(is_main_frame=True), description="missing", domain="HTTP", code=404
    )
    page._native.callbacks["fail_loading"](failure)
    page._native.emit("finish_loading")
    with pytest.raises(PageLoadError) as error:
        await waiting
    assert error.value.failure is failure
    assert not page.is_ready and page.load_failure is failure
    page.load_html("<body>")
    with pytest.raises(TimeoutError):
        await page.wait_ready(0.005)
    waiting = asyncio.create_task(page.wait_ready())
    await asyncio.sleep(0)
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting
    assert not page._state.waiters and not rt._async_work
    waiting = asyncio.create_task(page.wait_ready())
    await asyncio.sleep(0)
    rt.close()
    with pytest.raises(UltralightError) as error:
        await waiting
    assert error.value.code == ErrorCode.Closed
    assert not page._state.waiters and not rt._async_work


async def test_conditions_check_only_after_update_and_return_values():
    rt = runtime()
    page = view(rt)
    calls = []
    value = []

    def predicate():
        calls.append(rt._native.updates)
        return value

    waiting = asyncio.create_task(page.wait_until(predicate))
    await asyncio.sleep(0)
    value.append("answer")
    await asyncio.sleep(0.01)
    assert calls == [0] and not waiting.done()
    rt.update()
    assert await waiting is value
    assert calls == [0, 1]
    assert await page.wait_until(lambda: 42) == 42
    with pytest.raises(TypeError, match="synchronous"):
        await page.wait_until(lambda: asyncio.sleep(0))
    with pytest.raises(ZeroDivisionError):
        await page.wait_until(lambda: 1 / 0)
    for timeout in [True, 0, -1, float("nan"), float("inf"), "5", 10**400]:
        with pytest.raises(ValueError, match="timeout"):
            await page.wait_until(lambda: True, timeout)
    rt.close()


async def test_selector_encoding_ready_gate_and_syntax_errors():
    rt = runtime()
    page = view(rt)
    calls = []
    page.evaluate = lambda source: calls.append(source) or True
    page.load_html("<body>")
    waiting = asyncio.create_task(page.wait_for_selector('a[href="x\\y"]'))
    await asyncio.sleep(0)
    rt.update()
    assert not calls
    page._native.emit("dom_ready")
    rt.update()
    assert await waiting is True
    assert calls == ['!!document.querySelector("a[href=\\"x\\\\y\\"]")']
    for selector in [None, "", 3]:
        with pytest.raises(ValueError, match="selector"):
            await page.wait_for_selector(selector)
    rt.close()


async def test_settled_event_and_existing_state():
    rt = runtime()
    page = view(rt)
    urls = []
    page.set_callbacks(page_settled=urls.append)
    page.load_html("<body>")
    waiting = asyncio.create_task(page.wait_settled())
    await asyncio.sleep(0)
    page._native.emit("dom_ready")
    assert not waiting.done()
    page._native.emit("page_settled")
    await waiting
    await page.wait_settled()
    assert page.is_settled and urls == ["https://example.test"]
    page.load_html("<body>")
    assert not page.is_settled
    rt.close()


async def test_predicate_can_close_its_page_without_breaking_other_waiters():
    rt = runtime()
    left, right = view(rt), view(rt)

    def close_left():
        if rt._native.updates:
            left.close()
            return True
        return False

    first = asyncio.create_task(left.wait_until(close_left))
    second = asyncio.create_task(right.wait_until(lambda: rt._native.updates))
    await asyncio.sleep(0)
    rt.update()
    with pytest.raises(UltralightError) as error:
        await first
    assert error.value.code == ErrorCode.Closed
    assert await second == 1
    rt.close()
