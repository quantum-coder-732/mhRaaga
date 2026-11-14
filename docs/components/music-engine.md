# Pecova

**Many Agents. Adaptive Intelligence. One Outcome.**

Pecova is the backend engine behind Algo aKANADE's **integrations** — external
products (starting with [Outreach-Ai](https://github.com/algoanalytics-pvt/Outreach-Ai))
that call Akanade's APIs to get model access, routing, and (eventually) their
own spawned agents, without needing their own LLM infrastructure.

```
Outreach-Ai  →  AI integration layer (API + cache)  →  Akanade APIs  →  Pecova
```

Akanade is the backend. Pecova is the backend **engine**: the thing that
actually decides which model answers a given request, and — for integrations
that opt into it — runs and tracks the agents doing the work.

## PECOVA

| | |
|---|---|
| **PE** | Parallel Execution |
| **C** | Collaboration |
| **O** | Orchestration |
| **V** | Versatile Intelligence |
| **A** | Adaptation |

Multiple specialized agents and models collaborate, tasks are routed
intelligently, results are evaluated, and the system adapts through
feedback — without any exploration/bandit algorithm making that adaptation
non-deterministic or hard to explain. See [ARCHITECTURE.md](ARCHITECTURE.md)
for the full design, the two routing options an admin can choose between,
and exactly how an integration like Outreach-Ai connects.

## What's here

```
pecova/
  backend/    the routing service itself (FastAPI) — Option 1
  engine/     the SLM inference engine (Go) — Option 2's model runtime
  dashboard/  engine monitoring (optional, not the integration-approval UI —
              that lives in Akanade's own admin console, see ARCHITECTURE.md)
```

## Running it locally

```bash
cd backend
cp .env.example .env
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8200
```

`POST /route` with a list of candidates and a context, get back the order
to try them in. `POST /outcome` logs what actually happened. Nothing here
needs a database beyond a local JSON file until `STORAGE_BACKEND=dynamodb`
is set, same as the rest of Algo aKANADE.

## Deploying

Pecova runs as its own container, alongside Akanade's existing ones — see
[deploy/ec2/README_PECOVA.md](../../deploy/ec2/README_PECOVA.md) (next to
Algo aKANADE's own deploy scripts) for the docker-compose service and how
it's wired into the same deployment.
