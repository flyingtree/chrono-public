"""CHRONO | Planetary Journeys: The Market Timing Tool — Public Portfolio.

Zero API key.  yfinance (free) for price + local JSON for trade history.
Auto-refreshes every 60 seconds.  Deployed to Streamlit Community Cloud.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

_PROJECT = Path(__file__).resolve().parent
_REPORTS = _PROJECT / "reports"

# ---- Color palette (inline — no dependency on theme.py at deploy time) ----
BG = "#0f1117"
CARD = "#161b22"
BORDER = "#21262d"
GREEN = "#3fb950"
RED = "#f85149"
YELLOW = "#d2991d"
BLUE = "#58a6ff"
PURPLE = "#a371f7"
LABEL = "#8b949e"
SUB = "#484f58"
TEXT = "#e1e4e8"

# ---- Page config (MUST be first Streamlit call) ----
st.set_page_config(
    page_title="CHRONO | Planetary Journeys: The Market Timing Tool",
    page_icon="🪐",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---- CSS ----
st.markdown(f"""<style>
/* override Streamlit defaults */
.stApp {{ background: {BG}; }}
header[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stToolbar"] {{ display: none; }}
section[data-testid="stSidebar"] {{ display: none; }}
.stMainBlockContainer {{ padding-top: 1rem; max-width: 1100px; }}

/* ticker */
.ticker {{ font-size: 11px; color: {LABEL}; letter-spacing: 0.3px; }}
.price-large {{ font-size: 42px; font-weight: 700; line-height: 1.1; }}
.price-change {{ font-size: 16px; font-weight: 500; margin-left: 8px; }}

/* cards */
.card-row {{ display: flex; flex-wrap: wrap; gap: 10px; margin: 16px 0; }}
.card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 8px; padding: 14px 16px; min-width: 140px; flex: 1; }}
.card .label {{ font-size: 10px; color: {LABEL}; text-transform: uppercase; letter-spacing: 0.5px; }}
.card .value {{ font-size: 20px; font-weight: 700; margin-top: 4px; }}
.card .sub {{ font-size: 10px; color: {SUB}; margin-top: 2px; }}

/* tables */
.table-wrap {{ overflow-x: auto; }}
table {{ width: 100%; border-collapse: collapse; font-size: 12px; background: {CARD}; border: 1px solid {BORDER}; border-radius: 8px; }}
thead th {{ background: {CARD}; color: {LABEL}; font-weight: 600; text-align: left; padding: 10px 14px; border-bottom: 2px solid {BORDER}; white-space: nowrap; }}
tbody td {{ padding: 8px 14px; border-bottom: 1px solid {BORDER}; white-space: nowrap; color: {TEXT}; }}
tbody tr:hover {{ background: #1c2128; }}

/* badges */
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 10px; font-weight: 600; }}
.badge-long {{ background: #1b3a2a; color: {GREEN}; }}
.badge-short {{ background: #3a1b1b; color: {RED}; }}
.badge-grade-a {{ background: #2a1b3a; color: {PURPLE}; font-size: 10px; padding: 2px 6px; border-radius: 8px; }}
.badge-signal-buy {{ background: #1b3a2a; color: {GREEN}; font-size: 13px; padding: 4px 12px; border-radius: 6px; }}
.badge-signal-sell {{ background: #3a1b1b; color: {RED}; font-size: 13px; padding: 4px 12px; border-radius: 6px; }}
.badge-signal-wait {{ background: #1c2128; color: {LABEL}; font-size: 13px; padding: 4px 12px; border-radius: 6px; border: 1px solid {BORDER}; }}
.badge-signal-hold {{ background: #1a2f3a; color: {BLUE}; font-size: 13px; padding: 4px 12px; border-radius: 6px; border: 1px solid {BLUE}; }}

/* pivot cards */
.pivot-month {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 10px; padding: 16px; margin-bottom: 12px; }}
.pivot-month h3 {{ font-size: 14px; color: {TEXT}; margin: 0 0 10px 0; }}
.pivot-grid {{ display: flex; flex-wrap: wrap; gap: 8px; }}
.pivot-card {{ background: #0d1117; border: 1px solid {BORDER}; border-radius: 8px; padding: 10px 14px; font-size: 12px; min-width: 160px; flex: 1; }}
.pivot-card .date {{ font-weight: 700; color: {TEXT}; font-size: 14px; }}
.pivot-card .range {{ color: {LABEL}; font-size: 10px; }}
.pivot-card .meta {{ color: {SUB}; font-size: 10px; margin-top: 4px; }}

/* CTA section */
.cta-box {{ background: linear-gradient(135deg, #1a1f35 0%, #161b22 100%); border: 1px solid #30363d; border-radius: 12px; padding: 24px 28px; margin-top: 28px; text-align: center; }}
.cta-box h3 {{ font-size: 17px; color: {TEXT}; margin: 0 0 8px 0; }}
.cta-box p {{ color: {LABEL}; font-size: 12px; margin-bottom: 14px; }}
.cta-btn {{ display: inline-block; background: {GREEN}; color: #000; padding: 10px 24px; border-radius: 8px; font-weight: 700; font-size: 14px; text-decoration: none; }}
.cta-btn:hover {{ opacity: 0.9; }}

/* section headers */
.section-title {{ font-size: 14px; font-weight: 600; color: {LABEL}; text-transform: uppercase; letter-spacing: 0.5px; margin: 24px 0 10px; }}

/* footer */
.footer {{ font-size: 10px; color: {SUB}; margin-top: 32px; text-align: center; padding-bottom: 20px; }}
.footer a {{ color: {BLUE}; text-decoration: none; }}

/* green/red utility text */
.g {{ color: {GREEN}; }}
.r {{ color: {RED}; }}
.y {{ color: {YELLOW}; }}
</style>""", unsafe_allow_html=True)


# =============================================================================
# Data loading
# =============================================================================

@st.cache_data(ttl=300, show_spinner=False)
def load_public_state(symbol: str) -> dict | None:
    """Load public state JSON. Returns None if not found."""
    fname = symbol.split("-")[0].lower() + "_public_state.json"
    path = _REPORTS / fname
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(ttl=300, show_spinner=False)
def load_trade_log(symbol: str) -> dict | None:
    """Load trade log JSON."""
    fname = symbol.split("-")[0].lower() + "_trade_log.json"
    path = _REPORTS / fname
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(ttl=120, show_spinner=False)
def fetch_live_price(symbol: str) -> dict:
    """Fetch live price + 24h change from yfinance."""
    try:
        import yfinance as yf
        tkr = yf.Ticker(symbol)
        hist = tkr.history(period="2d")
        if hist is None or len(hist) < 2:
            return {}
        close = hist["Close"]
        price = float(close.iloc[-1])
        prev = float(close.iloc[-2])
        change_pct = (price / prev - 1) * 100
        return {"price": round(price, 2), "change_24h_pct": round(change_pct, 2)}
    except Exception:
        return {}


# =============================================================================
# Load data
# =============================================================================
SYMBOL = "ZEC-USD"
state = load_public_state(SYMBOL)
trade_log = load_trade_log(SYMBOL)
live = fetch_live_price(SYMBOL)

# Merge live price with stored data
current_price = live.get("price") or (trade_log.get("current_price", 0) if trade_log else 0)
price_change = live.get("change_24h_pct") or 0

last_update = ""
if state:
    last_update = state.get("generated_at", "")
elif trade_log:
    last_update = trade_log.get("generated_at", "")

# =============================================================================
# Header — ticker + value proposition
# =============================================================================
col_h, col_p = st.columns([2, 1])
with col_h:
    st.markdown(
        '<p class="ticker">🪐 CHRONO · Planetary Journeys: The Market Timing Tool</p>'
        '<p style="font-size:28px;font-weight:700;color:#f0f6fc;margin:2px 0 4px;">Zcash 趋势跟踪策略</p>'
        '<p style="font-size:12px;color:#8b949e;">Markets are not a random walk — they resonate with cosmic cycles.</p>',
        unsafe_allow_html=True,
    )

with col_p:
    change_cls = "g" if price_change >= 0 else "r"
    change_sign = "+" if price_change >= 0 else ""
    st.markdown(f"""
    <div style="text-align:right;padding-top:8px;">
        <div class="ticker">ZEC-USD 实时价格</div>
        <div class="price-large">${current_price:,.2f}</div>
        <span class="price-change {change_cls}">{change_sign}{price_change:.2f}%</span>
        <span class="ticker" style="display:block;margin-top:4px;">更新于 {last_update}</span>
    </div>
    """, unsafe_allow_html=True)

st.divider()

# =============================================================================
# Performance cards — 实盘账户核心数据
# =============================================================================
live_summary = state.get("live_summary", {}) if state else {}
pos_data = state.get("position") if state else None

equity = live_summary.get("equity", 0)
cash = live_summary.get("available_cash", 0)
realized_pnl = live_summary.get("total_pnl", 0)
closed_n = live_summary.get("closed_trades", 0)
live_win = live_summary.get("win_rate", 0)

unrealized_usd = (pos_data.get("unrealized_pnl_usd", 0) or 0) if pos_data else 0
unrealized_pct = (pos_data.get("unrealized_pnl_pct", 0) or 0) if pos_data else 0
combined_pnl = realized_pnl + unrealized_usd

c1, c2, c3, c4, c5, c6 = st.columns(6)
cards_data = [
    ("账户权益", f"${equity:,.0f}", f"Binance Testnet · {state.get('mode','')} 模式" if state else "",
     TEXT),
    ("累计盈亏", f"{combined_pnl:+,.0f}",
     f"已实现 {realized_pnl:+,.0f} + 浮盈 {unrealized_usd:+,.0f}",
     GREEN if combined_pnl >= 0 else RED),
    ("当前浮盈", f"{unrealized_usd:+,.0f}",
     f"{unrealized_pct:+.1f}%" if pos_data else "无持仓",
     GREEN if unrealized_usd >= 0 else RED),
    ("已实现盈亏", f"{realized_pnl:+,.0f}",
     f"已平仓 {closed_n} 笔 · 胜率 {live_win:.0f}%",
     GREEN if realized_pnl >= 0 else RED),
    ("可用资金", f"${cash:,.0f}",
     f"持仓占用 ${equity - cash:,.0f}",
     BLUE),
    ("杠杆倍数", f"{state.get('leverage', 1):.1f}x" if state else "1.0x",
     f"ZEC 现价 ${current_price:,.0f}",
     TEXT),
]
for ci, (label, value, sub, cls) in enumerate(cards_data):
    with [c1, c2, c3, c4, c5, c6][ci]:
        st.markdown(f"""
        <div style="background:{CARD};border:1px solid {BORDER};border-radius:8px;padding:12px 14px;">
            <div style="font-size:10px;color:{LABEL};text-transform:uppercase;letter-spacing:0.5px;">{label}</div>
            <div style="font-size:20px;font-weight:700;margin-top:4px;color:{cls};">{value}</div>
            <div style="font-size:10px;color:{SUB};margin-top:2px;">{sub}</div>
        </div>
        """, unsafe_allow_html=True)

# =============================================================================
# Current position + latest signal
# =============================================================================
pos = state.get("position") if state else None
col_pos, col_sig = st.columns(2)

with col_pos:
    st.markdown('<div class="section-title">📌 当前持仓</div>', unsafe_allow_html=True)
    if pos and pos.get("direction"):
        upnl_usd = pos.get("unrealized_pnl_usd", 0) or 0
        upnl_pct = pos.get("unrealized_pnl_pct", 0) or 0
        pnl_color = GREEN if upnl_usd >= 0 else RED
        pnl_sign = "+" if upnl_usd >= 0 else ""
        dir_badge = "badge-long" if pos["direction"] == "LONG" else "badge-short"
        pos_row = f"""
        <tr>
            <td>{pos.get("symbol", SYMBOL)}</td>
            <td><span class="badge {dir_badge}">{pos["direction"]}</span></td>
            <td>{pos.get("quantity", 0)}</td>
            <td>${pos["entry_price"]:,.2f}</td>
            <td>${pos["current_price"]:,.2f}</td>
            <td style="font-size:10px;">{pos.get("entry_reason", "—")}</td>
            <td style="color:{pnl_color};font-weight:600;">{pnl_sign}${abs(upnl_usd):,.2f}</td>
            <td style="color:{pnl_color};">{pnl_sign}{upnl_pct:.2f}%</td>
        </tr>"""
        st.markdown(f"""
        <div class="table-wrap">
        <table>
            <thead><tr>
                <th>品种</th><th>方向</th><th>数量</th><th>均价</th><th>现价</th><th>入场依据</th><th>浮盈 $</th><th>浮盈 %</th>
            </tr></thead>
            <tbody>{pos_row}</tbody>
        </table>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style="background:{CARD};border:1px solid {BORDER};border-radius:8px;padding:20px;text-align:center;">
            <div style="color:{SUB};font-size:14px;">暂无持仓</div>
            <div style="color:{SUB};font-size:11px;margin-top:4px;">等待下一个 Gann Pivot 信号</div>
        </div>
        """, unsafe_allow_html=True)

with col_sig:
    st.markdown('<div class="section-title">🔔 最新策略信号</div>', unsafe_allow_html=True)
    sig = state.get("latest_signal") if state else None
    if sig:
        sig_dir = sig["direction"]
        has_pos = pos and pos.get("direction")
        pos_dir = pos.get("direction") if has_pos else None

        if has_pos and sig_dir == pos_dir:
            badge = "badge-signal-hold"
            txt = "继续持有"
            action_note = f"已于 {pos.get('entry_time','')[:10] if pos.get('entry_time') else '—'} 入场，与信号方向一致"
        elif sig_dir == "LONG":
            badge = "badge-signal-buy"
            txt = "买入做多"
            action_note = ""
        elif sig_dir == "SHORT":
            badge = "badge-signal-sell"
            txt = "卖出做空"
            action_note = ""
        else:
            badge = "badge-signal-wait"
            txt = "观望等待"
            action_note = ""
        hold_note = ""
        if action_note:
            hold_note = f'<div style="margin-top:6px;font-size:11px;color:{BLUE};">{action_note}</div>'
        st.markdown(f"""
        <div style="background:{CARD};border:1px solid {BORDER};border-radius:8px;padding:16px;">
            <div style="display:flex;align-items:center;gap:12px;">
                <span class="{badge}">{txt}</span>
                <span style="color:{TEXT};font-weight:600;">强度 {sig['strength']:.0%}</span>
            </div>
            <div style="margin-top:10px;font-size:12px;color:{LABEL};">
                依据: {sig.get('reason','—').replace('_',' ').title()}<br>
                触发价: ${sig['price']:,.2f} · {sig.get('timestamp','')[:10]}
            </div>
            {hold_note}
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style="background:{CARD};border:1px solid {BORDER};border-radius:8px;padding:20px;text-align:center;">
            <div style="color:{SUB};font-size:14px;">无活跃信号</div>
            <div style="color:{SUB};font-size:11px;margin-top:4px;">等待市场条件触发</div>
        </div>
        """, unsafe_allow_html=True)

# =============================================================================
# About — CHRONO mission
# =============================================================================
st.markdown(f"""
<div style="background:linear-gradient(135deg, #1a1f35 0%, #161b22 100%); border:1px solid #30363d; border-radius:12px; padding:20px 24px; margin-bottom:20px;">
    <p style="color:{TEXT}; font-size:13px; line-height:1.8; margin:0;">
        We believe financial markets are not a random walk. Market movements are beautifully synchronized and in perfect resonance with cosmic cycles, forming a harmonic fractal across time.<br><br>
        <strong style="color:#f0f6fc;">CHRONO</strong> is a professional-grade market timing tool designed to help traders decode these geometric reflections. By translating complex cyclical frequencies into precise, actionable timing data, we empower your financial trading and elevate your market strategies. Welcome to our shared journey of discovery.
    </p>
</div>
""", unsafe_allow_html=True)

# =============================================================================
# Pivot forecast — 公开仅展示未来 2 个月，完整数据付费获取
# =============================================================================
st.markdown('<div class="section-title">🗓️ 未来 Gann Pivot 转折日预测（未来2个月）</div>', unsafe_allow_html=True)
pf = state.get("pivot_forecast") if state else None
if pf and pf.get("a_grade"):
    a_zones = pf["a_grade"]
    # Group by month
    months: dict[str, list] = {}
    for z in a_zones:
        peak = z.get("peak_date", "")
        if peak:
            peak_str = str(peak)
            try:
                if "T" in peak_str:
                    dt = datetime.fromisoformat(peak_str.replace("Z", "+00:00"))
                else:
                    dt = datetime.strptime(peak_str[:10], "%Y-%m-%d")
                month_key = dt.strftime("%Y年%m月")
            except ValueError:
                month_key = peak_str[:7]
            months.setdefault(month_key, []).append(z)

    sorted_months = sorted(months.keys())
    for mk in sorted_months[:2]:
        zones = months[mk]
        cards_html = ""
        for z in zones[:8]:
            peak_date = str(z.get("peak_date", ""))[:10]
            date_range = str(z.get("date_range", ""))
            score = z.get("score", 0)
            time_score = z.get("time_score", 0)
            price_zone = z.get("price_zone", "")
            triggers = z.get("convergence_desc", "")
            grade = z.get("grade", "")

            grade_badge = ""
            if grade == "A":
                grade_badge = '<span class="badge badge-grade-a">A级</span>'
            elif grade == "B":
                grade_badge = '<span class="badge badge-grade-a" style="background:#1c2128;">B级</span>'

            cards_html += f"""
            <div class="pivot-card">
                <div class="date">{peak_date} {grade_badge}</div>
                <div class="range">📅 {date_range}</div>
                <div class="meta">⭐ {score}分 · ⏱ {time_score}分 · 💰 {price_zone}</div>
                <div class="meta" style="color:{BLUE};">{triggers}</div>
            </div>
            """

        st.markdown(f"""
        <div class="pivot-month">
            <h3>📅 {mk}</h3>
            <div class="pivot-grid">{cards_html}</div>
        </div>
        """, unsafe_allow_html=True)

    if pf.get("b_grade"):
        with st.expander(f"B 级转折窗口（{len(pf['b_grade'])} 个）", expanded=False):
            b_items = ""
            for z in pf["b_grade"]:
                b_items += f'<span style="color:{LABEL};font-size:11px;">{str(z.get("peak_date",""))[:10]} ({z.get("score",0)}分)</span> · '
            st.markdown(b_items.rstrip(" · "), unsafe_allow_html=True)

    st.markdown(f"""
    <div style="background:{CARD};border:1px dashed {BORDER};border-radius:8px;padding:14px;margin-top:12px;text-align:center;">
        <span style="color:{LABEL};font-size:12px;">🔒 完整 12 个月 Pivot 预测 & 多资产分析 — </span>
        <a href="https://t.me/yourchannel" target="_blank" style="color:{BLUE};font-size:12px;font-weight:600;text-decoration:none;">加入付费频道解锁 →</a>
    </div>
    """, unsafe_allow_html=True)

else:
    st.markdown(f"""
    <div style="background:{CARD};border:1px solid {BORDER};border-radius:8px;padding:20px;text-align:center;">
        <div style="color:{SUB};font-size:14px;">Pivot 预测数据暂未生成</div>
        <div style="color:{SUB};font-size:11px;margin-top:4px;">运行 scripts/update_trade_data.py 以更新</div>
    </div>
    """, unsafe_allow_html=True)

# =============================================================================
# Trade history table
# =============================================================================
st.markdown('<div class="section-title">📋 历史交易明细</div>', unsafe_allow_html=True)

if trade_log and trade_log.get("live_trades"):
    rows = ""
    for t in trade_log["live_trades"]:
        pnl = t.get("pnl") or 0
        pnl_cls = "g" if pnl >= 0 else "r"
        pnl_sign = "+" if pnl >= 0 else ""
        dir_badge = "badge-long" if t.get("direction") == "LONG" else "badge-short"
        entry_time = (t.get("entry_time") or "—")
        if entry_time != "—" and len(entry_time) >= 16:
            entry_time = entry_time[5:16].replace("T", " ")  # MM-DD HH:MM
        exit_price_str = f"${t['exit_price']:,.2f}" if t.get("exit_price") else "—"
        is_open = not t.get("exit_price")
        if is_open:
            exit_cell = '<span style="color:#8b949e;font-size:10px;">持仓中</span>'
        else:
            exit_cell = t.get("exit_reason") or '<span style="color:#8b949e;font-size:10px;">—</span>'

        rows += f"""
        <tr>
            <td>{entry_time}</td>
            <td><span class="badge {dir_badge}">{t.get('direction','—')}</span></td>
            <td>${t.get('entry_price',0):,.2f}</td>
            <td>{exit_price_str}</td>
            <td style="font-size:10px;">{t.get('entry_reason','—')}</td>
            <td style="font-size:10px;">{exit_cell}</td>
            <td class="{pnl_cls}" style="font-weight:600;">{pnl_sign}${abs(pnl):,.0f}</td>
            <td class="{pnl_cls}">{pnl_sign}{t.get('pnl_pct',0)}%</td>
        </tr>"""

    st.markdown(f"""
    <div class="table-wrap">
    <table>
        <thead><tr>
            <th>时间</th><th>方向</th><th>入场价</th><th>离场价</th><th>入场依据</th><th>离场原因</th><th>PnL $</th><th>PnL %</th>
        </tr></thead>
        <tbody>{rows}</tbody>
    </table>
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown(f"""
    <div style="background:{CARD};border:1px solid {BORDER};border-radius:8px;padding:20px;text-align:center;">
        <div style="color:{SUB};font-size:14px;">暂无交易记录</div>
    </div>
    """, unsafe_allow_html=True)

# =============================================================================
# Equity mini chart — simple text summary if no plotly
# =============================================================================
if trade_log and trade_log.get("equity_curve"):
    eq = trade_log["equity_curve"]
    if len(eq) >= 2:
        start_eq = eq[0]["equity"]
        end_eq = eq[-1]["equity"]
        st.markdown(f"""
        <div style="background:{CARD};border:1px solid {BORDER};border-radius:8px;padding:16px;margin-top:16px;">
            <div style="font-size:10px;color:{LABEL};text-transform:uppercase;letter-spacing:0.5px;">权益曲线</div>
            <div style="font-size:14px;color:{TEXT};margin-top:4px;">
                ${start_eq:,.0f} → ${end_eq:,.0f}
                <span class="{'g' if end_eq>=start_eq else 'r'}" style="font-weight:600;margin-left:8px;">
                    {'+' if end_eq>=start_eq else ''}{(end_eq/start_eq - 1) * 100:.1f}%
                </span>
            </div>
            <div style="font-size:10px;color:{SUB};margin-top:2px;">
                {eq[0]['date']} → {eq[-1]['date']} · {len(eq)} 个交易日
            </div>
        </div>
        """, unsafe_allow_html=True)

# =============================================================================
# Backtest — 策略模型历史回测（参考说明，非实盘）
# =============================================================================
if trade_log and trade_log.get("backtest_summary"):
    bs = trade_log["backtest_summary"]
    with st.expander("📊 策略模型回测说明（历史模拟，非实盘绩效）", expanded=False):
        st.markdown(f"""
        <div style="font-size:12px;color:{LABEL};line-height:1.8;">
            <p>以下为 <strong>zec_trend</strong> 策略在历史数据上的模拟回测结果，仅用于说明策略逻辑的有效性，<strong>不代表实盘交易绩效</strong>。</p>
            <table style="width:100%;font-size:11px;">
                <tr><td>回测期间</td><td>{bs.get('period_start','')} → {bs.get('period_end','')}</td></tr>
                <tr><td>初始资金</td><td>${bs.get('initial_capital',0):,.0f}</td></tr>
                <tr><td>最终权益</td><td>${bs.get('final_equity',0):,.0f}</td></tr>
                <tr><td>总收益率</td><td>{bs.get('total_return_pct',0):+.1f}%</td></tr>
                <tr><td>买入持有</td><td>{bs.get('buy_hold_return_pct',0):+.1f}%</td></tr>
                <tr><td>超额收益</td><td>{bs.get('excess_return_pct',0):+.1f}%</td></tr>
                <tr><td>夏普比率</td><td>{bs.get('sharpe',0):.2f}</td></tr>
                <tr><td>最大回撤</td><td>{bs.get('max_drawdown_pct',0):.1f}%</td></tr>
                <tr><td>交易笔数</td><td>{bs.get('num_trades',0)} 笔 · 胜率 {bs.get('win_rate',0):.0f}% · PF {bs.get('profit_factor',0):.1f}</td></tr>
            </table>
        </div>
        """, unsafe_allow_html=True)

# =============================================================================
# CTA — call to action
# =============================================================================
st.markdown("""
<div class="cta-box">
    <h3>🚀 获取实时信号 + 完整交易指南</h3>
    <p>加入付费频道，第一时间收到 ZEC 买卖信号推送 · 每月 Gann 周期分析报告 · 教育文章</p>
    <div style="display:flex;gap:12px;justify-content:center;flex-wrap:wrap;">
        <a href="https://t.me/yourchannel" target="_blank" class="cta-btn" style="background:#58a6ff;">📱 CHRONO | Cycle Trading</a>
        <a href="mailto:your@email.com" target="_blank" class="cta-btn">📧 咨询订阅</a>
    </div>
    <div style="font-size:10px;color:#484f58;margin-top:12px;">
        公开页面数据延迟 60 分钟 · 付费用户实时推送
    </div>
</div>
""", unsafe_allow_html=True)

# =============================================================================
# Footer
# =============================================================================
st.markdown(f"""
<div class="footer">
    © 2026 CHRONO | Planetary Journeys: The Market Timing Tool<br>
    本页面仅展示策略绩效，不构成投资建议 · 加密货币交易风险极高<br>
    页面每 60 秒自动刷新 · 最近数据更新: {last_update}
</div>
""", unsafe_allow_html=True)

# =============================================================================
# Auto-refresh — JavaScript approach (reliable cross-platform)
# =============================================================================
st.html("""
<script>
setTimeout(function() { window.location.reload(); }, 60000);
</script>
""")
