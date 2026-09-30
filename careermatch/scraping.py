"""Opt-in browser collector for explicitly allowed, public HTTPS job pages."""

import asyncio
import hashlib
import ipaddress
import json
import socket
from collections.abc import Awaitable, Callable
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup
from pydantic import Field

from .models import RawJob, StrictModel

USER_AGENT = "CareerMatchPortfolio/0.1"


class ScrapeResult(StrictModel):
    jobs: list[RawJob] = Field(default_factory=list)
    errors: dict[str, str] = Field(default_factory=dict)
    duplicates: int = 0


def validate_url(url: str, allowed_hosts: set[str]) -> str:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or parsed.hostname not in allowed_hosts
    ):
        raise ValueError("Only HTTPS URLs on explicitly allowed hosts are permitted")
    return parsed.hostname


async def check_public_host(host: str):
    records = await asyncio.to_thread(socket.getaddrinfo, host, 443, type=socket.SOCK_STREAM)
    if not records or any(not ipaddress.ip_address(r[4][0]).is_global for r in records):
        raise ValueError("Non-public destination blocked")


def parse_page(html: str, url: str) -> RawJob:
    soup = BeautifulSoup(html, "html.parser")
    for element in soup.select('script[type="application/ld+json"]'):
        try:
            value = json.loads(element.get_text())
        except (ValueError, TypeError):
            continue
        candidates = value if isinstance(value, list) else [value]
        for candidate in candidates:
            if isinstance(candidate, dict) and "@graph" in candidate:
                candidates.extend(
                    candidate["@graph"] if isinstance(candidate["@graph"], list) else []
                )
            if not isinstance(candidate, dict) or candidate.get("@type") != "JobPosting":
                continue
            org = candidate.get("hiringOrganization", {})
            company = org.get("name", "Unknown") if isinstance(org, dict) else str(org)
            return RawJob(
                id=hashlib.sha256(url.encode()).hexdigest()[:16],
                title=candidate.get("title", "Untitled"),
                company=company,
                text=BeautifulSoup(str(candidate.get("description", "")), "html.parser").get_text(
                    " ", strip=True
                ),
                source=url,
            )
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    heading = soup.find("h1") or soup.find("title")
    body = soup.find("main") or soup.body or soup
    return RawJob(
        id=hashlib.sha256(url.encode()).hexdigest()[:16],
        title=heading.get_text(" ", strip=True) if heading else "Untitled",
        company="Unknown (page text fallback)",
        text=body.get_text(" ", strip=True)[:30000],
        source=url,
    )


async def collect(
    urls: list[str],
    fetch: Callable[[str], Awaitable[RawJob]],
    concurrency: int = 4,
    timeout: float = 35,
    retries: int = 1,
) -> ScrapeResult:
    if not 1 <= concurrency <= 8 or not 1 <= len(urls) <= 100 or not 0 <= retries <= 2:
        raise ValueError("Use 1-100 URLs, concurrency 1-8, retries 0-2")
    semaphore = asyncio.Semaphore(concurrency)
    result = ScrapeResult()
    unique_urls = list(dict.fromkeys(urls))
    result.duplicates = len(urls) - len(unique_urls)

    async def one(url):
        async with semaphore:
            for attempt in range(retries + 1):
                try:
                    return url, await asyncio.wait_for(fetch(url), timeout), None
                except (TimeoutError, httpx.TransportError):
                    if attempt == retries:
                        return url, None, "Transient fetch failure after bounded retries"
                    await asyncio.sleep(0.2 * (attempt + 1))
                except Exception as exc:
                    return url, None, f"Fetch rejected: {type(exc).__name__}"

    seen = set()
    for url, job, error in await asyncio.gather(*(one(u) for u in unique_urls)):
        if error:
            result.errors[url] = error
        else:
            fingerprint = hashlib.sha256(
                (job.company.casefold() + "\n" + job.title.casefold() + "\n" + job.text).encode()
            ).hexdigest()
            if fingerprint in seen:
                result.duplicates += 1
            else:
                seen.add(fingerprint)
                result.jobs.append(job)
    return result


class BrowserCollector:
    def __init__(self, allowed_hosts: set[str]):
        self.allowed_hosts = {h.casefold() for h in allowed_hosts}
        self.locks: dict[str, asyncio.Lock] = {}

    async def fetch(self, browser, url: str) -> RawJob:
        host = validate_url(url, self.allowed_hosts)
        await check_public_host(host)
        # Serialize per host, honor robots, and pause between attempts.
        async with self.locks.setdefault(host, asyncio.Lock()):
            async with httpx.AsyncClient(
                timeout=10, follow_redirects=False, trust_env=False
            ) as client:
                response = await client.get(
                    f"https://{host}/robots.txt", headers={"User-Agent": USER_AGENT}
                )
                if response.status_code != 200:
                    raise ValueError("Robots policy unavailable; collection blocked")
                policy = RobotFileParser()
                policy.parse(response.text.splitlines())
                if not policy.can_fetch(USER_AGENT, url):
                    raise ValueError("Robots policy disallows collection")
                delay = policy.crawl_delay(USER_AGENT) or policy.crawl_delay("*") or 1
                if delay > 10:
                    raise ValueError("Crawl delay exceeds this bounded collector's budget")
                await asyncio.sleep(max(1, delay))
            context = await browser.new_context(user_agent=USER_AGENT, service_workers="block")
            try:

                async def guard(route):
                    # Deliberately block third-party assets and redirected destinations.
                    try:
                        target = validate_url(route.request.url, {host})
                        await check_public_host(target)
                        if route.request.is_navigation_request() and route.request.url != url:
                            raise ValueError("Redirect navigation blocked")
                    except (ValueError, OSError):
                        await route.abort()
                        return
                    await route.continue_()

                await context.route("**/*", guard)
                page = await context.new_page()
                response = await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                if response is None or response.status >= 400 or page.url != url:
                    raise ValueError("Unsuccessful or redirected page")
                return parse_page(await page.content(), url)
            finally:
                await context.close()

    async def run(self, urls: list[str], concurrency: int = 4) -> ScrapeResult:
        try:
            from playwright.async_api import Error as BrowserError
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Install [browser] and run python -m playwright install chromium"
            ) from exc
        async with async_playwright() as p:
            try:
                browser = await p.chromium.launch(headless=True)
            except BrowserError as exc:
                raise RuntimeError(
                    "Chromium could not launch. Run python -m playwright install chromium "
                    "and check browser system dependencies."
                ) from exc
            try:
                return await collect(urls, lambda url: self.fetch(browser, url), concurrency)
            finally:
                await browser.close()
