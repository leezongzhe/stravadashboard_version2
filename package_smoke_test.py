"""Developer smoke test for an already-running packaged dashboard."""

import argparse
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright


async def verify(url):
    chrome_candidates = [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path.home() / "AppData/Local/Google/Chrome/Application/chrome.exe",
    ]
    chrome = next((path for path in chrome_candidates if path.exists()), None)
    if chrome is None:
        raise RuntimeError("Google Chrome was not found")
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(executable_path=str(chrome), headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        await page.goto(url, wait_until="domcontentloaded")
        await page.get_by_text("Strava Dashboard — Version 2", exact=False).wait_for(timeout=30000)
        await page.get_by_text("Local backup and restore", exact=False).count()
        body = await page.locator("body").inner_text()
        if any(label not in body for label in ("Training history", "Activity analysis", "Backup", "Settings")):
            raise RuntimeError("Expected dashboard navigation was not rendered")
        coach_controls = await page.get_by_text("AI Coach", exact=False).count()
        if coach_controls < 1:
            raise RuntimeError("The floating AI Coach control was not rendered")
        if errors:
            raise RuntimeError("; ".join(errors))
        await browser.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url", nargs="?", default="http://127.0.0.1:8767")
    args = parser.parse_args()
    asyncio.run(verify(args.url))
    print("Packaged dashboard rendered successfully.")


if __name__ == "__main__":
    main()
