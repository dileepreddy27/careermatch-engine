import asyncio

import pytest

from careermatch.api import ROOT
from careermatch.scraping import (
    BrowserCollector,
    check_public_host,
    collect,
    parse_page,
    validate_url,
)


def test_jsonld_and_fallback():
    html = (ROOT / "fixtures/job.html").read_text(encoding="utf-8")
    job = parse_page(html, "https://jobs.example.org/1")
    assert job.company == "Northstar Labs (fictional)"
    assert job.title == "Backend Engineer"
    fallback = parse_page(
        "<main><h1>Engineer</h1><p>Build Python applications for users.</p></main>",
        "https://jobs.example.org/2",
    )
    assert "Build Python" in fallback.text


async def test_bounded_collection_partial_failure_dedup_and_retry():
    active = peak = retries = 0
    fixture = (ROOT / "fixtures/job.html").read_text(encoding="utf-8")

    async def fetch(url):
        nonlocal active, peak, retries
        active += 1
        peak = max(peak, active)
        try:
            await asyncio.sleep(0.01)
            if url == "bad":
                raise ValueError("Unavailable")
            if url == "retry" and retries == 0:
                retries += 1
                raise TimeoutError
            return parse_page(fixture, url)
        finally:
            active -= 1

    result = await collect(["a", "b", "a", "bad", "retry"], fetch, concurrency=2)
    assert peak == 2
    assert len(result.jobs) == 1
    assert result.duplicates == 3
    assert "bad" in result.errors
    assert retries == 1


async def test_timeout_does_not_hang():
    async def fetch(url):
        await asyncio.sleep(5)

    result = await collect(["slow"], fetch, timeout=0.01, retries=0)
    assert not result.jobs and "slow" in result.errors


@pytest.mark.parametrize(
    "url",
    [
        "http://example.org/x",
        "https://other.org/x",
        "https://user:pass@example.org/x",
        "https://example.org:8443/x",
    ],
)
def test_url_policy(url):
    with pytest.raises(ValueError):
        validate_url(url, {"example.org"})


async def test_private_resolution_rejected(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", lambda *a, **kw: [(2, 1, 6, "", ("127.0.0.1", 443))])
    with pytest.raises(ValueError, match="Non-public"):
        await check_public_host("example.org")


@pytest.mark.parametrize(
    "robots,blocked", [("User-agent: *\nAllow: /", False), ("User-agent: *\nDisallow: /", True)]
)
async def test_browser_collector_policy_and_cleanup(monkeypatch, robots, blocked):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import httpx

    import careermatch.scraping as module

    original = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=robots))
    monkeypatch.setattr(
        module.httpx, "AsyncClient", lambda **kwargs: original(transport=transport, **kwargs)
    )
    monkeypatch.setattr(module, "check_public_host", AsyncMock())
    monkeypatch.setattr(module.asyncio, "sleep", AsyncMock())
    url = "https://jobs.example.org/1"
    page = SimpleNamespace(
        url=url,
        goto=AsyncMock(return_value=SimpleNamespace(status=200)),
        content=AsyncMock(return_value=(ROOT / "fixtures/job.html").read_text()),
    )
    context = SimpleNamespace(
        route=AsyncMock(), new_page=AsyncMock(return_value=page), close=AsyncMock()
    )
    browser = SimpleNamespace(new_context=AsyncMock(return_value=context))
    collector = BrowserCollector({"jobs.example.org"})
    if blocked:
        with pytest.raises(ValueError, match="disallows"):
            await collector.fetch(browser, url)
        browser.new_context.assert_not_awaited()
    else:
        job = await collector.fetch(browser, url)
        assert job.source == url
        context.close.assert_awaited_once()
        route_guard = context.route.call_args.args[1]
        malicious = SimpleNamespace(
            request=SimpleNamespace(url="https://untrusted.example/"),
            abort=AsyncMock(),
            continue_=AsyncMock(),
        )
        await route_guard(malicious)
        malicious.abort.assert_awaited_once()
        malicious.continue_.assert_not_awaited()


@pytest.mark.browser
async def test_browser_renders_job_fixture():
    playwright = pytest.importorskip("playwright.async_api")
    async with playwright.async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            page = await browser.new_page()
            await page.set_content((ROOT / "fixtures/job.html").read_text(encoding="utf-8"))
            assert await page.locator("h1").inner_text() == "Backend Engineer"
            assert (
                parse_page(await page.content(), "https://fixture.example/job").title
                == "Backend Engineer"
            )
        finally:
            await browser.close()
