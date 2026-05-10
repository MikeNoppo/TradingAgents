import asyncio
import datetime
import os
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

app = FastAPI(title="TradingAgents API")

UNSAFE_DEFAULT_TOKENS = {"", "admin", "admin123", "password", "changeme"}


def get_api_token() -> str:
    token = os.environ.get("API_AUTH_TOKEN") or os.environ.get("WEB_PASSWORD", "")
    if token.strip().lower() in UNSAFE_DEFAULT_TOKENS:
        raise HTTPException(
            status_code=503,
            detail="API auth token is not configured. Set WEB_PASSWORD or API_AUTH_TOKEN.",
        )
    return token


def validate_api_token(token: str | None) -> None:
    expected = get_api_token()
    if token != expected:
        raise HTTPException(status_code=401, detail="Invalid API token")

# --- Report Saving Logic (Adapted from CLI) ---
def save_report_to_disk(final_state, ticker: str) -> str:
    """Save complete analysis report to disk and return the folder name."""
    base_dir = Path.home() / ".tradingagents" / "reports"
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = f"{ticker}_{timestamp}"
    save_path = base_dir / folder_name
    
    save_path.mkdir(parents=True, exist_ok=True)
    sections = []

    # 1. Analysts
    analysts_dir = save_path / "1_analysts"
    analyst_parts = []
    if final_state.get("market_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "market.md").write_text(final_state["market_report"], encoding="utf-8")
        analyst_parts.append(("Market Analyst", final_state["market_report"]))
    if final_state.get("sentiment_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "sentiment.md").write_text(final_state["sentiment_report"], encoding="utf-8")
        analyst_parts.append(("Social Analyst", final_state["sentiment_report"]))
    if final_state.get("news_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "news.md").write_text(final_state["news_report"], encoding="utf-8")
        analyst_parts.append(("News Analyst", final_state["news_report"]))
    if final_state.get("fundamentals_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "fundamentals.md").write_text(final_state["fundamentals_report"], encoding="utf-8")
        analyst_parts.append(("Fundamentals Analyst", final_state["fundamentals_report"]))
    if analyst_parts:
        content = "\n\n".join(f"### {name}\n{text}" for name, text in analyst_parts)
        sections.append(f"## I. Analyst Team Reports\n\n{content}")

    # 2. Research
    if final_state.get("investment_debate_state"):
        research_dir = save_path / "2_research"
        debate = final_state["investment_debate_state"]
        research_parts = []
        if debate.get("bull_history"):
            research_dir.mkdir(exist_ok=True)
            (research_dir / "bull.md").write_text(debate["bull_history"], encoding="utf-8")
            research_parts.append(("Bull Researcher", debate["bull_history"]))
        if debate.get("bear_history"):
            research_dir.mkdir(exist_ok=True)
            (research_dir / "bear.md").write_text(debate["bear_history"], encoding="utf-8")
            research_parts.append(("Bear Researcher", debate["bear_history"]))
        if debate.get("judge_decision"):
            research_dir.mkdir(exist_ok=True)
            (research_dir / "manager.md").write_text(debate["judge_decision"], encoding="utf-8")
            research_parts.append(("Research Manager", debate["judge_decision"]))
        if research_parts:
            content = "\n\n".join(f"### {name}\n{text}" for name, text in research_parts)
            sections.append(f"## II. Research Team Decision\n\n{content}")

    # 3. Trading
    if final_state.get("trader_investment_plan"):
        trading_dir = save_path / "3_trading"
        trading_dir.mkdir(exist_ok=True)
        (trading_dir / "trader.md").write_text(final_state["trader_investment_plan"], encoding="utf-8")
        sections.append(f"## III. Trading Team Plan\n\n### Trader\n{final_state['trader_investment_plan']}")

    # 4. Risk Management
    if final_state.get("risk_debate_state"):
        risk_dir = save_path / "4_risk"
        risk = final_state["risk_debate_state"]
        risk_parts = []
        if risk.get("aggressive_history"):
            risk_dir.mkdir(exist_ok=True)
            (risk_dir / "aggressive.md").write_text(risk["aggressive_history"], encoding="utf-8")
            risk_parts.append(("Aggressive Analyst", risk["aggressive_history"]))
        if risk.get("conservative_history"):
            risk_dir.mkdir(exist_ok=True)
            (risk_dir / "conservative.md").write_text(risk["conservative_history"], encoding="utf-8")
            risk_parts.append(("Conservative Analyst", risk["conservative_history"]))
        if risk.get("neutral_history"):
            risk_dir.mkdir(exist_ok=True)
            (risk_dir / "neutral.md").write_text(risk["neutral_history"], encoding="utf-8")
            risk_parts.append(("Neutral Analyst", risk["neutral_history"]))
        if risk_parts:
            content = "\n\n".join(f"### {name}\n{text}" for name, text in risk_parts)
            sections.append(f"## IV. Risk Management Team Decision\n\n{content}")

        # 5. Portfolio Manager
        if risk.get("judge_decision"):
            portfolio_dir = save_path / "5_portfolio"
            portfolio_dir.mkdir(exist_ok=True)
            (portfolio_dir / "decision.md").write_text(risk["judge_decision"], encoding="utf-8")
            sections.append(f"## V. Portfolio Manager Decision\n\n### Portfolio Manager\n{risk['judge_decision']}")

    # Write consolidated report
    header = f"# Trading Analysis Report: {ticker}\n\nGenerated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    (save_path / "complete_report.md").write_text(header + "\n\n".join(sections), encoding="utf-8")
    
    return folder_name

# --- Custom Print Interceptor for WebSocket ---
import builtins
import threading

# Thread-local storage to map threads to websockets
_thread_locals = threading.local()
_original_print = builtins.print

def websocket_print(*args, **kwargs):
    """Intercepts print calls and sends them to the websocket if attached to the current thread."""
    message = " ".join(str(arg) for arg in args)
    
    # Still print to standard console
    _original_print(*args, **kwargs)
    
    # If this thread has an active websocket, queue the message
    if hasattr(_thread_locals, 'message_queue') and _thread_locals.message_queue is not None:
        try:
            # We use an asyncio queue to safely pass messages from the sync print to the async loop
            _thread_locals.message_queue.put_nowait(message)
        except Exception:
            pass

# Override built-in print globally (safe enough for personal use / single server)
builtins.print = websocket_print

async def stream_logs(websocket: WebSocket, queue: asyncio.Queue):
    """Continuously read from the queue and send to the websocket."""
    try:
        while True:
            message = await queue.get()
            if message is None: # Sentinel value to stop
                break
            await websocket.send_json({"type": "log", "content": message})
    except Exception:
        pass

# --- REST Endpoints for File Manager ---

def get_reports_base_dir() -> Path:
    return Path.home() / ".tradingagents" / "reports"

@app.get("/api/reports")
async def list_reports(x_api_token: str | None = Header(default=None)):
    """List all available report folders."""
    validate_api_token(x_api_token)
    base_dir = get_reports_base_dir()
    if not base_dir.exists():
        return {"reports": []}
    
    # Get all subdirectories, sorted by modification time (newest first)
    dirs = [d for d in base_dir.iterdir() if d.is_dir()]
    dirs.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    
    return {"reports": [d.name for d in dirs]}

@app.get("/api/reports/{report_id}")
async def get_report(report_id: str, x_api_token: str | None = Header(default=None)):
    """Get the complete_report.md content for a specific report."""
    validate_api_token(x_api_token)
    base_dir = get_reports_base_dir()
    report_file = base_dir / report_id / "complete_report.md"
    
    if not report_file.exists() or not report_file.is_file():
        raise HTTPException(status_code=404, detail="Report not found")
        
    content = report_file.read_text(encoding="utf-8")
    return {"content": content}

# --- WebSocket Endpoint ---

class AnalyzeRequest(BaseModel):
    ticker: str
    date: str
    llm_provider: str = "openai"
    deep_think_llm: str = "gpt-5.4-mini"
    quick_think_llm: str = "gpt-5.4-mini"
    max_debate_rounds: int = 1

@app.websocket("/ws/analyze")
async def websocket_analyze(websocket: WebSocket):
    await websocket.accept()
    queue = asyncio.Queue()
    
    try:
        data = await websocket.receive_json()
        try:
            validate_api_token(data.get("api_token"))
        except HTTPException as exc:
            await websocket.send_json({"type": "error", "content": exc.detail})
            await websocket.close(code=1008)
            return

        req = AnalyzeRequest(**data)
        
        await websocket.send_json({"type": "status", "content": f"Initializing engine for {req.ticker}..."})
        
        config = DEFAULT_CONFIG.copy()
        config["llm_provider"] = req.llm_provider
        config["deep_think_llm"] = req.deep_think_llm
        config["quick_think_llm"] = req.quick_think_llm
        config["max_debate_rounds"] = req.max_debate_rounds
        
        stream_task = asyncio.create_task(stream_logs(websocket, queue))
        
        def run_graph():
            _thread_locals.message_queue = queue
            try:
                ta = TradingAgentsGraph(debug=True, config=config)
                return ta.propagate(req.ticker, req.date)
            finally:
                _thread_locals.message_queue = None
                
        await websocket.send_json({"type": "status", "content": "Starting analysis... this may take a few minutes."})
        
        final_state, decision = await asyncio.to_thread(run_graph)
        
        # --- SAVE REPORT TO DISK ---
        report_folder = save_report_to_disk(final_state, req.ticker)
        await queue.put(f"Report automatically saved to server: {report_folder}")
        
        await queue.put(None) 
        await stream_task
        
        if decision:
            decision_dict = decision.model_dump()
            if hasattr(decision, 'action'):
                decision_dict['action'] = decision.action.value
                
            await websocket.send_json({
                "type": "result", 
                "content": decision_dict
            })
        else:
            await websocket.send_json({
                "type": "error", 
                "content": "No decision was returned."
            })
            
    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"Error in websocket: {e}")
        try:
            await websocket.send_json({"type": "error", "content": str(e)})
        except:
            pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
