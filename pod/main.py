from contextlib import asynccontextmanager

import nltk
import taskiq_fastapi
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.staticfiles import StaticFiles

from apps.admin_app.ws import admin_ws_router
from apps.chats_app.routes import chats_router
from apps.chats_app.ws import chat_ws_router
from apps.feeds_app.routes import feed_router
from apps.feeds_app.ws import feed_ws_router
from apps.notes_app.routes import notes_router
from apps.users_app.routes import users_router
from apps.vocabularies_app.routes import vocabularies_router
from services.firebase_service import initialize_firebase
from settings.my_config import get_settings
from settings.my_database import initialize_db
from settings.my_exceptions import ApiException
from settings.my_minio import initialize_minio
from settings.my_redis import initialize_redis_indexes
from settings.my_taskiq import broker
from utility.my_logger import my_logger

settings = get_settings()


@asynccontextmanager
async def app_lifespan(_app: FastAPI):
    my_logger.warning("🚀 Starting app_lifespan...")

    try:
        nltk.download("punkt_tab")
        initialize_firebase()
        await initialize_redis_indexes()
        await initialize_db()
        await initialize_minio()
        instrumentator.expose(_app)
        if not broker.is_worker_process:
            await broker.startup()
    except Exception as e:
        my_logger.exception(f"Exception in app_lifespan startup, e: {e}")
    yield

    try:
        if not broker.is_worker_process:
            await broker.shutdown()
    except Exception as e:
        my_logger.exception(f"Exception in app_lifespan shutdown, e: {e}")


app: FastAPI = FastAPI(lifespan=app_lifespan)
instrumentator = Instrumentator().instrument(app)

taskiq_fastapi.init(broker=broker, app_or_path=app)

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="static/templates")


@app.get(path="/", tags=["root"])
async def root() -> dict:
    return {"status": "ok"}


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("static/favicon.ico")


@app.get("/privacy", response_class=HTMLResponse, include_in_schema=False)
async def privacy_policy(request: Request):
    return templates.TemplateResponse("privacy_policy.html", {"request": request})


@app.get("/terms", response_class=HTMLResponse, include_in_schema=False)
async def terms_of_service(request: Request):
    return templates.TemplateResponse("terms_of_service.html", {"request": request})


@app.get("/account-deletion-info", response_class=HTMLResponse, include_in_schema=False)
async def terms_of_service(request: Request):
    return templates.TemplateResponse("account_deletion_info.html", {"request": request})


@app.get("/safety", response_class=HTMLResponse, include_in_schema=False)
async def terms_of_service(request: Request):
    return templates.TemplateResponse("safety.html", {"request": request})


# HTTP Routes
app.include_router(router=users_router, prefix="/api/v1/users", tags=["users"])
app.include_router(router=feed_router, prefix="/api/v1/feeds", tags=["feeds"])
app.include_router(router=chats_router, prefix="/api/v1/chats", tags=["chats"])
app.include_router(router=vocabularies_router, prefix="/api/v1/vocabularies", tags=["vocabularies"])
app.include_router(router=notes_router, prefix="/api/v1/notes", tags=["notes"])

# Websocket Routes
app.include_router(router=admin_ws_router, prefix="/api/v1/admin", tags=["admin ws"])
app.include_router(router=feed_ws_router, prefix="/api/v1/feeds", tags=["feeds ws"])
app.include_router(router=chat_ws_router, prefix="/api/v1/chats", tags=["chat ws"])


@app.exception_handler(ApiException)
async def api_exception_handler(request: Request, exception: ApiException):
    my_logger.exception(f"HTTP {exception.status_code} error {request.url.path} detail: {exception.detail}")
    return JSONResponse(status_code=exception.status_code, content={"details": exception.detail}, headers=exception.headers)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exception: RequestValidationError):
    details = []

    for error in exception.errors():
        my_logger.critical(f"error: {error}")
        ctx = error.get("ctx", {})
        if "error" in ctx:
            details.append(str(ctx["error"]))
        else:
            loc = error.get("loc", [])
            msg = error.get("msg", "")
            if len(loc) > 1:
                field = str(loc[1]).capitalize()
                details.append(f"{field} {msg.lower()}")

    my_logger.warning(f"HTTP validation error during {request.method} {request.url.path}, details: {details}")
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"details": details})
