import streamlit as st
import asyncio
import html
import websockets
import json
import os
import requests
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="TradingAgents",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- API base URL (configurable via .env for when running on VPS) ---
# On VPS, set API_BASE_URL=http://tradingagents-api:8000 (service name in docker)
API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")
WS_BASE_URL = API_BASE_URL.replace("http://", "ws://").replace("https://", "wss://")

# --- Responsive CSS ---
st.markdown("""
<style>
    /* ---- Hide Streamlit default UI clutter ---- */
    #MainMenu { visibility: hidden; }
    header[data-testid="stHeader"] { display: none; }
    [data-testid="collapsedControl"] { display: none; }
    footer { visibility: hidden; }

    /* ---- Global ---- */
    .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
        padding-left: 1rem;
        padding-right: 1rem;
    }

    /* ---- Sidebar ---- */
    [data-testid="stSidebar"] {
        min-width: 180px !important;
        max-width: 220px !important;
    }

    /* ---- Buttons: always full width and big enough to tap on mobile ---- */
    .stButton > button {
        width: 100%;
        min-height: 2.8rem;
        font-size: 1rem;
        border-radius: 8px;
    }

    /* ---- Download button ---- */
    .stDownloadButton > button {
        width: 100%;
        min-height: 2.8rem;
        border-radius: 8px;
    }

    /* ---- Log terminal area ---- */
    .log-box {
        background-color: #0e1117;
        color: #c8f5c8;
        font-family: monospace;
        font-size: 0.78rem;
        padding: 0.8rem;
        border-radius: 8px;
        max-height: 45vh;
        overflow-y: auto;
        white-space: pre-wrap;
        word-break: break-all;
        border: 1px solid #2e2e2e;
    }

    /* ---- Decision card ---- */
    .decision-card {
        border-radius: 12px;
        padding: 1.2rem;
        margin-top: 0.8rem;
        text-align: center;
        font-size: 1.4rem;
        font-weight: bold;
    }
    .decision-buy  { background: #1a3a1a; color: #4cff4c; border: 1px solid #4cff4c; }
    .decision-sell { background: #3a1a1a; color: #ff4c4c; border: 1px solid #ff4c4c; }
    .decision-hold { background: #2a2a2a; color: #aaaaaa; border: 1px solid #555555; }

    /* ---- Report content ---- */
    .report-content {
        max-height: 70vh;
        overflow-y: auto;
        padding: 0.5rem;
    }

    /* ---- Mobile: hide wide labels ---- */
    @media (max-width: 768px) {
        .block-container {
            padding-left: 0.5rem;
            padding-right: 0.5rem;
        }
        h1 { font-size: 1.4rem !important; }
        h2 { font-size: 1.1rem !important; }
        h3 { font-size: 1rem !important; }
        .log-box {
            max-height: 35vh;
            font-size: 0.72rem;
        }
        .decision-card { font-size: 1.1rem; }
    }
</style>
""", unsafe_allow_html=True)

# --- Security ---
CORRECT_PASSWORD = os.environ.get("WEB_PASSWORD", "")
API_AUTH_TOKEN = os.environ.get("API_AUTH_TOKEN") or CORRECT_PASSWORD

if not CORRECT_PASSWORD or CORRECT_PASSWORD in {"admin", "admin123", "password", "changeme"}:
    st.error("Set a strong WEB_PASSWORD environment variable before using the web UI.")
    st.stop()

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    # Centered login on mobile
    col_l, col_center, col_r = st.columns([1, 2, 1])
    with col_center:
        st.markdown("## 🔒 TradingAgents Login")
        pwd = st.text_input("Password", type="password", placeholder="Enter your password")
        if st.button("Login", use_container_width=True):
            if pwd == CORRECT_PASSWORD:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Incorrect password")
    st.stop()

# --- Session state for logs & results across reruns ---
if "logs" not in st.session_state:
    st.session_state.logs = []
if "result" not in st.session_state:
    st.session_state.result = None

# --- WebSocket Client ---
async def connect_and_analyze(payload, log_placeholder, result_placeholder):
    uri = f"{WS_BASE_URL}/ws/analyze"
    logs = []

    try:
        async with websockets.connect(uri, ping_interval=30, ping_timeout=600) as ws:
            await ws.send(json.dumps(payload))

            while True:
                raw = await ws.recv()
                data = json.loads(raw)
                msg_type = data.get("type")
                content = data.get("content")

                if msg_type in ("status", "log"):
                    prefix = "🔵 " if msg_type == "status" else ""
                    logs.append(f"{prefix}{content}")
                    if len(logs) > 100:
                        logs = logs[-100:]
                    # Render as terminal-style box
                    log_html = "<br>".join(html.escape(line) for line in logs[-60:])
                    log_placeholder.markdown(
                        f'<div class="log-box">{log_html}</div>',
                        unsafe_allow_html=True
                    )

                elif msg_type == "result":
                    st.session_state.result = content
                    _render_result(result_placeholder, content)
                    break

                elif msg_type == "error":
                    result_placeholder.error(f"Error: {content}")
                    break

    except Exception as e:
        result_placeholder.error(f"Connection failed: {e}")

def _render_result(container, content):
    action = content.get("action", "UNKNOWN")
    label = {"BUY": "🟢 BUY", "SELL": "🔴 SELL"}.get(action, "⚪ HOLD")
    css_class = {"BUY": "decision-buy", "SELL": "decision-sell"}.get(action, "decision-hold")

    with container:
        st.markdown(
            f'<div class="decision-card {css_class}">{label}</div>',
            unsafe_allow_html=True
        )
        st.markdown("#### Full Decision")
        st.json(content)

# --- Sidebar Navigation ---
with st.sidebar:
    st.markdown("## 📈 TradingAgents")
    st.markdown("---")
    menu = st.radio("", ["🔍 Run Analysis", "📂 File Manager"], label_visibility="collapsed")
    st.markdown("---")
    if st.button("Logout", use_container_width=True):
        st.session_state.authenticated = False
        st.rerun()

# ============================================================
# VIEW: Run Analysis
# ============================================================
if menu == "🔍 Run Analysis":
    st.markdown("### 🔍 Run Analysis")

    tab_config, tab_terminal = st.tabs(["⚙️ Configuration", "💻 Terminal & Result"])

    with tab_config:
        ticker = st.text_input("Ticker Symbol", value="AAPL", placeholder="e.g. NVDA, BTC-USD")
        date = st.date_input("Analysis Date")

        provider = st.selectbox(
            "LLM Provider",
            ["openai", "anthropic", "google", "deepseek", "ollama"],
        )
        deep_think = st.text_input("Deep Think Model", value="gpt-5.4-mini")
        quick_think = st.text_input("Quick Think Model", value="gpt-5.4-mini")
        rounds = st.slider("Debate Rounds", min_value=1, max_value=5, value=1)

        st.markdown("")  # spacer
        start_btn = st.button("🚀 Start Analysis", type="primary", use_container_width=True)

    with tab_terminal:
        log_placeholder = st.empty()
        st.markdown("---")
        result_placeholder = st.empty()

        # Re-render persisted result if user switched tabs and came back
        if st.session_state.result and not start_btn:
            _render_result(result_placeholder, st.session_state.result)

    if start_btn:
        if not ticker:
            st.warning("Please enter a ticker symbol.")
        else:
            # Clear old state
            st.session_state.logs = []
            st.session_state.result = None
            result_placeholder.empty()

            payload = {
                "ticker": ticker.upper(),
                "date": str(date),
                "llm_provider": provider,
                "deep_think_llm": deep_think,
                "quick_think_llm": quick_think,
                "max_debate_rounds": rounds,
                "api_token": API_AUTH_TOKEN,
            }
            # Switch user to terminal tab via info banner
            st.info("Analysis started! Switch to the **Terminal & Result** tab to see live logs.")
            asyncio.run(connect_and_analyze(payload, log_placeholder, result_placeholder))

# ============================================================
# VIEW: File Manager
# ============================================================
elif menu == "📂 File Manager":
    st.markdown("### 📂 Report File Manager")

    # Refresh button
    if st.button("🔄 Refresh List", use_container_width=True):
        st.rerun()

    try:
        response = requests.get(
            f"{API_BASE_URL}/api/reports",
            headers={"X-API-Token": API_AUTH_TOKEN},
            timeout=5,
        )
        reports = response.json().get("reports", []) if response.status_code == 200 else []
    except Exception as e:
        reports = []
        st.error(f"Cannot connect to API: {e}")

    if not reports:
        st.info("No reports found yet. Run an analysis first!")
    else:
        st.markdown(f"**{len(reports)} report(s) found.**")

        selected_report = st.selectbox("Select a report:", reports)

        if selected_report:
            st.markdown("---")

            try:
                res = requests.get(
                    f"{API_BASE_URL}/api/reports/{selected_report}",
                    headers={"X-API-Token": API_AUTH_TOKEN},
                    timeout=10,
                )
                if res.status_code == 200:
                    content = res.json().get("content", "")

                    st.download_button(
                        label="⬇️ Download as Markdown (.md)",
                        data=content,
                        file_name=f"{selected_report}_report.md",
                        mime="text/markdown",
                        use_container_width=True,
                    )

                    st.markdown("---")
                    st.markdown(content)
                else:
                    st.error("Report not found.")
            except Exception as e:
                st.error(f"Error loading report: {e}")
