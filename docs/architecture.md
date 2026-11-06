# EAGLE - Architecture

EAGLE is a FastAPI application with a small React frontend, PostgreSQL for the durable
record, Valkey for hot task state, and Mythic C2 as the execution backend. Operator input
and LLM suggestions become `AttackChain` rows, and those rows are replayed through Mythic
agents or local bash.

The runtime modules, how they connect, and the database model follow. Installation steps
are in the [README](../README.md).

## Technology overview

| Layer | Stack |
| --- | --- |
| Backend | Python 3.14, FastAPI 0.162, Pydantic 2, SQLAlchemy 2.1 async + asyncpg, Alembic |
| Data | PostgreSQL 18 (durable), Valkey 8.1 via `redis-py` (Redis protocol, hot events only) |
| Auth | PyJWT, bcrypt |
| C2 | Mythic 0.3.0rc9 client and GraphQL API |
| LLM | Ollama, OpenRouter / OpenAI-compatible endpoints, g4f pool |
| Agent / tooling | MCP 2.3 server, MITRE ATT&CK JSON loaded at startup |
| Frontend | React 19, Vite 8, React Router 7, Tailwind 4, assistant-ui, Phosphor icons |
| Runtime | Docker, uvicorn, uvloop |

## System architecture

Module paths are relative to `backend/` unless they start with `frontend/`. The diagram
shows runtime calls, not imports. A trailing `*` marks the modules that write
PostgreSQL; `**` marks the module that writes Valkey.

```mermaid
%%{init: {"flowchart": {"nodeSpacing": 14, "rankSpacing": 22, "padding": 2, "diagramPadding": 2, "curve": "linear"}}}%%
flowchart LR
    subgraph FE["frontend/src"]
        fe_app["app/<br/>App, router"]
        fe_pages["pages/<br/>Login, kill-chains"]
        fe_agent["pages/agent/<br/>AgentPanel, useAgentThread"]
        fe_widgets["widgets/<br/>StepCard, Column, Navbar"]
        fe_features["features/<br/>run, phase, switch"]
        fe_entities["entities/<br/>chainApi, stepApi, agentApi"]
        fe_shared["shared/<br/>axios, runControl"]
    end

    subgraph API["app/api"]
        api_router["api_router.py<br/>mounts /api"]
        auth_api["auth.py + users.py *<br/>/auth, /users"]
        llm_api["llm.py *<br/>/llm"]
        agent_api["agent_{sessions,chat,drafts}.py<br/>/agent"]
        export_api["kill_chain.py *<br/>/export-chain"]
        tasks_api["tasks.py<br/>/cmd"]
        mcp_api["tasks_mcp.py *<br/>/mcp"]
    end

    subgraph SVC["app/services"]
        agent_svc["agent_chat/document/draft<br/>_service.py *"]
        ttp_svc["ttp_info_service.py"]
        chain_svc["chain_service.py *"]
        c2_svc["c2_service.py *"]
        payload_svc["payload_service.py *"]
        exec_svc["chain_exec_service.py *"]
        bash_svc["bash_service.py *"]
    end

    subgraph CMD["app/cmd"]
        llmcmd["llm_analysis.py<br/>LLMService, providers"]
        events["mythic_events.py * **"]
        proc["proc.py *"]
        c2tool["c2_tool.py"]
        localbash["local_bash.py"]
    end

    subgraph AGENT["app/agent"]
        pipeline["pipeline.py"]
        prompts["prompts.py"]
        parsing["parsing.py"]
        validation["validation.py"]
    end

    subgraph STATE["state"]
        mitre[("data/*.json<br/>MITRE ATT&CK")]
        pg[("PostgreSQL 18<br/>models.py + alembic *")]
        valkey[("Valkey 8.1<br/>eagle:task / eagle:bash **")]
    end

    subgraph EXT["external"]
        llm["Ollama / OpenRouter / g4f"]
        mythic["Mythic C2"]
        agents["zero / remote agents"]
    end

    fe_app --> fe_pages
    fe_pages --> fe_agent
    fe_pages --> fe_widgets
    fe_pages --> fe_features
    fe_pages --> fe_entities
    fe_agent --> fe_entities
    fe_features --> fe_entities
    fe_entities --> fe_shared
    fe_shared --> api_router

    export_api --> llmcmd
    llm_api --> agent_svc
    agent_api --> agent_svc
    agent_api --> pipeline
    tasks_api & mcp_api -->|commands / tools| exec_svc
    tasks_api & mcp_api --> chain_svc
    tasks_api --> events
    mcp_api -->|tools| ttp_svc

    exec_svc --> proc
    c2_svc --> proc
    payload_svc --> proc
    bash_svc --> localbash
    bash_svc --> events
    agent_svc --> llmcmd
    agent_svc --> pipeline
    agent_svc --> parsing
    agent_svc --> validation
    pipeline --> parsing
    pipeline --> validation
    pipeline --> prompts

    proc --> c2tool
    proc --> localbash
    proc --> llmcmd

    ttp_svc --> mitre
    c2tool --> mythic
    llmcmd --> llm
    mythic --> agents
```

`frontend/src/app` owns routing; `pages/` holds login, the chain canvas, and the agent
panel; `entities/` holds the API clients; `features/` holds the run and phase hooks;
`widgets/` holds the canvas cards and navigation; `shared/` holds axios and run control.

`app/main.py` opens the Mythic connection and the event service at startup, hands the
finished `TTPInfoService` to `tasks_mcp`, and mounts `/api`, `/mcp`, and the built
frontend. `app/api/api_router.py` wires the endpoint files, which validate input and call
a service or the database session directly (`auth.py`, `users.py`, `kill_chain.py`).
Endpoints never import `app/cmd/*`; `app/services/*` owns chain, task, and agent
persistence, and all LLM access goes through `AgentChatService`
(`app/services/agent_chat_service.py`) on top of `app/cmd/llm_analysis.py`. That module
holds both the chain-work pool (`LLMService`) and the streaming agent providers
(`build_provider`, `list_models`).

Agent state is split across three services: `AgentChatService` (sessions, messages, runs,
LLM facade), `AgentDocumentService` (untrusted uploads and parsing), and
`AgentDraftService` (drafts, validation, chain import and edit operations). Shared
ownership checks live in `app/services/agent_scope.py`.

Chain execution goes through `app/cmd/proc.py`; Mythic tasking is in
`app/cmd/c2_tool.py`; local commands run in `app/cmd/local_bash.py`.
`app/cmd/mythic_events.py` is the only bridge that turns Mythic task events into Valkey
rows and NDJSON/SSE. `app/core/*` holds config, JWT/bcrypt, and the async database
session; the agent's safety caps (document size, chunking, temperature) live there as
module constants.

PostgreSQL is the durable record. Valkey holds current task status only, with a TTL. Raw
bash logs and parsed uploads stay in `backend/data/` and are referenced by path.

## Failure boundaries

- Mythic down at startup: EAGLE still starts, auth and database endpoints work, C2
  commands fail until the connection returns.
- Valkey down: the stream returns the initial database snapshot and then closes. The
  durable record is not affected.
- LLM down: suggestions and analysis fail, but stored chains still replay.
- Uploaded documents are untrusted data. They are parsed, never executed, and every
  finding must point to a verbatim span before validation accepts it.

## Database model

PostgreSQL is the durable store. Every model inherits `create_time` and `update_time` from
`Base`; only the important columns are shown below. The full schema is in
`backend/app/models.py`.

```mermaid
%%{init: {"er": {"diagramPadding": 10, "minEntityWidth": 55, "minEntityHeight": 24, "entityPadding": 8}}}%%
erDiagram
    USER_ACCOUNT ||--o{ REFRESH_TOKEN : ""
    USER_ACCOUNT ||--o{ ATTACK_CHAIN : ""
    USER_ACCOUNT ||--o{ AGENT_SESSION : ""
    USER_ACCOUNT ||--o{ CHAIN_DRAFT : ""
    ATTACK_CHAIN ||--o{ ATTACK_STEP : ""
    ATTACK_CHAIN ||--|| CURRENT_ATTACK_PHASE : ""
    AGENT_SESSION }o--o| ATTACK_CHAIN : ""
    ATTACK_STEP ||--o{ AGENT : ""
    ATTACK_STEP ||--o{ MYTHIC_TASK : ""
    ATTACK_STEP ||--o{ BASH_TASK : ""
    AGENT_SESSION ||--o{ AGENT_MESSAGE : ""
    AGENT_SESSION ||--o{ AGENT_DOCUMENT : ""
    AGENT_SESSION ||--o{ AGENT_RUN : ""
    AGENT_SESSION ||--o{ CHAIN_DRAFT : ""
    AGENT_SESSION ||--o{ AGENT_FINDING : ""
    AGENT_RUN |o--o{ AGENT_MESSAGE : ""
    AGENT_DOCUMENT |o--o{ AGENT_RUN : ""
    AGENT_RUN ||--o{ AGENT_FINDING : ""
    AGENT_RUN |o--o{ CHAIN_DRAFT : ""

    subgraph auth
        USER_ACCOUNT {
            uuid user_id PK
            string email UK
            string role
        }

        REFRESH_TOKEN {
            bigint id PK
            bigint user_id FK
        }
    end

    subgraph chain_management
        ATTACK_CHAIN {
            bigint id PK
            uuid user_id FK
            string chain_name UK
            string final_status
        }

        CURRENT_ATTACK_PHASE {
            bigint id PK
            bigint chain_id FK
            string phase
        }

        ATTACK_STEP {
            bigint id PK
            bigint chain_id FK
            string step_type
            string status
        }

        AGENT {
            bigint id PK
            bigint step_id FK
            int callback_display_id
        }
    end

    subgraph status
        MYTHIC_TASK {
            bigint id PK
            bigint step_id FK
            string status
        }

        BASH_TASK {
            bigint id PK
            bigint step_id FK
            string status
        }
    end

    subgraph llm_agent
        AGENT_SESSION {
            bigint id PK
            uuid user_id FK
            bigint chain_id FK
            string status
        }

        AGENT_MESSAGE {
            bigint id PK
            bigint session_id FK
            bigint run_id FK
            string role
        }

        AGENT_DOCUMENT {
            bigint id PK
            bigint session_id FK
            string parse_status
        }

        AGENT_RUN {
            bigint id PK
            bigint session_id FK
            bigint document_id FK
            string status
        }

        AGENT_FINDING {
            bigint id PK
            bigint run_id FK
            bigint session_id FK
            jsonb evidence
        }

        CHAIN_DRAFT {
            bigint id PK
            bigint session_id FK
            bigint run_id FK
            uuid user_id FK
            string status
        }
    end
```

`CURRENT_ATTACK_PHASE` is one row per chain, `AGENT_FINDING` keeps `session_id` alongside
`run_id` for cheap session cleanup, and `CHAIN_DRAFT` stays JSONB until the operator
imports it into typed `ATTACK_STEP` rows.
