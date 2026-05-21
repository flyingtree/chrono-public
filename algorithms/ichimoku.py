"""algorithms/ichimoku.py  —  Ichimoku 云图计算与波形分析"""

import numpy as np
import pandas as pd
from datetime import date, timedelta
from algorithms.pivot_detection import _find_swing_pivots, _detect_n_wave, _detect_v_wave, _detect_i_wave
from shared.config import _ICHIMOKU_CYCLES, _ICHIMOKU_CYCLES_WEEKLY
from shared.utils import _to_date

def _calc_ichimoku(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate Ichimoku Cloud components (Tenkan, Kijun, Senkou A/B, Chikou)."""
    df = df.copy()
    df['tenkan_sen']    = (df['High'].rolling(9).max()  + df['Low'].rolling(9).min()) / 2
    df['kijun_sen']     = (df['High'].rolling(26).max() + df['Low'].rolling(26).min()) / 2
    # Senkou Spans: raw values (no shift), plotted via senkou_date
    df['senkou_span_a'] = (df['tenkan_sen'] + df['kijun_sen']) / 2
    df['senkou_span_b'] = (df['High'].rolling(52).max() + df['Low'].rolling(52).min()) / 2
    df['chikou_span']   = df['Close'].shift(-26)
    # Senkou forward offset: 26 periods based on avg bar interval
    # (日线≈36d, 周线≈182d, 4H≈104h — 自动适应任何 timeframe)
    bar_interval = (df.index[-1] - df.index[0]) / max(len(df) - 1, 1)
    df['senkou_date'] = df.index + bar_interval * 26
    return df

def _ichimoku_wave_price_analysis(df, ichi, manual_pivots=None, order=5):
    """
    Ichimoku Wave Theory (波動論) + Price Theory (価格論).

    Detects wave patterns using progressive cascade:
      1) N wave  (4-point, highest priority) → V/N/E
      2) V wave  (3-point)                    → V/N/E
      3) I wave  (2-point)                    → V/N/E (E=N, no retracement)
      4) Fallback to period-based extremes

    Each level enforces LuxAlgo-style geometric constraints and
    requires minimum 9 K-lines between first and last pivot.

    Computes 4 price targets:
        V-target = 2N − E
        N-target = E + (N − V)   (uptrend) / E − (V − N) (downtrend)
        E-target = 2N − V
        NT-target = 2E − V

    Also computes independent period-based levels (52-bar).

    manual_pivots: optional dict with keys 'v', 'n', 'e' (prices) and
                   optionally 'v_date', 'n_date', 'e_date' (date objects).
                   If provided, skips automatic pivot detection.

    Returns dict or None.
    """
    if len(df) < 52:
        return None
    kijun_series = ichi['kijun_sen'].dropna()
    if kijun_series.empty:
        return None

    current_price = float(df['Close'].iloc[-1])
    last_kijun = float(kijun_series.iloc[-1])
    current_price = float(df['Close'].iloc[-1])
    last_kijun = float(kijun_series.iloc[-1])

    # ── 多因子趋势判定（Kijun + Cloud + Chikou + Slope）──
    uptrend = current_price > last_kijun
    # Cloud position: price above Senkou A/B = confirmed uptrend
    sa = ichi.get('senkou_span_a', pd.Series(dtype=float)).dropna()
    sb = ichi.get('senkou_span_b', pd.Series(dtype=float)).dropna()
    if not sa.empty and not sb.empty:
        ct = max(float(sa.iloc[-1]), float(sb.iloc[-1]))
        cb = min(float(sa.iloc[-1]), float(sb.iloc[-1]))
        if current_price > ct:
            uptrend = True
        elif current_price < cb:
            uptrend = False
    # Chikou confirmation (26-bar lag)
    if 'chikou_span' in ichi.columns and len(df) >= 26:
        ck = ichi['chikou_span'].dropna()
        if len(ck) > 0:
            ck_last = float(ck.iloc[-1])
            p26 = float(df['Close'].iloc[-26])
            if ck_last > p26 and not uptrend:
                uptrend = True
            elif ck_last < p26 and uptrend:
                uptrend = False
    # Kijun slope
    if len(kijun_series) >= 5:
        ks = kijun_series.iloc[-1] - kijun_series.iloc[-5]
        if ks > 0 and not uptrend:
            uptrend = True
        elif ks < 0 and uptrend:
            uptrend = False

    # ── Manual pivot override ──
    if manual_pivots:
        v_price = manual_pivots.get('v', 0.0)
        n_price = manual_pivots.get('n', 0.0)
        e_price = manual_pivots.get('e', 0.0)
        v_date_d = manual_pivots.get('v_date', df.index[-1].date())
        n_date_d = manual_pivots.get('n_date', df.index[-1].date())
        e_date_d = manual_pivots.get('e_date', df.index[-1].date())
        # Determine trend from V/N/E pattern (not from Kijun)
        if n_price < v_price and n_price < e_price:
            uptrend = False   # H→L→H (downtrend N wave)
            v_type, n_type, e_type = 'H', 'L', 'H'
        else:
            uptrend = True    # L→H→L (uptrend N wave)
            v_type, n_type, e_type = 'L', 'H', 'L'
        pivots_manual = True
        detected_type = 'manual'
    else:
        # Find alternating swing pivots (now returns 4-tuple)
        p_dates, p_prices, p_types, p_indices = _find_swing_pivots(df, order=order)

        # Cascade detection: N → V → 3-point auto → I → fallback
        n_result = None
        v_result = None
        i_result = None

        if len(p_dates) >= 4:
            n_result = _detect_n_wave(p_dates, p_prices, p_types, p_indices)
        if len(p_dates) >= 3 and n_result is None:
            v_result = _detect_v_wave(p_dates, p_prices, p_types, p_indices)
        if len(p_dates) >= 2 and n_result is None and v_result is None:
            i_result = _detect_i_wave(p_dates, p_prices, p_types, p_indices)

        if n_result is not None:
            v_date_d, n_date_d, e_date_d, v_price, n_price, e_price, v_type, n_type, e_type, uptrend = n_result
            pivots_manual = False
            detected_type = 'N'
        elif v_result is not None:
            v_date_d, n_date_d, e_date_d, v_price, n_price, e_price, v_type, n_type, e_type, uptrend = v_result
            pivots_manual = False
            detected_type = 'V'
        elif len(p_dates) >= 3:
            # 3-point auto: V wave geometry didn't pass but we still
            # have 3 alternating pivots — extract V/N/E directly for
            # Price Theory (L→H→L or H→L→H).
            v_date, v_price, v_type = p_dates[-3], p_prices[-3], p_types[-3]
            n_date, n_price, n_type = p_dates[-2], p_prices[-2], p_types[-2]
            e_date, e_price, e_type = p_dates[-1], p_prices[-1], p_types[-1]
            if v_type == 'L' and n_type == 'H' and e_type == 'L':
                uptrend = True
            elif v_type == 'H' and n_type == 'L' and e_type == 'H':
                uptrend = False
            else:
                return _fallback_levels(df, current_price, last_kijun)
            v_date_d = _to_date(v_date)
            n_date_d = _to_date(n_date)
            e_date_d = _to_date(e_date)
            pivots_manual = False
            detected_type = 'auto'
        elif i_result is not None:
            v_date_d, n_date_d, e_date_d, v_price, n_price, e_price, v_type, n_type, e_type, uptrend = i_result
            pivots_manual = False
            detected_type = 'I'
        else:
            return _fallback_levels(df, current_price, last_kijun)

    # ── Compute price targets ──
    if uptrend:
        amp = n_price - v_price
        v_target = round(2 * n_price - e_price, 2)          # V = 2N - E
        n_target = round(e_price + (n_price - v_price), 2)  # N = E + (N - V)
        e_target = round(2 * n_price - v_price, 2)          # E = 2N - V
        nt_target = round(2 * e_price - v_price, 2)         # NT = 2E - V
        # Extended targets (LuxAlgo 2E/3E)
        e2_target = round(n_price + 2 * (n_price - v_price), 2)
        e3_target = round(n_price + 3 * (n_price - v_price), 2)
    else:
        amp = v_price - n_price
        v_target = round(2 * n_price - e_price, 2)          # V = 2N - E
        n_target = round(e_price - (v_price - n_price), 2)  # N = E - (V - N)
        e_target = round(n_price - (v_price - n_price), 2)  # E = N - (V - N)
        nt_target = round(e_price - (v_price - e_price), 2) # NT = E - (V - E)
        # Extended targets (LuxAlgo 2E/3E)
        e2_target = round(n_price - 2 * (v_price - n_price), 2)
        e3_target = round(n_price - 3 * (v_price - n_price), 2)

    days_vn = (n_date_d - v_date_d).days
    days_ne = abs((e_date_d - n_date_d).days)

    # Period-based extremes (52-bar)
    e_period = round(float(df['Low'].tail(52).min()), 2)
    n_period = round(float(df['High'].tail(52).max()), 2)
    v_kijun = round(last_kijun, 2)
    vp = round(2 * n_period - e_period, 2)
    np_t = round(e_period + (n_period - v_kijun), 2) if uptrend else round(e_period - (v_kijun - n_period), 2)
    ep_t = round(2 * n_period - v_kijun, 2) if uptrend else round(n_period - (v_kijun - n_period), 2)
    ntp = round(2 * e_period - v_kijun, 2) if uptrend else round(e_period - (v_kijun - e_period), 2)

    return {
        'trend': '上行' if uptrend else '下行',
        'uptrend': uptrend,
        'v': (v_date_d, v_price),
        'n': (n_date_d, n_price),
        'e': (e_date_d, e_price),
        'wave_type': detected_type,
        'levels': {
            'V': round(v_price, 2), 'N': round(n_price, 2), 'E': round(e_price, 2),
            'NT': v_target, 'n_target': n_target, 'e_target': e_target, 'nt_target': nt_target,
            '2E': e2_target, '3E': e3_target,
        },
        'levels_period': {
            'V': v_kijun, 'N': n_period, 'E': e_period,
            'NT': vp, 'n_target': np_t, 'e_target': ep_t, 'nt_target': ntp,
        },
        'amplitude': round(amp, 2),
        'days_vn': days_vn,
        'days_ne': days_ne,
        'kijun': last_kijun,
        'current_price': current_price,
        'manual_pivots': pivots_manual,
    }

def _fallback_levels(df, current_price, last_kijun):
    """Fallback: compute period-based levels only (no wave structure detected)."""
    e_period = round(float(df['Low'].tail(52).min()), 2)
    n_period = round(float(df['High'].tail(52).max()), 2)
    v_kijun = round(last_kijun, 2)
    upt = current_price > last_kijun
    vp = round(2 * n_period - e_period, 2)
    np_t = round(e_period + (n_period - v_kijun), 2) if upt else round(e_period - (v_kijun - n_period), 2)
    ep_t = round(2 * n_period - v_kijun, 2) if upt else round(n_period - (v_kijun - n_period), 2)
    ntp = round(2 * e_period - v_kijun, 2) if upt else round(e_period - (v_kijun - e_period), 2)
    return {
        'trend': '—',
        'uptrend': upt,
        'v': (df.index[-1], current_price),
        'n': (df.index[-1], current_price),
        'e': (df.index[-1], current_price),
        'wave_type': 'fallback',
        'levels': {
            'V': v_kijun, 'N': n_period, 'E': e_period,
            'NT': vp, 'n_target': np_t, 'e_target': ep_t, 'nt_target': ntp,
        },
        'levels_period': {
            'V': v_kijun, 'N': n_period, 'E': e_period,
            'NT': vp, 'n_target': np_t, 'e_target': ep_t, 'nt_target': ntp,
        },
        'amplitude': round(n_period - e_period, 2),
        'days_vn': 0, 'days_ne': 0,
        'kijun': last_kijun,
        'current_price': current_price,
        'manual_pivots': False,
    }

def _ichimoku_time_projections(wave, analysis_date, weekly=False):
    """
    Ichimoku Time Theory (時間論).

    返回 (label, date, cluster) 列表，按日期排序。
    包含三种投影模型：
      1) Kihon Suchi（基本数値）投影 —— 9/17/26/33/42…
      2) Taito Suchi（対等数値）投影 —— 将 V→E 周期长度 N 倍投影
      3) Time Parity（时间等距）投影 —— V→N、N→E 时间间隔从 E 投射

    cluster 表示该日期被多少种不同投影覆盖（≥2 为时间簇，信号更强）。
    """
    if wave is None:
        return []
    ad = analysis_date or date.today()
    # 记录每种投影的 (label, date) 用于去重和聚类
    raw: list[tuple[str, date]] = []
    e_date = wave['e'][0]
    v_date = wave['v'][0]
    n_date = wave['n'][0]
    days_vn = wave['days_vn'] or 0
    days_ne = wave['days_ne'] or 0

    # 1) Kihon Suchi from E, V, N (日线用完整序列，周线用精简序列)
    _cycles = _ICHIMOKU_CYCLES_WEEKLY if weekly else _ICHIMOKU_CYCLES
    for label, origin in [('E', e_date), ('V', v_date), ('N', n_date)]:
        for n in _cycles:
            d = origin + timedelta(days=n)
            if d >= ad:
                raw.append((f"{label}+{n}d", d))

    # 1b) Taito Suchi: 将 V→E 完整周期长度 N 依次乘 1~9 倍投影到未来
    total_ve = days_vn + days_ne
    if total_ve > 0:
        for mult in range(1, 10):
            d = e_date + timedelta(days=total_ve * mult)
            if d >= ad:
                raw.append((f"VE×{mult}({total_ve*mult}d)", d))

    # 2) Time Parity: V→N and N→E intervals projected from E
    if days_vn > 0:
        d1 = e_date + timedelta(days=days_vn)
        if d1 >= ad:
            raw.append((f"VN相等({days_vn}d)", d1))
    if days_ne > 0:
        d2 = e_date + timedelta(days=days_ne)
        if d2 >= ad:
            raw.append((f"NE相等({days_ne}d)", d2))
    # 综合等距: (V→N)+(N→E) 从 E 投射
    if days_vn > 0 and days_ne > 0:
        d3 = e_date + timedelta(days=days_vn + days_ne)
        if d3 >= ad:
            raw.append((f"VN+NE({days_vn+days_ne}d)", d3))

    # 3) 聚类 + 加权：按波浪类型权重调节 cluster 信号
    wave_weight = {'N': 1.5, 'V': 1.2, 'I': 1.0, 'auto': 0.8, 'fallback': 0.5}.get(
        wave.get('wave_type', 'fallback'), 1.0)
    from collections import Counter
    date_counts: Counter = Counter(d for _, d in raw)
    seen_dates: set[date] = set()
    rows: list[tuple[str, date, int]] = []
    for label, d in raw:
        if d not in seen_dates:
            seen_dates.add(d)
            score = date_counts[d]
            # 加权 cluster：E 源投影权重 x1.5
            if label.startswith('E+'):
                score = int(score * 1.5 + 0.5)
            rows.append((label, d, max(1, score)))

    rows.sort(key=lambda r: r[1])
    return rows

def _calc_volume_sr_zones(df, vol_ma=6, num_zones=30):
    """Detect volume-based fractal S/R zones. Returns (resistance_zones, support_zones)."""
    import numpy as np
    n = len(df)
    hi = np.asarray(df['High'], dtype=float).ravel()
    lo = np.asarray(df['Low'], dtype=float).ravel()
    vol_arr = np.asarray(df['Volume'], dtype=float).ravel()
    vol_ma_arr = np.convolve(vol_arr, np.ones(vol_ma)/vol_ma, mode='same')
    resistance = []; support = []
    for i in range(2, n - 2):
        if np.isnan(vol_ma_arr[i]) or vol_arr[i] < vol_ma_arr[i]:
            continue
        if hi[i] > hi[i-2:i].max() and hi[i] > hi[i+1:i+3].max():
            resistance.append((df.index[i], float(hi[i]), float(vol_arr[i])))
        if lo[i] < lo[i-2:i].min() and lo[i] < lo[i+1:i+3].min():
            support.append((df.index[i], float(lo[i]), float(vol_arr[i])))
    return resistance[-num_zones:], support[-num_zones:]

def _kumo_breakout_analysis(ichi: pd.DataFrame, ticker: str) -> dict | None:
    """
    对单只股票进行 Ichimoku 云层突破分析。

    算法：
    1. 当前 Bar 对应的云 = senkou_span_A/B 在 26 根 K 线前的值
       (标准一目均衡表：先行线前移 26 期)
    2. 根据收盘价与云顶/云底的相对位置判断状态
    3. Tenkan/Kijun 关系加分
    4. Tenkan 斜率加分

    返回 dict: { ticker, close, cloud_top, cloud_bottom, score, status, details, ... }
    数据不足时返回 None。
    """
    n = len(ichi)
    if n < 78:  # 需要至少 52(云B) + 26(偏移) 根 K 线
        return None

    close = float(ichi['Close'].iloc[-1])

    # 当前时间点对应的云 = 26 根 K 线前的先行值
    cloud_a = ichi['senkou_span_a'].iloc[-26]
    cloud_b = ichi['senkou_span_b'].iloc[-26]
    if pd.isna(cloud_a) or pd.isna(cloud_b):
        return None

    cloud_top = float(max(cloud_a, cloud_b))
    cloud_bottom = float(min(cloud_a, cloud_b))
    cloud_thick = (cloud_top - cloud_bottom) / close if close > 0 else 0

    # Tenkan / Kijun
    tenkan = float(ichi['tenkan_sen'].iloc[-1])
    kijun = float(ichi['kijun_sen'].iloc[-1])
    tenkan_prev = float(ichi['tenkan_sen'].iloc[-5]) if n >= 5 else tenkan
    tenkan_rising = tenkan > tenkan_prev

    # Chikou 相对 26 期前的收盘价
    chikou = ichi['chikou_span'].iloc[-1]
    chikou_above = not pd.isna(chikou) and chikou > ichi['Close'].iloc[-26]

    # ── 打分 ──
    score = 0
    details = []
    status = ""

    pos_ratio = 0.0  # 价格在云中的相对位置（0=云底, 1=云顶），云外则用负值或>1
    if close > cloud_top:
        # ── 云上 ──
        pos_ratio = 1.0 + (close - cloud_top) / (cloud_top - cloud_bottom + 1e-10)
        ratio = close / cloud_top
        if ratio < 1.015:
            score += 60
            status = "刚刚突破 ↑"
            details.append("刚刚突破云层")
        elif ratio < 1.05:
            score += 48
            status = "突破确认 ☀️"
            details.append("突破云层确认")
        elif ratio < 1.10:
            score += 35
            status = "云上运行 ☀️"
            details.append("云上运行")
        else:
            score += 20
            status = "远离云层 (上) ⛅"
            details.append("远离云层上方")
    elif close >= cloud_bottom:
        # ── 云中 ──
        pos_ratio = (close - cloud_bottom) / (cloud_top - cloud_bottom + 1e-10)
        if pos_ratio >= 0.85:
            score += 55
            status = "即将突破 🔥"
            details.append("云层上部，即将突破")
        elif pos_ratio >= 0.60:
            score += 38
            status = "云中偏上 📈"
            details.append("云层中上位置")
        elif pos_ratio >= 0.35:
            score += 22
            status = "云中 📊"
            details.append("云层中部")
        else:
            score += 10
            status = "云中偏下 📉"
            details.append("云层底部附近")
    else:
        # ── 云下 ──
        pos_ratio = (close - cloud_bottom) / (cloud_top - cloud_bottom + 1e-10)  # < 0
        ratio = close / cloud_bottom
        if ratio > 0.97:
            score += 35
            status = "接近云底 📈"
            details.append("接近云层底部")
        elif ratio > 0.93:
            score += 18
            status = "云下 📉"
            details.append("云层下方")
        else:
            score += 5
            status = "远离云层 (下) ⛅"
            details.append("远离云层下方")

    # Tenkan > Kijun → 偏多
    if tenkan > kijun:
        score += 15
        details.append("Tenkan > Kijun 偏多")
    elif tenkan < kijun and close > cloud_top:
        score += 5
        details.append("注意: Tenkan < Kijun")

    # Tenkan 上行趋势
    if tenkan_rising:
        score += 8
        details.append("Tenkan 上行")

    # Chikou 确认
    if chikou_above:
        score += 5
        details.append("Chikou > 价格(确认)")

    # ── Tenkan 上穿 Kijun（黄金交叉）──
    tk_golden_cross = False
    for i in range(1, min(4, n)):
        pt = ichi['tenkan_sen'].iloc[-(i + 1)]
        pk = ichi['kijun_sen'].iloc[-(i + 1)]
        if pd.isna(pt) or pd.isna(pk):
            continue
        if pt <= pk and tenkan > kijun:
            tk_golden_cross = True
            break
    if tk_golden_cross:
        score += 10
        details.append("Tenkan 上穿 Kijun（黄金交叉）")

    # ── 三役好転（三重确认买入信号）──
    triple_bull = bool(
        close > cloud_top and tk_golden_cross and chikou_above
    )
    if triple_bull:
        score += 15
        details.append("三役好転（三重确认买入信号）🚀")

    score = min(100, max(0, round(score)))

    # ── 最近5根K线是否有突破 ──
    recent_break = False
    for i in range(1, min(6, n - 27)):
        prev_ct = float(max(
            ichi['senkou_span_a'].iloc[-(26 + i)],
            ichi['senkou_span_b'].iloc[-(26 + i)],
        ))
        prev_cb = float(min(
            ichi['senkou_span_a'].iloc[-(26 + i)],
            ichi['senkou_span_b'].iloc[-(26 + i)],
        ))
        prev_c = float(ichi['Close'].iloc[-(1 + i)])
        if prev_c <= prev_ct and close > cloud_top:
            recent_break = True
            break

    return {
        'ticker': ticker,
        'close': round(close, 2),
        'cloud_top': round(cloud_top, 2),
        'cloud_bottom': round(cloud_bottom, 2),
        'cloud_thick_pct': round(cloud_thick * 100, 2),
        'tenkan': round(tenkan, 2),
        'kijun': round(kijun, 2),
        'tenkan_rising': tenkan_rising,
        'chikou_above': chikou_above,
        'pos_ratio': round(pos_ratio, 3),
        'score': score,
        'status': status,
        'details': ' | '.join(details),
        'recent_break': recent_break,
        'tk_golden_cross': tk_golden_cross,
        'triple_bull': triple_bull,
        'ichi': ichi,  # 用于绘图
    }

def _kumo_enhanced_analysis(ichi: pd.DataFrame, ticker: str) -> dict | None:
    """
    加强版 Ichimoku 突破分析 —— 四条件全满足才算候选。

    条件:
      1. 价格即将突破或刚突破云层（云层上 80% 区间 or 云上 5% 以内）
      2. 未来云层已变绿（最近 26 期投影中 senkou_a > senkou_b 占比 ≥ 60%）
      3. 价格在 Tenkan > Kijun 之上，且两线均呈上升趋势（5 期前对比）
      4. Chikou Span 在 K 线之上（当前收盘 > 26 期前收盘 = 趋势确认）
    """
    n = len(ichi)
    if n < 78:
        return None

    close = float(ichi['Close'].iloc[-1])

    cloud_a = ichi['senkou_span_a'].iloc[-26]
    cloud_b = ichi['senkou_span_b'].iloc[-26]
    if pd.isna(cloud_a) or pd.isna(cloud_b):
        return None

    cloud_top = float(max(cloud_a, cloud_b))
    cloud_bottom = float(min(cloud_a, cloud_b))
    cloud_thick = (cloud_top - cloud_bottom) / close if close > 0 else 0

    tenkan = float(ichi['tenkan_sen'].iloc[-1])
    kijun = float(ichi['kijun_sen'].iloc[-1])
    tenkan_5 = float(ichi['tenkan_sen'].iloc[-5]) if n >= 5 else tenkan
    kijun_5 = float(ichi['kijun_sen'].iloc[-5]) if n >= 5 else kijun
    tenkan_rising = tenkan > tenkan_5
    kijun_rising = kijun > kijun_5

    close_26_ago = float(ichi['Close'].iloc[-26])

    # ── C1: 价格在云层顶部附近或刚突破 ──
    c1_pass, c1_score = False, 0
    if close > cloud_top:
        ratio = close / cloud_top
        if ratio < 1.05:
            c1_pass, c1_score = True, 30
        elif ratio < 1.10:
            c1_pass, c1_score = False, 22
        else:
            c1_pass, c1_score = False, 10
    elif close >= cloud_bottom:
        pos = (close - cloud_bottom) / (cloud_top - cloud_bottom + 1e-10)
        if pos >= 0.80:
            c1_pass, c1_score = True, 28
        elif pos >= 0.60:
            c1_pass, c1_score = False, 18
        else:
            c1_pass, c1_score = False, 5
    else:
        c1_pass, c1_score = False, 0

    # ── C2: 未来云层变绿 ──
    green_cnt, total_cnt = 0, 0
    for i in range(-26, 0):
        sa = ichi['senkou_span_a'].iloc[i]
        sb = ichi['senkou_span_b'].iloc[i]
        if not pd.isna(sa) and not pd.isna(sb):
            total_cnt += 1
            if sa > sb:
                green_cnt += 1
    green_pct = green_cnt / total_cnt if total_cnt > 0 else 0.0
    c2_pass = green_pct >= 0.60
    c2_score = min(25, int(green_pct * 25))

    # ── C3: 价格 > Tenkan > Kijun，两线向上 ──
    tk_aligned = close > tenkan > kijun
    c3_pass = tk_aligned and tenkan_rising and kijun_rising
    c3_score = 0
    if tk_aligned:
        c3_score += 10
    if tenkan_rising:
        c3_score += 8
    if kijun_rising:
        c3_score += 7

    # ── C4: Chikou 在 K 线之上 ──
    chikou_above = close > close_26_ago
    c4_pass = chikou_above
    chikou_margin = (close / close_26_ago - 1) * 100 if close_26_ago > 0 else 0
    c4_score = min(20, max(0, int(chikou_margin * 2))) if chikou_above else 0

    # ── TK 黄金交叉（加强模式额外加分）──
    tk_golden_cross = False
    for i in range(1, min(4, n)):
        pt = ichi['tenkan_sen'].iloc[-(i + 1)]
        pk = ichi['kijun_sen'].iloc[-(i + 1)]
        if pd.isna(pt) or pd.isna(pk): continue
        if pt <= pk and tenkan > kijun:
            tk_golden_cross = True
            break
    if tk_golden_cross:
        total_score += 8

    # ── 三役好転（三重确认：云上 + 金叉 + Chikou 确认）──
    triple_bull = close > cloud_top and tk_golden_cross and chikou_above

    # ── 综合 ──
    all_pass = c1_pass and c2_pass and c3_pass and c4_pass
    total_score = c1_score + c2_score + c3_score + c4_score
    if triple_bull and all_pass:
        total_score += 10
        status = "🌟 加强+三役好転"

    fails = []
    if not c1_pass: fails.append("云层位置")
    if not c2_pass: fails.append(f"云层{green_pct:.0%}绿<60%")
    if not c3_pass: fails.append("TK排列")
    if not c4_pass: fails.append("Chikou滞后")
    status = "🌟 加强突破" if all_pass else "❌ " + " · ".join(fails)

    return {
        'ticker': ticker,
        'close': round(close, 2),
        'cloud_top': round(cloud_top, 2),
        'cloud_bottom': round(cloud_bottom, 2),
        'cloud_thick_pct': round(cloud_thick * 100, 2),
        'tenkan': round(tenkan, 2),
        'kijun': round(kijun, 2),
        'tenkan_rising': tenkan_rising,
        'kijun_rising': kijun_rising,
        'green_pct': round(green_pct * 100, 1),
        'chikou_above': chikou_above,
        'score': total_score,
        'status': status,
        'all_pass': all_pass,
        'c1': c1_pass, 'c2': c2_pass, 'c3': c3_pass, 'c4': c4_pass,
        'tk_golden_cross': tk_golden_cross,
        'triple_bull': triple_bull,
        'recent_break': c1_pass,
        'ichi': ichi,
        'timeframe': '1D',
    }

def _flagship_signal_analysis(ichi: pd.DataFrame, ticker: str, df: pd.DataFrame = None) -> dict | None:
    """
    THE FLAGSHIP SIGNAL — Ichimuku Five‑Condition Stack.

    Stacks five conditions across cloud, momentum, and price structure:

      C1 – Price above Kumo (breakout)
      C2 – Kumo turning green (Senkou A > B forward projection)
      C3 – TK alignment (Tenkan > Kijun, both rising)
      C4 – Chikou position relative to Kumo
      C5 – Accumulation structure (consolidation before breakout)

    Signal type:
      EARLY     – C1–C3 pass, Chikou still inside Kumo
      CONFIRMED – C1–C4 pass, Chikou has cleared the cloud

    Conviction (WEAK → MODERATE → STRONG):
      Cloud thickness, accumulation length, breakout volume, Chikou clearance.
    """
    n = len(ichi)
    if n < 78:
        return None

    close = float(ichi['Close'].iloc[-1])
    cloud_a = ichi['senkou_span_a'].iloc[-26]
    cloud_b = ichi['senkou_span_b'].iloc[-26]
    if pd.isna(cloud_a) or pd.isna(cloud_b):
        return None

    cloud_top = float(max(cloud_a, cloud_b))
    cloud_bot = float(min(cloud_a, cloud_b))
    cloud_thick_pct = (cloud_top - cloud_bot) / cloud_bot * 100 if cloud_bot > 0 else 0

    tenkan = float(ichi['tenkan_sen'].iloc[-1])
    kijun = float(ichi['kijun_sen'].iloc[-1])
    tenkan_5 = float(ichi['tenkan_sen'].iloc[-5]) if n >= 5 else tenkan
    kijun_5 = float(ichi['kijun_sen'].iloc[-5]) if n >= 5 else kijun
    tenkan_rising = tenkan > tenkan_5
    kijun_rising = kijun > kijun_5

    close_26 = float(ichi['Close'].iloc[-26])

    # ── C1: Price above cloud  ──
    c1 = close > cloud_top

    # ── C2: Future cloud green (≥60% Senkou A > B over last 26)  ──
    green_cnt = 0
    for i in range(-26, 0):
        sa = ichi['senkou_span_a'].iloc[i]
        sb = ichi['senkou_span_b'].iloc[i]
        if not pd.isna(sa) and not pd.isna(sb) and sa > sb:
            green_cnt += 1
    c2 = (green_cnt / 26) >= 0.6

    # ── C3: TK alignment + both rising  ──
    c3 = close > tenkan > kijun and tenkan_rising and kijun_rising

    # ── C4: Chikou vs Kumo  ──
    chikou_in_cloud = cloud_bot <= close_26 <= cloud_top
    chikou_above_cloud = close_26 > cloud_top
    chikou_margin_pct = ((close_26 - cloud_top) / cloud_top * 100) if cloud_top > 0 else 0

    # ── C5: Accumulation structure  ──
    if n >= 52:
        recent_range = float(ichi['High'].iloc[-26:].max() - ichi['Low'].iloc[-26:].min())
        older_range = float(ichi['High'].iloc[-52:-26].max() - ichi['Low'].iloc[-52:-26].min())
        consolidation = recent_range < older_range * 0.85 if older_range > 0 else False
    else:
        consolidation = False

    # ── Determine early vs confirmed  ──
    confirmed = c1 and c2 and c3 and chikou_above_cloud
    # EARLY: 价格必须接近云顶（未大涨远离），排除已经涨上天的标的
    price_rally_pct = (close - cloud_top) / cloud_top * 100 if cloud_top > 0 else 0
    early = c1 and c2 and c3 and chikou_in_cloud and price_rally_pct < 8

    if not (early or confirmed):
        return None

    signal_type = "CONFIRMED" if confirmed else "EARLY"

    # ── Conviction scoring (0–100)  ──
    conviction_score = 0
    conviction_notes = []

    # 1) Cloud thickness (0–25)
    thick_score = min(25, int(cloud_thick_pct * 2))
    conviction_score += thick_score

    # 2) Accumulation length (0–25)
    #    Longer consolidation = more conviction
    if consolidation:
        acc_score = 25
        conviction_notes.append("consolidation")
    elif n >= 26 and c1:
        # Price above cloud but no clear consolidation
        acc_score = 10
    else:
        acc_score = 0
    conviction_score += acc_score

    # 3) Breakout volume (0–25)
    vol_score = 0
    if df is not None and 'Volume' in df.columns and len(df) >= 6:
        vol_latest = float(df['Volume'].iloc[-1])
        vol_avg = float(df['Volume'].iloc[-6:-1].mean())
        if vol_avg > 0 and vol_latest > vol_avg * 1.5:
            vol_score = 25
        elif vol_avg > 0 and vol_latest > vol_avg * 1.2:
            vol_score = 15
        elif vol_avg > 0 and vol_latest > vol_avg:
            vol_score = 10
    conviction_score += vol_score

    # 4) Chikou clearance (0–25)  — how far Chikou is through the cloud
    if chikou_above_cloud:
        clear_score = min(25, max(0, int(chikou_margin_pct * 3)))
    elif chikou_in_cloud:
        # How far through the cloud
        if cloud_top > cloud_bot:
            chikou_pos = (close_26 - cloud_bot) / (cloud_top - cloud_bot)
            clear_score = int(chikou_pos * 15)
        else:
            clear_score = 5
    else:
        clear_score = 0
    conviction_score += clear_score

    # 5) Triple bull bonus (三役好転) — 仅给刚突破的票加分
    #    已经涨太多的确认票不加分，避免选出等回调的标的
    triple_bull = c1 and c3 and chikou_above_cloud
    if triple_bull and close < cloud_top * 1.05:
        conviction_score += 15  # 刚突破 + 三役好転 = 最强信号
    elif triple_bull and close < cloud_top * 1.10:
        conviction_score += 8   # 已经涨了一段，加分减半
    # 超过云顶 10% 的三役好転不再额外加分（已涨太多）

    # 6) CONFIRMED bonus — 鼓励 Chikou 刚出云的趋势确认
    if confirmed and chikou_margin_pct < 5:
        conviction_score += 10  # Chikou 刚出云 = 趋势刚确认
    elif confirmed:
        conviction_score += 5   # 出云已久，加分减半

    # Map to conviction level
    if conviction_score >= 70:
        conviction = "STRONG"
    elif conviction_score >= 40:
        conviction = "MODERATE"
    else:
        conviction = "WEAK"

    status_icon = "🟢" if confirmed else "🟡"
    status_label = f"{status_icon} {signal_type} · {conviction}"

    return {
        'ticker': ticker,
        'close': round(close, 2),
        'cloud_top': round(cloud_top, 2),
        'cloud_bottom': round(cloud_bot, 2),
        'cloud_thick_pct': round(cloud_thick_pct, 2),
        'tenkan': round(tenkan, 2),
        'kijun': round(kijun, 2),
        'tenkan_rising': tenkan_rising,
        'chikou_above': chikou_above_cloud,
        'score': conviction_score,
        'status': status_label,
        'details': f"{signal_type} · {conviction}",
        'signal_type': signal_type,
        'conviction': conviction,
        'chikou_clearance_pct': round(chikou_margin_pct, 1),
        'green_pct': round(green_cnt / 26 * 100, 1),
        'tk_golden_cross': (tenkan > kijun),
        'triple_bull': triple_bull,
        'recent_break': c1,
        'ichi': ichi,
        'timeframe': '1D',
    }
