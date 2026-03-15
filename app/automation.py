from __future__ import annotations

import asyncio
import logging
import os
import platform
import random
import shutil
import subprocess
from datetime import datetime

from patchright.async_api import async_playwright

from app.database import update_page_status, get_page

log = logging.getLogger(__name__)

_SYSTEM = platform.system()


def _get_chrome_user_data_dir() -> str:
    if _SYSTEM == "Darwin":
        return os.path.expanduser("~/Library/Application Support/Google/Chrome")
    elif _SYSTEM == "Windows":
        return os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "User Data")
    else:
        return os.path.expanduser("~/.config/google-chrome")


def _get_chrome_exe() -> str:
    if _SYSTEM == "Windows":
        for base in [os.environ.get("PROGRAMFILES", ""), os.environ.get("PROGRAMFILES(X86)", "")]:
            p = os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")
            if os.path.isfile(p):
                return p
        return "chrome"
    elif _SYSTEM == "Darwin":
        return "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    else:
        return shutil.which("google-chrome") or shutil.which("chromium-browser") or "google-chrome"


CDP_PORT = 9222


def _kill_chrome():
    """Закрыть все процессы Chrome."""
    try:
        if _SYSTEM == "Windows":
            subprocess.run(["taskkill", "/F", "/IM", "chrome.exe"], capture_output=True)
        else:
            subprocess.run(["pkill", "-f", "Google Chrome"], capture_output=True)
    except Exception as e:
        log.warning("Не удалось закрыть Chrome: %s", e)


def _launch_chrome_debug(user_data_dir: str, url: str) -> subprocess.Popen:
    """Запустить Chrome с remote debugging и открыть URL."""
    exe = _get_chrome_exe()
    args = [
        exe,
        f"--user-data-dir={user_data_dir}",
        f"--remote-debugging-port={CDP_PORT}",
        "--no-first-run",
        "--disable-sync",
        url,
    ]
    if _SYSTEM == "Windows":
        return subprocess.Popen(args, creationflags=subprocess.DETACHED_PROCESS)
    else:
        return subprocess.Popen(args, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _start_chrome():
    """Открыть Chrome обратно (без debugging)."""
    try:
        exe = _get_chrome_exe()
        if _SYSTEM == "Windows":
            subprocess.Popen([exe], creationflags=subprocess.DETACHED_PROCESS)
        else:
            subprocess.Popen([exe], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        log.warning("Не удалось запустить Chrome: %s", e)

# "Купити" button on coins.bank.gov.ua
CLICK_SELECTOR = "#r_buy_intovar button.buy"
# After click, button is replaced with "В кошику" link
VERIFY_SELECTOR = "#r_buy_intovar a.popup_cart"
# Cloudflare Turnstile iframe
TURNSTILE_IFRAME = "challenges.cloudflare.com"

WAIT_FOR_BUTTON_SEC = 3     # wait for "Купити" after page load
WAIT_FOR_TURNSTILE_SEC = 5  # wait for Turnstile iframe after clicking "Купити"
WAIT_FOR_CART_SEC = 15       # wait for "В кошику" after solving captcha

_lock = asyncio.Lock()

# Track running tasks so they can be cancelled
_running_tasks: dict[int, asyncio.Task] = {}


async def run_page_task(page_id: int, broadcast):
    task = asyncio.current_task()
    _running_tasks[page_id] = task
    try:
        async with _lock:
            await _run(page_id, broadcast)
    except asyncio.CancelledError:
        await update_page_status(page_id, "stopped", last_error="Остановлено пользователем")
        await broadcast(page_id)
    finally:
        _running_tasks.pop(page_id, None)


def stop_page_task(page_id: int) -> bool:
    task = _running_tasks.get(page_id)
    if task and not task.done():
        task.cancel()
        return True
    return False


# --------------- Helpers ---------------

async def _is_visible(page, selector: str) -> bool:
    """Check if an element matching selector exists and is visible."""
    try:
        el = await page.query_selector(selector)
        return el is not None and await el.is_visible()
    except Exception:
        return False


# --------------- Main automation ---------------

async def _run(page_id: int, broadcast):
    page_data = await get_page(page_id)
    if not page_data:
        return

    window_end = datetime.fromisoformat(page_data["window_end"])
    url = page_data["url"]

    await update_page_status(page_id, "in-progress")
    await broadcast(page_id)

    chrome_proc = None
    try:
        user_data_dir = _get_chrome_user_data_dir()
        log.info("Закрываю Chrome, профиль: %s", user_data_dir)
        _kill_chrome()
        await asyncio.sleep(2)

        chrome_proc = _launch_chrome_debug(user_data_dir, url)
        await asyncio.sleep(3)  # дать Chrome время запуститься

        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
            context = browser.contexts[0]

            # Найти вкладку с нашим URL
            browser_page = None
            for pg in context.pages:
                if pg.url != "about:blank":
                    browser_page = pg
                    break
            if not browser_page:
                browser_page = context.pages[0] if context.pages else await context.new_page()
                await browser_page.goto(url, wait_until="domcontentloaded", timeout=30000)

            success = False
            while datetime.now() < window_end:
                try:
                    # ====================================================
                    # Step 0: ALWAYS check "В кошику" first.
                    # ====================================================
                    if await _is_visible(browser_page, VERIFY_SELECTOR):
                        await update_page_status(page_id, "successful")
                        await broadcast(page_id)
                        success = True
                        break

                    # ====================================================
                    # Step 1: Wait up to 3 s for "Купити" button.
                    # ====================================================
                    btn = None
                    for _ in range(int(WAIT_FOR_BUTTON_SEC * 4)):
                        if await _is_visible(browser_page, VERIFY_SELECTOR):
                            await update_page_status(page_id, "successful")
                            await broadcast(page_id)
                            success = True
                            break
                        btn = await browser_page.query_selector(CLICK_SELECTOR)
                        if btn and await btn.is_visible():
                            break
                        btn = None
                        await asyncio.sleep(0.25)

                    if success:
                        break

                    if not btn:
                        await update_page_status(
                            page_id, "in-progress",
                            last_error="Ни «Купити», ни «В кошику» — обновляю страницу…",
                            inc_attempts=True,
                        )
                        await broadcast(page_id)
                        await asyncio.sleep(random.uniform(1, 3))
                        try:
                            await browser_page.reload(wait_until="domcontentloaded", timeout=15000)
                        except Exception:
                            pass
                        continue

                    # ====================================================
                    # Step 2: Click "Купити"
                    # ====================================================
                    await btn.click()
                    await update_page_status(
                        page_id, "in-progress", last_error="Нажато «Купити»…"
                    )
                    await broadcast(page_id)

                    # ====================================================
                    # Step 3: Handle Turnstile captcha (up to 5 s).
                    # ====================================================
                    turnstile_frame = None
                    for _ in range(int(WAIT_FOR_TURNSTILE_SEC * 4)):
                        if await _is_visible(browser_page, VERIFY_SELECTOR):
                            await update_page_status(page_id, "successful")
                            await broadcast(page_id)
                            success = True
                            break
                        for frame in browser_page.frames:
                            if TURNSTILE_IFRAME in (frame.url or ""):
                                turnstile_frame = frame
                                break
                        if turnstile_frame:
                            break
                        await asyncio.sleep(0.25)

                    if success:
                        break

                    if turnstile_frame:
                        await update_page_status(
                            page_id, "in-progress", last_error="Captcha найдена, кликаю…"
                        )
                        await broadcast(page_id)
                        await asyncio.sleep(0.5)
                        try:
                            cb = await turnstile_frame.wait_for_selector(
                                "input[type='checkbox'], .ctp-checkbox-label, #challenge-stage",
                                timeout=5000,
                            )
                            if cb:
                                await cb.click()
                        except Exception:
                            iframe_el = await browser_page.query_selector(
                                f"iframe[src*='{TURNSTILE_IFRAME}']"
                            )
                            if iframe_el:
                                await iframe_el.click()
                        await update_page_status(
                            page_id, "in-progress", last_error="Captcha решена, жду «В кошику»…"
                        )
                        await broadcast(page_id)

                    # ====================================================
                    # Step 4: Wait up to 15 s for "В кошику" to confirm.
                    # ====================================================
                    verified = False
                    for _ in range(int(WAIT_FOR_CART_SEC * 4)):
                        if await _is_visible(browser_page, VERIFY_SELECTOR):
                            verified = True
                            break
                        await asyncio.sleep(0.25)

                    if verified:
                        await update_page_status(page_id, "successful")
                        await broadcast(page_id)
                        success = True
                        break

                    # Click happened but "В кошику" never appeared — retry
                    await update_page_status(
                        page_id, "in-progress",
                        last_error="Нажато, но «В кошику» не появилось — обновляю…",
                        inc_attempts=True,
                    )
                    await broadcast(page_id)
                    await asyncio.sleep(random.uniform(1, 3))
                    try:
                        await browser_page.reload(wait_until="domcontentloaded", timeout=15000)
                    except Exception:
                        pass

                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    await update_page_status(
                        page_id, "in-progress", last_error=str(e), inc_attempts=True
                    )
                    await broadcast(page_id)
                    await asyncio.sleep(random.uniform(1, 3))

            if not success:
                await update_page_status(
                    page_id, "expired", last_error="Время окна истекло"
                )
                await broadcast(page_id)

            await browser.close()

    except asyncio.CancelledError:
        raise
    except Exception as e:
        await update_page_status(page_id, "failed", last_error=str(e))
        await broadcast(page_id)
    finally:
        if chrome_proc:
            try:
                chrome_proc.terminate()
            except Exception:
                pass
        _start_chrome()
