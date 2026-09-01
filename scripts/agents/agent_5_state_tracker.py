# ============================================================
# Agent 5: 状态追踪 Agent (StateTracker) — 七猫男频通用版 (v4.0 Universal)
# ⚠️ 注意：StateTracker 在 run_pipeline.py 中已升级为增量 JSON Patch + 代码递归深度合并模式（杜绝长程状态全量膨胀）。
# ============================================================

import os
import json
import re
from typing import Dict, Any, Optional
from storage.state_manager import read_state_file, write_state_file
from pipeline.prompt_loader import load_prompt


def run_state_tracker(
    chapter_num: int,
    memory_anchor: str,
    client,
    model_name: str,
    cfg: Dict[str, Any],
    log_func=None
) -> dict:
    """状态追踪 Agent：基于增量 Patch 模式更新状态文件与 SQLite 知识图谱"""
    state_tracking_enabled = cfg.get("state_tracking", {}).get("enabled", False)
    if not state_tracking_enabled:
        return {"status": "SKIP", "reason": "state_tracking.enabled=false"}

    novel_dir = cfg["project"]["novel_dir"]
    state_file_name = cfg.get("state_tracking", {}).get("file", "状态文件.json")
    state_file_path = os.path.join(novel_dir, state_file_name)

    if log_func:
        log_func(f"[StateTracker] 增量解析第{chapter_num}章状态变更...")
    current_state_str = read_state_file(state_file_path)
    try:
        current_state = json.loads(current_state_str)
    except Exception:
        current_state = {}

    user_msg = f"""请根据以下第{chapter_num}章的记忆锚点信息，输出需要【新增或变更】的增量 JSON Patch（无需输出未变化的庞大历史数据）。

【本章记忆锚点】：
{memory_anchor}

【追踪项】：
- characters: 新出场角色或发生状态变化的角色
- resources: 获得的道具或消耗的资产
- plot_threads: 推进的伏笔或新埋的线索
- realm_tracking: 突破或境界变动
- skill_usage: 金手指使用次数变化
- volume_thread_tracking: 卷级三线进度看板变更（主线/情感/支线技术推进进度与预警）

请输出符合 JSON 格式的变更字典。
"""
    sys_prompt = load_prompt("06_state_tracker", custom_dir=novel_dir)
    max_tokens_val = cfg.get("models", {}).get("state_tracker", {}).get("max_tokens", 4096)
    try:
        resp = client.chat.completions.create(
            model=model_name,
            temperature=cfg.get("models", {}).get("state_tracker", {}).get("temperature", 0.2),
            max_tokens=max_tokens_val,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user",   "content": user_msg},
            ]
        )
        result = resp.choices[0].message.content or ""
    except Exception as e:
        if log_func:
            log_func(f"[StateTracker 异常] 模型调用失败: {e}")
        return {"status": "ERROR", "reason": str(e)}

    json_match = re.search(r"```json\s*\n(.*?)\n```", result, re.DOTALL)
    patch_data = {}
    if json_match:
        try:
            patch_data = json.loads(json_match.group(1))
        except Exception:
            pass
    elif result.strip().startswith("{"):
        try:
            patch_data = json.loads(result.strip())
        except Exception:
            pass

    # 递归深度合并
    def deep_merge(target: dict, patch: dict):
        for k, v in patch.items():
            if isinstance(v, dict) and k in target and isinstance(target[k], dict):
                deep_merge(target[k], v)
            else:
                target[k] = v

    if patch_data and isinstance(patch_data, dict):
        deep_merge(current_state, patch_data)

    # 自动计算与回写副手轮换、怪癖保活与物象里程碑状态 (0 业务硬编码)
    try:
        rotation = cfg.get("output_constraints", {}).get("breathing_chapter_rotation", [])
        if rotation:
            current_state.setdefault("emotion", {})
            current_state.setdefault("character_quirks", {})
            found_sidekick = None
            for s_name in rotation:
                if s_name in memory_anchor:
                    found_sidekick = s_name
                    current_state["character_quirks"][s_name] = chapter_num
            if found_sidekick:
                current_state["emotion"]["last_sidekick_featured"] = found_sidekick
                cur_idx = rotation.index(found_sidekick)
                next_idx = (cur_idx + 1) % len(rotation)
                current_state["emotion"]["next_due_sidekick"] = rotation[next_idx]

        # 自动检查物象里程碑达成
        core_art = cfg.get("core_artifact", {})
        ms_list = core_art.get("milestones", [])
        for ms in ms_list:
            if ms.get("chapter") == chapter_num and ms.get("status") == "pending":
                ms["status"] = "resolved"
                current_state.setdefault("core_artifact", {})
                current_state["core_artifact"]["last_milestone_resolved"] = ms.get("event", f"第{chapter_num}章里程碑")
    except Exception:
        pass

    current_state["last_updated_chapter"] = chapter_num
    try:
        write_state_file(json.dumps(current_state, ensure_ascii=False, indent=2), state_file_path)
        if log_func:
            log_func(f"[StateTracker] ✅ 第{chapter_num}章状态已增量合并写入 {os.path.basename(state_file_path)}")
    except Exception as e:
        if log_func:
            log_func(f"[StateTracker 警告] 写入状态文件失败: {e}")

    # 同步沉淀至知识图谱
    try:
        from storage.knowledge_graph import NovelKnowledgeGraph
        kg_db_path = os.path.join(novel_dir, "knowledge_graph.db")
        if os.path.exists(kg_db_path):
            kg = NovelKnowledgeGraph(kg_db_path)
            kg.sync_chapter_memory_anchor(chapter_num, memory_anchor, patch_data)

            # 同步灵魂物象状态变更
            if "soul_totem" in patch_data and isinstance(patch_data["soul_totem"], dict):
                totem_data = patch_data["soul_totem"]
                t_name = totem_data.get("name", "灵魂物象")
                t_state = totem_data.get("physical_state", "intact")
                t_reason = totem_data.get("reason", f"第{chapter_num}章状态演化")
                kg.update_soul_totem_state(t_name, t_state, chapter_num, t_reason)

            # 同步角色前史创伤触发
            if "character_trauma" in patch_data and isinstance(patch_data["character_trauma"], dict):
                trauma_data = patch_data["character_trauma"]
                c_name = trauma_data.get("character", "")
                t_desc = trauma_data.get("detail", f"第{chapter_num}章创伤触发")
                if c_name:
                    kg.record_character_trauma_trigger(c_name, chapter_num, t_desc)

            # 同步卷级三线进度看板 (volume_thread_tracking)
            if "volume_thread_tracking" in patch_data and isinstance(patch_data["volume_thread_tracking"], dict):
                vtt_data = patch_data["volume_thread_tracking"]
                vol_num = vtt_data.get("volume", 1)
                kg.record_volume_thread_tracking(vol_num, vtt_data, chapter_num)

            kg.close()
    except Exception:
        pass

    # 同步沉淀至长程记忆库 (memory.db / plot_vault)
    try:
        mem_db_path = os.path.join(novel_dir, "memory.db")
        if os.path.exists(mem_db_path):
            import sqlite3
            from pipeline.utils import configure_sqlite_resilience
            conn_mem = sqlite3.connect(mem_db_path)
            configure_sqlite_resilience(conn_mem)
            cur_mem = conn_mem.cursor()

            # 检查是否有闭环伏笔
            resolved_threads = patch_data.get("resolved_plot_threads", [])
            if isinstance(resolved_threads, list):
                for r_thread in resolved_threads:
                    if isinstance(r_thread, str):
                        cur_mem.execute("UPDATE plot_vault SET status = 'RESOLVED' WHERE thread_name LIKE ? OR title LIKE ?", (f"%{r_thread}%", f"%{r_thread}%"))
            conn_mem.commit()
            conn_mem.close()
    except Exception:
        pass

    # 同步更新战斗微状态机 (battle_state.py)
    try:
        from storage.battle_state import load_battle_state, update_battle_turn, end_battle
        bstate = load_battle_state(custom_novel_dir=novel_dir)
        if bstate.get("active"):
            battle_patch = patch_data.get("battle_update", {})
            if isinstance(battle_patch, dict):
                update_battle_turn(
                    consumed_item=battle_patch.get("consumed_item"),
                    boss_damage_layer=battle_patch.get("damage_layer", 0),
                    broken_item=battle_patch.get("broken_item"),
                    terrain_damage=battle_patch.get("terrain_damage"),
                    new_distance=battle_patch.get("new_distance"),
                    new_phase=battle_patch.get("new_phase"),
                    progress_log=battle_patch.get("progress_log"),
                    custom_novel_dir=novel_dir
                )
            # 若标记为战后结算或胜利
            if patch_data.get("battle_settled") or battle_patch.get("settled"):
                spoils_list = patch_data.get("battle_spoils") or battle_patch.get("spoils", [])
                end_battle(custom_novel_dir=novel_dir, final_result="VICTORY", spoils=spoils_list)
    except Exception:
        pass

    return {"status": "OK", "patch": patch_data}

