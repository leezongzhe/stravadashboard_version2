import asyncio
import re
import socket
import subprocess
from pathlib import Path

from playwright.async_api import async_playwright

from .config import BROWSER_DATA_DIR, INCOMING_DIR, load_config
from .database import (
    get_app_setting,
    imported_activity_ids,
    initialize_database,
    record_download_failure,
    register_discovered,
    reset_failures,
    retryable_activity_ids,
    set_app_setting,
)
from .importer import import_all, import_tcx


TRAINING_URL = "https://www.strava.com/athlete/training"
INITIAL_DOWNLOAD_SETUP_SETTING = "initial_download_setup_complete"


class ChromeSession:
    """Expose a BrowserContext-like interface and own the Chrome process."""

    def __init__(self, browser, context, process):
        self.browser = browser
        self.context = context
        self.process = process

    @property
    def pages(self):
        return self.context.pages

    async def new_page(self):
        return await self.context.new_page()

    async def close(self):
        try:
            await self.browser.close()
        finally:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    await asyncio.to_thread(self.process.wait, 5)
                except subprocess.TimeoutExpired:
                    self.process.kill()


def _find_chrome():
    candidates = [
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path.home() / "AppData/Local/Google/Chrome/Application/chrome.exe",
    ]
    return next((path for path in candidates if path.exists()), None)


def _find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


async def _connect_to_chrome(playwright, port, process, timeout=20):
    """Wait until Chrome's local DevTools endpoint accepts a connection."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    last_error = None
    while loop.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Chrome exited during startup (code {process.returncode}).")
        try:
            return await playwright.chromium.connect_over_cdp(
                f"http://127.0.0.1:{port}",
                timeout=1000,
            )
        except Exception as error:
            last_error = error
        await asyncio.sleep(0.25)
    raise RuntimeError(
        "Chrome remote-debugging endpoint did not start within 20 seconds."
    ) from last_error


def _authenticated(url):
    return bool(re.match(r"https://(www\.)?strava\.com/(?!login|register)", url))


async def launch_browser(playwright):
    """Start normal Chrome, then attach Playwright to the private V2 profile."""
    BROWSER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    chrome_path = _find_chrome()
    if chrome_path is None:
        raise RuntimeError("Google Chrome was not found. Install Chrome before synchronizing.")

    port = _find_free_port()
    command = [
        str(chrome_path),
        f"--user-data-dir={BROWSER_DATA_DIR}",
        f"--remote-debugging-port={port}",
        "--no-first-run",
        "--no-default-browser-check",
        "about:blank",
    ]
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(command, creationflags=creation_flags)
    try:
        browser = await _connect_to_chrome(playwright, port, process)
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        return ChromeSession(browser, context, process)
    except Exception:
        if process.poll() is None:
            process.terminate()
        raise


async def ensure_login(page):
    await page.goto(TRAINING_URL, wait_until="domcontentloaded")
    await asyncio.sleep(2)
    if _authenticated(page.url):
        print("[OK] Existing Strava session found.")
        return

    google_name = re.compile(
        r"(continue|sign up|log in|sign in).*google|google.*(continue|sign up|log in|sign in)",
        re.I,
    )
    controls = [
        page.get_by_role("button", name=google_name),
        page.get_by_role("link", name=google_name),
    ]
    for control in controls:
        if await control.count() and await control.first.is_visible():
            print("[*] Pressing the Strava Google login control...")
            await control.first.click()
            await asyncio.sleep(2)
            break

    if "accounts.google.com" in page.url and "/signin/rejected" in page.url:
        raise RuntimeError(
            "Google rejected this browser session. Close every Chrome window, "
            "remove this app's browser_data folder, and run synchronization again."
        )

    print("[*] If prompted, finish Google/Strava login in the open Chrome window.")
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
    print("[OK] Strava login completed and saved in Version 2 browser_data.")


def _extract_activity_ids(hrefs):
    ids = []
    seen = set()
    for href in hrefs:
        match = re.search(r"/activities/(\d+)", href or "")
        if match and match.group(1) not in seen:
            seen.add(match.group(1))
            ids.append(match.group(1))
    return ids


def _pagination_total(text):
    match = re.search(r"\b\d+\s*[-–]\s*\d+\s+of\s+([\d,]+)\b", text or "", re.I)
    return int(match.group(1).replace(",", "")) if match else None


async def _activity_ids_on_page(page):
    hrefs = await page.eval_on_selector_all(
        "a[href*='/activities/']",
        "elements => elements.map(element => element.getAttribute('href'))",
    )
    return _extract_activity_ids(hrefs)


async def _find_next_control(page):
    next_name = re.compile(r"^\s*(next|next page|→|›|>)\s*$", re.I)
    candidates = [
        page.locator("a[rel='next']"),
        page.locator("button[aria-label*='next' i]"),
        page.locator("a[aria-label*='next' i]"),
        page.get_by_role("button", name=next_name),
        page.get_by_role("link", name=next_name),
    ]
    for candidate in candidates:
        if not await candidate.count():
            continue
        control = candidate.first
        if not await control.is_visible() or not await control.is_enabled():
            continue
        aria_disabled = (await control.get_attribute("aria-disabled") or "").lower()
        classes = (await control.get_attribute("class") or "").lower().split()
        if aria_disabled == "true" or "disabled" in classes:
            continue
        return control
    return None


async def discover_activity_ids(
    page,
    history_limit=None,
    routine_pages=2,
    scroll_rounds=12,
    settle_seconds=3,
    max_pages=500,
):
    """Discover initial history or a bounded number of newest routine pages."""
    if history_limit != "all" and history_limit is not None:
        history_limit = int(history_limit)
        if history_limit < 1:
            raise ValueError("Initial download count must be at least 1")

    await page.goto(TRAINING_URL, wait_until="domcontentloaded")
    await asyncio.sleep(settle_seconds)
    discovered = []
    discovered_set = set()
    seen_pages = set()
    expected_total = None
    routine_pages = max(1, int(routine_pages))
    paginate = history_limit is not None or routine_pages > 1

    for page_number in range(1, max_pages + 1):
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

        page_ids = await _activity_ids_on_page(page)
        if not page_ids:
            raise RuntimeError(f"No activity links were found on training page {page_number}.")
        signature = tuple(sorted(page_ids))
        if signature in seen_pages:
            raise RuntimeError(
                f"Training pagination repeated page {page_number}; initial setup remains incomplete."
            )
        seen_pages.add(signature)
        for activity_id in page_ids:
            if activity_id not in discovered_set:
                discovered_set.add(activity_id)
                discovered.append(activity_id)

        body_text = await page.locator("body").inner_text()
        expected_total = _pagination_total(body_text) or expected_total
        print(
            f"[OK] Training page {page_number}: {len(page_ids)} activities "
            f"({len(discovered)} unique discovered)."
        )
        if history_limit is None and page_number >= routine_pages:
            break

        requested_count = None if history_limit == "all" else history_limit
        required_count = (
            min(requested_count, expected_total)
            if requested_count is not None and expected_total is not None
            else requested_count
        )
        if required_count is not None and len(discovered) >= required_count:
            break
        if expected_total is not None and len(discovered) >= expected_total:
            break

        next_control = await _find_next_control(page)
        if next_control is None:
            if expected_total is not None and len(discovered) < expected_total:
                raise RuntimeError(
                    f"Strava reports {expected_total} activities, but pagination stopped after "
                    f"discovering {len(discovered)}. Initial setup remains incomplete."
                )
            if page_number == 1 and expected_total is None and len(page_ids) >= 20:
                raise RuntimeError(
                    "The first page is full, but the Next control and activity total could not be found. "
                    "Initial setup remains incomplete."
                )
            break

        previous_signature = signature
        await next_control.click()
        deadline = asyncio.get_running_loop().time() + 20
        while asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.25)
            current_ids = await _activity_ids_on_page(page)
            if current_ids and tuple(sorted(current_ids)) != previous_signature:
                break
        else:
            raise RuntimeError(
                f"Strava did not advance beyond training page {page_number}. "
                "Initial setup remains incomplete."
            )
        await asyncio.sleep(0.75)
    else:
        raise RuntimeError(f"Training history exceeded the safety limit of {max_pages} pages.")

    if history_limit != "all" and history_limit is not None:
        discovered = discovered[:history_limit]
    expected_requested = (
        expected_total
        if history_limit == "all"
        else min(history_limit, expected_total)
        if history_limit is not None and expected_total is not None
        else history_limit
    )
    if paginate and expected_requested is not None and len(discovered) < expected_requested:
        raise RuntimeError(
            f"Initial history scan found {len(discovered)} of {expected_requested} requested activities."
        )
    print(f"[OK] Selected {len(discovered)} activities across {len(seen_pages)} page(s).")
    return set(discovered)


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


async def synchronize(retry_failed=False, skip_browser=False, initial_download_limit=None):
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
            initial_setup_complete = (
                get_app_setting(INITIAL_DOWNLOAD_SETUP_SETTING) == "true"
            )
            if not initial_setup_complete and initial_download_limit is None:
                raise RuntimeError(
                    "Choose 'Download all' or enter the latest number of activities for first-time setup."
                )
            history_limit = initial_download_limit if not initial_setup_complete else None
            if history_limit == "all":
                print("[*] First-time setup will download all available activities.")
            elif history_limit is not None:
                print(f"[*] First-time setup will download the latest {history_limit} activities.")
            else:
                print("[*] Initial setup is complete; inspecting the newest two pages.")

            discovered = await discover_activity_ids(page, history_limit=history_limit)
            for activity_id in discovered:
                register_discovered(activity_id)
            if not initial_setup_complete:
                set_app_setting(INITIAL_DOWNLOAD_SETUP_SETTING, "true")
                set_app_setting("initial_download_selection", history_limit)
                print("[OK] First-time download selection recorded.")

            handled = imported_activity_ids()
            pending = sorted(
                (discovered - handled)
                | retryable_activity_ids(int(config["automatic_retry_limit"])),
                key=int,
                reverse=True,
            )
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
                "initial_setup": not initial_setup_complete,
            }
        finally:
            await context.close()
