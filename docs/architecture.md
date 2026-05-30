# System Architecture Design

## 1. Purpose

This document defines the target-state architecture for a cryptocurrency simulation trading agent platform built with Next.js, FastAPI, and a Python agent runtime.

The platform may ingest real-world public market data from exchanges and data providers, but only through read-only market data connectors. It never connects to private account endpoints, private trading endpoints, wallets, decentralized exchange signing flows, or brokerage execution APIs. It also supports local, imported, generated, and synthetic data. All orders, fills, fees, account balances, PnL, drawdown, and risk outcomes are simulated inside the platform.

The core architectural boundary is:

```text
Agents produce structured trading intent.
Risk validates or rejects that intent.
Portfolio sizing converts approved intent into simulated orders.
The simulated broker and matching engine execute only inside the simulation.
The ledger records only simulated balances, positions, fees, and PnL.
Market data connectors are read-only inputs and cannot submit orders or read balances.
The frontend observes, controls, reviews, and compares simulation runs.
```

This design preserves agent research, reinforcement learning, plugin expansion, and long-running observation while avoiding live-trading complexity and capital safety risk.

## 2. Explicit Non-Goals

The current system version must not:

- Connect to private trading or account endpoints on Binance, OKX, Bybit, Coinbase, DEX protocols, wallets, or any live market execution API.
- Store, request, or sign with trading API keys, account API keys, wallet keys, or order-signing credentials.
- Submit real orders.
- Read real exchange balances.
- Provide a live trading mode.
- Call private trading/account methods such as `createOrder`, `cancelOrder`, `fetchBalance`, `fetchOpenOrders`, `fetchPositions`, or wallet-signing flows.
- Let natural-language agent output bypass schema validation, risk review, or portfolio controls.

Read-only public market data credentials are allowed only when a provider requires them for data access. They must be stored separately from trading credentials, scoped to market data where the provider supports scopes, and never passed to broker, portfolio, risk, agent, or plugin code that can create orders.

All trading behavior must occur inside:

- Simulated exchange.
- Simulated account.
- Simulated matching engine.
- Market replay engine.
- Synthetic market engine.

## 3. Core Goals

The complete target system supports:

- Read-only ingestion of real public market data.
- Local historical market data import.
- Synthetic market generation.
- Manual and scripted event injection.
- Point-in-time observation building.
- Multi-agent trading decision workflows.
- Reinforcement learning assisted strategy research.
- Independent risk control.
- Portfolio and position management.
- Simulated order matching.
- Simulated account settlement.
- Long-running runtime observation.
- Realtime frontend monitoring.
- Agent decision traceability.
- Replay, review, comparison, and reporting.
- Experiment and model registry workflows.
- Plugin-based extension for data, features, events, analysis, and reports.

## 4. High-Level Architecture

```mermaid
flowchart TB
    subgraph frontend["Next.js Frontend"]
        dashboard["Dashboard"]
        marketUI["Market Replay"]
        agentUI["Agent Trace"]
        portfolioUI["Portfolio"]
        riskUI["Risk Console"]
        labUI["RL and Experiment Lab"]
    end

    subgraph api["FastAPI Backend"]
        rest["REST API"]
        ws["WebSocket / SSE"]
        auth["Auth / RBAC"]
    end

    subgraph runtime["Simulation Runtime"]
        clock["Simulation Clock"]
        eventBus["Event Bus"]
        orchestrator["Run Orchestrator"]
    end

    subgraph data["Data and Observation"]
        importers["Read-Only Data Connectors<br/>CCXT / Cryptofeed / Files / Synthetic"]
        store["Market Data Store"]
        feature["Feature Engine"]
        obs["Observation Builder"]
        memory["Memory / RAG Store"]
    end

    subgraph agents["Agent Layer"]
        regime["Market Regime Agent"]
        technical["Technical Agent"]
        eventAgent["Event Agent"]
        quant["Quant / RL Agent"]
        trader["Trader Agent"]
        critic["Critic Agent"]
        portfolioAgent["Portfolio Agent"]
    end

    subgraph control["Decision, Risk, and Portfolio"]
        decision["Decision Layer"]
        risk["Risk Engine"]
        portfolio["Portfolio Engine"]
    end

    subgraph sim["Simulated Exchange"]
        broker["Sim Broker"]
        matching["Matching Engine"]
        ledger["Account Ledger"]
        metrics["PnL / Metrics Engine"]
    end

    subgraph infra["Storage and Infrastructure"]
        pg["PostgreSQL / TimescaleDB"]
        redis["Redis"]
        object["Object Store"]
        workers["Workers"]
    end

    frontend <--> api
    rest --> orchestrator
    ws --> frontend

    importers --> store
    store --> feature
    feature --> obs
    memory --> obs

    clock --> eventBus
    eventBus --> orchestrator
    orchestrator --> obs
    obs --> agents
    agents --> decision
    decision --> risk
    risk --> portfolio
    portfolio --> broker
    broker --> matching
    matching --> ledger
    ledger --> metrics
    metrics --> eventBus
    metrics --> memory

    api --> pg
    runtime --> pg
    data --> pg
    sim --> pg
    eventBus --> redis
    workers --> redis
    object --> data
```

## 5. Architectural Responsibilities

| Layer | Responsibility |
| --- | --- |
| Next.js frontend | Observe, control, inspect, compare, and review simulation runs. |
| FastAPI backend | Provide APIs, realtime streams, authentication, authorization, and run control. |
| Simulation runtime | Advance simulated time, dispatch events, orchestrate agents, risk, portfolio, and exchange simulation. |
| Data and observation | Import or stream read-only market data, validate, align, feature-engineer, and package point-in-time observations. |
| Agent layer | Analyze observations and produce structured trading intent. |
| Decision layer | Validate, persist, and audit agent intent. |
| Risk engine | Enforce hard limits, circuit breakers, data-quality gates, and rejection logic. |
| Portfolio engine | Convert approved targets into simulated order instructions. |
| Simulated exchange | Match orders, apply fees and slippage, update positions, and write ledger entries. |
| Memory and evaluation | Store reviews, outcomes, traces, reflections, and experiment results. |

## 6. Runtime Modes

### 6.1 Historical Replay Mode

Historical replay mode runs a simulation over imported historical data.

Use cases:

- Reproduce a historical market period.
- Let agents make decisions on a historical timeline.
- Detect lookahead bias.
- Compare agent, strategy, risk, and broker configurations.

Properties:

- Time is controlled by the simulation clock.
- Runs support 1x, 10x, 100x, pause, resume, and single-step execution.
- Every event has `simulated_time`.
- Agents can access only data whose `as_of` time is less than or equal to the current simulated time.

### 6.2 Live Simulated Clock Mode

Live simulated clock mode advances market time at a steady wall-clock cadence while still simulating all execution internally. The clock may be driven by imported data, generated data, synthetic data, or real-world public market data streams.

Use cases:

- Long-running observation from the frontend.
- Multi-day or multi-week simulated operations.
- Operational monitoring of agents, risk, orders, fills, and PnL.

Data sources:

- Read-only public exchange market data streams.
- Read-only market data provider APIs.
- Previously imported historical data.
- Synthetic market generators.
- Manual event injection.
- Scripted news, volatility, liquidity, and funding events.

### 6.3 Synthetic Market Mode

Synthetic market mode creates controlled market scenarios.

Use cases:

- Stress-test agents.
- Generate trend, range, crash, wick, and volatility-regime scenarios.
- Validate risk controls, stop-loss behavior, circuit breakers, and slippage models.
- Train and evaluate reinforcement learning environments.

Example configuration:

```yaml
scenario:
  name: high_volatility_btc_perp
  symbols:
    - BTCUSDT
    - ETHUSDT
  start_price:
    BTCUSDT: 68000
    ETHUSDT: 3500
  volatility:
    regime: high
    annualized: 0.95
  trend:
    drift: -0.15
  jumps:
    enabled: true
    probability_per_day: 0.08
    size_distribution: student_t
  liquidity:
    spread_bps_mean: 8
    depth_usd_mean: 500000
  funding:
    enabled: true
    mean_8h: 0.0002
```

### 6.4 Manual Event Injection Mode

Manual event injection lets an operator inject simulated events into a run.

Supported examples:

- Mock news events.
- On-chain activity shocks.
- Exchange outage simulation.
- Liquidity deterioration.
- Funding-rate spikes.
- Volatility shocks.

Example event:

```json
{
  "type": "news_event",
  "simulated_time": "2026-01-15T08:00:00Z",
  "symbol": "BTCUSDT",
  "severity": "high",
  "headline": "Mock ETF outflow shock",
  "sentiment": -0.8,
  "confidence": 0.9
}
```

## 7. Time Model

The system must distinguish all relevant time dimensions:

| Time field | Meaning |
| --- | --- |
| `wall_time` | Real machine time. |
| `simulated_time` | Current simulated market time. |
| `as_of` | Point-in-time validity timestamp for a data item. |
| `fetched_at` | Real time when data was written into the system. |
| `created_at` | Database record creation time. |
| `decision_time` | Simulated time when an agent made a decision. |
| `execution_time` | Simulated time when an order was executed. |

All observation inputs must be point-in-time safe. No observation may include future candles, future events, revised future-aware data, or memory entries whose availability would violate the current simulated time.

## 8. Domain Model

The domain model should be implemented as explicit schemas in the API layer and corresponding persistence models in the database layer.

### 8.1 Asset

```python
class Asset(BaseModel):
    symbol: str
    base_asset: str
    quote_asset: str
    market_type: Literal["spot", "perp", "synthetic"]
    tick_size: Decimal
    lot_size: Decimal
    min_notional: Decimal
    fee_tier: str
    is_active: bool
```

### 8.2 Candle

```python
class Candle(BaseModel):
    symbol: str
    timeframe: str
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    quote_volume: Decimal | None = None
    source: str
    as_of: datetime
    created_at: datetime
```

### 8.3 Order Book Snapshot

```python
class OrderBookSnapshot(BaseModel):
    symbol: str
    as_of: datetime
    bids: list[tuple[Decimal, Decimal]]
    asks: list[tuple[Decimal, Decimal]]
    mid_price: Decimal
    spread_bps: Decimal
    depth_1pct_usd: Decimal
    source: str
```

### 8.4 Market Event

```python
class MarketEvent(BaseModel):
    event_id: UUID
    type: Literal[
        "candle_closed",
        "tick",
        "orderbook_snapshot",
        "funding_update",
        "news_event",
        "liquidity_shock",
        "volatility_shock",
        "system_event",
    ]
    symbol: str | None
    simulated_time: datetime
    payload: dict
    source: str
    confidence: float
```

### 8.5 Simulated Account

```python
class SimAccount(BaseModel):
    account_id: UUID
    name: str
    base_currency: str = "USDT"
    initial_equity: Decimal
    cash_balance: Decimal
    total_equity: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    max_drawdown: Decimal
    status: Literal["active", "paused", "liquidated", "stopped"]
```

### 8.6 Position

```python
class Position(BaseModel):
    position_id: UUID
    account_id: UUID
    symbol: str
    side: Literal["long", "short", "flat"]
    quantity: Decimal
    avg_entry_price: Decimal
    mark_price: Decimal
    notional: Decimal
    leverage: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    liquidation_price: Decimal | None = None
    updated_at_sim_time: datetime
```

### 8.7 Trade Intent

Agent output must be strict structured JSON. Natural-language reasoning can be stored as evidence or thesis, but it must not be executable by itself.

```python
class TradeIntent(BaseModel):
    decision_id: UUID
    run_id: UUID
    agent_id: str
    symbol: str
    market_type: Literal["spot", "perp", "synthetic"]
    action: Literal[
        "open_long",
        "open_short",
        "increase_long",
        "increase_short",
        "reduce_long",
        "reduce_short",
        "close_position",
        "hold",
        "rebalance",
    ]
    target_weight: Decimal
    target_notional: Decimal | None = None
    max_leverage: Decimal
    confidence: float
    expected_holding_period: str
    thesis: str
    evidence: list[dict]
    invalidation_conditions: list[str]
    data_quality_score: float
    created_at_sim_time: datetime
```

## 9. Backend Architecture

The FastAPI backend is the control plane. It should remain lightweight and should not run heavy agent inference, long backtests, reinforcement learning training, or report generation inside request handlers.

### 9.1 Backend Responsibilities

- Expose REST APIs.
- Expose WebSocket or SSE streams.
- Receive frontend control commands.
- Manage simulation run lifecycle.
- Query relational, time-series, vector, and object storage.
- Create background jobs.
- Validate request and response schemas.
- Enforce authentication and authorization.
- Record audit logs.

### 9.2 Suggested Backend Structure

```text
apps/api/
  app/
    main.py
    api/
      routes/
        simulations.py
        datasets.py
        market.py
        agents.py
        decisions.py
        portfolio.py
        orders.py
        risk.py
        experiments.py
        models.py
        plugins.py
        reports.py
        websocket.py
    core/
      config.py
      auth.py
      logging.py
      event_bus.py
      errors.py
    db/
      session.py
      models/
      repositories/
      migrations/
    schemas/
      market.py
      simulation.py
      agent.py
      decision.py
      order.py
      portfolio.py
      risk.py
      experiment.py
    services/
      simulation_service.py
      market_data_service.py
      observation_service.py
      agent_service.py
      decision_service.py
      risk_service.py
      broker_service.py
      portfolio_service.py
      report_service.py
    runtime/
      clock.py
      orchestrator.py
      scheduler.py
      event_handlers.py
    workers/
      agent_worker.py
      backtest_worker.py
      rl_worker.py
      report_worker.py
```

### 9.3 Process Roles

| Process | Responsibility |
| --- | --- |
| API server | Request-response APIs, realtime sessions, auth, run control. |
| Worker | Agent inference, backtests, RL training, report generation. |
| Scheduler | Simulation clock advancement and event dispatch. |
| Watchdog | Health checks, stuck-run detection, alert generation. |

## 10. Frontend Architecture

The Next.js frontend is a long-running observation cockpit rather than a simple admin panel.

It should answer:

- What simulated time is the run currently at?
- Why did the agent make this decision?
- Why did risk approve, reject, resize, or circuit-break the decision?
- What are current equity, drawdown, exposure, fees, funding, and slippage?
- Did simulated orders fill as expected?
- Which agent, model, feature, or event contributed to profit or loss?
- What happened before and after a losing trade?

### 10.1 Suggested Frontend Structure

```text
apps/web/
  app/
    layout.tsx
    page.tsx
    simulations/
      page.tsx
      [runId]/
        page.tsx
        dashboard/
        market/
        agent-trace/
        decisions/
        portfolio/
        orders/
        risk/
        memory/
        reports/
    datasets/
      page.tsx
      upload/
      [datasetId]/
    experiments/
      page.tsx
      [experimentId]/
    models/
      page.tsx
      [modelId]/
    plugins/
      page.tsx
    settings/
      page.tsx
  components/
    charts/
    tables/
    timeline/
    agent/
    portfolio/
    risk/
    market/
    layout/
  lib/
    api-client.tsx
    websocket.tsx
    types.tsx
    format.tsx
```

### 10.2 Main Pages

| Page | Purpose |
| --- | --- |
| `/simulations` | List simulation runs, status, return, drawdown, and runtime. |
| `/simulations/[runId]/dashboard` | Long-running operational overview. |
| `/simulations/[runId]/market` | Candles, order book, volume, trades, replay controls, and event injection. |
| `/simulations/[runId]/agent-trace` | Agent role outputs, reasoning traces, evidence, and disagreements. |
| `/simulations/[runId]/decisions` | Structured trade intents, confidence, status, and posterior performance. |
| `/simulations/[runId]/portfolio` | Equity curve, positions, exposure, PnL, drawdown, and risk budget. |
| `/simulations/[runId]/orders` | Simulated orders, fills, fees, slippage, and matching status. |
| `/simulations/[runId]/risk` | Risk rules, rejections, circuit breakers, limits, and alerts. |
| `/simulations/[runId]/memory` | Decision memory, reviews, reflections, and failure cases. |
| `/experiments` | Backtests, walk-forward tests, parameter comparisons, and model experiments. |
| `/models` | RL, ML, and rule model versions, metrics, artifacts, and promotion status. |
| `/datasets` | Imports, data quality, ranges, gaps, and validation reports. |
| `/plugins` | Data, feature, event, report, and analysis plugins. |
| `/reports` | Daily reports, weekly reports, decision reviews, and simulation reports. |

### 10.3 Frontend State

| State type | Suggested handling |
| --- | --- |
| Server state | React Query or SWR-style cache over REST APIs. |
| Realtime state | WebSocket event reducer keyed by `run_id` and topic. |
| Local UI state | URL state, lightweight store, or React context. |
| Large historical data | Pagination, downsampling, and viewport-based chart queries. |

## 11. Realtime Event Channel

The frontend should observe long-running simulations through a realtime stream instead of polling.

Suggested endpoint:

```text
/ws/simulations/{run_id}
```

Subscription payload:

```json
{
  "type": "subscribe",
  "topics": [
    "market.candle",
    "agent.run",
    "decision.created",
    "risk.reviewed",
    "order.updated",
    "fill.created",
    "portfolio.updated",
    "alert.created",
    "simulation.status"
  ]
}
```

Event payload:

```json
{
  "event_id": "evt_01",
  "topic": "decision.created",
  "run_id": "run_001",
  "simulated_time": "2025-08-01T12:00:00Z",
  "payload": {
    "decision_id": "dec_001",
    "symbol": "BTCUSDT",
    "action": "increase_long",
    "target_weight": 0.18,
    "confidence": 0.67
  }
}
```

All realtime events must also be persisted so the frontend can recover state after refresh or reconnect.

## 12. Simulation Runtime

### 12.1 Core Loop

```text
1. Simulation clock advances to the next simulated timestamp.
2. Market replay emits point-in-time market events.
3. Feature engine updates feature snapshots.
4. Observation builder creates an observation packet.
5. Agent runtime evaluates the observation.
6. Decision layer validates and persists structured trade intent.
7. Risk engine approves, rejects, resizes, or circuit-breaks the intent.
8. Portfolio engine converts approved targets to simulated orders.
9. Sim broker submits orders to the simulated matching engine.
10. Matching engine creates fills.
11. Ledger updates cash, positions, fees, funding, and PnL.
12. Metrics engine records snapshots.
13. Event bus publishes updates to storage, workers, and frontend streams.
```

### 12.2 Orchestrator Pseudocode

```python
class SimulationOrchestrator:
    def step(self, run_id: UUID) -> None:
        context = self.load_run_context(run_id)
        market_events = self.clock.next_events(context)

        for market_event in market_events:
            self.event_bus.publish(market_event)
            self.feature_engine.update(market_event)

        observation = self.observation_builder.build(
            run_id=run_id,
            as_of=context.current_simulated_time,
        )

        agent_result = self.agent_runtime.run(observation)
        trade_intent = self.decision_service.validate_and_store(agent_result)
        risk_review = self.risk_engine.review(trade_intent, observation)

        if risk_review.status == "approved":
            order_requests = self.portfolio_engine.create_orders(
                intent=trade_intent,
                risk_review=risk_review,
                observation=observation,
            )
            execution_result = self.broker.submit(order_requests)
            self.ledger.apply(execution_result)

        self.metrics.update(run_id)
        self.event_bus.flush(run_id)
```

## 13. Data Layer

### 13.1 Data Policy

The data layer may use real-world market data, but the connection must remain strictly read-only. Real market data is an input to the simulated environment; it is not permission to trade on the source venue.

Required controls:

- Use public market data endpoints whenever possible.
- Keep market data credentials separate from any trading or account credentials.
- Do not configure API secrets that allow order placement, balance reads, withdrawals, wallet signing, or position management.
- Disable or block private SDK methods at the connector boundary.
- Persist all ingested data with source, `as_of`, `fetched_at`, and ingestion run metadata.
- Normalize symbols, timestamps, time zones, precision, and venue-specific field names before the observation builder consumes the data.
- Store raw data separately from normalized data so ingestion bugs can be replayed and audited.

### 13.2 Recommended Data Connectors

| Connector | Best use | Why it fits this system | Boundary |
| --- | --- | --- | --- |
| CCXT | REST-based exchange market data, historical OHLCV backfill, tickers, trades, order books, market metadata. | It provides a unified Python interface over many crypto exchanges and exposes public market data methods such as `fetchOHLCV`, `fetchTicker`, `fetchTrades`, and `fetchOrderBook`. Public CCXT market data can usually be used without exchange API keys. | Use only public methods. Block private methods such as order creation, balance reads, and position reads. |
| Cryptofeed | Realtime WebSocket collection for trades, L1/L2/L3 books, tickers, candles, funding, open interest, and liquidations. | It normalizes public WebSocket feeds across many exchanges and can write directly to backends such as Redis, PostgreSQL, Kafka, and other stores. | Subscribe only to public market data channels. Do not enable authenticated user-data channels. |
| Official exchange public APIs | Venue-specific source-of-truth ingestion where direct support is needed, especially Binance spot or futures klines, trades, depth, and mark-price data. | Official APIs document exact limits, fields, weights, intervals, and venue-specific semantics. | Use public REST/WebSocket endpoints only. Never use signed endpoints. |
| CoinGecko API or SDK | Broad asset universe, metadata, market cap, volume, daily/hourly OHLC, and cross-exchange reference data. | It is useful for universe selection and market context across many assets and networks. | Treat it as reference data, not execution-grade order book or matching data. API keys, when used, are data-provider keys only. |
| yfinance | Quick research baselines, notebooks, and low-friction historical crypto candles such as `BTC-USD` or `ETH-USD`. | It is simple to use and returns pandas-friendly historical market data. | Development and research only unless licensing and data quality are explicitly accepted. Not the primary source for simulated matching. |

Recommended default:

```text
Historical replay:
  CCXT REST backfill or official exchange public archive
  -> raw object storage
  -> normalized PostgreSQL/TimescaleDB tables

Realtime observation:
  Cryptofeed public WebSocket streams
  -> Redis/Kafka ingestion buffer
  -> normalized PostgreSQL/TimescaleDB tables

Market context:
  CoinGecko API or yfinance
  -> reference data tables
  -> observation builder as low-priority context
```

### 13.3 Data Sources

Supported sources:

- Read-only public exchange REST APIs.
- Read-only public exchange WebSocket streams.
- Read-only market data provider APIs.
- CSV.
- Parquet.
- JSON.
- Synthetic generators.
- Manually injected events.
- Generated scenario scripts.

Live market data connectors are allowed only as read-only data inputs. Live execution connectors are not allowed.

### 13.4 Data Types

The data layer should support:

- Candles.
- Ticks.
- Order book snapshots.
- Funding rates.
- Open interest.
- Market events.
- Synthetic news or sentiment events.
- Liquidity and volatility shocks.
- Portfolio snapshots.
- Metrics snapshots.

### 13.5 Data Quality Checks

Dataset validation must check:

- Missing timestamps.
- Duplicate timestamps.
- Out-of-order records.
- Invalid OHLC relationships.
- Negative or impossible volume.
- Large unexplained gaps.
- Symbol and timeframe consistency.
- Future-dated data relative to the run window.
- Point-in-time availability.
- Deterministic synthetic generation by seed.
- Source outage gaps.
- Provider rate-limit truncation.
- Exchange maintenance windows.
- Cross-source price divergence beyond configured tolerance.
- WebSocket sequence gaps or order book checksum failures where supported.

## 14. Observation Builder

The observation builder is the only path by which agents receive market, portfolio, memory, and risk context.

It must:

- Enforce `as_of` boundaries.
- Align multi-timeframe and multi-symbol data.
- Include current account, position, and risk state.
- Include only memory available at the simulated time.
- Emit explicit data-quality indicators.
- Produce both LLM-friendly structured context and RL-friendly numeric state vectors where needed.

Example packet shape:

```json
{
  "run_id": "run_001",
  "as_of": "2025-08-01T12:00:00Z",
  "symbols": ["BTCUSDT", "ETHUSDT"],
  "market": {
    "BTCUSDT": {
      "timeframe": "1h",
      "last_close": "68000.00",
      "returns": {
        "1h": 0.012,
        "24h": -0.031
      },
      "volatility": {
        "realized_24h": 0.62
      }
    }
  },
  "portfolio": {
    "equity": "103420.00",
    "gross_exposure": 0.64,
    "max_drawdown": -0.018
  },
  "risk": {
    "mode": "normal",
    "remaining_daily_loss_budget": 0.014
  },
  "data_quality": {
    "score": 0.97,
    "warnings": []
  }
}
```

## 15. Agent Layer

### 15.1 Agent Boundary

Agents may:

- Read observation packets.
- Use approved analysis tools.
- Produce structured trade intent.
- Produce rationale, evidence, uncertainty, and invalidation conditions.

Agents must not:

- Submit orders.
- Modify account state.
- Override risk controls.
- Read future data.
- Request live exchange access.
- Execute plugin code without sandbox approval.

### 15.2 Agent Roles

| Agent | Responsibility |
| --- | --- |
| Coordinator Agent | Dispatches and aggregates role outputs. |
| Market Regime Agent | Classifies trend, range, volatility, liquidity, and risk regime. |
| Technical Agent | Evaluates price action, indicators, trend, momentum, and mean reversion. |
| Event Agent | Interprets synthetic news, sentiment, funding, and event shocks. |
| Quant / RL Agent | Provides numeric policy signal or target weight suggestion. |
| Trader Agent | Converts analysis into candidate trade intent. |
| Critic Agent | Challenges assumptions, evidence, and risk. |
| Portfolio Agent | Suggests portfolio-level target allocation before hard risk review. |

### 15.3 Agent Workflow

```text
Observation packet
  -> role-specific analysis
  -> evidence collection
  -> candidate trade intent
  -> critic review
  -> final structured intent
  -> decision validation
```

All intermediate outputs should be stored as `agent_runs` and `agent_messages` for traceability.

## 16. Decision Layer

The decision layer validates, persists, and audits agent output.

Decision state machine:

```text
created
  -> schema_validated
  -> risk_reviewed
  -> approved | rejected | resized | circuit_blocked
  -> converted_to_order | no_order
  -> reviewed
```

Every decision must preserve:

- Observation ID.
- Agent run ID.
- Input data availability timestamp.
- Structured trade intent.
- Evidence references.
- Critic output.
- Risk review.
- Resulting orders and fills.
- Posterior review metrics.

## 17. Risk Engine

The risk engine is independent from the agent layer.

### 17.1 Risk Hierarchy

| Level | Examples |
| --- | --- |
| Data quality | Missing data, stale data, future data, low confidence. |
| Instrument | Symbol whitelist, min notional, tick size, liquidity, spread. |
| Position | Max position size, max leverage, concentration, direction. |
| Portfolio | Gross exposure, net exposure, drawdown, daily loss, volatility. |
| Runtime | Agent timeout, repeated errors, stuck orders, unhealthy worker. |
| Circuit breaker | Stop run, pause trading, force hold-only mode. |

### 17.2 Risk Review Output

```python
class RiskReview(BaseModel):
    review_id: UUID
    decision_id: UUID
    status: Literal["approved", "rejected", "resized", "circuit_blocked"]
    original_target_weight: Decimal
    approved_target_weight: Decimal
    max_order_notional: Decimal
    reasons: list[str]
    triggered_rules: list[str]
    created_at_sim_time: datetime
```

## 18. Portfolio Engine

The portfolio engine converts approved target exposure into simulated order requests.

Inputs:

- Approved trade intent.
- Risk review.
- Current account equity.
- Current positions.
- Symbol constraints.
- Broker fee and slippage model.
- Target leverage and exposure limits.

Outputs:

- One or more simulated order requests.
- Order sizing explanation.
- Expected notional, fee estimate, and slippage estimate.
- No-order result when the target is already satisfied or too small to execute.

Order logic:

```text
target_notional = approved_target_weight * total_equity
delta_notional = target_notional - current_position_notional
quantity = round_to_lot_size(delta_notional / reference_price)
reject or no-op when abs(quantity) is below min_notional
```

## 19. Simulated Exchange

### 19.1 Components

| Component | Responsibility |
| --- | --- |
| Sim broker | Accepts order requests and owns order lifecycle. |
| Matching engine | Simulates market, limit, partial, and expired fills. |
| Fee engine | Applies maker, taker, funding, and configurable fee tiers. |
| Slippage engine | Computes slippage from volatility, liquidity, spread, and order size. |
| Ledger | Applies fills to cash, positions, realized PnL, unrealized PnL, and fees. |
| Metrics engine | Emits account, portfolio, risk, and performance snapshots. |

### 19.2 Order State Machine

```text
created
  -> submitted
  -> accepted | rejected
  -> open
  -> partially_filled
  -> filled | canceled | expired
```

### 19.3 Matching Models

Market orders:

- Fill at current reference price plus simulated slippage.
- Apply taker fee.
- May be rejected if spread, liquidity, data quality, or risk state is unacceptable.

Limit orders:

- Fill only if replayed or synthetic market prices cross the limit.
- Support partial fills based on simulated depth.
- Expire according to time-in-force rules.

Funding fees:

- Apply to perpetual positions at configured simulated funding intervals.
- Record ledger entries separately from trading fees.

## 20. PnL and Metrics

### 20.1 Account Metrics

- Total equity.
- Cash balance.
- Realized PnL.
- Unrealized PnL.
- Cumulative fees.
- Cumulative funding.
- Gross exposure.
- Net exposure.
- Max drawdown.
- Sharpe-like and Sortino-like metrics where data frequency supports them.
- Turnover.
- Win rate.
- Profit factor.

### 20.2 Agent Metrics

- Decision count.
- Approval rate.
- Rejection rate.
- Average confidence.
- Realized return by horizon.
- Directional accuracy.
- Contribution to PnL.
- Average adverse excursion.
- Average favorable excursion.
- Overconfidence indicators.

### 20.3 Posterior Decision Review

Each decision should be reviewed after configured horizons such as 1h, 4h, 24h, and 7d.

```python
class DecisionReview(BaseModel):
    decision_id: UUID
    horizon: str
    realized_return: Decimal
    max_adverse_excursion: Decimal
    max_favorable_excursion: Decimal
    was_correct_directionally: bool
    error_tags: list[str]
    reviewer_summary: str
```

Error tags:

```text
bad_regime_detection
late_entry
overconfidence
data_missing
risk_too_loose
risk_too_strict
slippage_underestimated
event_misread
rl_signal_failed
```

## 21. Reinforcement Learning Lab

Reinforcement learning is an advisory research component. It must not directly control the account or bypass the decision, risk, portfolio, and broker layers.

### 21.1 Environment Contract

```python
class TradingEnvironment:
    def reset(self, seed: int | None = None) -> Observation:
        ...

    def step(self, action: Action) -> tuple[Observation, float, bool, dict]:
        ...
```

### 21.2 State Space

The RL state can include:

- Recent returns.
- Volatility.
- Volume and liquidity features.
- Spread and depth.
- Funding rate.
- Current position ratio.
- Unrealized PnL.
- Drawdown.
- Gross and net exposure.
- Remaining risk budget.

### 21.3 Action Space

Discrete example:

```text
0 = flat
1 = 10% long
2 = 25% long
3 = 50% long
4 = 10% short
5 = 25% short
6 = 50% short
```

Continuous example:

```text
target_weight in [-1.0, 1.0]
```

### 21.4 Reward Function

```text
reward =
  portfolio_return
  - fee_cost
  - slippage_cost
  - funding_cost
  - drawdown_penalty
  - leverage_penalty
  - turnover_penalty
  - invalid_action_penalty
```

### 21.5 Model Registry

```python
class ModelRegistryEntry(BaseModel):
    model_id: UUID
    name: str
    version: str
    model_type: Literal["rl", "ml", "rule"]
    algorithm: str
    training_dataset_id: UUID
    validation_dataset_id: UUID
    metrics: dict
    artifact_uri: str
    status: Literal["draft", "validated", "paper_enabled", "archived"]
    created_at: datetime
```

## 22. Memory and Reflection

Memory is auxiliary context. It must not replace validation, risk review, or reproducible testing.

Memory types:

- Decision memory: prior decision, rationale, and outcome.
- Failure memory: losing cases, error tags, and avoidance conditions.
- Regime memory: strategy performance by market regime.
- Agent memory: long-term behavior of each agent.
- Experiment memory: experiment conclusions and limitations.

Memory entries must carry availability timestamps so the observation builder can enforce point-in-time access.

## 23. Plugin System

The plugin system expands data, features, synthetic events, analysis, and reports without adding live trading access.

Allowed plugin categories:

- Read-only market data connector plugins.
- Data import plugins.
- Synthetic market plugins.
- Feature calculation plugins.
- Event generation plugins.
- Analysis tool plugins.
- Report plugins.
- Experiment plugins.

### 23.1 Plugin Manifest

```yaml
name: synthetic_liquidity_shock_generator
version: 0.1.0
type: event_generator
description: Generate synthetic liquidity shock events for BTC/ETH.
permissions:
  read_market_data: true
  write_market_events: true
  write_orders: false
  network: false
inputs:
  - run_id
  - symbols
  - probability_per_day
  - severity_distribution
outputs:
  schema: MarketEvent
tests:
  - test_schema_valid
  - test_no_future_events
  - test_deterministic_seed
status: draft
```

### 23.2 Plugin Approval Flow

```text
Agent proposes plugin need
  -> tool builder creates plugin draft
  -> sandbox executes tests
  -> schema validation
  -> determinism validation
  -> permission validation
  -> human or policy approval
  -> plugin registry entry
  -> enabled for selected simulation runs
```

### 23.3 Plugin Permissions

```python
class PluginPermissions(BaseModel):
    read_market_data: bool = False
    read_portfolio: bool = False
    write_market_events: bool = False
    write_features: bool = False
    write_orders: bool = False
    network_access: bool = False
    file_system_access: Literal["none", "sandbox", "readonly"] = "sandbox"
```

Recommended defaults:

```text
network_access = false for ordinary plugins
network_access = true only for approved read-only market data connector plugins with an allowlisted provider
write_orders = false
file_system_access = sandbox
```

## 24. Persistence Architecture

### 24.1 Storage Choices

| Store | Usage |
| --- | --- |
| PostgreSQL | Accounts, orders, fills, decisions, configuration, audit logs. |
| TimescaleDB or partitioned PostgreSQL tables | Candles, ticks, portfolio snapshots, metrics. |
| Object store | Parquet datasets, model artifacts, raw agent logs, report artifacts. |
| Redis | Queues, Pub/Sub, short-lived runtime state, WebSocket fanout. |
| Vector store | Decision memory, reports, event summaries, agent reflections. |

### 24.2 Main Tables

```text
users
projects
simulations
simulation_runs
datasets
assets
candles
orderbook_snapshots
market_events
feature_snapshots
observation_snapshots
agent_runs
agent_messages
decisions
risk_reviews
orders
fills
accounts
positions
ledger_entries
portfolio_snapshots
metric_snapshots
alerts
experiments
model_registry
plugin_registry
audit_logs
reports
```

### 24.3 Example Tables

```sql
CREATE TABLE simulation_runs (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    mode TEXT NOT NULL,
    dataset_id UUID,
    account_id UUID NOT NULL,
    start_sim_time TIMESTAMPTZ NOT NULL,
    end_sim_time TIMESTAMPTZ,
    current_sim_time TIMESTAMPTZ,
    speed_multiplier NUMERIC NOT NULL DEFAULT 1,
    config JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE decisions (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL,
    observation_id UUID NOT NULL,
    agent_run_id UUID NOT NULL,
    symbol TEXT NOT NULL,
    action TEXT NOT NULL,
    target_weight NUMERIC NOT NULL,
    confidence NUMERIC NOT NULL,
    thesis TEXT,
    evidence JSONB NOT NULL,
    status TEXT NOT NULL,
    created_at_sim_time TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE orders (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL,
    account_id UUID NOT NULL,
    decision_id UUID,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    order_type TEXT NOT NULL,
    quantity NUMERIC NOT NULL,
    limit_price NUMERIC,
    status TEXT NOT NULL,
    submitted_at_sim_time TIMESTAMPTZ NOT NULL,
    updated_at_sim_time TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE fills (
    id UUID PRIMARY KEY,
    order_id UUID NOT NULL,
    run_id UUID NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity NUMERIC NOT NULL,
    price NUMERIC NOT NULL,
    fee NUMERIC NOT NULL,
    slippage_bps NUMERIC NOT NULL,
    filled_at_sim_time TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## 25. API Design

### 25.1 Simulation API

```text
POST   /api/simulations
GET    /api/simulations
GET    /api/simulations/{run_id}
POST   /api/simulations/{run_id}/start
POST   /api/simulations/{run_id}/pause
POST   /api/simulations/{run_id}/resume
POST   /api/simulations/{run_id}/stop
POST   /api/simulations/{run_id}/step
POST   /api/simulations/{run_id}/speed
GET    /api/simulations/{run_id}/events
GET    /api/simulations/{run_id}/status
```

### 25.2 Dataset API

```text
POST   /api/datasets/upload
GET    /api/datasets
GET    /api/datasets/{dataset_id}
POST   /api/datasets/{dataset_id}/validate
GET    /api/datasets/{dataset_id}/quality
GET    /api/datasets/{dataset_id}/candles
```

### 25.3 Market API

```text
GET    /api/market/symbols
GET    /api/market/candles
GET    /api/market/orderbook
GET    /api/market/events
POST   /api/market/events/inject
```

### 25.4 Agent API

```text
GET    /api/agents
GET    /api/agents/runs
GET    /api/agents/runs/{agent_run_id}
GET    /api/agents/runs/{agent_run_id}/messages
POST   /api/agents/runs/{agent_run_id}/replay
```

### 25.5 Decision API

```text
GET    /api/decisions
GET    /api/decisions/{decision_id}
GET    /api/decisions/{decision_id}/trace
GET    /api/decisions/{decision_id}/review
POST   /api/decisions/{decision_id}/annotate
```

### 25.6 Portfolio API

```text
GET    /api/portfolio/{run_id}/summary
GET    /api/portfolio/{run_id}/positions
GET    /api/portfolio/{run_id}/snapshots
GET    /api/portfolio/{run_id}/pnl
GET    /api/portfolio/{run_id}/drawdown
```

### 25.7 Order API

```text
GET    /api/orders
GET    /api/orders/{order_id}
GET    /api/fills
GET    /api/fills/{fill_id}
```

### 25.8 Risk API

```text
GET    /api/risk/{run_id}/limits
PUT    /api/risk/{run_id}/limits
GET    /api/risk/{run_id}/reviews
GET    /api/risk/{run_id}/alerts
POST   /api/risk/{run_id}/pause
POST   /api/risk/{run_id}/resume
```

### 25.9 Experiment and Model API

```text
POST   /api/experiments
GET    /api/experiments
GET    /api/experiments/{experiment_id}
POST   /api/experiments/{experiment_id}/run
GET    /api/models
GET    /api/models/{model_id}
POST   /api/models/{model_id}/promote
POST   /api/models/{model_id}/archive
```

## 26. Long-Running Observation

### 26.1 Watchdog

The watchdog checks:

- Stuck simulations.
- Agent timeouts.
- Dead workers.
- WebSocket backlog.
- Data stream gaps.
- Orders stuck open for too long.
- Abnormal risk state.
- Abnormal PnL jumps.

### 26.2 Heartbeat Event

```json
{
  "topic": "simulation.heartbeat",
  "run_id": "run_001",
  "wall_time": "2026-05-30T12:00:00Z",
  "simulated_time": "2025-08-01T12:00:00Z",
  "status": "running",
  "clock_lag_ms": 120,
  "event_queue_depth": 4,
  "worker_status": "healthy"
}
```

### 26.3 Alerts

Alert categories:

- PnL alerts.
- Drawdown alerts.
- Agent timeout alerts.
- Data quality alerts.
- Order anomaly alerts.
- Runtime stuck alerts.
- Worker health alerts.
- Risk circuit-breaker alerts.
- Model degradation alerts.

## 27. Reporting

### 27.1 Simulation Report

Simulation reports include:

- Run configuration.
- Dataset information.
- Start and end simulated time.
- Equity curve.
- Drawdown curve.
- Position curve.
- Trade list.
- Key metrics.
- Risk events.
- Agent performance.
- Error attribution.

### 27.2 Decision Report

Decision reports include:

- Observation snapshot.
- Agent subreports.
- Final trade intent.
- Critic objections.
- Risk review.
- Orders and fills.
- Posterior performance.
- Review conclusion.

### 27.3 Experiment Report

Experiment reports include:

- Hypothesis.
- Training, validation, and test periods.
- Parameters.
- Model version.
- Backtest results.
- Stress tests.
- Out-of-sample performance.
- Eligibility decision for simulated use.

## 28. Security and Permissions

### 28.1 Roles

| Role | Permissions |
| --- | --- |
| Admin | Manage all configuration, plugins, models, and datasets. |
| Researcher | Create experiments, upload datasets, run backtests. |
| Operator | Start and stop simulations, observe runs, inject events. |
| Viewer | Read-only observation. |

### 28.2 Plugin Sandbox

Plugins must:

- Have no network access by default, except approved read-only market data connector plugins.
- Be unable to write orders by default.
- Access only approved directories.
- Emit schema-validated output.
- Run under CPU, memory, and time limits.

Market data connector plugins with network access must be restricted by provider allowlist, method allowlist, rate limits, and credential scope. They must not expose private trading, account, balance, position, withdrawal, transfer, or wallet-signing methods to agents.

### 28.3 Prompt Injection Defense

Even simulated news and events must be treated as untrusted data.

Required controls:

- Event text is data, not instruction.
- Agent system prompts and data prompts are separated.
- Tool calls pass through a permission layer.
- Trade intents require schema validation.
- The risk layer does not accept natural-language overrides.

## 29. Configuration

### 29.1 Simulation Config

```yaml
simulation:
  name: btc_eth_agent_long_run
  mode: live_simulated_clock
  speed_multiplier: 10
  start_time: "2025-01-01T00:00:00Z"
  end_time: "2025-06-01T00:00:00Z"
  symbols:
    - BTCUSDT
    - ETHUSDT
  timeframe: 1h
  decision_interval: 1h
  initial_equity: 100000
```

### 29.2 Agent Config

```yaml
agents:
  coordinator:
    enabled: true
  market_regime:
    enabled: true
  technical:
    enabled: true
  derivatives:
    enabled: true
  event:
    enabled: true
  quant_rl:
    enabled: true
    model_id: rl_btc_eth_v3
  critic:
    enabled: true
  portfolio:
    enabled: true

llm:
  provider: local_or_external
  temperature: 0.1
  max_tokens: 4096
  timeout_seconds: 60
```

### 29.3 Sim Broker Config

```yaml
broker:
  fee:
    maker_bps: 2
    taker_bps: 5
  slippage:
    base_bps: 3
    volatility_multiplier: 0.2
    liquidity_multiplier: 1.5
  order:
    allow_market: true
    allow_limit: true
    allow_short: true
    allow_leverage: true
  latency:
    decision_to_order_ms: 500
    order_to_fill_ms_mean: 300
```

### 29.4 Market Data Connector Config

```yaml
market_data:
  primary_historical_connector: ccxt
  primary_realtime_connector: cryptofeed
  allow_private_exchange_methods: false
  allow_trading_credentials: false
  raw_storage_uri: s3://tiko-market-data/raw
  normalized_storage: timescaledb

  connectors:
    ccxt:
      enabled: true
      exchanges:
        - binance
        - okx
      methods_allowlist:
        - fetchMarkets
        - fetchTicker
        - fetchTickers
        - fetchTrades
        - fetchOrderBook
        - fetchOHLCV
      methods_blocklist:
        - createOrder
        - cancelOrder
        - fetchBalance
        - fetchOpenOrders
        - fetchPositions

    cryptofeed:
      enabled: true
      channels:
        - trades
        - l2_book
        - ticker
        - candles
        - funding
        - open_interest
      authenticated_channels_enabled: false

    coingecko:
      enabled: true
      purpose: reference_data
      api_key_secret_name: COINGECKO_MARKET_DATA_KEY

    yfinance:
      enabled: true
      purpose: research_only
```

## 30. Repository Layout

Suggested target layout:

```text
crypto-sim-agent/
  apps/
    web/
      app/
      components/
      lib/
      public/
      package.json

    api/
      app/
        main.py
        api/
        core/
        db/
        schemas/
        services/
        runtime/
        workers/
      pyproject.toml

  packages/
    shared-types/

  backend/
    domain/
      market/
      portfolio/
      orders/
      risk/
      decisions/
      agents/
      simulation/

    data/
      importers/
      validators/
      feature_engine/
      synthetic/

    observation/
      builder.py
      schemas.py

    agents/
      orchestrator.py
      roles/
        coordinator.py
        market_regime.py
        technical.py
        derivatives.py
        event.py
        quant.py
        trader.py
        critic.py
        portfolio.py
      prompts/

    simulation/
      clock.py
      market_replay.py
      broker.py
      matching_engine.py
      fee_engine.py
      slippage_engine.py
      ledger.py
      metrics.py

    rl_lab/
      envs/
      training/
      evaluation/
      registry/

    memory/
      decision_memory.py
      vector_store.py
      reflection.py

    plugins/
      registry.py
      sandbox.py
      manifests/

  infra/
    docker-compose.yml
    postgres/
    redis/
    grafana/
    prometheus/

  datasets/
    samples/

  tests/
    unit/
    integration/
    replay/
    determinism/
```

## 31. Deployment Topology

```yaml
services:
  web:
    build: ./apps/web
    ports:
      - "3000:3000"
    environment:
      NEXT_PUBLIC_API_BASE_URL: http://localhost:8000

  api:
    build: ./apps/api
    ports:
      - "8000:8000"
    depends_on:
      - postgres
      - redis
    environment:
      DATABASE_URL: postgresql://app:app@postgres:5432/app
      REDIS_URL: redis://redis:6379/0

  worker:
    build: ./apps/api
    command: ["python", "-m", "app.workers.main"]
    depends_on:
      - postgres
      - redis

  scheduler:
    build: ./apps/api
    command: ["python", "-m", "app.runtime.scheduler"]
    depends_on:
      - postgres
      - redis

  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: app
      POSTGRES_PASSWORD: app
      POSTGRES_DB: app
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7

  object-store:
    image: minio/minio
    command: server /data --console-address ":9001"

volumes:
  pgdata:
```

## 32. Testing Strategy

### 32.1 Unit Tests

Unit tests should cover:

- Feature engine.
- Read-only data connector method allowlists.
- Market data normalization.
- Observation builder.
- Risk rules.
- Portfolio sizing.
- Fee calculation.
- Slippage model.
- Order state machine.
- PnL calculation.

### 32.2 Integration Tests

Integration tests should cover:

```text
dataset import
  -> simulation creation
  -> clock advancement
  -> observation building
  -> agent decision
  -> risk review
  -> simulated matching
  -> ledger update
  -> metrics update
```

### 32.3 Deterministic Replay Test

The same configuration, dataset, and seed must produce the same orders, fills, and PnL.

```text
same config + same seed = same orders + same fills + same PnL
```

### 32.4 Lookahead Test

Lookahead tests must ensure:

- `Observation.as_of = T`.
- Every input has `data.as_of <= T`.
- Future events are excluded.
- Rolling features use only historical windows.
- Memory entries are available only if their timestamps allow it.

### 32.5 Risk Tests

Risk tests must ensure:

- Oversized positions are rejected or resized.
- Daily loss limits trigger circuit breakers.
- Insufficient data quality rejects decisions.
- Low-confidence decisions are rejected.
- Excessive slippage rejects or resizes orders.

## 33. Recommended Build Order

1. Domain schemas for assets, candles, events, accounts, positions, orders, fills, and decisions.
2. Database schema, migrations, and repositories.
3. Read-only market data connector, dataset import, normalization, and validation for CCXT, Cryptofeed, CSV, and Parquet.
4. Simulation clock and market replay.
5. Sim broker, matching engine, fee engine, slippage engine, ledger, and metrics.
6. Point-in-time observation builder.
7. Risk engine and portfolio engine.
8. Agent runtime with structured `TradeIntent` output.
9. FastAPI REST and WebSocket APIs.
10. Next.js long-running dashboard, orders, positions, risk, and decision trace pages.
11. Memory and posterior decision review.
12. RL lab environment, training, evaluation, and model registry.
13. Plugin registry and sandbox.
14. Reporting and alerting.
15. Deterministic replay, benchmark, and run comparison tooling.

## 34. Final System Definition

The complete system is a cryptocurrency simulation trading agent platform. It constructs point-in-time market environments from read-only real-world market data, local files, imported datasets, generated scenarios, and synthetic data; runs a Python agent runtime and RL lab to generate structured trading intent; uses independent risk and portfolio engines to convert approved intent into simulated orders; and executes those orders through an internal simulated exchange that records fills, fees, ledger entries, PnL, and metrics.

FastAPI provides the control plane, data access, job dispatch, and realtime event stream. Next.js provides long-running observation, decision tracing, risk monitoring, experiment management, replay, review, and reporting.

The central implementation rule is that the agent layer never executes trades. It only proposes intent. Real market data connectors are read-only inputs. Every executable simulated action must pass through deterministic schema validation, risk review, portfolio sizing, simulated broker handling, and ledger recording.

## 35. Research Sources

The connector recommendations above are based on current public documentation and project documentation:

- [CCXT](https://github.com/ccxt/ccxt): unified exchange public market data methods and separation between public and private APIs.
- [Cryptofeed](https://github.com/bmoscon/cryptofeed): normalized public WebSocket market data channels and storage backends.
- [Binance Spot Market Data Endpoints](https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints): official public kline, trade, and market data endpoint semantics.
- [CoinGecko API](https://docs.coingecko.com): asset metadata, OHLC, market chart, REST, WebSocket, webhook, and official SDK capabilities.
- [yfinance](https://github.com/ranaroussi/yfinance): research-oriented Yahoo Finance data access and usage caveats.
