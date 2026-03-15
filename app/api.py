import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from sse_starlette.sse import EventSourceResponse

from app.database import init_db, insert_page, get_all_pages, get_page, delete_page, update_page_status
from app.schemas import PageCreate, PageOut
from app.scheduler import scheduler, schedule_page, cancel_page, reschedule_all, run_page_now, set_broadcast

_sse_clients: list[asyncio.Queue] = []


async def broadcast(page_id: int):
    page = await get_page(page_id)
    if not page:
        return
    data = json.dumps(page)
    for q in list(_sse_clients):
        try:
            q.put_nowait(data)
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    set_broadcast(broadcast)
    scheduler.start()
    await reschedule_all()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def index():
    return FileResponse("static/index.html")


@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)


@app.get("/api/pages", response_model=list[PageOut])
async def list_pages():
    return await get_all_pages()


@app.post("/api/pages", response_model=PageOut)
async def create_page(body: PageCreate):
    page = await insert_page(body.url, body.label, body.window_start, body.window_end)
    await update_page_status(page["id"], "scheduled")
    page = await get_page(page["id"])
    schedule_page(page["id"], page["window_start"])
    await broadcast(page["id"])
    return page


@app.delete("/api/pages/{page_id}")
async def remove_page(page_id: int):
    cancel_page(page_id)
    deleted = await delete_page(page_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Страница не найдена")
    return {"ok": True}


@app.post("/api/pages/{page_id}/run")
async def run_now(page_id: int):
    page = await get_page(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Страница не найдена")
    await run_page_now(page_id)
    return {"ok": True, "message": "Задача запущена"}


@app.post("/api/pages/{page_id}/stop")
async def stop_now(page_id: int):
    from app.automation import stop_page_task
    stopped = stop_page_task(page_id)
    if not stopped:
        raise HTTPException(status_code=400, detail="Задача не выполняется")
    return {"ok": True, "message": "Задача останавливается"}


@app.get("/api/events")
async def sse_stream():
    q: asyncio.Queue = asyncio.Queue()
    _sse_clients.append(q)

    async def event_generator():
        try:
            while True:
                data = await q.get()
                yield {"event": "update", "data": data}
        except asyncio.CancelledError:
            pass
        finally:
            _sse_clients.remove(q)

    return EventSourceResponse(event_generator())
