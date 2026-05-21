"""
algorithms/pivot_detection.py  —  Swing pivot 检测与 N/V/I 波形识别
"""
import numpy as np
import pandas as pd

from shared.utils import _to_date


def _local_extrema(values: list, order: int, mode: str) -> list:
    """Rolling-window local maxima (mode='high') or minima (mode='low')."""
    n, result = len(values), []
    for i in range(order, n - order):
        window_vals = values[i - order : i + order + 1]
        center = values[i]
        if mode == "high" and center == max(window_vals) and center > 0:
            result.append(i)
        elif mode == "low" and center == min(window_vals) and center > 0:
            result.append(i)
    return result


def find_major_pivots(df: pd.DataFrame, order: int = 7, top_n: int = 4):
    """
    Returns (pivot_highs, pivot_lows), each a list of (date, price) tuples.
    Sorted by magnitude (highs descending, lows ascending).
    """
    h_idx = _local_extrema(df["High"].tolist(), order, "high")
    l_idx = _local_extrema(df["Low"].tolist(),  order, "low")

    pivot_highs = sorted(
        [(df.index[i].date(), float(df["High"].iloc[i])) for i in h_idx],
        key=lambda x: -x[1],
    )
    pivot_lows = sorted(
        [(df.index[i].date(), float(df["Low"].iloc[i])) for i in l_idx],
        key=lambda x:  x[1],
    )
    return pivot_highs[:top_n], pivot_lows[:top_n]


def _find_swing_pivots(df, order=5):
    """
    Multi-order swing pivot detection (order=3,5,9 merged by consensus).
    Returns (pivot_dates, pivot_prices, pivot_types, pivot_indices).
    """
    n = len(df)

    def _detect_at_order(o):
        win = 2 * o + 1
        hi_roll = df['High'].rolling(win, center=True).max()
        lo_roll = df['Low'].rolling(win, center=True).min()
        hi = set(np.where(df['High'].values == hi_roll.values)[0])
        lo = set(np.where(df['Low'].values == lo_roll.values)[0])
        for i in list(hi):
            if i < o or i >= n - o:
                hi.discard(i)
        for i in list(lo):
            if i < o or i >= n - o:
                lo.discard(i)
        return hi, lo

    hi_a, lo_a = _detect_at_order(3)
    hi_b, lo_b = _detect_at_order(5)
    hi_c, lo_c = _detect_at_order(9)

    hi_idx = sorted([i for i in (hi_a | hi_b | hi_c)
                     if sum([i in hi_a, i in hi_b, i in hi_c]) >= 2])
    lo_idx = sorted([i for i in (lo_a | lo_b | lo_c)
                     if sum([i in lo_a, i in lo_b, i in lo_c]) >= 2])

    all_pts = []
    for i in hi_idx:
        all_pts.append((df.index[i], float(df['High'].iloc[i]), 'H', i))
    for i in lo_idx:
        all_pts.append((df.index[i], float(df['Low'].iloc[i]), 'L', i))
    all_pts.sort(key=lambda x: x[0])

    alt = []
    last_type = None
    for d, p, t, idx in all_pts:
        if t != last_type:
            alt.append((d, p, t, idx))
            last_type = t
        else:
            if t == 'H' and p > alt[-1][1]:
                alt[-1] = (d, p, t, idx)
            elif t == 'L' and p < alt[-1][1]:
                alt[-1] = (d, p, t, idx)

    if alt and (n - alt[-1][3]) > 3:
        last_d, last_p, last_t, last_i = alt[-1]
        trailing = df.iloc[last_i + 1:]
        if last_t == 'H' and len(trailing) > 2:
            min_pos = trailing['Low'].idxmin()
            mi = df.index.get_loc(min_pos)
            if mi > last_i + 1 and mi < n - 1:
                alt.append((df.index[mi], float(df['Low'].iloc[mi]), 'L', mi))
        elif last_t == 'L' and len(trailing) > 2:
            max_pos = trailing['High'].idxmax()
            mi = df.index.get_loc(max_pos)
            if mi > last_i + 1 and mi < n - 1:
                alt.append((df.index[mi], float(df['High'].iloc[mi]), 'H', mi))

    dates = [a[0] for a in alt]
    prices = [a[1] for a in alt]
    types = [a[2] for a in alt]
    indices = [a[3] for a in alt]
    return dates, prices, types, indices


def _detect_n_wave(dates, prices, types, indices):
    """
    LuxAlgo-style N wave detection using 4 alternating swing points.
    Returns (V_date, N_date, E_date, V_price, N_price, E_price,
             V_type, N_type, E_type, trend_up) or None.
    """
    a_d, a_p, a_t = dates[-4], prices[-4], types[-4]
    b_d, b_p, b_t = dates[-3], prices[-3], types[-3]
    c_d, c_p, c_t = dates[-2], prices[-2], types[-2]
    d_d, d_p, d_t = dates[-1], prices[-1], types[-1]
    ai, bi, ci, di = indices[-4], indices[-3], indices[-2], indices[-1]

    if (di - ai) < 9:
        return None

    threshold = abs(a_p - b_p) * 0.15

    if a_t == 'L' and b_t == 'H' and c_t == 'L' and d_t == 'H':
        if a_p < b_p and c_p < b_p - threshold and d_p > b_p:
            return (_to_date(a_d), _to_date(b_d), _to_date(c_d),
                    a_p, b_p, c_p, 'L', 'H', 'L', True)

    if a_t == 'H' and b_t == 'L' and c_t == 'H' and d_t == 'L':
        if a_p > b_p and c_p > b_p + threshold and d_p < b_p:
            return (_to_date(a_d), _to_date(b_d), _to_date(c_d),
                    a_p, b_p, c_p, 'H', 'L', 'H', False)

    return None


def _detect_v_wave(dates, prices, types, indices):
    """
    V wave detection using 3 alternating swing points.
    Returns (V_date, N_date, E_date, V_price, N_price, E_price,
             V_type, N_type, E_type, trend_up) or None.
    """
    a_d, a_p, a_t = dates[-3], prices[-3], types[-3]
    b_d, b_p, b_t = dates[-2], prices[-2], types[-2]
    c_d, c_p, c_t = dates[-1], prices[-1], types[-1]
    ai, ci = indices[-3], indices[-1]

    if (ci - ai) < 9:
        return None

    amplitude = abs(a_p - b_p)
    threshold = amplitude * 0.15

    if a_t == 'L' and b_t == 'H' and c_t == 'L':
        if abs(c_p - a_p) <= threshold:
            return (_to_date(a_d), _to_date(b_d), _to_date(c_d),
                    a_p, b_p, c_p, 'L', 'H', 'L', True)

    if a_t == 'H' and b_t == 'L' and c_t == 'H':
        if abs(c_p - a_p) <= threshold:
            return (_to_date(a_d), _to_date(b_d), _to_date(c_d),
                    a_p, b_p, c_p, 'H', 'L', 'H', False)

    return None


def _detect_i_wave(dates, prices, types, indices):
    """
    I wave (simple 2-point unidirectional move).
    Minimum 9 K-lines span. E=N (no retracement yet).
    """
    a_d, a_p, a_t = dates[-2], prices[-2], types[-2]
    b_d, b_p, b_t = dates[-1], prices[-1], types[-1]
    ai, bi = indices[-2], indices[-1]

    if (bi - ai) < 9:
        return None

    if a_t == 'L' and b_t == 'H' and a_p < b_p:
        return (_to_date(a_d), _to_date(b_d), _to_date(a_d),
                a_p, b_p, a_p, 'L', 'H', 'L', True)

    if a_t == 'H' and b_t == 'L' and a_p > b_p:
        return (_to_date(a_d), _to_date(b_d), _to_date(a_d),
                a_p, b_p, a_p, 'H', 'L', 'H', False)

    return None
