from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

from app.database import get_pending_scheduled_pages, update_page_status

scheduler = AsyncIOScheduler()

_broadcast_fn = None


def set_broadcast(fn):
    global _broadcast_fn
    _broadcast_fn = fn


async def _job_wrapper(page_id: int):
    from app.automation import run_page_task
    await run_page_task(page_id, _broadcast_fn)


def schedule_page(page_id: int, window_start: str):
    run_date = datetime.fromisoformat(window_start)
    now = datetime.now()

    # All times are local — no timezone conversion
    if run_date <= now:
        run_date = now

    job_id = f"page_{page_id}"
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass

    scheduler.add_job(
        _job_wrapper,
        trigger=DateTrigger(run_date=run_date),
        id=job_id,
        kwargs={"page_id": page_id},
        replace_existing=True,
    )


def cancel_page(page_id: int):
    try:
        scheduler.remove_job(f"page_{page_id}")
    except Exception:
        pass


async def run_page_now(page_id: int):
    """Run a page task immediately in a cancellable asyncio Task."""
    import asyncio
    asyncio.create_task(_job_wrapper(page_id))


async def reschedule_all():
    pages = await get_pending_scheduled_pages()
    for page in pages:
        await update_page_status(page["id"], "scheduled")
        schedule_page(page["id"], page["window_start"])
