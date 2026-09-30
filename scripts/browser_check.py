"""Run the actual UI against a local FastAPI server, with no external services."""

import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright


def main():
    output = Path("work")
    output.mkdir(exist_ok=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    with (output / "browser-server.log").open("w", encoding="utf-8") as log:
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "careermatch.api:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            stdout=log,
            stderr=log,
        )
        try:
            with httpx.Client(trust_env=False) as client:
                for _ in range(120):
                    if server.poll() is not None:
                        raise RuntimeError("Demo server exited; inspect work/browser-server.log")
                    try:
                        if client.get(url + "/health", timeout=1).status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(0.25)
                else:
                    raise RuntimeError("Demo server did not become ready")
            with sync_playwright() as p:
                browser = p.chromium.launch()
                try:
                    page = browser.new_page(viewport={"width": 1440, "height": 1100})
                    errors = []
                    page.on("pageerror", lambda err: errors.append(str(err)))
                    page.goto(url)
                    expect(page.locator("#status")).to_contain_text("Synthetic inputs ready")
                    page.get_by_role("button", name="Find the evidence").click()
                    expect(page.locator(".job")).to_have_count(4)
                    expect(page.locator(".job h3").first).to_have_text("Backend Engineer")
                    page.locator(".job summary").first.click()
                    expect(page.locator(".job blockquote").first).to_contain_text("Built Python")
                    with page.expect_download() as item:
                        page.get_by_role("button", name="Download review notes").first.click()
                    item.value.save_as(output / "review.md")
                    assert "Source:" in (output / "review.md").read_text(encoding="utf-8")
                    page.screenshot(path=str(output / "dashboard.png"), full_page=True)
                    page.set_viewport_size({"width": 390, "height": 844})
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    page.screenshot(path=str(output / "mobile.png"), full_page=True)
                    # Malformed input must remove stale results and expose a recoverable error.
                    page.locator(".inputs summary").click()
                    page.locator("#jobs").fill("not JSON")
                    page.get_by_role("button", name="Find the evidence").click()
                    expect(page.locator("#status")).to_have_class("error")
                    expect(page.locator(".job")).to_have_count(0)
                    page.get_by_role("button", name="Reset demo").click()
                    expect(page.locator("#status")).to_contain_text("Synthetic inputs ready")
                    # Render untrusted text as text, never as markup.
                    jobs = json.loads(page.locator("#jobs").input_value())
                    jobs[0]["title"] = '<img src=x onerror="window.injected=true">'
                    page.locator("#jobs").fill(json.dumps(jobs))
                    page.get_by_role("button", name="Find the evidence").click()
                    expect(page.locator(".job")).to_have_count(4)
                    assert page.locator(".job img").count() == 0
                    assert page.evaluate("window.injected === undefined")
                    assert errors == []
                    print(
                        "Browser checks passed: ranking, evidence, export, mobile, "
                        "errors, text safety"
                    )
                finally:
                    browser.close()
        finally:
            server.terminate()
            server.wait(timeout=10)


if __name__ == "__main__":
    main()
