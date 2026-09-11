"""
Main module responsible for the upper-level API design,
security middleware layers, and Swagger parameters
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from app.api.api_router import api_router, auth_router, frontend_router
from app.api.deps import ChainController
from app.api.endpoints import tasks_mcp
from app.api.endpoints.tasks_mcp import mcp as eagle_mcp
from app.cmd.c2_tool import MythicClient
from app.core.config import DEBUG_MODE_C, get_settings
from app.mitre_loader import build_apt_chain_index, load_attack_graph
from app.services.ttp_info_service import TTPInfoService

# mount only the raw ASGI handler for mcp
eagle_mcp.streamable_http_app(streamable_http_path="/")
_mcp_session_manager = eagle_mcp._lowlevel_server._session_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """create and manage services for C2"""
    mythic_client = MythicClient()
    try:
        await mythic_client.connect()
    except Exception as e:
        print(
            "\033[1;33mWARNING:   \033[0mok, you can test some without mythic because",
            e,
        )
    app.state.mythic_client = mythic_client
    app.state.chain_controller = ChainController()

    # load MITRE ATT&CK data for TTP queries in MCP
    settings = get_settings()
    try:
        graph = load_attack_graph(
            settings.mitre.enterprise_attack_path,
            settings.mitre.threat_groups_path,
        )
        app.state.attack_graph = graph
        tasks_mcp._attack_graph = graph

        # build APT co-use chain index for suggest_next_ttps
        _ttp_svc = TTPInfoService(graph)
        chain_index = build_apt_chain_index(graph, _ttp_svc.get_phase_for_ttp)
        app.state.apt_chain_index = chain_index
        tasks_mcp._apt_chain_index = chain_index
    except Exception as e:
        print("\033[1;33mWARNING:   \033[0mMITRE data load failed:", e)
        app.state.attack_graph = None
        app.state.apt_chain_index = None

    # required for streamable HTTP in mcp
    async with _mcp_session_manager.run():
        yield

    await mythic_client.disconnect()


app = FastAPI(
    title="EAGLE",
    version="0.0.1",
    description="Emulated Attack Generator w/ Layered Engine <br>"
    "<a href='https://github.com/eogod/EAGLE'>source</a> "
    "<a href='/'>GUI</a> <br><br>",
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    lifespan=lifespan,
)

app.include_router(auth_router, prefix="/api")
app.include_router(api_router, prefix="/api")

app.mount("/mcp", _mcp_session_manager.asgi_app)

app.include_router(frontend_router)
# Sets all CORS enabled origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "127.0.0.1"  # DEBUG, CHANGE ME BEFORE RUN
        #    str(origin).rstrip("/")
        #    for origin in get_settings().security.backend_cors_origins
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Guards against HTTP Host Header attacks
# app.add_middleware(
#    TrustedHostMiddleware,
#    allowed_hosts=get_settings().security.allowed_hosts,)


@app.middleware("http")
async def log_requests_body(request: Request, call_next):
    if DEBUG_MODE_C:
        print(f"\033[1;33mDEBUG:   Request \033[0m: {request.method} {request.url}")
        try:
            body = await request.body()
            if body:
                print(f"\033[1;33mDEBUG:   Request body \033[0m:{body.decode()}")
        except Exception:
            return None

    response = await call_next(request)
    return response


app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).parent.parent.parent / "frontend"),
    name="static",
)


@app.exception_handler(AssertionError)
async def assertion_exception_handler(request: Request, exc: AssertionError):
    """we don't need 500 at bad input"""
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError):
    """we don't need 500 at bad value inside"""
    return JSONResponse(status_code=400, content={"detail": str(exc)})
