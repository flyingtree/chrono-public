"""CHRONO | Planetary Journeys: The Market Timing Tool — Public Portfolio.

Zero API key.  yfinance (free) for price + local JSON for trade history.
Auto-refreshes every 60 seconds.  Deployed to Streamlit Community Cloud.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

_PROJECT = Path(__file__).resolve().parent
_REPORTS = _PROJECT / "reports"

# ---- Color palette: Premium Quant Terminal (see chrono-brand skill §2.8) ----
BG      = "#0C0D0E"  # Canvas — deep matte carbon
CARD    = "#141617"  # Surface
BORDER  = "#1F2224"  # 1px hairline
GREEN   = "#4ECAA6"  # Long / positive — muted mint
RED     = "#E06C75"  # Short / negative — muted pink
YELLOW  = "#D4A853"  # Warning / neutral — muted gold
BLUE    = "#6CB6FF"  # Info / links — muted blue
PURPLE  = "#B392F0"  # A-grade pivot — muted purple
LABEL   = "#8A8F93"  # Secondary label — readable on dark bg
SUB     = "#5A5E63"  # Tertiary — readable on dark cards
TEXT    = "#FFFFFF"  # Primary text

# ---- Page config (MUST be first Streamlit call) ----
st.set_page_config(
    page_title="CHRONO | Planetary Journeys: The Market Timing Tool",
    page_icon="🪐",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---- CSS — Premium Quant Terminal (chrono-brand skill §2.8) ----
st.markdown(f"""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

/* ---- Streamlit chrome ---- */
.stApp {{ background: {BG}; }}
header[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stToolbar"] {{ display: none; }}
section[data-testid="stSidebar"] {{ display: none; }}
.stMainBlockContainer {{ padding: 12px 0 0 0; max-width: 1100px; }}
div[data-testid="stVerticalBlock"] > div {{ gap: 8px; }}

/* ---- Typography foundation ---- */
* {{ font-family: 'Inter', 'SF Pro Display', -apple-system, BlinkMacSystemFont, sans-serif; }}
.mono, .mono *, [data-mono] {{ font-family: 'JetBrains Mono', 'Roboto Mono', 'SF Mono', monospace; }}

/* ---- Ticker / header ---- */
.ticker {{ font-size: 10px; color: {LABEL}; letter-spacing: 0.05em; text-transform: uppercase; }}
.price-large {{ font-size: 36px; font-weight: 600; line-height: 1.1; font-family: 'JetBrains Mono', 'Roboto Mono', monospace; }}
.price-change {{ font-size: 13px; font-weight: 500; margin-left: 8px; font-family: 'JetBrains Mono', 'Roboto Mono', monospace; }}

/* ---- Metric cards ---- */
.card-row {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 8px 0; }}
.card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 6px; padding: 10px 14px; min-width: 140px; flex: 1; }}
.card .label {{ font-size: 10px; color: {LABEL}; text-transform: uppercase; letter-spacing: 0.05em; }}
.card .value {{ font-size: 18px; font-weight: 600; margin-top: 2px; font-family: 'JetBrains Mono', 'Roboto Mono', monospace; }}
.card .sub {{ font-size: 10px; color: {SUB}; margin-top: 2px; }}

/* ---- Tables — compact quant style ---- */
.table-wrap {{ overflow-x: auto; }}
table {{ width: 100%; border-collapse: collapse; font-size: 11px; background: {CARD}; border: 1px solid {BORDER}; border-radius: 6px; }}
thead th {{ background: {CARD}; color: {LABEL}; font-weight: 500; font-size: 10px; text-transform: uppercase; letter-spacing: 0.05em; text-align: left; padding: 8px 12px; border-bottom: 1px solid {BORDER}; white-space: nowrap; }}
tbody td {{ padding: 7px 12px; border-bottom: 1px solid {BORDER}; white-space: nowrap; color: {TEXT}; font-size: 11px; }}
tbody tr:hover {{ background: {BG}; }}
tbody td:first-child, thead th:first-child {{ padding-left: 14px; }}

/* ---- Status badge — ghost pill style ---- */
.badge {{ display: inline-block; padding: 1px 8px; border-radius: 4px; font-size: 10px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.03em; }}
.badge-long {{ border: 1px solid {GREEN}; color: {GREEN}; }}
.badge-short {{ border: 1px solid {RED}; color: {RED}; }}
.badge-grade-a {{ border: 1px solid {PURPLE}; color: {PURPLE}; font-size: 10px; padding: 1px 6px; border-radius: 4px; }}

/* ---- Signal badges ---- */
.badge-signal-buy {{ border: 1px solid {GREEN}; color: {GREEN}; font-size: 11px; padding: 3px 10px; border-radius: 4px; text-transform: uppercase; letter-spacing: 0.03em; font-weight: 500; }}
.badge-signal-sell {{ border: 1px solid {RED}; color: {RED}; font-size: 11px; padding: 3px 10px; border-radius: 4px; text-transform: uppercase; letter-spacing: 0.03em; font-weight: 500; }}
.badge-signal-wait {{ border: 1px solid {BORDER}; color: {LABEL}; font-size: 11px; padding: 3px 10px; border-radius: 4px; text-transform: uppercase; letter-spacing: 0.03em; font-weight: 500; }}
.badge-signal-hold {{ border: 1px solid {BLUE}; color: {BLUE}; font-size: 11px; padding: 3px 10px; border-radius: 4px; text-transform: uppercase; letter-spacing: 0.03em; font-weight: 500; }}

/* ---- Section headers — uppercase label style ---- */
.section-title {{ font-size: 11px; font-weight: 500; color: {LABEL}; text-transform: uppercase; letter-spacing: 0.05em; margin: 20px 0 8px; }}

/* ---- CTA — flat ghost style ---- */
.cta-box {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 6px; padding: 20px 24px; margin-top: 24px; text-align: center; }}
.cta-box h3 {{ font-size: 13px; color: {TEXT}; margin: 0 0 6px 0; font-weight: 600; }}
.cta-box p {{ color: {LABEL}; font-size: 11px; margin-bottom: 12px; }}
.cta-btn {{ display: inline-block; border: 1px solid {GREEN}; color: {GREEN}; padding: 7px 18px; border-radius: 4px; font-weight: 500; font-size: 11px; text-decoration: none; text-transform: uppercase; letter-spacing: 0.03em; transition: opacity 0.15s; }}
.cta-btn:hover {{ opacity: 0.8; }}

/* ---- Footer ---- */
.footer {{ font-size: 10px; color: {SUB}; margin-top: 28px; text-align: center; padding-bottom: 16px; }}
.footer a {{ color: {BLUE}; text-decoration: none; }}

/* ---- Utility ---- */
.g {{ color: {GREEN}; }}
.r {{ color: {RED}; }}
.y {{ color: {YELLOW}; }}
</style>""", unsafe_allow_html=True)


# =============================================================================
# Data loading — yfinance 优先 (Streamlit Cloud US-friendly) + Binance 备选
# =============================================================================

def _bars_from_yf(symbol: str, period: str, interval: str) -> pd.DataFrame | None:
    """Fetch OHLCV from yfinance. Returns DataFrame with DatetimeIndex or None."""
    try:
        import yfinance as yf
        tkr = yf.Ticker(symbol)
        df = tkr.history(period=period, interval=interval)
        if df is None or df.empty:
            return None
        df = df[["Open","High","Low","Close","Volume"]].copy()
        return df
    except Exception:
        return None


def _bars_from_ccxt(symbol: str, timeframe: str, limit: int) -> pd.DataFrame | None:
    """Fetch OHLCV from Binance CCXT. Returns DataFrame with DatetimeIndex or None."""
    try:
        import ccxt
        ex = ccxt.binance({'enableRateLimit': True})
        ticker = symbol.replace("-USD", "/USDT:USDT")
        raw = ex.fetch_ohlcv(ticker, timeframe, limit=limit)
        if not raw:
            return None
        df = pd.DataFrame(raw, columns=['timestamp','Open','High','Low','Close','Volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        return df.astype(float)
    except Exception:
        return None


@st.cache_data(ttl=60, show_spinner=False)
def fetch_live_price(symbol: str) -> dict:
    """Live price + 24h change — yfinance first, Binance fallback."""
    # yfinance
    df = _bars_from_yf(symbol, period="2d", interval="1d")
    if df is not None and len(df) >= 2:
        price = float(df["Close"].iloc[-1])
        prev = float(df["Close"].iloc[-2])
        return {"price": round(price, 2), "change_24h_pct": round((price / prev - 1) * 100, 2)}

    # Binance fallback
    df = _bars_from_ccxt(symbol, "4h", limit=2)
    if df is not None and len(df) >= 2:
        price = float(df["Close"].iloc[-1])
        prev = float(df["Close"].iloc[-2])
        return {"price": round(price, 2), "change_24h_pct": round((price / prev - 1) * 100, 2)}

    return {}


@st.cache_data(ttl=300, show_spinner="正在拉取实时数据...")
def fetch_strategy_data(symbol: str):
    """Fetch bars + compute Ichimoku cloud state + signal.

    yfinance 优先 (works from US-based Streamlit Cloud).
    Uses 1h bars resampled to 4H for Ichimoku, 1d bars for exit confirmation.
    Falls back to Binance CCXT if yfinance fails.
    """
    import numpy as np
    from algorithms.ichimoku import _calc_ichimoku

    bars_4h = None
    bars_1d = None

    # ---- Try yfinance first ----
    # 1h bars → resample to 4H (~60 days of hourly needed for 300 4H bars)
    df_1h = _bars_from_yf(symbol, period="60d", interval="1h")
    if df_1h is not None and len(df_1h) >= 50:
        bars_4h = df_1h.resample("4h").agg({
            "Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"
        }).dropna()
        if len(bars_4h) < 52:
            bars_4h = None

    # Daily bars from yfinance
    df_1d = _bars_from_yf(symbol, period="6mo", interval="1d")
    if df_1d is not None and len(df_1d) >= 52:
        bars_1d = df_1d

    # ---- Binance fallback ----
    if bars_4h is None:
        bars_4h = _bars_from_ccxt(symbol, "4h", limit=300)
    if bars_1d is None:
        bars_1d = _bars_from_ccxt(symbol, "1d", limit=120)

    if bars_4h is None or len(bars_4h) < 52:
        return {"error": "无法获取K线数据 — 请稍后刷新重试"}

    close_4h = bars_4h["Close"]
    high_4h = bars_4h["High"]
    low_4h = bars_4h["Low"]
    current_price = float(close_4h.iloc[-1])
    current_idx = len(bars_4h) - 1

    # 4H Ichimoku
    ichi_4h = _calc_ichimoku(bars_4h)
    if ichi_4h is None or len(ichi_4h) < 52:
        return {"error": "insufficient_4h_data"}

    tk = float(ichi_4h["tenkan_sen"].iloc[-1])
    kj = float(ichi_4h["kijun_sen"].iloc[-1])
    sa = float(ichi_4h["senkou_span_a"].iloc[-1])
    sb = float(ichi_4h["senkou_span_b"].iloc[-1])
    cloud_top = max(sa, sb)
    cloud_bottom = min(sa, sb)
    above_cloud = current_price > cloud_top
    below_cloud = current_price < cloud_bottom
    in_cloud = not above_cloud and not below_cloud

    cloud_4h = "above" if above_cloud else ("below" if below_cloud else "in")

    # TK stability (3+ bars)
    tk_stable = (
        tk > kj
        and float(ichi_4h["tenkan_sen"].iloc[-2]) > float(ichi_4h["kijun_sen"].iloc[-2])
        and float(ichi_4h["tenkan_sen"].iloc[-3]) > float(ichi_4h["kijun_sen"].iloc[-3])
    )

    # Chikou
    chikou_bullish = True
    if current_idx >= 26:
        chikou_val = float(close_4h.iloc[current_idx - 26])
        chikou_bullish = current_price > chikou_val

    # Daily Ichimoku (exit confirmation)
    cloud_1d = None
    daily_below = False
    daily_above = False
    if bars_1d is not None and len(bars_1d) >= 52:
        daily_ichi = _calc_ichimoku(bars_1d)
        if daily_ichi is not None and len(daily_ichi) >= 52:
            d_close = float(bars_1d["Close"].iloc[-1])
            d_sa = float(daily_ichi["senkou_span_a"].iloc[-1])
            d_sb = float(daily_ichi["senkou_span_b"].iloc[-1])
            if d_close > max(d_sa, d_sb):
                cloud_1d = "above"
                daily_above = True
            elif d_close < min(d_sa, d_sb):
                cloud_1d = "below"
                daily_below = True
            else:
                cloud_1d = "in"

    # Signal logic
    signal = None
    if below_cloud:
        daily_confirmed = True if bars_1d is None else daily_below
        if daily_confirmed:
            signal = {"direction": "CLOSE", "strength": 1.0, "price": round(current_price, 2),
                      "reason": "cloud_breakdown"}
    elif above_cloud and tk_stable and chikou_bullish:
        signal = {"direction": "LONG", "strength": 0.85, "price": round(current_price, 2),
                  "reason": "cloud_breakout"}
    elif above_cloud and tk_stable:
        signal = {"direction": "LONG", "strength": 0.65, "price": round(current_price, 2),
                  "reason": "trend_continuation"}

    return {
        "signal": signal,
        "cloud_4h": cloud_4h,
        "cloud_1d": cloud_1d,
        "tenkan": round(tk, 2),
        "kijun": round(kj, 2),
        "cloud_top": round(cloud_top, 2),
        "cloud_bottom": round(cloud_bottom, 2),
        "below_cloud": below_cloud,
        "above_cloud": above_cloud,
        "in_cloud": in_cloud,
        "tk_stable": tk_stable,
        "chikou_bullish": chikou_bullish,
        "current_price": current_price,
        "bar_time": str(bars_4h.index[-1]),
    }


@st.cache_data(ttl=3600, show_spinner="正在计算 Gann Pivot 预测...")
def fetch_pivot_forecast(symbol: str):
    """Compute Gann pivot forecast — yfinance daily bars first, Binance fallback."""
    from algorithms.pivot_detection import _local_extrema
    from gann_pivot_scorer import Pivot, scan_future_pivots

    bars = _bars_from_yf(symbol, period="1y", interval="1d")
    if bars is None or len(bars) < 100:
        bars = _bars_from_ccxt(symbol, "1d", limit=365)

    if bars is None or len(bars) < 100:
        return None

    high_vals = bars["High"].tolist()
    low_vals = bars["Low"].tolist()
    high_idx = _local_extrema(high_vals, order=5, mode="high")
    low_idx = _local_extrema(low_vals, order=5, mode="low")

    pivots = []
    for i in high_idx:
        pivots.append(Pivot(date=bars.index[i].date(), price=float(bars["High"].iloc[i]), pivot_type="HIGH"))
    for i in low_idx:
        pivots.append(Pivot(date=bars.index[i].date(), price=float(bars["Low"].iloc[i]), pivot_type="LOW"))

    start_date = bars.index[-1].date()
    zones = scan_future_pivots(
        pivots=pivots, start_date=start_date, days_ahead=365,
        cluster_days=4, max_zone_width=10, grade_a=80, grade_b=55,
    )

    a_grade = []
    b_grade = []
    for z in zones:
        d = {
            "peak_date": str(z.peak_date),
            "date_range": (str(z.date_range[0]), str(z.date_range[1])),
            "grade": z.grade,
            "score": round(z.score, 1),
            "time_score": round(z.time_score, 1),
            "price_zone": (round(z.price_zone[0], 2) if z.price_zone[0] else 0,
                           round(z.price_zone[1], 2) if z.price_zone[1] else 0),
            "convergence_desc": z.convergence_desc or "",
            "triggered": z.triggered or [],
        }
        if z.grade == "A":
            a_grade.append(d)
        elif z.grade == "B":
            b_grade.append(d)

    return {"a_grade": a_grade, "b_grade": b_grade, "pivot_count": len(pivots)}


@st.cache_data(ttl=600, show_spinner=False)
def load_trade_log(symbol: str) -> dict | None:
    """Load trade log JSON (optional — only needed for historical trades)."""
    fname = symbol.split("-")[0].lower() + "_trade_log.json"
    path = _REPORTS / fname
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# =============================================================================
# Load data
# =============================================================================
SYMBOL = "ZEC-USD"
live = fetch_live_price(SYMBOL)
strategy_data = fetch_strategy_data(SYMBOL)
trade_log = load_trade_log(SYMBOL)
pivot_forecast = fetch_pivot_forecast(SYMBOL)

current_price = live.get("price") or strategy_data.get("current_price", 0)
price_change = live.get("change_24h_pct") or 0
page_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
last_update = page_time

# =============================================================================
# Header — ticker + value proposition
# =============================================================================
col_h, col_p = st.columns([2, 1])
with col_h:
    st.markdown(
        '<p class="ticker">🪐 CHRONO · Planetary Journeys: The Market Timing Tool</p>'
       f'<p style="font-size:22px;font-weight:600;color:{TEXT};margin:2px 0 4px;">Zcash 趋势跟踪策略</p>'
       f'<p style="font-size:11px;color:{LABEL};">Markets are not a random walk — they resonate with cosmic cycles.</p>',
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
# Performance cards — 实时市场数据 + 策略信号
# =============================================================================
sig = strategy_data.get("signal")
cloud_4h = strategy_data.get("cloud_4h", "?")
cloud_1d = strategy_data.get("cloud_1d")
tk = strategy_data.get("tenkan", 0)
kj = strategy_data.get("kijun", 0)
cloud_top = strategy_data.get("cloud_top", 0)
cloud_bottom = strategy_data.get("cloud_bottom", 0)
tk_stable = strategy_data.get("tk_stable", False)
chikou_bullish = strategy_data.get("chikou_bullish", False)

cloud_label = {"above": "云上 ☁️", "below": "云下 ☁️", "in": "云中 ☁️"}.get(cloud_4h, cloud_4h)
cloud_1d_label = {"above": "日线云上", "below": "日线云下", "in": "日线云中"}.get(cloud_1d, str(cloud_1d)) if cloud_1d else ""

# Backtest summary from JSON (optional)
bs = trade_log.get("backtest_summary") if trade_log else None

# Build performance cards from live strategy data + optional backtest
tk_status = "金叉 ↑" if tk_stable else ("死叉 ↓" if (tk < kj) else "缠绕 —")
tk_color = GREEN if tk_stable else (RED if (tk < kj) else YELLOW)
ichi_4h_label = {"above": "云上 ☁️", "below": "云下 ☁️", "in": "云中 ☁️"}.get(cloud_4h, cloud_4h)
ichi_4h_color = GREEN if cloud_4h == "above" else (RED if cloud_4h == "below" else YELLOW)
d_cloud_label = cloud_1d_label if cloud_1d_label else "—"

c1, c2, c3, c4, c5, c6 = st.columns(6)
cards_data = [
    ("ZEC 现价", f"${current_price:,.2f}",
     f"24h {price_change:+.2f}% · 4H Bar {strategy_data.get('bar_time','')[:16]}",
     TEXT),
    ("4H 一目均衡", ichi_4h_label,
     f"Tenkan ${tk:,.2f} · Kijun ${kj:,.2f}",
     ichi_4h_color),
    ("TK 交叉", tk_status,
     f"云顶 ${cloud_top:,.2f} · 云底 ${cloud_bottom:,.2f}",
     tk_color),
    ("日线确认", d_cloud_label,
     f"Chikou {'看涨' if chikou_bullish else '看跌'}",
     GREEN if cloud_1d == "above" else (RED if cloud_1d == "below" else YELLOW)),
    ("回测收益", f"{bs['total_return_pct']:+.1f}%" if bs else "—",
     f"夏普 {bs['sharpe']:.2f}" if bs else "运行脚本生成",
     GREEN if (bs and bs.get('total_return_pct', 0) >= 0) else RED),
    ("胜率 / PF", f"{bs['win_rate']:.0f}% · {bs['profit_factor']:.1f}" if bs else "—",
     f"{bs['num_trades']} 笔交易" if bs else "",
     GREEN if (bs and bs.get('win_rate', 0) >= 50) else YELLOW),
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
# Market structure + latest signal
# =============================================================================
col_mkt, col_sig = st.columns([1.5, 1])

with col_mkt:
    st.markdown('<div class="section-title">🏗️ 4H 市场结构</div>', unsafe_allow_html=True)
    # Build Ichimoku component status
    tk_kj_status = "TK 金叉" if tk_stable else ("TK 死叉" if (tk < kj) else "TK 缠绕")
    chikou_status = "Chikou 看涨" if chikou_bullish else "Chikou 看跌"
    cloud_status = {"above": "价格在云上方 → 多头区域", "below": "价格在云下方 → 空头区域", "in": "价格在云中 → 震荡区域"}.get(cloud_4h, "—")

    ichi_rows = f"""
    <tr><td style="color:{LABEL};">Tenkan-sen (转换线)</td><td style="font-family:'JetBrains Mono',monospace;">${tk:,.2f}</td></tr>
    <tr><td style="color:{LABEL};">Kijun-sen (基准线)</td><td style="font-family:'JetBrains Mono',monospace;">${kj:,.2f}</td></tr>
    <tr><td style="color:{LABEL};">Senkou Span A (先行A)</td><td style="font-family:'JetBrains Mono',monospace;">${cloud_top:,.2f}</td></tr>
    <tr><td style="color:{LABEL};">Senkou Span B (先行B)</td><td style="font-family:'JetBrains Mono',monospace;">${cloud_bottom:,.2f}</td></tr>
    <tr><td style="color:{LABEL};">{tk_kj_status}</td><td style="color:{tk_color};">{tk_kj_status}</td></tr>
    <tr><td style="color:{LABEL};">{chikou_status}</td><td style="color:{GREEN if chikou_bullish else RED};">{chikou_status}</td></tr>
    <tr><td style="color:{LABEL};">云层状态</td><td style="color:{ichi_4h_color};">{cloud_status}</td></tr>
    """
    if cloud_1d:
        d_status = {"above": "日线多头", "below": "日线空头", "in": "日线震荡"}.get(cloud_1d, "")
        ichi_rows += f"""
    <tr><td style="color:{LABEL};">日线确认</td><td style="color:{GREEN if cloud_1d=='above' else (RED if cloud_1d=='below' else YELLOW)};">{d_status}</td></tr>
    """
    st.markdown(f"""
    <div class="table-wrap">
    <table>
        <thead><tr><th>指标</th><th>数值</th></tr></thead>
        <tbody>{ichi_rows}</tbody>
    </table>
    </div>
    """, unsafe_allow_html=True)

with col_sig:
    st.markdown('<div class="section-title">🔔 实时策略信号</div>', unsafe_allow_html=True)
    if sig:
        sig_dir = sig["direction"]
        if sig_dir == "LONG":
            badge = "badge-signal-buy"
            txt = "买入做多"
        elif sig_dir == "SHORT" or sig_dir == "CLOSE":
            badge = "badge-signal-sell"
            txt = "平仓/做空"
        else:
            badge = "badge-signal-wait"
            txt = "观望等待"

        st.markdown(f"""
        <div style="background:{CARD};border:1px solid {BORDER};border-radius:8px;padding:16px;">
            <div style="display:flex;align-items:center;gap:12px;">
                <span class="{badge}">{txt}</span>
                <span style="color:{TEXT};font-weight:600;">强度 {sig['strength']:.0%}</span>
            </div>
            <div style="margin-top:10px;font-size:12px;color:{LABEL};">
                依据: {sig.get('reason','—').replace('_',' ').title()}<br>
                触发价: ${sig['price']:,.2f} · 4H Bar: {strategy_data.get('bar_time','')[:16]}
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style="background:{CARD};border:1px solid {BORDER};border-radius:8px;padding:20px;text-align:center;">
            <div style="color:{SUB};font-size:14px;">无活跃信号</div>
            <div style="color:{SUB};font-size:11px;margin-top:4px;">等待云层突破或 TK 金叉确认</div>
        </div>
        """, unsafe_allow_html=True)

# =============================================================================
# Pivot forecast — 表格形式，未来 2 个月，完整数据付费获取
# =============================================================================
st.markdown('<div class="section-title">🗓️ 未来 Gann Pivot 转折日预测（未来2个月）</div>', unsafe_allow_html=True)
pf = pivot_forecast
if pf and pf.get("a_grade"):
    a_zones = pf["a_grade"]
    # Collect all A-grade zones, keep only first 2 months
    all_zones = []
    cutoff = None
    for z in a_zones:
        peak = z.get("peak_date", "")
        if not peak:
            continue
        peak_str = str(peak)
        try:
            if "T" in peak_str:
                dt = datetime.fromisoformat(peak_str.replace("Z", "+00:00"))
            else:
                dt = datetime.strptime(peak_str[:10], "%Y-%m-%d")
        except ValueError:
            continue
        if cutoff is None:
            from dateutil.relativedelta import relativedelta
            cutoff = dt + relativedelta(months=2)
        if cutoff and dt > cutoff:
            continue
        all_zones.append((dt, z))

    all_zones.sort(key=lambda x: x[0])

    if all_zones:
        table_rows = ""
        for dt, z in all_zones:
            peak_date = dt.strftime("%m-%d")
            date_range = str(z.get("date_range", ""))
            score = z.get("score", 0)
            price_zone = z.get("price_zone", "")
            triggers = z.get("convergence_desc", "")
            grade = z.get("grade", "")
            grade_badge = '<span class="badge badge-grade-a">A级</span>' if grade == "A" else f'<span class="badge badge-grade-a" style="border-color:{LABEL};color:{LABEL};">B级</span>'

            table_rows += f"""
            <tr>
                <td style="font-weight:600;">{peak_date}</td>
                <td>{grade_badge}</td>
                <td style="font-size:11px;color:{LABEL};">{date_range}</td>
                <td style="color:{YELLOW};">{score}分</td>
                <td style="color:{BLUE};">{price_zone}</td>
                <td style="font-size:11px;color:{LABEL};">{triggers}</td>
            </tr>"""

        st.markdown(f"""
        <div class="table-wrap">
        <table>
            <thead><tr>
                <th>日期</th><th>级别</th><th>共振窗口</th><th>评分</th><th>价格区间</th><th>触发原因</th>
            </tr></thead>
            <tbody>{table_rows}</tbody>
        </table>
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
        <div style="color:{SUB};font-size:14px;">Pivot 预测计算中...</div>
        <div style="color:{SUB};font-size:11px;margin-top:4px;">如持续显示此信息，请检查 Binance API 连接</div>
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
            exit_cell = '<span style="color:#8A8F93;font-size:10px;">持仓中</span>'
        else:
            exit_cell = t.get("exit_reason") or '<span style="color:#8A8F93;font-size:10px;">—</span>'

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
# Performance chart — Buy & Hold vs CHRONO Strategy (real PnL)
# =============================================================================
pc = trade_log.get("performance_curve") if trade_log else None
if pc and len(pc) >= 2:
    st.markdown('<div class="section-title">📈 实盘回报曲线 · 策略 vs 买入持有</div>', unsafe_allow_html=True)
    chart_data = []
    for pt in pc:
        row = {}
        d = pt.get("date", "")
        if d:
            row["date"] = pd.to_datetime(d)
        bh = pt.get("buy_hold")
        stv = pt.get("strategy")
        if bh is not None:
            row["Buy & Hold"] = bh
        if stv is not None:
            row["CHRONO"] = stv
        if row:
            chart_data.append(row)
    if chart_data:
        df = pd.DataFrame(chart_data).set_index("date")
        df = df.ffill()

        import plotly.graph_objects as go
        fig = go.Figure()
        if "Buy & Hold" in df.columns:
            fig.add_trace(go.Scatter(
                x=df.index, y=df["Buy & Hold"],
                mode="lines", name="Buy & Hold",
                line=dict(color="#61666A", width=1.5),
                hovertemplate="Buy & Hold: %{y:+.1f}%<extra></extra>",
            ))
        if "CHRONO" in df.columns:
            fig.add_trace(go.Scatter(
                x=df.index, y=df["CHRONO"],
                mode="lines", name="CHRONO",
                line=dict(color="#4ECAA6", width=1.5),
                hovertemplate="CHRONO: %{y:+.1f}%<extra></extra>",
            ))
        fig.update_layout(
            height=300,
            margin=dict(l=0, r=0, t=0, b=0),
            paper_bgcolor="#141617",
            plot_bgcolor="#141617",
            font=dict(color="#8A8F93", size=10, family="JetBrains Mono"),
            xaxis=dict(showgrid=False, zeroline=False, color="#5A5E63"),
            yaxis=dict(
                showgrid=True, gridcolor="#1F2224", gridwidth=1,
                zeroline=True, zerolinecolor="#1F2224",
                ticksuffix="%",
                color="#5A5E63",
            ),
            legend=dict(
                orientation="h", yanchor="top", y=1.12, xanchor="left", x=0,
                font=dict(color="#8A8F93", size=10, family="Inter"),
            ),
            hovermode="x unified",
            dragmode=False,
        )
        st.plotly_chart(fig, config={"displayModeBar": False}, use_container_width=True)
        # Compute and display final returns
        if "Buy & Hold" in df.columns and "CHRONO" in df.columns:
            bh_ret = df["Buy & Hold"].iloc[-1]
            st_ret = df["CHRONO"].iloc[-1]
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"""
                <div style="font-size:10px;color:{LABEL};text-transform:uppercase;letter-spacing:0.05em;">Buy & Hold</div>
                <div style="font-size:14px;color:#8A8F93;font-family:'JetBrains Mono',monospace;">{bh_ret:+.1f}%</div>
                """, unsafe_allow_html=True)
            with c2:
                st.markdown(f"""
                <div style="font-size:10px;color:{LABEL};text-transform:uppercase;letter-spacing:0.05em;">CHRONO 策略</div>
                <div style="font-size:14px;color:{GREEN};font-family:'JetBrains Mono',monospace;">{st_ret:+.1f}%</div>
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
# About — CHRONO 背景说明
# =============================================================================
st.markdown(f"""
<div style="background:{CARD}; border:1px solid {BORDER}; border-radius:6px; padding:16px 20px; margin-bottom:12px;">
    <p style="color:{TEXT}; font-size:11px; line-height:1.8; margin:0;">
        We believe financial markets are not a random walk. Market movements are beautifully synchronized and in perfect resonance with cosmic cycles, forming a harmonic fractal across time.<br><br>
        <strong style="color:{TEXT};">CHRONO</strong> is a professional-grade market timing tool designed to help traders decode these geometric reflections. By translating complex cyclical frequencies into precise, actionable timing data, we empower your financial trading and elevate your market strategies. Welcome to our shared journey of discovery.
    </p>
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
