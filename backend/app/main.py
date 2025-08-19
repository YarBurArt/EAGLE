"""
Main module responsible for the upper-level API design,
security middleware layers, and Swagger parameters
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from fastapi.staticfiles import StaticFiles
from pathlib import Path

from pydantic import ValidationError

from app.api.api_router import api_router, auth_router
from app.core.config import get_settings

from app.cmd.c2_tool import init_mythic

app = FastAPI(
    title="EAGLE",
    version="0.0.1",
    description="Emulated Attack Generator w/ Layered Engine"
                "https://github.com/eogod/EAGLE",
    openapi_url="/openapi.json",
    docs_url="/",
)

app.include_router(auth_router)
app.include_router(api_router)

# Sets all CORS enabled origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        str(origin).rstrip("/")
        for origin in get_settings().security.backend_cors_origins
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Guards against HTTP Host Header attacks
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=get_settings().security.allowed_hosts,
)

app.mount("/static", StaticFiles(
    directory=Path(__file__).parent.parent.parent / "frontend"
    ), name="static")


@app.on_event("startup")
async def on_startup():
    """ init steps for any chain """
    try:
        await init_mythic()
    except Exception as e:
        print("\033[1;33mWARNING:   \033[0m"
              "ok, you can test some without mythic because", e)


@app.exception_handler(AssertionError)
async def assertion_exception_handler(request: Request, exc: AssertionError):
    """ we dont need 500 at bad input """
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)}
    )


@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError):
    """ we dont need 500 at bad value inside """
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)}
    )
