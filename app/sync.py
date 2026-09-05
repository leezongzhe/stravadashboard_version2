import asyncio
import re

from playwright.async_api import async_playwright

from .config import BROWSER_DATA_DIR, INCOMING_DIR, load_config
from .database import (
    imported_activity_ids,
    initialize_database,
    record_download_failure,
    register_discovered,
    reset_failures,
)
from .importer import import_all, import_tcx


TRAINING_URL = "https://www.strava.com/athlete/training"


def _authenticated(url):
    return bool(re.match(r"https://(www\.)?strava\.com/(?!login|register)", url))


async def launch_browser(playwright):
    """Launch the browser using Version 1's proven persistent-profile flow."""
    BROWSER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    options = {
        "user_data_dir": str(BROWSER_DATA_DIR),
        "headless": False,
        "accept_downloads": True,
    }
    try:
        return await playwright.chromium.launch_persistent_context(
            channel="chrome",
            **options,
        )
    except Exception as chrome_error:
        print(f"[!] Google Chrome could not be launched: {chrome_error}")
        print("[*] Trying Playwright Chromium instead...")
        return await playwright.chromium.launch_persistent_context(**options)


async def ensure_login(page):
    await page.goto(TRAINING_URL, wait_until="domcontentloaded")
    await asyncio.sleep(2)
    if _authenticated(page.url):
        print("[OK] Existing Strava session found.")
        return

    google_name = re.compile(r"(continue|sign up|log in|sign in).*google|google.*(continue|sign up|log in|sign in)", re.I)
    controls = [page.get_by_role("button", name=google_name), page.get_by_role("link", name=google_name)]
    for control in controls:
        if await control.count() and await control.first.is_visible():
            print("[*] Reusing saved Google authentication...")
            await control.first.click()
            break

    print("[*] If prompted, finish Google/Strava login in the browser.")
    try:
        await page.wait_for_url(
            re.compile(r"https://(www\.)?strava\.com/(?!login|register).+"),
            timeout=300000,
            wait_until="domcontentloaded",
        )
    except Exception as error:
        raise RuntimeError("Login was not completed within five minutes") from error

    await page.goto(TRAINING_URL, wait_until="domcontentloaded")
    await asyncio.sleep(2)
    if not _authenticated(page.url):
        raise RuntimeError("Strava login could not be verified")
    print("[OK] Strava login completed.")


async def discover_activity_ids(page, scroll_rounds=12):
    """Scroll the training log to include lazy-loaded historical activities."""
    await page.goto(TRAINING_URL, wait_until="domcontentloaded")
    await asyncio.sleep(3)
    previous_height = 0
    stable_rounds = 0
    for _ in range(scroll_rounds):
        height = await page.evaluate("document.body.scrollHeight")
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1)
        if height == previous_height:
            stable_rounds += 1
            if stable_rounds >= 2:
                break
        else:
            stable_rounds = 0
        previous_height = height

    hrefs = await page.eval_on_selector_all(
        "a[href*='/activities/']",
        "elements => elements.map(element => element.getAttribute('href'))",
    )
    ids = set()
    for href in hrefs:
        match = re.search(r"/activities/(\d+)", href or "")
        if match:
            ids.add(match.group(1))
    print(f"[OK] Discovered {len(ids)} activities.")
    return ids


async def download_tcx(page, activity_id):
    INCOMING_DIR.mkdir(parents=True, exist_ok=True)
    output = INCOMING_DIR / f"{activity_id}.tcx"
    download_page = await page.context.new_page()
    try:
        async with download_page.expect_download(timeout=20000) as info:
            try:
                await download_page.goto(f"https://www.strava.com/activities/{activity_id}/export_tcx")
            except Exception as error:
                if "ERR_ABORTED" not in str(error) and "Download is starting" not in str(error):
                    raise
        download = await info.value
        await download.save_as(str(output))
        return output
    finally:
        await download_page.close()


async def synchronize(retry_failed=False, skip_browser=False):
    initialize_database()
    config = load_config()
    if retry_failed:
        reset_failures()
        print("[*] Failed and unavailable activities were reset for retry.")

    # Always repair/import local files first. This also migrates copied v1 data.
    print("[*] Importing local TCX files...")
    local_results = import_all()
    if skip_browser:
        return {"local": local_results, "discovered": 0, "downloaded": 0, "failed": 0}

    async with async_playwright() as playwright:
        context = await launch_browser(playwright)
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            await ensure_login(page)
            discovered = await discover_activity_ids(page)
            for activity_id in discovered:
                register_discovered(activity_id)

            handled = imported_activity_ids()
            pending = sorted(discovered - handled)
            downloaded = 0
            failed = 0
            print(f"[*] {len(pending)} activities require download or retry.")
            for index, activity_id in enumerate(pending, 1):
                print(f"[{index}/{len(pending)}] Activity {activity_id}")
                existing_file = INCOMING_DIR / f"{activity_id}.tcx"
                try:
                    path = existing_file if existing_file.exists() else await download_tcx(page, activity_id)
                    import_tcx(path)
                    downloaded += 1
                    print("[OK] Downloaded and imported.")
                except Exception as error:
                    failed += 1
                    status = record_download_failure(
                        activity_id,
                        error,
                        int(config["automatic_retry_limit"]),
                    )
                    print(f"[!] {status}: {error}")
                await asyncio.sleep(1)
            return {
                "local": local_results,
                "discovered": len(discovered),
                "downloaded": downloaded,
                "failed": failed,
            }
        finally:
            await context.close()
