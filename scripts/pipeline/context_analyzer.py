# -*- coding: utf-8 -*-
"""
pipeline/context_analyzer.py - 叙事语境分析器
包含：
1. 章节结尾模式与连续独白探测 (detect_ending_pattern / detect_monologue_ending_streak)
2. 沉寂伏笔与未决因果主动唤醒探针 (detect_dormant_foreshadowing)
3. 留存策略自适应分段匹配 (get_retention_strategy)
"""

import os
import re
import json
from typing import Dict, Any, List, Optional


def detect_ending_pattern(text: str) -> str:
    """检测章节结尾的模式类型，返回 'monologue' 或 'other'"""
    if not text:
        return "other"
    tail = text[-200:]
    monologue_keywords = [
        r"这一世[，,]", r"这辈子[，,]", r"连本带利", r"一样一样.*拿回来",
        r"不会让.{1,4}成", r"会付出代价", r"他在心[里中].*[：:]",
        r"他对自己说", r"一个字一个字.*咀嚼", r"绝不会再", r"该还的",
        r"他攥紧", r"全吐出来",
    ]
    monologue_count = 0
    for kw in monologue_keywords:
        if re.search(kw, tail):
            monologue_count += 1
    return "monologue" if monologue_count >= 2 else "other"


def detect_monologue_ending_streak(
    novel_dir: str,
    ch_prefix: str,
    ch_suffix: str,
    chapter_num: int
) -> int:
    """检测连续内心独白宣言结尾的次数"""
    streak = 0
    for ch in range(chapter_num - 1, 0, -1):
        target_file = None
        for d in [os.path.join(novel_dir, "正文"), novel_dir]:
            p = os.path.join(d, f"{ch_prefix}第{ch}章{ch_suffix}")
            if os.path.exists(p):
                target_file = p
                break
        if not target_file:
            break
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                text = f.read()
            if detect_ending_pattern(text) == "monologue":
                streak += 1
            else:
                break
        except Exception:
            break
    return streak


def detect_dormant_foreshadowing(
    state_json_str: str,
    current_chapter: int,
    novel_dir: str = ""
) -> str:
    """分析状态快照与知识图谱，生成沉寂伏笔与未决因果主动唤醒提醒（双轨探针机制）"""
    alerts = []
    # 1. 扫描状态文件中的 plot_threads
    if state_json_str and state_json_str.strip() not in ("", "{}", "null"):
        try:
            data = json.loads(state_json_str)
            threads = data.get("plot_threads", {})
            for name, info in threads.items():
                if not isinstance(info, dict):
                    continue
                st = info.get("state", "in_progress")
                if st in ("resolved", "closed"):
                    continue
                last_ch = None
                if "last_progress" in info:
                    m = re.search(r"第?(\d+)章?", str(info["last_progress"]))
                    if m:
                        last_ch = int(m.group(1))
                if last_ch is None and "planted" in info:
                    m = re.search(r"第?(\d+)章?", str(info["planted"]))
                    if m:
                        last_ch = int(m.group(1))
                if last_ch and (current_chapter - last_ch) >= 15:
                    gap = current_chapter - last_ch
                    desc = info.get("desc", name)
                    alerts.append(f"- 伏笔【{name}】（第{last_ch}章埋下，已沉寂 {gap} 章）：{desc} ➔ 建议适时回收或推进")
        except Exception:
            pass

    # 2. 扫描 SQLite 知识图谱中的未闭环因果 (unresolved causal hooks)
    if novel_dir:
        try:
            from storage.knowledge_graph import get_knowledge_graph
            kg = get_knowledge_graph(novel_dir)
            if kg and hasattr(kg, "query_unresolved_causal_hooks"):
                unresolved = kg.query_unresolved_causal_hooks(current_chapter=current_chapter, min_gap=10)
                if unresolved:
                    for h in unresolved:
                        alerts.append(f"- 剧情伏线【{h.get('name', '未命名')}】（已沉寂 {h.get('gap', 10)} 章）：{h.get('desc', '')} ➔ 需在本章或临近章节做出物理反应")
        except Exception:
            pass

    if not alerts:
        return "（当前无长时间沉寂的紧急伏笔，按大纲规划推进即可）"
    return "\n".join(alerts)


def detect_action_prop_streak(
    novel_dir: str,
    chapter_num: int,
    cfg: Dict[str, Any],
    ch_prefix: str = "C_正文_第",
    ch_suffix: str = "章.md"
) -> str:
    """
    微观动作与道具跨章动态冷却节流器 (Action Cooldown Throttle):
    扫描前 1~2 章正文文本，若检测到某测量工具或生理质感动作连续高频出现，
    自动生成本章禁用提示并从 action_pool_registry 提取替代动作建议。
    """
    if chapter_num <= 1 or not novel_dir or not os.path.exists(novel_dir):
        return ""

    prev_texts = []
    for ch in range(chapter_num - 1, max(0, chapter_num - 3), -1):
        target_file = None
        for d in [os.path.join(novel_dir, "正文"), novel_dir]:
            p = os.path.join(d, f"{ch_prefix}{ch}{ch_suffix}")
            if os.path.exists(p):
                target_file = p
                break
        if target_file:
            try:
                with open(target_file, "r", encoding="utf-8") as f:
                    prev_texts.append((ch, f.read()))
            except Exception:
                pass

    if not prev_texts:
        return ""

    registry = cfg.get("action_pool_registry", {})
    tools = registry.get("measurement_tools", [
        {"name": "骨质游标卡尺", "action": "指腹推移游标卡尺测爪，核对公差刻槽"},
        {"name": "重力铅锤垂线", "action": "悬起麻绳重力铅锤，微调立柱垂直度"},
        {"name": "自磨气泡水平管", "action": "水准管气泡在两条红线间轻微晃动，校准基座沉降"},
        {"name": "划针与红松炭条", "action": "执起钢划针在冷铁皮上划出规整的下刀基准线"}
    ])
    sensory = registry.get("life_sensory_details", [
        {"name": "炭火烘烤", "action": "将冻僵发青的指节悬在暗红炭火上缓缓烘烤，感受皮肉发胀的微温"},
        {"name": "松针开水", "action": "端起粗瓷碗咽下一口带松脂清苦的热水，撕开胸腔深处的寒意"},
        {"name": "粗布缠裹", "action": "取来细麻布死死缠紧开裂渗血的虎口，打下牢固的死结"}
    ])

    forbidden_items = []
    # 1. 检查测量工具复读 (卡尺/骨尺/铅锤等)
    tool_keywords = {
        "骨质卡尺/游标卡尺": [r"卡尺", r"骨尺", r"游标"],
        "铅锤垂线": [r"铅锤", r"垂线"],
        "气泡水平管": [r"水准管", r"气泡管", r"水平管"],
        "钢划针/炭条": [r"划针", r"炭条"]
    }
    for item_name, pats in tool_keywords.items():
        hit_count = 0
        for ch, txt in prev_texts:
            if any(re.search(p, txt) for p in pats):
                hit_count += 1
        if hit_count >= 1 and len(prev_texts) >= 1 and any(re.search(p, prev_texts[0][1]) for p in pats):
            # 上一章刚出现过，或者连续出现
            forbidden_items.append(item_name)

    # 2. 检查生活与生理动作复读 (硬麦饼/冷唾沫/粗茶等)
    sensory_keywords = {
        "嚼硬麦饼/粗粝麦麸": [r"麦饼", r"硬饼", r"麦麸"],
        "咽冷唾沫/发干咽喉": [r"冷唾沫", r"干涩微苦", r"咽喉.*发干"],
        "粗茶微苦": [r"粗茶", r"砖茶.*微苦"]
    }
    for item_name, pats in sensory_keywords.items():
        hit_count = 0
        for ch, txt in prev_texts:
            if any(re.search(p, txt) for p in pats):
                hit_count += 1
        if hit_count >= 1 and len(prev_texts) >= 1 and any(re.search(p, prev_texts[0][1]) for p in pats):
            forbidden_items.append(item_name)

    if not forbidden_items:
        return ""

    alt_tools = [f"  * 【{t['name']}】：{t['action']}" for t in tools if not any(k in t['name'] for k in forbidden_items)][:3]
    alt_sensory = [f"  * 【{s['name']}】：{s['action']}" for s in sensory if not any(k in s['name'] for k in forbidden_items)][:3]

    lines = [
        "【微观动作与道具跨章动态节流指令（强制执行）】：",
        f"- ⚠️ 监测到前序章节（第{chapter_num-1}章）已高频使用：【{'、'.join(forbidden_items)}】！",
        "- 🚫 本章正文严禁重复使用上述已被冷却的动作/道具，必须在以下候选池中挑选轮换置换：",
        "  [推荐替代测量工具池]："
    ] + alt_tools + [
        "  [推荐替代生活质感池]："
    ] + alt_sensory

    return "\n".join(lines)


def get_retention_strategy(chapter_num: int, retention_cfg: Dict[str, Any]) -> str:
    """根据当前章节号匹配前50章留存策略核心指令"""
    if not retention_cfg:
        return ""
    for stage_key, directive in retention_cfg.items():
        m = re.search(r"(\d+)-(\d+)", str(stage_key))
        if m:
            start_ch, end_ch = int(m.group(1)), int(m.group(2))
            if start_ch <= chapter_num <= end_ch:
                return f"【当前所处留存黄金期（第{start_ch}-{end_ch}章）】：{directive}"
        elif f"第{chapter_num}章" in str(stage_key) or str(chapter_num) == str(stage_key):
            return f"【当前所处留存关键卡点】：{directive}"
    return "【常规推进期】：维持情绪波浪线，每章必有即时爽点或微观破局，拒绝平铺直叙。"


def detect_tech_streak_without_face_slap(
    novel_dir: str,
    chapter_num: int,
    cfg: Dict[str, Any],
    current_outline: str = ""
) -> Optional[str]:
    """检测是否出现连续 ≥5 章技术攻关且缺乏爽点/打脸的情形，若是则触发蓄力熔断提醒 (02_block_blueprint 规范对齐)"""
    if chapter_num < 5:
        return None

    try:
        from pipeline.context_builder import load_chapter_outline
    except ImportError:
        try:
            from .context_builder import load_chapter_outline
        except ImportError:
            return None

    tech_kws = ["技术", "研发", "制造", "工匠", "冶炼", "制药", "锻造", "机关", "推演", "设计", "改良", "试制", "C类"]
    cool_kws = ["打脸", "爽点", "震撼", "惊骇", "服气", "扬眉吐气", "反转", "大胜", "降服", "晋升", "封赏", "威慑", "立威", "碾压", "吃瘪", "反击", "破局", "惊艳"]

    streak_count = 0
    start_ch = max(1, chapter_num - 4)
    for ch in range(start_ch, chapter_num + 1):
        outline_text = ""
        if ch == chapter_num and current_outline:
            outline_text = current_outline
        else:
            try:
                outline_text = load_chapter_outline(cfg, ch)
            except Exception:
                pass
        if not outline_text:
            continue

        is_tech = any(k in outline_text for k in tech_kws)
        has_cool = any(k in outline_text for k in cool_kws)

        if is_tech and not has_cool:
            streak_count += 1
        else:
            streak_count = 0

    if streak_count >= 5:
        return "【⚠️ 爽点蓄力熔断提醒】：检测到连续 5 章技术攻关蓄力且缺乏核心爽点释放！本章正文前 1500 字内必须强制嵌入微型打脸或阶段性成果展示（如外人质疑被当场反击、小人眼红吃瘪或阶段样品惊艳全场），严禁继续无爽点纯说明书推进！"

    return None


def detect_thread_fatigue(
    novel_dir: str,
    chapter_num: int,
    cfg: Dict[str, Any],
    current_outline: str = ""
) -> Optional[str]:
    """检测多章序列中的三线节奏疲劳（如连续 ≥5 章缺乏情感线或缺乏主线推进）"""
    if chapter_num < 5:
        return None

    try:
        from pipeline.context_builder import load_chapter_outline
    except ImportError:
        try:
            from .context_builder import load_chapter_outline
        except ImportError:
            return None

    start_ch = max(1, chapter_num - 4)
    emotional_count = 0
    main_count = 0

    for ch in range(start_ch, chapter_num + 1):
        outline_text = ""
        if ch == chapter_num and current_outline:
            outline_text = current_outline
        else:
            try:
                outline_text = load_chapter_outline(cfg, ch)
            except Exception:
                pass
        if not outline_text:
            continue

        if any(k in outline_text for k in ["情感", "羁绊", "日常", "温情", "互动", "信物", "D类", "B类"]):
            emotional_count += 1
        if any(k in outline_text for k in ["主线", "夺权", "战争", "交锋", "决战", "攻坚", "突破", "A类", "F类"]):
            main_count += 1

    if emotional_count == 0:
        return f"【⚠️ 三线节奏疲劳预警】：前序及当前连续 5 章完全缺失【情感羁绊/温情互动】描写，读者极易产生情绪疲劳，建议适度穿插日常互动或信物擦拭细节。"
    return None

