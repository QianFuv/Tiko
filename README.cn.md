# Tiko

Tiko 是一个加密货币仿真交易智能体平台，由 FastAPI 后端、Python 仿真运行时和
Next.js 前端组成。

系统可以使用真实的公开市场数据、导入数据集、生成数据和合成市场场景，但不会发起
真实交易。订单、成交、余额、盈亏、回撤、风险决策、报告和智能体结果都只在平台内
部仿真。

## 安全边界

- 不暴露任何交易所私有交易接口。
- 不使用钱包、提现、转账、券商执行或签名流程。
- 只允许为读取公开市场数据配置只读数据凭证。
- 智能体只输出结构化交易意图。
- 所有可执行的仿真动作都必须经过 schema 校验、风险审核、组合 sizing 和内部仿真
  broker。

## 架构

- `tiko/`：FastAPI 控制面、领域模型、服务层、仿真运行时、数据连接器、插件沙箱、
  RL 实验室和 worker。
- `app/`：Next.js 前端，用于仿真、市场回放、智能体 trace、决策、组合、订单、风
  控、记忆、数据集、实验、模型、插件和报告。
- `tests/`：后端单元测试和集成测试。
- `infra/`：部署和进程拓扑参考。
- `docs/`：架构和任务计划文档。

目标状态系统设计见 `docs/architecture.md`。

## 环境要求

- Python 3.12
- `uv`
- Node.js
- `pnpm`

## 后端初始化

在仓库根目录安装 Python 环境：

```powershell
uv sync --extra dev
```

需要后端 API 时启动服务：

```powershell
uv run uvicorn tiko.api.main:create_app --factory --host 127.0.0.1 --port 8000
```

## 前端初始化

在 `app/` 目录安装前端依赖：

```powershell
cd app
pnpm install
```

启动开发服务：

```powershell
pnpm dev
```

前端默认地址是 `http://127.0.0.1:3000`。后端地址读取
`NEXT_PUBLIC_API_BASE_URL`，默认是 `http://127.0.0.1:8000`。

## 配置

在本地 `.env` 文件中放置密钥。该文件已被 Git 忽略。

OpenRouter 仿真智能体评估可使用以下任一变量：

```text
TIKO_OPENROUTER_API_KEY=...
OPENROUTER_API_KEY=...
```

可选 OpenRouter 配置：

```text
TIKO_OPENROUTER_MODEL=liquid/lfm-2.5-1.2b-instruct:free
TIKO_OPENROUTER_TIMEOUT_SECONDS=60
TIKO_OPENROUTER_TEMPERATURE=0.1
TIKO_OPENROUTER_MAX_TOKENS=4096
```

不要在本项目中保存真实交易凭证。

## 质量检查

后端：

```powershell
uv run ruff format --check tiko tests
uv run ruff check tiko tests
uv run mypy tiko tests
uv run pytest tests -W error
```

前端：

```powershell
cd app
pnpm exec prettier --write src
pnpm exec eslint src
pnpm exec tsc --noEmit
```

## 常用工作流

- 上传或导入市场数据集。
- 创建历史回放、实时仿真时钟或合成市场运行。
- 观察仿真市场状态、决策、风险审核、订单、成交和组合状态。
- 运行规则型或 OpenRouter 支持的仿真智能体。
- 复盘决策结果、记忆、报告、实验、模型和插件沙箱状态。

## 当前状态

该仓库当前是仿真专用研究平台。测试覆盖控制面、市场数据导入、回放、智能体运行
时、风险与组合控制、仿真交易所、实时流、报告、模型与插件 registry，以及 RL 实
验室组件。
