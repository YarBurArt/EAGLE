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

So far, this has been tested on latest `Kali Linux` and `Parrot OS`. Debian may need to build new python [from source](https://docs.python.org/3/using/unix.html#building-python
).

The main requirement is `python3.13` and above.

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
SECURITY__BACKEND_CORS_ORIGINS=["http://localhost:3000","http://localhost:8001"]
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
