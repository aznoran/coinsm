import sys
import uvicorn
from app.config import HOST, PORT

if sys.platform == "win32":
    # Uvicorn switches to SelectorEventLoop when reload=True on Windows,
    # but SelectorEventLoop doesn't support create_subprocess_exec
    # which patchright needs to launch the browser.
    # Force ProactorEventLoop in all cases.
    import asyncio
    from uvicorn.loops import asyncio as _uv_loops
    _uv_loops.asyncio_loop_factory = lambda use_subprocess=False: asyncio.ProactorEventLoop

if __name__ == "__main__":
    try:
        uvicorn.run("app.api:app", host=HOST, port=PORT, reload=True)
    except KeyboardInterrupt:
        pass
