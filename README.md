# Tiko

> **T**eam **I**nsights, **K**inetic **O**utputs.
>
> We pool data and intelligence (Team Insights) to drive powerful, real-time
> simulation results (Kinetic Outputs), all within a zero-risk sandbox.

Tiko is a cryptocurrency simulation trading agent platform built with a FastAPI
backend, a Python simulation runtime, and a Next.js frontend.

The system can use real public market data, imported datasets, generated data,
and synthetic market scenarios. It does not place real trades. All orders,
fills, balances, PnL, drawdown, risk decisions, reports, and agent outcomes are
simulated inside the platform.

## Safety Boundary

- No private exchange trading endpoints are exposed.
- No wallet, withdrawal, transfer, broker execution, or signing flows are used.
- Read-only public market data credentials are allowed only for data access.
- Agents produce structured trade intent only.
- Every simulated action must pass schema validation, risk review, portfolio
  sizing, and the internal simulated broker.

## Architecture

- `tiko/`: FastAPI control plane, domain models, services, simulation runtime,
  data connectors, plugin sandbox, RL lab, and workers.
- `app/`: Next.js frontend for simulations, market replay, agent traces,
  decisions, portfolio, orders, risk, memory, datasets, experiments, models,
  plugins, and reports.
- `tests/`: Backend unit and integration tests.
- `infra/`: Deployment and process topology references.
- `docs/`: Architecture and task planning documents.

See `docs/architecture.md` for the target-state system design.

## Requirements

- Python 3.12
- `uv`
- Node.js
- `pnpm`

## Backend Setup

Install the Python environment from the repository root:

```powershell
uv sync --extra dev
```

Run the API server when backend endpoints are needed:

```powershell
uv run uvicorn tiko.api.main:create_app --factory --host 127.0.0.1 --port 8000
```

## Frontend Setup

Install frontend dependencies from `app/`:

```powershell
cd app
pnpm install
```

Run the development server:

```powershell
pnpm dev
```

The frontend defaults to `http://127.0.0.1:3000` and reads the backend from
`NEXT_PUBLIC_API_BASE_URL`, defaulting to `http://127.0.0.1:8000`.

## Configuration

Create a local `.env` file for secrets. The file is ignored by Git.

OpenRouter-backed simulated agent evaluation can use one of:

```text
TIKO_OPENROUTER_API_KEY=...
OPENROUTER_API_KEY=...
```

Optional OpenRouter settings:

```text
TIKO_OPENROUTER_MODEL=liquid/lfm-2.5-1.2b-instruct:free
TIKO_OPENROUTER_TIMEOUT_SECONDS=60
TIKO_OPENROUTER_TEMPERATURE=0.1
TIKO_OPENROUTER_MAX_TOKENS=4096
```

Do not store real trading credentials in this project.

## Quality Checks

Backend:

```powershell
uv run ruff format --check tiko tests
uv run ruff check tiko tests
uv run mypy tiko tests
uv run pytest tests -W error
```

Frontend:

```powershell
cd app
pnpm exec prettier --write src
pnpm exec eslint src
pnpm exec tsc --noEmit
```

## Common Workflows

- Upload or import market datasets.
- Create historical replay, live simulated clock, or synthetic market runs.
- Observe simulated market state, decisions, risk reviews, orders, fills, and
  portfolio state.
- Run rule-based or OpenRouter-backed simulated agents.
- Review decision outcomes, memory, reports, experiments, models, and plugin
  sandbox status.

## Current Status

The repository is configured as a simulation-only research platform. The tests
cover the control plane, market data import, replay, agent runtime, risk and
portfolio controls, simulated exchange, realtime streams, reports, model and
plugin registries, and RL lab components.
