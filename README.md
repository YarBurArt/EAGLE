# EAGLE - Emulated Attack Generator w/ Layered Engine

The Emulated Attack Generator with Layered Engine is an interactive system for building
and executing realistic attack chains based on the [Unified Cyber Kill Chain](https://www.unifiedkillchain.com/) stages and supports the dynamic formation of attack chains in real
time. It works in the context of an API that uses GraphQL and the Mythics library plus a minimal frontend.

The platform operates through a C2 infrastructure (Mythic C2 + agents, zero agent) and
supports the generation of new agents during an attack, emulating Lateral movement and
deep penetration into the infrastructure.

Commands that are executed locally are executed for the first stages of the chain only through zero agent.

The project is developed using `FastAPI` + `PostgreSQL` (`SQLAlchemy 2.0` + `alembic`), based on [Minimal async FastAPI + PostgreSQL template](https://github.com/rafsaf/minimal-fastapi-postgres-template/tree/main) 

## Requirements

So far, this has been tested on latest `Kali Linux` and `Parrot OS`. Debian, if the version is lower than 13, may need to build new python [from source](https://docs.python.org/3/using/unix.html#building-python
). The latest `Astra Linux` (Debian 10-12 with MAC policy) have the same problem, but for some reason install_docker_kali.sh works for the mythic, and it even considers the mythic and EAGLE containers secure. EAGLE itself can also work if mythic is on a remote host, zero agent is on another, and postgres is not in the container. On Windows, it is easiest to run it via `WSL2` on Ubuntu or Kali.

The main requirement is `python3.13` and above.

If you decide not to deploy using Docker, you should use `PostgreSQL 17`.

The minimum RAM requirement is 4-8GB, but 16GB is recommended due to agents, profiles from Mythic C2, and zero agent itself.
A minimum dual-core CPU , but it 's difficult with containers.

## Installation 
Initially, Mythic C2 must be installed and running https://docs.mythic-c2.net/installation

For now, the `zero agent` should also work. In fact, you infect yourself in debug mode and connect to C2. The important number here is the first `callback_display_id` to connect to the EAGLE , you will need to specify it in the interface. In Mythic C2 it is located to the left of the active callback.

Clone repository
```bash
git clone https://github.com/eogod/EAGLE.git
```
```bash
cd ./EAGLE/backend
```

At this point, you need to set .env in EAGLE/backend like this, port of db must be different than Mythic C2 postgres, `MYTHIC__` variables should be taken from your `Mythic/.env`
```env
SECURITY__JWT_SECRET_KEY=super_secret_key
SECURITY__BACKEND_CORS_ORIGINS=["http://127.0.0.1:3001","http://localhost:8001", "http://localhost:8000", "http://127.0.0.1:8000"]
SECURITY__ALLOWED_HOSTS=["localhost", "127.0.0.1"]

DATABASE__HOSTNAME=localhost
DATABASE__USERNAME=super_secret_user
DATABASE__PASSWORD=super_secret_password
DATABASE__PORT=5455
DATABASE__DB=default_db

MYTHIC__SERVER_IP=127.0.0.1
MYTHIC__USERNAME=super_secret_user
MYTHIC__PASSWORD=super_secret_password
MYTHIC__SERVER_PORT=7443
MYTHIC__TIMEOUT=-1
MYTHIC__PAYLOAD_PORT_HTTP=1337
```
If you need local LLM via [ollama](https://github.com/ollama/ollama) add to env also 
```env
LLMSERVICE__API_URL=http://localhost:69228
LLMSERVICE__API_KEY=super_secret_key
LLMSERVICE__TIMEOUT=120
LLMSERVICE__DEFAULT_MODEL=mistral
```
Install dependencies
```bash
# Poetry install (python3.13)
poetry install
# or on debian / parrot
python3.13 -m poetry install
```
Setup database and migrations 
```bash
# Setup database
docker-compose up -d

python3.13 -m poetry shell

# Run Alembic migrations for DB changes
alembic upgrade head
```
Run backend FastAPI
```bash
python3.13 -m poetry shell  # if you exited

uvicorn app.main:app --reload
```

## Usage

By default, the application runs at **http://127.0.0.1:8000** and connects to `Mythic C2` on startup.
At this URL you’ll find the API with a `Swagger UI`.  Frontend is on **/f/index** for now.
Registration is available via **/auth/register** using email/password , this is required because AttackChains are attached to users by ID. After registering, you can log in and obtain a JWT token via **/auth/access-token** (or via Swagger auth).
> Note that the login field is the email you used during registration.

Once authenticated, you can create a new attack chain with **/cmd/new-chain/**.
A new chain with your specified name will be assigned an ID, which is used to attach steps to that chain.
> For simplicity, utility names and their types are linked, a chain consists of individual steps, each connected to agents and containing information about the current attack phase.

You can generate commands via the LLM, almost like a *pentest with LLM*.
Currently, if a command not execute, it will not be saved to the database but LLM integration will be made more intuitive over time.

The first commands are often Reconnaissance and run locally, so you need `Zero agent` and its `display_id`,
which you include in requests to **/cmd/run-command**.
If you may have made a mistake and any command was somewhy saved to the DB, you can reject the last saved command in the chain and delete it via **/cmd/reject-s/{chain_name}**

For agent-specific commands, use **/cmd/run-agent-command**, also specifying the agent utility name, for local it's set as `shell`.
Commands executed this way are immediately saved to the chain, 
you can use the LLM to assist with command generation and output analysis.
> Note that the LLM does not write directly to the database and LLM decisions are user-driven.

You can create payloads via the LLM and route them through proc, 
then run **/cmd/update-agents** to save remote agents in the database for reproducibility of the chain. If the task needs more precise adjustments, or the LLM makes a mistake somewhere, you should use **/cmd/new-agent** for create mythic payload via EAGLE in context of chain, then **/cmd/run-command** for uploading payload to the rhost and then also **/cmd/update-agents** .

You can set attack phases with **/cmd/next-phase/{chain_id}**
or set a specific phase via **/cmd/set-phase/{chain_id}**.
Chain status can be retrieved with **/cmd/chain-phase/{chain_id}**.
> Note that if, for example, you uploaded a payload via a curl command using Mythic payload UUID, it will remain the old payload during replay because the agent-type attack step has already stored the original payload. This is done for simplicity and is one example of why our project’s stability depends on Mythic’s stability; you still need to use Mythic to some extent. *Profiles* for agent payloads are also created before run EAGLE.

To run chain, use **/cmd/run-chain/{chain_id}**, which streams each step’s output as HTTP chunks.
Emergency stop is available via WebSocket or HTTP cancel endpoints.
For convenience and stability, a minimal frontend is provided at **/f/index**, offering command execution ( agent / local ),
LLM-assisted output analysis, and chain management.

Export a chain (with or without LLM analysis) via **/export-chain/json** or **/export-chain/yaml** to `JSON` or `YAML`.

Similar to how diving into [Mythic python library](https://github.com/MythicMeta/Mythic_Scripting/blob/master/mythic/mythic.py) source code clarifies its functionality, examining the other Swagger endpoints and read `EAGLE` codebase provides deeper insight into using it effectively. If anything is unclear, write it in the [issues](https://github.com/eogod/EAGLE/issues) section.
