#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LangGraph P3 升级落地：通用战役与动作微状态机 (Universal Battle Subgraph Tracker)
解决 2~4 章连环大战/生死擂台/万人攻防/大纵深追杀时的微观状态一致性：
  1. 三大战斗范式自适应支持 (DUEL_BOSS / ARMY_SIEGE / PURSUIT_ESCAPE)
  2. 目标阻力层数衰减与破防日志追踪 (objective_progress)
  3. 跨章已消耗底牌与已损毁装备刚性锁定 (hard_resource_locks, 防止法宝装备碎了又掏出复读)
  4. 动态空间坐标、交战距离与战术推进阶段追踪 (spatial_and_tactical)
  5. 战后软着陆自动归档与战利品沉淀机制 (combat_aftermath)
"""

import os
import sys
import json
from typing import Dict, Any, Optional, List

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from pipeline.utils import load_active_config, get_active_project_dir


def _resolve_battle_file(custom_novel_dir: Optional[str] = None) -> str:
    """动态解析当前小说工作区下的 battle_state.json 物理路径"""
    if custom_novel_dir and os.path.exists(custom_novel_dir):
        return os.path.join(custom_novel_dir, "battle_state.json")
    
    act_dir = get_active_project_dir(os.path.dirname(SCRIPT_DIR))
    if act_dir and os.path.exists(act_dir):
        return os.path.join(act_dir, "battle_state.json")
    
    cfg = load_active_config(script_dir=os.path.dirname(SCRIPT_DIR))
    novel_dir = cfg.get("project", {}).get("novel_dir", "")
    if novel_dir and os.path.exists(novel_dir):
        return os.path.join(novel_dir, "battle_state.json")
    
    return os.path.join(SCRIPT_DIR, "battle_state.json")


def load_battle_state(custom_novel_dir: Optional[str] = None) -> dict:
    """加载战斗状态文件"""
    b_file = _resolve_battle_file(custom_novel_dir)
    if os.path.exists(b_file):
        try:
            with open(b_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"active": False}
    return {"active": False}


def save_battle_state(data: dict, custom_novel_dir: Optional[str] = None):
    """保存战斗状态文件"""
    b_file = _resolve_battle_file(custom_novel_dir)
    os.makedirs(os.path.dirname(b_file), exist_ok=True)
    with open(b_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def start_battle_universal(
    battle_name: str,
    combat_mode: str = "DUEL_BOSS",  # DUEL_BOSS | ARMY_SIEGE | PURSUIT_ESCAPE
    hero_side: str = "主角方",
    opponent_side: str = "强敌方",
    location: str = "预设主战场",
    total_layers: int = 3,
    objective_description: str = "击破强敌核心防御",
    engagement_distance: str = "近距交锋 (30步内)",
    tactical_phase: str = "CONTACT",  # CONTACT | CLASH | BREAKTHROUGH | MOPUP
    start_chapter: int = 1,
    custom_novel_dir: Optional[str] = None
) -> dict:
    """开启一场通用跨章节战斗子图（支持三大范式）"""
    valid_modes = ["DUEL_BOSS", "ARMY_SIEGE", "PURSUIT_ESCAPE"]
    mode = combat_mode if combat_mode in valid_modes else "DUEL_BOSS"

    bstate = {
        "active": True,
        "battle_name": battle_name,
        "combat_mode": mode,
        "start_chapter": start_chapter,
        "current_phase": tactical_phase,
        "combatants": {
            "hero_side": hero_side,
            "opponent_side": opponent_side
        },
        "objective_progress": {
            "mode_type": mode,
            "description": objective_description,
            "total_layers": total_layers,
            "remaining_layers": total_layers,
            "layer_breakdown_log": []
        },
        "spatial_and_tactical": {
            "current_location": location,
            "engagement_distance": engagement_distance,
            "terrain_damage": "战场初始完好",
            "tactical_phase": tactical_phase
        },
        "hard_resource_locks": {
            "consumed_trump_cards": [],
            "broken_weapons_or_shields": [],
            "critical_ticking_reserves": ""
        },
        "combat_aftermath": {
            "settled": False,
            "final_result": None,
            "spoils_or_losses": []
        },
        # 兼容旧字段
        "hero_name": hero_side,
        "boss_name": opponent_side,
        "location": location,
        "boss_hp_layers_remaining": total_layers
    }
    save_battle_state(bstate, custom_novel_dir)
    return bstate


def start_battle(
    battle_name: str,
    hero_name: str = "主角",
    boss_name: str = "强敌",
    location: str = "战场",
    initial_hp_layers: int = 3,
    start_chapter: int = 1,
    custom_novel_dir: Optional[str] = None
) -> dict:
    """向后兼容原有单体 BOSS 战 API"""
    return start_battle_universal(
        battle_name=battle_name,
        combat_mode="DUEL_BOSS",
        hero_side=hero_name,
        opponent_side=boss_name,
        location=location,
        total_layers=initial_hp_layers,
        objective_description=f"击破 {boss_name} 的护体/血条防御",
        start_chapter=start_chapter,
        custom_novel_dir=custom_novel_dir
    )


def update_battle_turn(
    consumed_item: Optional[str] = None,
    boss_damage_layer: int = 0,
    broken_item: Optional[str] = None,
    terrain_damage: Optional[str] = None,
    new_distance: Optional[str] = None,
    new_phase: Optional[str] = None,
    progress_log: Optional[str] = None,
    custom_novel_dir: Optional[str] = None
):
    """通用推进战斗子图状态"""
    bstate = load_battle_state(custom_novel_dir)
    if not bstate.get("active"):
        return

    # 1. 刚性资源与装备锁定
    locks = bstate.setdefault("hard_resource_locks", {})
    if consumed_item:
        if consumed_item not in locks.setdefault("consumed_trump_cards", []):
            locks["consumed_trump_cards"].append(consumed_item)
    if broken_item:
        if broken_item not in locks.setdefault("broken_weapons_or_shields", []):
            locks["broken_weapons_or_shields"].append(broken_item)

    # 2. 目标阻力推进
    obj = bstate.setdefault("objective_progress", {})
    if boss_damage_layer > 0:
        cur_rem = obj.get("remaining_layers", bstate.get("boss_hp_layers_remaining", 1))
        new_rem = max(0, cur_rem - boss_damage_layer)
        obj["remaining_layers"] = new_rem
        bstate["boss_hp_layers_remaining"] = new_rem
    
    if progress_log:
        obj.setdefault("layer_breakdown_log", []).append(progress_log)

    # 3. 空间与战术
    st = bstate.setdefault("spatial_and_tactical", {})
    if terrain_damage:
        st["terrain_damage"] = terrain_damage
        bstate["terrain_damage_state"] = terrain_damage
    if new_distance:
        st["engagement_distance"] = new_distance
    if new_phase:
        st["tactical_phase"] = new_phase
        bstate["current_phase"] = new_phase

    # 兼容旧列表
    if consumed_item and consumed_item not in bstate.setdefault("consumed_trump_cards", []):
        bstate["consumed_trump_cards"].append(consumed_item)
    if broken_item and broken_item not in bstate.setdefault("broken_weapons_or_shields", []):
        bstate["broken_weapons_or_shields"].append(broken_item)

    save_battle_state(bstate, custom_novel_dir)


def end_battle(
    custom_novel_dir: Optional[str] = None,
    final_result: str = "VICTORY",
    spoils: Optional[List[str]] = None
) -> dict:
    """结束并归档战斗子图"""
    bstate = load_battle_state(custom_novel_dir)
    bstate["active"] = False
    aftermath = bstate.setdefault("combat_aftermath", {})
    aftermath["settled"] = True
    aftermath["final_result"] = final_result
    if spoils:
        aftermath["spoils_or_losses"] = spoils
    save_battle_state(bstate, custom_novel_dir)
    return bstate


def get_battle_subgraph_context(chapter_num: int = 0, custom_novel_dir: Optional[str] = None) -> str:
    """提取战斗子图上下文，针对三大范式自适应格式化注入 Planner / Writer"""
    bstate = load_battle_state(custom_novel_dir)
    if not bstate.get("active"):
        return ""

    mode = bstate.get("combat_mode", "DUEL_BOSS")
    b_name = bstate.get("battle_name", "大型战役")
    hero = bstate.get("combatants", {}).get("hero_side") or bstate.get("hero_name", "主角方")
    opponent = bstate.get("combatants", {}).get("opponent_side") or bstate.get("boss_name", "敌方")
    
    obj = bstate.get("objective_progress", {})
    rem_layers = obj.get("remaining_layers", bstate.get("boss_hp_layers_remaining", 1))
    tot_layers = obj.get("total_layers", max(1, rem_layers))
    obj_desc = obj.get("description", "击破核心阻力")
    
    st = bstate.get("spatial_and_tactical", {})
    loc = st.get("current_location") or bstate.get("location", "战场")
    dist = st.get("engagement_distance", "近距交锋")
    terrain = st.get("terrain_damage") or bstate.get("terrain_damage_state", "场地受损")
    phase = st.get("tactical_phase") or bstate.get("current_phase", "CLASH")

    locks = bstate.get("hard_resource_locks", {})
    consumed = locks.get("consumed_trump_cards") or bstate.get("consumed_trump_cards", [])
    broken = locks.get("broken_weapons_or_shields") or bstate.get("broken_weapons_or_shields", [])

    lines = ["<battle_subgraph_context>"]
    
    # 标题头
    mode_labels = {
        "DUEL_BOSS": "⚡【当前正处于生死单挑/斩首强敌决战中】",
        "ARMY_SIEGE": "🏰【当前正处于万人大兵团/阵地要塞攻防战中】",
        "PURSUIT_ESCAPE": "🏹【当前正处于大纵深千里追杀/突围逃逸序列中】"
    }
    lines.append(f"{mode_labels.get(mode, '⚔️【当前正处于大型连环战役中】')}：{b_name}")
    lines.append(f"- 参战双方：{hero} VS {opponent}")
    lines.append(f"- 战术阶段：{phase} ｜ 核心战场坐标：{loc}")
    lines.append(f"- 交战距离/射程标尺：{dist}")

    # 阻力度量
    if mode == "ARMY_SIEGE":
        lines.append(f"- 阵地/要塞防御阻力：{obj_desc}（剩余 {rem_layers}/{tot_layers} 道防线/军阵）")
    elif mode == "PURSUIT_ESCAPE":
        lines.append(f"- 追逃突破进度：{obj_desc}（剩余阻隔/距离标尺：{rem_layers}/{tot_layers} 阶段）")
    else:
        lines.append(f"- 敌方核心护体/血条状态：{obj_desc}（剩余 {rem_layers}/{tot_layers} 层护甲）")

    # 战损与推进历史
    breakdown = obj.get("layer_breakdown_log", [])
    if breakdown:
        lines.append(f"- 前序破防战果：{'; '.join(breakdown[-2:])}")

    # 刚性锁定（核心防复读）
    if consumed:
        lines.append(f"- ⛔ 本场已消耗底牌与特种弹药（本章严禁重复掏出使用）：{', '.join(consumed)}")
    if broken:
        lines.append(f"- ❌ 战场已打碎/损毁的装备武器（已报废，严禁完好出场）：{', '.join(broken)}")
    
    lines.append(f"- 🌍 战场微地形破坏状态：{terrain}")
    lines.append("</battle_subgraph_context>")
    
    return "\n".join(lines)


def get_active_battle_context(chapter_num: int = 0, custom_novel_dir: Optional[str] = None) -> str:
    """别名函数：供 agent_1_planner 与 pipeline 调用"""
    return get_battle_subgraph_context(chapter_num, custom_novel_dir)
