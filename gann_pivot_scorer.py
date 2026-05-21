#!/usr/bin/env python3
"""
gann_pivot_scorer.py
江恩关键反转日（Pivot Day）概率评分系统

基于 W.D. Gann《大师预测法》的六维共振框架：
  1. 季节性变盘窗口   (max 20 分)
  2. 时间计数共振     (max 25 分)  ← A级天数25/B级天数8/B级周数5
  3. 周年纪念日       (max 15 分)
  4. 价格阻力/支撑位  (max 15 分)  ← 仅HIGH↔LOW对，50%=15/25-75%=10
  5. 时价平方         (max 20 分)
  6. 几何角度线(1×1) (max 15 分)
  ★ 多维共振加成      (max 10 分)
总计上限: 100 分

等级:  A ≥ 80 / B ≥ 55 / C ≥ 28 / - < 28

用法:
  python gann_pivot_scorer.py              # 运行内置示例
  或在代码中 import 后调用 analyze_pivot()
"""

import math
import sys
from datetime import date, datetime, timedelta
from dataclasses import dataclass
from typing import Optional
from zoneinfo import ZoneInfo

# 确保 Windows 终端以 UTF-8 输出特殊字符
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════
#  常量：江恩核心参数
# ══════════════════════════════════════════════════════════════════════

# 季节性变盘窗口（月, 日）
_SEASONAL_A = [(3, 20), (6, 21), (9, 22), (12, 21)]  # 四分点 ─ 最强信号
_SEASONAL_B = [(2,  4), (5,  5), (8,  5), (11,  8)]  # 中季点 ─ 次强信号

_SEASONAL_C = [(1, 16), (4,  3), (7,  5), (10, 17)]  # Gann关键窗
# 关键时间计数（天）
_DAYS_A = {144, 288, 360, 432, 576, 720, 864, 1080}          # 新增 1080 = 3×360 三圆完整循环
_DAYS_B = {45, 90, 120, 135, 180, 225, 270, 300, 315}
_DAYS_C = {30, 42, 49, 60, 84}

# 关键时间计数（周）
_WEEKS_A = {144, 360}
_WEEKS_B = {7, 21, 42, 45, 90, 120, 180}  # 90w≈630d, 120w≈840d, 180w≈1260d

# 关键时间计数（月）
_MONTHS_A = {60, 120, 240}   # 5年/10年/20年
_MONTHS_B = {7, 10, 12, 21, 24, 30, 36, 42, 84}  # 36m=3年 在3年回看期内

# 多周期平方：calendar-days 等效（用于极端价格平方跨周期检测）
_WEEK_DAYS  = 7.0
_MONTH_DAYS = 30.4375

# 大师12图表节点（144的倍数）
_MASTER12 = {144 * n for n in range(1, 50)}

# 容差配置
_DATE_TOL_DAYS   = 3      # 日期容差：±3天（收紧，减少季节/周年误报）
_PRICE_TOL_PCT   = 0.006  # 价格容差：±0.6%
_SQ9_TOL_DEG     = 10.0   # 九方图角度容差：±10°
_ANGLE_TOL_PCT   = 0.010  # 角度线容差：±1.0%（收紧，减少远期角度线误报）
_SQUARE_TOL_PCT  = 0.06   # 时价平方容差：±6%
_TIME_TOL_DAYS   = 3      # 时间计数容差：±3天
_TIME_TOL_WEEKS  = 0.4    # 时间计数容差：±0.4周
_TIME_TOL_MONTHS = 0.5    # 时间计数容差：±0.5月（从1.2大幅收紧，月线计数原为最大膨胀源）
_MIN_ELAPSED_DAYS = 30    # 时价平方/角度线：排除30天内极近期pivot（防止近期pivot自我循环）


# ══════════════════════════════════════════════════════════════════════
#  数据结构
# ══════════════════════════════════════════════════════════════════════

@dataclass
class Pivot:
    """历史关键转折点"""
    date:       date
    price:      float
    pivot_type: str = "?"   # "HIGH" 或 "LOW"

    def __str__(self) -> str:
        return f"{self.pivot_type}({self.price:.2f}@{self.date})"


@dataclass
class Component:
    """单个评分维度"""
    name:      str
    score:     float
    max_score: float
    detail:    str


@dataclass
class PivotAnalysis:
    """完整分析结果"""
    current_date:  date
    current_price: float
    total_score:   float       # 0-100
    grade:         str         # "A" / "B" / "C" / "-"
    probability:   str
    components:    list        # list[Component]
    triggered:     list        # list[str] — 有得分的因素说明
    warning:       str


@dataclass
class FutureZone:
    """预测的未来关键共振时间窗口"""
    peak_date:        date    # 该窗口内得分最高的日期
    date_range:       tuple   # (window_start, window_end)
    grade:            str     # "A" / "B" / "C"
    score:            float   # 0-100
    time_score:       float   # 时间维度小计（季节+时间计数+周年）
    price_zone:       tuple   # (lo_proj, hi_proj) — 角度线预测价格区间
    convergence_desc: str     # 角度线收敛描述（若发生）
    triggered:        list    # 触发因素列表


# ══════════════════════════════════════════════════════════════════════
#  内部工具函数
# ══════════════════════════════════════════════════════════════════════

def _days(d1: date, d2: date) -> int:
    return abs((d2 - d1).days)

def _weeks(d1: date, d2: date) -> float:
    return _days(d1, d2) / 7.0

def _months(d1: date, d2: date) -> float:
    return _days(d1, d2) / 30.4375

def _nearest(value: float, key_set: set, tol: float) -> Optional[float]:
    """返回集合中最近的匹配值（在容差内），否则返回 None"""
    best, best_err = None, float('inf')
    for k in key_set:
        err = abs(value - k)
        if err < best_err and err <= tol:
            best_err, best = err, k
    return best

def _seasonal_hit(d: date, candidates: list, tol: int) -> tuple:
    """返回 (是否命中, 偏差天数, 节点名称)"""
    for month, day in candidates:
        try:
            candidate = date(d.year, month, day)
            dist = abs((d - candidate).days)
            if dist <= tol:
                return True, dist, f"{month}/{day}"
        except ValueError:
            pass
    return False, 999, ""

def _anniversary_hit(current: date, pivot_date: date, tol: int) -> tuple:
    """返回 (是否命中, 偏差天数) — 检查同月同日（要求pivot在上一年或更早，避免同年假周年）"""
    if pivot_date.year >= current.year:
        return False, 999   # 同年pivot无法形成真周年纪念日
    try:
        ann = date(current.year, pivot_date.month, pivot_date.day)
        dist = abs((current - ann).days)
        return dist <= tol, dist
    except ValueError:
        return False, 999

def _sq9_degrees(p_ref: float, p_cur: float) -> float:
    """计算两价格在九方图上的角度差（每 Δ√P = 0.25 对应 45°）"""
    return abs(math.sqrt(max(p_ref, 0.01)) - math.sqrt(max(p_cur, 0.01))) / 0.25 * 45.0

def _sq9_harmonic(p_ref: float, p_cur: float, tol_deg: float) -> tuple:
    """返回 (是否成谐波, 最近45°倍数角度, 误差°)"""
    deg = _sq9_degrees(p_ref, p_cur)
    nearest = round(deg / 45) * 45
    err = abs(deg - nearest)
    return err <= tol_deg, int(nearest), round(err, 1)

def _scale_of_prices(price: float) -> float:
    """
    江恩降维缩放法则（Scale of Prices）：
    将任意价格缩放到自然时间范围（1–360）内。
    例：8000→80, 500→50, 50→50, 12→12
    """
    scaled = abs(price)
    while scaled > 360:
        scaled /= 10.0
    while 0 < scaled < 1:
        scaled *= 10.0
    return scaled


# ══════════════════════════════════════════════════════════════════════
#  各维度评分函数
# ══════════════════════════════════════════════════════════════════════

def _score_seasonal(d: date) -> Component:
    """维度1：季节性变盘窗口（max 20 分）"""
    hit_a, dist_a, name_a = _seasonal_hit(d, _SEASONAL_A, _DATE_TOL_DAYS)
    hit_b, dist_b, name_b = _seasonal_hit(d, _SEASONAL_B, _DATE_TOL_DAYS)
    hit_c, dist_c, name_c = _seasonal_hit(d, _SEASONAL_C, _DATE_TOL_DAYS)

    if hit_a:
        score  = max(20 - dist_a * 2, 14)
        detail = f"命中A级四分节点 {name_a}（偏差 {dist_a} 天）"
    elif hit_b:
        score  = max(13 - dist_b * 2, 7)
        detail = f"命中B级中季点 {name_b}（偏差 {dist_b} 天）"
    elif hit_c:
        score  = max(8 - dist_c * 2, 4)
        detail = f"命中C级Gann关键窗 {name_c}（偏差 {dist_c} 天）"
    else:
        score, detail = 0, "未命中任何季节性节点"

    return Component("季节性变盘窗口", score, 20, detail)


def _score_time_counts(current: date, pivots: list) -> Component:
    """维度2：时间计数共振（max 25 分）"""
    best_score, best_detail = 0, "未发现显著时间计数共振"
    details = []
    cumulative = 0.0

    for pv in pivots:
        d = _days(pv.date, current)
        w = _weeks(pv.date, current)
        m = _months(pv.date, current)

        # A级天数
        hit = _nearest(d, _DAYS_A, _TIME_TOL_DAYS)
        if hit:
            cumulative += 25
            details.append(f"距 {pv} 已 {d} 天 ~ {int(hit)} (A级天数+25)")

        # B级天数
        hit = _nearest(d, _DAYS_B, _TIME_TOL_DAYS)
        if hit:
            cumulative += 8
            details.append(f"距 {pv} 已 {d} 天 ~ {int(hit)} (B级天数+8)")

        # A级周数
        hit = _nearest(w, _WEEKS_A, _TIME_TOL_WEEKS)
        if hit:
            cumulative += 18
            details.append(f"距 {pv} 已 {w:.1f} 周 ~ {int(hit)} (A级周数+18)")

        # B级周数
        hit = _nearest(w, _WEEKS_B, _TIME_TOL_WEEKS)
        if hit:
            cumulative += 5
            details.append(f"距 {pv} 已 {w:.1f} 周 ~ {int(hit)} (B级周数+5)")

        # A级月数
        hit = _nearest(m, _MONTHS_A, _TIME_TOL_MONTHS)
        if hit:
            cumulative += 15
            details.append(f"距 {pv} 已 {m:.1f} 月 ~ {int(hit)} (A级月数+15)")

    best_score = min(cumulative, 30)
    if details:
        best_detail = "; ".join(details[:5])
        if len(details) > 5:
            best_detail += f"; 等共{len(details)}个共振"
    return Component("时间计数共振", best_score, 25, best_detail)


def _score_anniversary(current: date, pivots: list) -> Component:
    """维度3：周年纪念日（max 15 分）"""
    best_score, best_detail = 0, "无周年纪念日重合"

    for pv in pivots:
        hit, dist = _anniversary_hit(current, pv.date, _DATE_TOL_DAYS)
        if hit:
            s   = max(15 - dist * 2, 8)
            det = f"{pv} 的周年纪念日（偏差 {dist} 天）"
            if s > best_score:
                best_score, best_detail = s, det

        elapsed = _days(pv.date, current)
        # 52周周年
        if abs(elapsed - 364) <= 3:
            s = 10
            det = f"{pv} 的52周周年（已{elapsed}天）"
            if s > best_score: best_score, best_detail = s, det
        # 12月周年
        if abs(elapsed - 365) <= 5 or abs(elapsed - 366) <= 5:
            s = 12
            det = f"{pv} 的12月周年（已{elapsed}天）"
            if s > best_score: best_score, best_detail = s, det

    return Component("周年纪念日", best_score, 15, best_detail)


def _score_price_levels(current_price: float, pivots: list) -> Component:
    """维度4：价格阻力/支撑位（max 20 分）"""
    best_score, best_detail = 0, "未命中显著价格阻力位"

    def _check(target: float, label: str, pts: int, context: str) -> None:
        nonlocal best_score, best_detail
        if target <= 0:
            return
        err = abs(current_price - target) / target
        if err <= _PRICE_TOL_PCT:
            info = f"价格 {current_price:.2f} ≈ {label}={target:.2f}（{context}，误差{err*100:.2f}%）"
            if pts > best_score:
                best_score, best_detail = pts, info

    # ── 波幅分割：仅计算 HIGH↔LOW 的真实波段（排除同向对，避免大量重叠假阻力位）
    for i, pv_a in enumerate(pivots):
        for j, pv_b in enumerate(pivots):
            if i >= j:
                continue
            if pv_a.pivot_type == pv_b.pivot_type:
                continue   # 同向对无意义（HIGH-HIGH / LOW-LOW）
            hi = max(pv_a.price, pv_b.price)
            lo = min(pv_a.price, pv_b.price)
            rng = hi - lo
            if rng < 1e-6:
                continue
            ctx = f"波段[{lo:.1f}→{hi:.1f}]"
            _check(lo + 0.500 * rng, "50%回撤",  15, ctx)
            _check(lo + 0.250 * rng, "25%",       10, ctx)
            _check(lo + 0.750 * rng, "75%",       10, ctx)
            _check(lo + 0.125 * rng, "12.5%",      6, ctx)
            _check(lo + 0.875 * rng, "87.5%",      6, ctx)
            _check(lo + 0.333 * rng, "33.3%",      5, ctx)
            _check(lo + 0.375 * rng, "37.5%",      5, ctx)
            _check(lo + 0.625 * rng, "62.5%",      5, ctx)
            _check(lo + 0.667 * rng, "66.7%",      5, ctx)

    # ── 大师12图表节点（144的倍数）
    for node in sorted(_MASTER12):
        # 144循环7/8阻力
        frac_144 = (current_price % 144) / 144.0
        if abs(frac_144 - 0.875) <= 0.03:
            _check(current_price, f"144cycle_7/8({current_price:.0f})", 8, "144 cycle 7/8 of 144")
        if abs(current_price - node) / node <= _PRICE_TOL_PCT:
            _check(node, f"大师12节点({node})", 10, "144的倍数")
            break

    # S9 45deg special numbers
    s9_45deg = [7, 21, 43, 75, 111, 157, 211, 273, 343, 421, 507, 601]
    for n in s9_45deg:
        if abs(current_price - n) / max(n, 1) <= _PRICE_TOL_PCT:
            _check(float(n), f"S9_45({n})", 10, "Square of 9 45deg")

    # ── 九方图谐波（与各参考价格）
    for pv in pivots:
        is_h, deg, err_deg = _sq9_harmonic(pv.price, current_price, _SQ9_TOL_DEG)
        if is_h and deg > 0:
            pts = 12 if deg in (180, 360) else (9 if deg in (90, 270) else 6)
            # 理论谐波价位
            sqrt_ref = math.sqrt(max(pv.price, 0.01))
            sqrt_target = sqrt_ref + deg / 45.0 * 0.25
            harmonic_price = sqrt_target * sqrt_target
            price_diff = abs(current_price - harmonic_price)
            det = (f"价格 {current_price:.2f} 与 {pv} 在九方图上成 {deg}° 谐波"
                   f"（理论 {harmonic_price:.2f}，仅差 ${price_diff:.2f}）")
            if pts > best_score:
                best_score, best_detail = pts, det

    return Component("价格阻力/支撑位", min(best_score, 15), 15, best_detail)


def _score_squaring(current: date, current_price: float,
                    pivots: list) -> Component:
    """
    维度5：时价平方（max 20 分）

    Price=Time 严格字面等量（price_scale=1）：
      N 个价格点数直接对应 N 天时间，不存在换算系数。
      Scale of Prices 仅用于归一化枢轴价格数值本身，与价格移动幅度无关。
    """
    best_score, best_detail = 0, "未发现时价平方关系"

    def _reg(s: int, det: str) -> None:
        nonlocal best_score, best_detail
        if s > best_score:
            best_score, best_detail = s, det

    for pv in pivots:
        elapsed = _days(pv.date, current)
        # 排除极近期pivot（<30天），避免1×1角度线与1:1平方相互强化的自循环误报
        if elapsed < _MIN_ELAPSED_DAYS:
            continue

        price_move = abs(current_price - pv.price)

        # ── 时价1:1平方（最核心）：仅在江恩关键天数节点检测，防止45°线持续跟踪产生误报
        # price_scale=1：价格点数直接与天数比较，N点=N天
        key_day = _nearest(elapsed, _DAYS_A | _DAYS_B, _TIME_TOL_DAYS)
        # time squaring (independent)
        ts = min(8, int(25 * (1 - _TIME_TOL_DAYS / max(elapsed, 1)))) if key_day and elapsed > 0 else 0
        if ts > 0:
            _reg(ts, f"time square: {elapsed}d~{int(key_day)} key node")
        # time squaring (separate scoring)
        time_score = min(8, int(25 * (1 - _TIME_TOL_DAYS / max(elapsed, 1)))) if key_day and elapsed > 0 else 0
        if time_score > 0:
            _reg(time_score, f"time square: {elapsed}d~{int(key_day)} key node")
        if key_day and elapsed > 0:
            err = abs(price_move - elapsed) / elapsed
            if err <= _SQUARE_TOL_PCT:
                _reg(20, (f"1:1时价平方：价格移动 {price_move:.1f}点 ≈ "
                          f"{elapsed}天（距{pv}，≈{int(key_day)}关键节点，误差{err*100:.1f}%）"))

        # ── 2:1 和 1:2 平方（同样需命中关键天数）
        for ratio, label in [(2.0, "2:1"), (0.5, "1:2")]:
            if key_day and elapsed > 0:
                err = abs(price_move - elapsed * ratio) / (elapsed * ratio)
                if err <= _SQUARE_TOL_PCT:
                    _reg(13, (f"{label}时价平方：距{pv}已{elapsed}天≈{int(key_day)}（误差{err*100:.1f}%）"))

        # ── 极端价格平方（Squaring the Extreme Price）
        # Scale of Prices 将枢轴价格数值降维到1-360范围，再直接与天数比较（price_scale=1）
        sp = _scale_of_prices(pv.price)
        exp_d = sp   # 缩放后的价格数值即为预期天数（字面等量）
        if 10 < exp_d < 2000:
            err = abs(elapsed - exp_d) / exp_d
            if err <= _SQUARE_TOL_PCT:
                _reg(18, (f"极端价格平方：{pv.price:.0f}→降维{sp:.0f}，"
                          f"预测{exp_d:.0f}天 ≈ 已运行{elapsed}天（误差{err*100:.1f}%）"))

        # ── 区间平方：HIGH↔LOW 波幅点数 ≈ 已运行天数（price_scale=1，直接字面比较）
        for pv2 in pivots:
            if pv2 is pv or pv.pivot_type == pv2.pivot_type:
                continue
            price_range = abs(pv.price - pv2.price)
            if price_range > 0 and elapsed > 0:
                err = abs(elapsed - price_range) / price_range
                if err <= _SQUARE_TOL_PCT * 0.5:   # 区间平方用更严格容差（3%）
                    lo = min(pv.price, pv2.price)
                    hi = max(pv.price, pv2.price)
                    _reg(20, (f"区间平方：波幅[{lo:.0f}→{hi:.0f}]={price_range:.0f}点 "
                              f"≈ {elapsed}天（误差{err*100:.1f}%）"))

    return Component("时价平方", best_score, 20, best_detail)


def _score_angle_line(current: date, current_price: float,
                      pivots: list) -> Component:
    """
    维度6：几何角度线（max 15 分）

    price_scale=1：1×1线从枢轴出发每天移动1个价格点（字面等量）。
    理论价格 = pivot_price ± elapsed × mult
    """
    best_score, best_detail = 0, "未接近任何几何角度线"

    for pv in pivots:
        elapsed = _days(pv.date, current)
        # 排除极近期pivot，防止角度线几乎贴着pivot原价导致任意小波动都命中
        if elapsed < _MIN_ELAPSED_DAYS:
            continue

        # 从参考 pivot 拉出的各角度线
        # 1×1线要求elapsed命中关键天数（防止45°线持续跟踪产生误报）；非1×1线无此限制
        key_day = _nearest(elapsed, _DAYS_A | _DAYS_B, _TIME_TOL_DAYS)
        for mult, mult_name, pts in [
            (1.0, "1×1(45°)", 15),
            (2.0, "2×1",       8),
            (0.5, "1×2",       6),
            (4.0, "4×1",       5),
            (0.25,"1×4",       4),
        ]:
            if mult == 1.0 and not key_day:
                continue   # 1×1线非关键节点时跳过，避免45°线跟踪误报
            step = elapsed * mult   # price_scale=1：每天移动1点，直接字面等量
            for direction, sign in [("↑", +1), ("↓", -1)]:
                angle_price = pv.price + sign * step
                if angle_price <= 0:
                    continue
                err = abs(current_price - angle_price) / angle_price
                if err <= _ANGLE_TOL_PCT:
                    s = max(int(pts * (1 - err / _ANGLE_TOL_PCT * 0.4)), int(pts * 0.6))
                    det = (f"价格 {current_price:.2f} 接近从{pv}拉出的"
                           f"{mult_name}{direction}角度线（理论值{angle_price:.2f}，"
                           f"误差{err*100:.2f}%）")
                    if s > best_score:
                        best_score, best_detail = s, det

    return Component("几何角度线(1×1)", best_score, 15, best_detail)


# ══════════════════════════════════════════════════════════════════════
#  主函数
# ══════════════════════════════════════════════════════════════════════

def analyze_pivot(
    current_date:  date,
    current_price: float,
    pivots:        list,        # list[Pivot]
    price_scale:   float = 1.0, # 已废弃参数，保留以兼容旧调用，内部强制使用 price_scale=1
    grade_a:       int   = 80,  # A 级最低分
    grade_b:       int   = 55,  # B 级最低分
    grade_c:       int   = 28,  # C 级最低分
) -> PivotAnalysis:
    """
    分析当前日期/价格是否为江恩 Pivot 节点。

    参数:
        current_date:  待分析日期（应与访问者时区下的日历日期一致）
        current_price: 当日价格（收盘价或关键日内价格）
        pivots:        历史关键转折点列表（每条 Pivot.date 亦应为同一日历口径）
        price_scale:   已废弃，强制 price_scale=1（江恩 Price=Time 字面等量原则）
        grade_a/b/c:   A/B/C 级分数阈值（默认 80/55/28）

    返回:
        PivotAnalysis（含总分、等级、各维度明细）
    """
    if not pivots:
        raise ValueError("至少需要提供 1 个历史 Pivot 参考点")

    c1 = _score_seasonal(current_date)
    c2 = _score_time_counts(current_date, pivots)
    c3 = _score_anniversary(current_date, pivots)
    c4 = _score_price_levels(current_price, pivots)
    c5 = _score_squaring(current_date, current_price, pivots)
    c6 = _score_angle_line(current_date, current_price, pivots)

    components = [c1, c2, c3, c4, c5, c6]

    # ── 多维共振加成（要求更高门槛，防止多个弱信号叠加虚报高分）
    sig_high = [c for c in components if c.max_score > 0 and c.score / c.max_score >= 0.55]
    sig_low  = [c for c in components if c.max_score > 0 and c.score / c.max_score >= 0.40]
    n_sig  = len(sig_high)
    n_sig2 = len(sig_low)
    bonus = 10 if n_sig >= 3 else (4 if n_sig2 >= 3 else 0)
    bonus_detail = (f"★ {n_sig}/{n_sig2}维度共振加成: +{bonus}分" if bonus else "")

    raw   = sum(c.score for c in components) + bonus
    total = min(round(raw), 100)

    if total >= grade_a:
        grade = "A"; prob = "极高（三维以上强共振，历史级别反转概率显著）"
    elif total >= grade_b:
        grade = "B"; prob = "较高（双维度共振，次级波段转折可能，等待形态确认）"
    elif total >= grade_c:
        grade = "C"; prob = "中等（单维度预警，保持观察）"
    else:
        grade = "-"; prob = "低（无显著共振，正常波动，不建议逆势操作）"

    triggered = [c.detail for c in components if c.score > 0]
    if bonus_detail:
        triggered.append(bonus_detail)

    warning = (
        "⚠️  入场前务必确认形态读取（W底/M顶/突破点）；"
        "止损设在入场价 3 点以内；单笔风险 ≤ 总资本 10%。"
    )

    return PivotAnalysis(
        current_date=current_date,
        current_price=current_price,
        total_score=total,
        grade=grade,
        probability=prob,
        components=components,
        triggered=triggered,
        warning=warning,
    )


# ══════════════════════════════════════════════════════════════════════
#  前向扫描：预测未来共振窗口
# ══════════════════════════════════════════════════════════════════════

def scan_future_pivots(
    pivots:       list,          # list[Pivot]
    price_scale:  float = 1.0,   # 已废弃，内部强制 price_scale=1（Price=Time 字面等量）
    start_date:   date   = None,
    days_ahead:   int    = 180,
    min_score:    int    = 18,
    cluster_days: int    = 6,
    max_zone_width: int = 10,    # 单个窗口最宽天数（防止事件链式合并）
    grade_a:      int    = 80,
    grade_b:      int    = 55,
    calendar_tz:  Optional[str] = None,
) -> list:
    """
    向前扫描 days_ahead 天，预测 Gann 共振窗口。

    calendar_tz: 当 start_date 未传入时，用此时区的“今天”作为扫描起点；传入 start_date 时不起作用。

    评分逻辑
    ────────
    • 时间维度（确定性）：季节节点 / 时间计数 / 周年纪念  ← 与 analyze_pivot 完全一致
    • 价格维度（投影）  ：从各 Pivot 拉出 1×1 角度线，检查（price_scale=1，每天1点）
        – 上升线 ↑ 与下降线 ↓ 在该日期交叉（最重要，角度线交叉理论）
        – 同向线收敛（两条上升线或两条下降线价格相近）
        – 投影价格碰到已知波幅分割位（50%/25%/75%/Master12）
        – 时间计数恰好是关键 Gann 数字（佐证平方关系）

    返回: 按得分降序排列的 FutureZone 列表
    """
    if start_date is None:
        if calendar_tz:
            try:
                start_date = datetime.now(ZoneInfo(calendar_tz)).date()
            except Exception:
                start_date = date.today()
        else:
            start_date = date.today()

    # ── Step 1: 逐日打分
    daily = []

    for offset in range(1, days_ahead + 1):
        fdate = start_date + timedelta(days=offset)

        # 时间维度得分（完全确定）
        c_sea  = _score_seasonal(fdate)
        c_time = _score_time_counts(fdate, pivots)
        c_ann  = _score_anniversary(fdate, pivots)
        time_sub = c_sea.score + c_time.score + c_ann.score

        # 角度线投影
        up_lines   = []   # (Pivot, projected_price)  ← from LOW
        down_lines = []   # (Pivot, projected_price)  ← from HIGH
        for pv in pivots:
            elapsed = (fdate - pv.date).days
            if elapsed <= 0:
                continue
            if pv.pivot_type == "LOW":
                up_lines.append((pv, pv.price + elapsed))   # price_scale=1，每天1点
            elif pv.pivot_type == "HIGH":
                proj = pv.price - elapsed                    # price_scale=1，每天1点
                if proj > 0:
                    down_lines.append((pv, proj))

        all_lines = up_lines + down_lines

        # 角度线交叉（上升线 ↑ 遇到下降线 ↓）—— 最高权重
        conv_score     = 0
        conv_desc      = ""
        crossing_prices: list = []
        for pv_u, p_u in up_lines:
            for pv_d, p_d in down_lines:
                diff = abs(p_u - p_d) / max(p_u, p_d, 0.001)
                if diff <= 0.015:
                    cp = (p_u + p_d) / 2
                    crossing_prices.append(cp)
                    if conv_score < 20:
                        conv_score = 20
                        conv_desc  = (
                            f"↑{pv_u.price:.0f} × ↓{pv_d.price:.0f} "
                            f"交叉于 {cp:.2f}（差 {diff*100:.1f}%）"
                        )
                elif diff <= 0.04:
                    crossing_prices.append((p_u + p_d) / 2)
                    if conv_score < 11:
                        conv_score = 11
                        conv_desc  = (
                            f"↑{pv_u.price:.0f} 接近 ↓{pv_d.price:.0f}（差 {diff*100:.1f}%）"
                        )

        # 同向线收敛（例如两个不同低点拉出的上升线价格接近）
        for group in [up_lines, down_lines]:
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    _, pi = group[i];  _, pj = group[j]
                    diff = abs(pi - pj) / max(pi, pj, 0.001)
                    if diff <= 0.012 and conv_score < 8:
                        conv_score = 8
                        conv_desc  = f"同向角度线收敛于 {(pi+pj)/2:.2f}（差 {diff*100:.1f}%）"

        # 投影价格碰到已知波幅分割位
        level_score = 0
        for _, proj_p in all_lines:
            if proj_p > 0:
                ls = _score_price_levels(proj_p, pivots)
                level_score = max(level_score, min(ls.score, 12))

        # 时间计数关键节点 + 三种时价平方加成
        sq_bonus   = 0
        sq_factors = []
        for pv in pivots:
            elapsed = (fdate - pv.date).days
            if elapsed <= 0:
                continue

            # A: 关键天数节点
            if _nearest(elapsed, _DAYS_A, _TIME_TOL_DAYS):
                if sq_bonus < 8:
                    sq_bonus = 8
                    sq_factors.append(f"关键天数节点 {elapsed}d")
            elif _nearest(elapsed, _DAYS_B, _TIME_TOL_DAYS):
                if sq_bonus < 4:
                    sq_bonus = 4

            # B: 极端价格多周期平方（price_scale=1，sp 即为预期天数/周数/月数）
            sp = _scale_of_prices(pv.price)

            # B1 日线：Scale of Prices 降维后直接与天数比较（price_scale=1）
            exp_d = sp   # 降维后的数值即为预期天数
            if exp_d > 0:
                err = abs(elapsed - exp_d) / exp_d
                if err <= _SQUARE_TOL_PCT and sq_bonus < 12:
                    sq_bonus = 12
                    sq_factors.append(
                        f"日线极端价格平方: {pv.price:.0f}→降维{sp:.0f}天"
                        f" @{elapsed}d (误差{err*100:.1f}%)"
                    )

            # B2 周线：sp 作为周数，× 7 转换为天数
            exp_w = sp * _WEEK_DAYS
            if 20 < exp_w < 1200:
                err = abs(elapsed - exp_w) / exp_w
                if err <= _SQUARE_TOL_PCT and sq_bonus < 10:
                    sq_bonus = 10
                    sq_factors.append(
                        f"周线极端价格平方: {pv.price:.0f}→{sp:.0f}周"
                        f"(≈{exp_w:.0f}天) @{elapsed}d (误差{err*100:.1f}%)"
                    )

            # B3 月线：sp 作为月数，× 30.44 转换为天数
            exp_m = sp * _MONTH_DAYS
            if 20 < exp_m < 1200:
                err = abs(elapsed - exp_m) / exp_m
                if err <= _SQUARE_TOL_PCT and sq_bonus < 8:
                    sq_bonus = 8
                    sq_factors.append(
                        f"月线极端价格平方: {pv.price:.0f}→{sp:.0f}月"
                        f"(≈{exp_m:.0f}天) @{elapsed}d (误差{err*100:.1f}%)"
                    )

            # C: 区间平方：HIGH↔LOW 波幅点数直接与天数比较（price_scale=1）
            for pv2 in pivots:
                if pv2 is pv or pv.pivot_type == pv2.pivot_type:
                    continue
                rng = abs(pv.price - pv2.price)
                if rng > 0:
                    err = abs(elapsed - rng) / rng   # 点数直接等于天数（字面等量）
                    if err <= _SQUARE_TOL_PCT:
                        if sq_bonus < 10:
                            sq_bonus = 10
                            lo, hi = min(pv.price, pv2.price), max(pv.price, pv2.price)
                            sq_factors.append(
                                f"区间平方: [{lo:.0f}→{hi:.0f}]={rng:.0f}pts"
                                f" ≈ {elapsed}d (误差{err*100:.1f}%)"
                            )

        # 时间多维共振加成（3个时间维度全部达到55%方可获得最高加成）
        n_tsig_h = sum(1 for c in [c_sea, c_time, c_ann] if c.max_score > 0 and c.score / c.max_score >= 0.55)
        n_tsig_l = sum(1 for c in [c_sea, c_time, c_ann] if c.max_score > 0 and c.score / c.max_score >= 0.40)
        n_tsig = n_tsig_h
        bonus = 10 if n_tsig_h >= 3 else (4 if n_tsig_l >= 3 else 0)

        total = min(round(time_sub + conv_score + level_score + sq_bonus + bonus), 100)

        if total < min_score:
            continue

        # 触发因素
        triggered = []
        for c, label in [(c_sea, "季节"), (c_time, "时间计数"), (c_ann, "周年")]:
            if c.score > 0:
                triggered.append(f"[{label}] {c.detail}")
        if conv_desc:
            triggered.append(f"[角度线] {conv_desc}")
        if level_score > 0:
            triggered.append(f"[价格位] 投影价格命中已知阻力/支撑（{level_score:.0f}分）")
        if sq_bonus > 0:
            detail = sq_factors[0] if sq_factors else "时间计数关键节点"
            triggered.append(f"[平方] {detail} +{sq_bonus}分")
        if bonus > 0:
            triggered.append(f"[共振] {n_tsig}维时间共振加成 +{bonus}分")

        daily.append({
            "date":            fdate,
            "total":           total,
            "time_sub":        time_sub,
            "lines":           all_lines,
            "crossing_prices": crossing_prices,
            "conv_desc":       conv_desc,
            "triggered":       triggered,
        })

    if not daily:
        return []

    # ── Step 2: 聚合邻近日期为窗口（限制最大宽度，防止不同事件链式合并）
    zones_raw = [[daily[0]]]
    zone_start_date = daily[0]["date"]

    for entry in daily[1:]:
        prev_date = zones_raw[-1][-1]["date"]
        gap       = (entry["date"] - prev_date).days
        width     = (entry["date"] - zone_start_date).days
        if gap <= cluster_days and width <= max_zone_width:
            zones_raw[-1].append(entry)
        else:
            zones_raw.append([entry])
            zone_start_date = entry["date"]

    # ── Step 3: 汇总每个窗口
    result = []
    for zone in zones_raw:
        best          = max(zone, key=lambda x: x["total"])
        all_dates     = [e["date"] for e in zone]
        all_crossings = [p for e in zone for p in e.get("crossing_prices", []) if p > 0]
        all_proj      = [p for e in zone for _, p in e["lines"] if p > 0]

        if all_crossings:
            # Prefer angle-line crossing prices — they are the actual predicted price
            price_zone = (round(min(all_crossings), 2), round(max(all_crossings), 2))
        elif all_proj:
            # Fallback: use interquartile range to avoid extreme outliers
            sp = sorted(all_proj)
            n  = len(sp)
            lo = sp[n // 4];  hi = sp[3 * n // 4]
            inner = [p for p in sp if lo <= p <= hi]
            price_zone = (round(min(inner), 2), round(max(inner), 2)) if inner else (round(sp[0], 2), round(sp[-1], 2))
        else:
            price_zone = (0.0, 0.0)
        grade = "A" if best["total"] >= grade_a else "B" if best["total"] >= grade_b else "C"

        result.append(FutureZone(
            peak_date        = best["date"],
            date_range       = (min(all_dates), max(all_dates)),
            grade            = grade,
            score            = best["total"],
            time_score       = best["time_sub"],
            price_zone       = price_zone,
            convergence_desc = best["conv_desc"],
            triggered        = best["triggered"],
        ))

    return sorted(result, key=lambda x: -x.score)


# ══════════════════════════════════════════════════════════════════════
#  格式化输出
# ══════════════════════════════════════════════════════════════════════

def print_analysis(a: PivotAnalysis) -> None:
    W = 64
    grade_icons = {"A": "🔴", "B": "🟡", "C": "🟢", "-": "⬜"}

    print("\n" + "═" * W)
    print(f"  江恩 Pivot Day 评分报告")
    print(f"  分析日期: {a.current_date}   参考价格: {a.current_price:,.2f}")
    print("═" * W)

    score_bar_len = int(a.total_score / 100 * 30)
    score_bar = "█" * score_bar_len + "░" * (30 - score_bar_len)
    grade_text = {
        "A": "A级 ─ 极高概率反转",
        "B": "B级 ─ 高概率反转",
        "C": "C级 ─ 重要预警",
        "-": "无显著信号",
    }[a.grade]

    print(f"  总评分  [{score_bar}] {a.total_score:>3}/100")
    print(f"  等  级  {grade_icons[a.grade]}  {grade_text}")
    print(f"  概  率  {a.probability}")
    print("─" * W)
    print("  各维度得分:")

    for c in a.components:
        if c.max_score > 0:
            ratio = c.score / c.max_score
            filled = int(ratio * 14)
            bar = "█" * filled + "░" * (14 - filled)
            flag = " ★" if ratio >= 0.5 else ("  " if ratio > 0 else "  ")
            print(f"  [{bar}] {c.score:4.0f}/{c.max_score:.0f}  {c.name}{flag}")
            if c.score > 0:
                print(f"          → {c.detail}")

    if a.triggered:
        print("─" * W)
        print("  触发因素汇总:")
        for t in a.triggered:
            print(f"    • {t}")

    print("─" * W)
    print(f"  {a.warning}")
    print("═" * W + "\n")


# ══════════════════════════════════════════════════════════════════════
#  示例
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":

    print("\n" + "#" * 64)
    print("  Example 1: SPX (S&P 500) -- Autumn Equinox + key level")
    print("#" * 64)

    spx_pivots = [
        Pivot(date(2022, 10, 13), 3492.0, "LOW"),   # 熊市低点
        Pivot(date(2023, 10, 27), 4103.0, "LOW"),   # 近期重要低点
        Pivot(date(2024,  7, 16), 5669.7, "HIGH"),  # 近期高点
    ]
    r1 = analyze_pivot(
        current_date  = date(2024, 9, 22),   # 秋分
        current_price = 5250.0,
        pivots        = spx_pivots,
        # price_scale 已废弃，内部强制 price_scale=1（江恩 Price=Time 字面等量）
    )
    print_analysis(r1)

    print("#" * 64)
    print("  Example 2: Stock -- 144-day window + 50% retracement")
    print("#" * 64)

    stock_pivots = [
        Pivot(date(2024, 1, 15), 120.0, "HIGH"),
        Pivot(date(2024, 4,  8),  80.0, "LOW"),
    ]
    # 从低点起算第 144 天 = 2024-09-28
    r2 = analyze_pivot(
        current_date  = date(2024, 9, 28),  # 距LOW点约144天
        current_price = 100.0,              # 恰好是 [80→120] 的 50% = 100
        pivots        = stock_pivots,
    )
    print_analysis(r2)

    print("#" * 64)
    print("  Example 3: Weak-signal day -- no resonance")
    print("#" * 64)

    r3 = analyze_pivot(
        current_date  = date(2024, 8, 22),
        current_price = 3350.0,
        pivots        = [Pivot(date(2024, 5, 10), 3100.0, "LOW")],
    )
    print_analysis(r3)
