"""Two-parameter Weibull maximum likelihood with exact, interval and right-censored observations."""
import math
import random
import numpy as np
from scipy.optimize import minimize

MAX_KM = 10_000_000.0
KIND_LABELS = {"exact": "精确失效", "interval": "巡检区间失效", "censored": "在役（右删失）"}


def metadata():
    return {
        "name": "车队部件寿命估计", "short": "fleet-weibull", "tagline": "保留在役与巡检区间，用删失似然估计预防检修窗口",
        "client": "模拟客户：鹭湾公交机务组，96 辆公交车跟踪两种空气压缩机。",
        "workflow": "机务组每月导出更换与巡检记录：失效件往往只知道在哪两次检查之间坏了，在役件只知道截止里程。",
        "pains": ["巡检只知道部件在哪两次检查之间坏了，把发现里程当故障点会推迟检修", "只看坏件会丢掉在役件的寿命信息", "不同压缩机型号被混在一个均值内", "检修里程未表达可靠度假设"],
        "upstream": "部件安装里程、两次检查之间的失效区间、精确失效里程与截止日仍在役里程", "downstream": "机务检修评审，人工结合安全规程安排检查。",
        "entities": ["部件寿命样本", "可靠度估计", "机务简报计划"], "dataset_name": "鹭湾公交_压缩机寿命与在役截止.csv",
        "columns": [
            {"key": "asset", "label": "部件资产号", "type": "string"},
            {"key": "model", "label": "型号", "type": "string"},
            {"key": "km", "label": "发现失效/截止在役里程", "type": "number"},
            {"key": "km_lower", "label": "上次检查确认正常里程（可选）", "type": "number", "required": False},
            {"key": "failed", "label": "已失效1/在役0", "type": "number"},
        ],
        "parameters": [{"key": "model", "label": "部件型号", "type": "select", "default": "AC-8", "options": [{"value": "AC-8", "label": "AC-8 螺杆机"}, {"value": "AC-12", "label": "AC-12 改进型"}]}, {"key": "reliability", "label": "目标可靠度", "type": "number", "default": 0.9, "min": 0.6, "max": 0.99}],
        "workbench_title": "删失样本与检修可靠度", "action_label": "拟合寿命曲线", "unit": "公里", "accent": "oklch(51% 0.13 35)", "style": "fleet-chart",
        "seed_story": ["08:00 导入鹭湾公交_压缩机寿命与在役截止.csv，200件部件、206条记录（含同件复检）。", "08:20 对照资产编号确认 failed=0 是截止仍在役，不是零寿命。", "08:40 巡检只确认失效落在两次检查之间，录入上次检查里程，不把发现里程当故障点。", "09:00 选择 AC-8，目标可靠度设为0.90。", "09:15 执行含右删失与巡检区间的Weibull极大似然估计。", "09:30 查看形状参数、B10寿命和目标可靠度里程。", "10:00 切到AC-12独立拟合，避免混合型号。", "11:00 对区间仍偏宽的部件补报复检区间，生成新版本，旧版本区间与批准状态不变。", "14:00 将曲线与样本结构提交机务评审，并创建本地分发记录。"],
        "method": "独立删失条件下，精确失效用f(t)，在役件用S(t)，巡检只知区间时用S(下界)−S(上界)进入似然；S(t)=exp[−(t/η)^β]。同一资产的多条故障记录先取区间交集。在logβ/logη空间求极大似然；目标里程t=η[−ln R]^(1/β)。",
        "limitations": ["假设独立删失和同质运行工况，未纳入线路、载荷、批次等协变量。", "巡检区间按区间内发生失效的概率计似然，未把发现里程当作故障点；区间越宽，估计越依赖巡检间隔。", "里程阈值是样本模型估计，不替代厂家安全规范，也未包含参数置信区间。"],
    }


def seed_records():
    rng = random.Random(1017)
    rows = []
    for model, scale, shape in (("AC-8", 88000, 2.4), ("AC-12", 116000, 1.8)):
        for index in range(100):
            failure = rng.weibullvariate(scale, shape)
            cutoff = rng.uniform(35000, 145000)
            if failure > cutoff:
                rows.append({"asset": f"{model}-{index+1:03}", "model": model, "km": round(cutoff, 1), "failed": 0})
                continue
            # 六成失效在巡检中才发现：只知上次检查正常、本次检查已坏，不把发现里程当故障点。
            if rng.random() < 0.6:
                interval = rng.uniform(15000, 30000)
                phase = rng.uniform(0, interval)
                found = math.ceil((failure - phase) / interval) * interval + phase
                lower = max(0.0, found - interval)
                rows.append({"asset": f"{model}-{index+1:03}", "model": model, "km": round(found, 1), "km_lower": round(lower, 1), "failed": 1})
            else:
                rows.append({"asset": f"{model}-{index+1:03}", "model": model, "km": round(failure, 1), "failed": 1})
    # 每个型号各三次复检回报：同一资产新增一条故障记录，合并时取区间交集，而不是各算一件或取发现里程。
    for model in ("AC-8", "AC-12"):
        repeated = [row for row in rows if row["model"] == model and row.get("km_lower", 0) and row["failed"] == 1][:3]
        for row in repeated:
            lower, upper = row["km_lower"], row["km"]
            width = upper - lower
            rows.append({"asset": row["asset"], "model": row["model"], "km": round(upper - width * 0.2, 1), "km_lower": round(lower + width * 0.4, 1), "failed": 1})
    return rows


def _number(value, message):
    try:
        if isinstance(value, bool):
            raise ValueError
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(message) from None
    if not math.isfinite(number):
        raise ValueError(message)
    return number


def merge_observations(records):
    """Merge raw rows by asset. Multiple fault rows keep the intersection of their intervals."""
    if not isinstance(records, list) or not records:
        raise ValueError("请先提供含失效标记的部件寿命样本")
    groups, order = {}, []
    for index, row in enumerate(records):
        if not isinstance(row, dict):
            raise ValueError(f"第 {index + 1} 行不是有效记录")
        asset = str(row.get("asset") or "").strip()
        model = str(row.get("model") or "").strip()
        if not asset:
            raise ValueError(f"第 {index + 1} 行缺少部件资产号")
        upper = _number(row.get("km"), f"第 {index + 1} 行须有1至1000万公里的发现失效/截止在役里程")
        failed = _number(row.get("failed"), f"第 {index + 1} 行的失效标记只能是0或1")
        if not 1 <= upper <= MAX_KM:
            raise ValueError(f"第 {index + 1} 行里程须为1至1000万公里")
        if failed not in (0.0, 1.0):
            raise ValueError(f"第 {index + 1} 行的失效标记只能是0或1")
        if not model:
            raise ValueError(f"第 {index + 1} 行缺少部件型号")
        lower = None
        raw_lower = row.get("km_lower")
        if raw_lower not in (None, ""):
            if failed == 0:
                raise ValueError(f"第 {index + 1} 行是在役件，不应填写失效区间下界")
            lower = _number(raw_lower, f"第 {index + 1} 行的上次检查里程须为数值")
            if not 0 <= lower <= upper:
                raise ValueError(f"第 {index + 1} 行的上次检查里程须在0与发现失效里程之间")
        group = groups.get(asset)
        if group is None:
            group = {"asset": asset, "model": model, "rows": []}
            groups[asset] = group
            order.append(asset)
        elif group["model"] != model:
            raise ValueError(f"资产 {asset} 的记录型号不一致（{group['model']} / {model}），整批退回")
        group["rows"].append({"upper": upper, "lower": lower, "failed": int(failed)})
    observations = []
    for asset in order:
        group = groups[asset]
        faults = [row for row in group["rows"] if row["failed"] == 1]
        alive = [row for row in group["rows"] if row["failed"] == 0]
        if faults and alive:
            raise ValueError(f"资产 {asset} 同时存在失效与在役记录，无法合并，整批退回")
        if alive:
            observations.append({"asset": asset, "model": group["model"], "kind": "censored", "lower": None, "upper": max(row["upper"] for row in alive), "sources": len(alive)})
            continue
        lower = max((row["lower"] if row["lower"] is not None else row["upper"]) for row in faults)
        upper = min(row["upper"] for row in faults)
        if lower > upper:
            raise ValueError(f"资产 {asset} 的故障区间交集为空（下界 {lower:,.0f} 公里 > 上界 {upper:,.0f} 公里），整批退回")
        if lower == upper:
            observations.append({"asset": asset, "model": group["model"], "kind": "exact", "lower": None, "upper": upper, "sources": len(faults)})
        else:
            observations.append({"asset": asset, "model": group["model"], "kind": "interval", "lower": lower, "upper": upper, "sources": len(faults)})
    return observations


def apply_supplements(observations, supplements):
    """Narrow observations with supplement reports. Each supplement must intersect and narrow."""
    result = [dict(item) for item in observations]
    index = {item["asset"]: item for item in result}
    flat = []
    for batch in supplements or []:
        flat.extend(batch if isinstance(batch, list) else [batch])
    for supplement in flat:
        asset = str(supplement.get("asset") or "").strip()
        current = index.get(asset)
        if current is None:
            raise ValueError(f"补报资产 {asset} 不在数据批次中")
        if current["kind"] == "censored":
            raise ValueError(f"资产 {asset} 在批次中仍在役，不能补报失效区间")
        lower = _number(supplement.get("lower_km"), f"资产 {asset} 的补报下界须为有限数值")
        upper = _number(supplement.get("upper_km"), f"资产 {asset} 的补报上界须为有限数值")
        if not 0 <= lower <= upper <= MAX_KM:
            raise ValueError(f"资产 {asset} 的补报区间须为0至1000万公里且下界不大于上界")
        current_lower = current["lower"] if current["kind"] == "interval" else current["upper"]
        current_upper = current["upper"]
        merged_lower = max(current_lower, lower)
        merged_upper = min(current_upper, upper)
        if merged_lower > merged_upper:
            raise ValueError(f"资产 {asset} 的补报区间与现有估计区间无交集")
        if merged_lower == current_lower and merged_upper == current_upper:
            raise ValueError(f"资产 {asset} 的补报没有收窄现有区间")
        if merged_lower == merged_upper:
            current.update({"kind": "exact", "lower": None, "upper": merged_upper})
        else:
            current.update({"kind": "interval", "lower": merged_lower, "upper": merged_upper})
        current["supplements"] = int(current.get("supplements", 0)) + 1
    return result


def _log_one_minus_exp(value):
    # log(1 - exp(-value)) for value > 0, stable for both small and large values
    if value > 0.6931471805599453:
        return math.log1p(-math.exp(-value))
    return math.log(-math.expm1(-value))


def analyze(records, params, supplements=None):
    if not isinstance(records, list) or not records:
        raise ValueError("请先提供含失效标记的部件寿命样本")
    model_name = str(params.get("model", "AC-8"))
    try:
        reliability = float(params.get("reliability", 0.9))
    except (ValueError, TypeError):
        raise ValueError("目标可靠度必须是数值") from None
    if not math.isfinite(reliability) or not 0.6 <= reliability <= 0.99:
        raise ValueError("目标可靠度须介于0.6和0.99")
    observations = apply_supplements(merge_observations(records), supplements)
    selected = [item for item in observations if item["model"] == model_name]
    kinds = np.array([item["kind"] for item in selected], dtype=object)
    uppers = np.array([item["upper"] for item in selected], dtype=float)
    lowers = np.array([item["lower"] if item["lower"] is not None else 0.0 for item in selected], dtype=float)
    failures = int(np.sum(kinds != "censored"))
    if len(selected) < 25 or failures < 10:
        raise ValueError("所选型号至少需要25件样本和10件已失效样本")
    log_uppers = np.log(uppers)
    interval_mask = kinds == "interval"
    exact_mask = kinds == "exact"
    other_mask = ~interval_mask

    def objective(theta):
        shape, scale = np.exp(theta)
        log_scale = math.log(scale)
        powers = np.exp(np.clip(shape * (log_uppers - log_scale), -600, 600))
        total = float(np.sum(powers[other_mask]))
        if interval_mask.any():
            safe_lowers = np.maximum(lowers[interval_mask], 1e-9)
            lower_powers = np.exp(np.clip(shape * (np.log(safe_lowers) - log_scale), -600, 600))
            total += float(np.sum(lower_powers))
            gaps = np.maximum(powers[interval_mask] - lower_powers, 1e-12)
            total -= float(np.sum([_log_one_minus_exp(float(gap)) for gap in gaps]))
        if exact_mask.any():
            log_density = math.log(shape) - shape * log_scale + (shape - 1) * log_uppers[exact_mask]
            total -= float(np.sum(log_density))
        return total

    solution = minimize(objective, np.log([1.8, float(np.median(uppers)) * 1.3]), method="L-BFGS-B", bounds=[(math.log(0.1), math.log(15)), (math.log(float(uppers.min()) * 0.1), math.log(float(uppers.max()) * 100))])
    if not solution.success or not math.isfinite(float(solution.fun)):
        raise ValueError("寿命似然未收敛，请检查样本或增加失效观测")
    shape, scale = [float(value) for value in np.exp(solution.x)]
    b10 = scale * (-math.log(0.9)) ** (1 / shape)
    threshold = scale * (-math.log(reliability)) ** (1 / shape)
    mean_life = scale * math.gamma(1 + 1 / shape)
    levels = sorted({0.99, 0.95, 0.9, 0.8, 0.7, reliability}, reverse=True)
    rows = [{"reliability": round(level, 4), "km": round(scale * (-math.log(level)) ** (1 / shape), 1), "failed_pct": round((1-level)*100, 2), "target": "本次目标" if level == reliability else "参考水平"} for level in levels]
    chart_x = np.linspace(0, float(uppers.max()) * 1.2, 41)
    curve = [round(math.exp(-(float(value) / scale) ** shape) * 100, 4) for value in chart_x]
    counts = {kind: int(np.sum(kinds == kind)) for kind in ("exact", "interval", "censored")}
    warnings = []
    if counts["censored"] / len(selected) > 0.6:
        warnings.append("超过60%的样本仍在役，尾部寿命外推不稳定。")
    if threshold > float(uppers.max()):
        warnings.append("目标可靠度里程超过最大观测里程，属于外推。")
    if shape < 0.11 or shape > 14.9:
        warnings.append("形状参数接近优化边界，当前二参数假设可能不适合数据。")
    wide = [item for item in selected if item["kind"] == "interval" and item["upper"] > 0 and (item["upper"] - item["lower"]) / item["upper"] > 0.5]
    if wide:
        warnings.append(f"{len(wide)} 件失效只知道较宽的检查区间（超过观测里程的一半），估计依赖巡检间隔，建议缩短检查周期或补报。")
    observation_rows = [{"asset": item["asset"], "model": item["model"], "kind": item["kind"], "kind_label": KIND_LABELS[item["kind"]], "lower": None if item["lower"] is None else round(item["lower"], 1), "upper": round(item["upper"], 1), "sources": int(item.get("sources", 1)), "supplements": int(item.get("supplements", 0))} for item in selected]
    return {
        "summary": f"{model_name}的{len(selected)}件样本含{counts['exact']}件精确失效、{counts['interval']}件巡检区间失效、{counts['censored']}件右删失；目标可靠度{reliability:.0%}对应运行里程约{threshold:,.0f}公里。",
        "metrics": [{"label": "形状参数β", "value": round(shape, 4)}, {"label": "尺度参数η", "value": round(scale, 1), "unit": "公里"}, {"label": "B10寿命", "value": round(b10, 1), "unit": "公里"}, {"label": "目标可靠度里程", "value": round(threshold, 1), "unit": "公里"}],
        "table": {"columns": [{"key": "reliability", "label": "可靠度R"}, {"key": "km", "label": "运行里程"}, {"key": "failed_pct", "label": "累计失效概率%"}, {"key": "target", "label": "用途"}], "rows": rows},
        "chart": {"type": "line", "labels": [str(round(float(value))) for value in chart_x], "series": [{"name": "仍正常运行概率%", "values": curve}]},
        "observations": observation_rows,
        "sample_mix": counts,
        "findings": [f"β={shape:.3f}，{'提示随里程增加的磨损趋势' if shape > 1 else '提示早期失效或近似恒定风险，应检查样本同质性'}；这不是因果判断。", f"模型平均寿命为{mean_life:,.0f}公里；均值不等于预防检修推荐里程。", f"在役件贡献生存概率，不被错误当成已失效件；删失比例{counts['censored']/len(selected):.1%}。" + (f"另有{counts['interval']}件只知道失效落在巡检区间内，按区间内失效的概率计似然，发现里程没有当作故障点。" if counts["interval"] else "")],
        "method": metadata()["method"], "warnings": warnings,
    }
