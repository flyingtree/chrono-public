"""
algorithms/gann_sq9.py  —  Gann Square of 9 价格与时间计算
"""
import math
from datetime import date, timedelta

import pandas as pd


def _find_sq9_ref_levels(subset_df: pd.DataFrame, order: int = 5):
    """Find confirmed swing high/low levels for Gann Square of 9.

    Uses rolling window detection on High/Low independently to identify
    confirmed pivot points (interior to the range, not edge prices).
    Falls back to untrimmed max/min if insufficient pivot data.

    Returns (confirmed_high, confirmed_low, high_date, low_date).
    """
    highs = subset_df['High'].values
    lows = subset_df['Low'].values
    dates = subset_df.index
    n = len(highs)

    pivot_highs, pivot_high_dates = [], []
    pivot_lows, pivot_low_dates = [], []
    for i in range(order, n - order):
        if highs[i] == max(highs[i - order : i + order + 1]):
            pivot_highs.append(highs[i])
            pivot_high_dates.append(dates[i])
        if lows[i] == min(lows[i - order : i + order + 1]):
            pivot_lows.append(lows[i])
            pivot_low_dates.append(dates[i])

    if pivot_highs:
        idx = pivot_highs.index(max(pivot_highs))
        confirmed_high = float(pivot_highs[idx])
        high_date = pivot_high_dates[idx].date()
    else:
        confirmed_high = float(max(highs))
        high_date = dates[highs.argmax()].date()

    if pivot_lows:
        idx = pivot_lows.index(min(pivot_lows))
        confirmed_low = float(pivot_lows[idx])
        low_date = pivot_low_dates[idx].date()
    else:
        confirmed_low = float(min(lows))
        low_date = dates[lows.argmin()].date()

    return float(confirmed_high), float(confirmed_low), high_date, low_date


def _calc_square_of_9_levels(high_price: float, low_price: float, max_steps: int = 15, scale: float = 1.0) -> dict:
    """Calculate Gann Square of 9 price levels at 90° increments.

    360° (full circle) levels are returned separately as solid-line candidates,
    90° levels as dashed-line candidates.

    Red lines (from high):  (√H − step·n)²  (down),  (√H + step·n)² (up)
    Blue lines (from low):  (√L + step·n)²  (up),  (√L − step·n)² (down)
    where step = 0.5 * scale.

    360° = 2.0 sqrt-step = 4 × 90° = every 4th n (n % 4 == 0).
    """
    step = 0.5 * scale
    sqrt_h = math.sqrt(high_price)
    sqrt_l = math.sqrt(low_price)

    red_90, red_360, red_tags = [], [], []
    for n in range(1, max_steps + 1):
        level = (sqrt_h - step * n) ** 2
        if level <= 0:
            break
        level = round(level, 2)
        if n % 4 == 0:
            red_360.append(level)
            red_tags.append((level, f"{n*90}°"))
        elif n % 2 == 0:
            red_tags.append((level, f"{n*90}°"))
        red_90.append(level)

    red_above_90, red_above_360, red_above_tags = [], [], []
    for n in range(1, max_steps + 1):
        level = round((sqrt_h + step * n) ** 2, 2)
        if n % 4 == 0:
            red_above_360.append(level)
            red_above_tags.append((level, f"{n*90}°"))
        elif n % 2 == 0:
            red_above_tags.append((level, f"{n*90}°"))
        red_above_90.append(level)

    blue_90, blue_360, blue_tags = [], [], []
    for n in range(1, max_steps + 1):
        level = round((sqrt_l + step * n) ** 2, 2)
        if n % 4 == 0:
            blue_360.append(level)
            blue_tags.append((level, f"{n*90}°"))
        elif n % 2 == 0:
            blue_tags.append((level, f"{n*90}°"))
        blue_90.append(level)

    blue_below_90, blue_below_360, blue_below_tags = [], [], []
    for n in range(1, max_steps + 1):
        level = (sqrt_l - step * n) ** 2
        if level <= 0:
            break
        level = round(level, 2)
        if n % 4 == 0:
            blue_below_360.append(level)
            blue_below_tags.append((level, f"{n*90}°"))
        elif n % 2 == 0:
            blue_below_tags.append((level, f"{n*90}°"))
        blue_below_90.append(level)

    return {
        'red_90': red_90, 'red_360': red_360,
        'red_above_90': red_above_90, 'red_above_360': red_above_360,
        'blue_90': blue_90, 'blue_360': blue_360,
        'blue_below_90': blue_below_90, 'blue_below_360': blue_below_360,
        'red_tags': red_tags, 'red_above_tags': red_above_tags,
        'blue_tags': blue_tags, 'blue_below_tags': blue_below_tags,
        'high': round(high_price, 2), 'low': round(low_price, 2),
    }


def _calc_geometry_45_dates(ref_date: date, num_steps: int = 12):
    """Calculate dates at 45° solar intervals (~45 calendar days) from a reference date.

    Returns dates going forward in time only.
    """
    dates = []
    for n in range(1, num_steps + 1):
        d = ref_date + timedelta(days=45 * n)
        dates.append(d)
    return dates
