# Agent Instructions

This repository is a multi-agent trading framework using LangGraph. These instructions are meant to help automated agents (like OpenCode) navigate the codebase effectively.

## Repository Context

* **Forked Open Source**: This is a forked repository of an open-source project. Keep upstream compatibility in mind when making architectural changes, and ensure no personal secrets or credentials are ever hardcoded into the open-source history.

## Architecture & Boundaries

* **Graph Execution**: The central control flow is a LangGraph state machine located in `tradingagents/graph/trading_graph.py`. State structures (`AgentState`, `InvestDebateState`, `RiskDebateState`) are found in `tradingagents/agents/utils/agent_states.py`.
* **Data Providers**: External APIs (e.g., `yfinance`, Alpha Vantage) are abstracted in `tradingagents/dataflows/`. **Never call `yfinance` directly from an agent.** Always use the abstraction layer in `tradingagents/agents/utils/agent_utils.py` (e.g., `get_stock_data`, `get_fundamentals`), which respects the user's data vendor configuration.
* **LLM Clients**: Support for multiple model providers is managed centrally. Always use `create_llm_client` from `tradingagents/llm_clients/factory.py` to get an LLM instance rather than directly instantiating `ChatOpenAI` or `ChatAnthropic`.
* **Structured Output**: The decision-making agents (Trader, Research Manager, Portfolio Manager) return strictly typed Pydantic models defined in `tradingagents/agents/schemas.py`. Always use these schemas when parsing final agent outputs.

## State & Persistence

* **Memory Log**: Historical decisions and reflections are saved to `~/.tradingagents/memory/trading_memory.md` and injected into future portfolio manager prompts.
* **Checkpoints (Crucial Gotcha)**: LangGraph state checkpoints are saved locally to `~/.tradingagents/cache/checkpoints/<TICKER>.db`. **If you modify the schema of the graph state or need to test a full run from scratch, be aware that existing checkpoints might cause parsing errors or skip your new nodes.** Advise the user to run with `--clear-checkpoints` or manually delete the `.db` file if state-shape changes are made.

## Environment & Testing

* **Package Manager**: The project uses `uv`. To install dependencies and the CLI, run `uv pip install -e .`.
* **Configuration**: Default settings are defined in `tradingagents/default_config.py`. Use this file instead of hardcoding defaults in individual classes.
* **Running Tests**: Run `pytest tests/`. 
  * Test execution is categorized by markers: `@pytest.mark.unit`, `@pytest.mark.integration`, and `@pytest.mark.smoke`.
  * **API Keys**: You do not need to provide real API keys to run unit tests. `tests/conftest.py` automatically stubs out all API keys globally with placeholders to prevent hangs or failures on CI. 
  * If a test requires actual external data fetching (like pulling live quotes), mark it with `@pytest.mark.integration` and know it will hit the network.
