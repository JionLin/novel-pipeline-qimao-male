#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
state_manager.py - 全息小说世界状态中枢管理与快照投影器 (v5.0 Unified State Bus)
核心职责：
1. 统一维护 `状态文件.json` 的标准 4 大板块规范 (world_clock, core_protagonist, active_cast_state, urgent_causal_hooks, recent_plot_deltas)
2. 双向同步：从 knowledge_graph.db 和 memory.db 投影生成 0ms 极速快照；作者手动改动 JSON 时自动回写图谱
3. 组装高密度叙事上下文 assemble_narrative_context()，替代粗暴的 500 字正文尾截断
"""

import os
import sys
import json
import time
import sqlite3
from typing import Dict, Any, List, Optional, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

DEFAULT_STATE_TEMPLATE = {
    "chapter_cursor": 0,
    "last_updated": "",
    "world_clock": {
        "current_location": "待定起始地点",
        "timeline_day": "第1天",
        "active_crisis": "宗门底层危机 / 生死危机"
    },
    "core_protagonist": {
        "name": "主角",
        "realm": "初始境界",
        "current_status": "正常",
        "inventory_active": []
    },
    "active_cast_state": {},
    "urgent_causal_hooks": [],
    "recent_plot_deltas": []
}

def get_state_file_path(novel_dir: str) -> str:
    return os.path.join(novel_dir, "状态文件.json")

def load_state(novel_dir: str) -> Dict[str, Any]:
    """安全读取状态文件.json，如不存在则返回并初始化默认模板"""
    path = get_state_file_path(novel_dir)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # 补齐缺失字段
                for k, v in DEFAULT_STATE_TEMPLATE.items():
                    if k not in data:
                        data[k] = v
                return data
        except Exception:
            pass
    return DEFAULT_STATE_TEMPLATE.copy()

def save_state(novel_dir: str, state_data: Dict[str, Any]) -> bool:
    """原子化保存状态文件.json"""
    path = get_state_file_path(novel_dir)
    state_data["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    tmp_path = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(state_data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
        return True
    except Exception as e:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        return False

def project_state_from_dbs(novel_dir: str, current_chapter: int = 1) -> Dict[str, Any]:
    """从 knowledge_graph.db 与 memory.db 抽取当前最活跃的实体与伏笔，投影更新 状态文件.json"""
    state = load_state(novel_dir)
    state["chapter_cursor"] = current_chapter

    kg_path = os.path.join(novel_dir, "knowledge_graph.db")
    if os.path.exists(kg_path):
        conn = None
        try:
            conn = sqlite3.connect(kg_path)
            try:
                from pipeline.utils import configure_sqlite_resilience
                configure_sqlite_resilience(conn)
            except Exception:
                pass
            cur = conn.cursor()

            # 1. 抽取主角信息与活跃角色
            cur.execute("SELECT id, name, category, properties FROM nodes WHERE category = 'character'")
            for row in cur.fetchall():
                c_id, name, cat, prop_raw = row
                props = json.loads(prop_raw) if prop_raw else {}
                
                # 若是主角
                if c_id == "char:主角" or props.get("is_protagonist") or name == state["core_protagonist"]["name"]:
                    state["core_protagonist"]["name"] = name
                    state["core_protagonist"]["realm"] = props.get("realm", state["core_protagonist"]["realm"])
                    state["core_protagonist"]["current_status"] = props.get("physiological_cost", props.get("current_status", "正常"))
                else:
                    state["active_cast_state"][name] = {
                        "id": c_id,
                        "realm": props.get("realm", "未知"),
                        "alive": props.get("alive", True),
                        "status": props.get("status", "活跃"),
                        "identity": props.get("identity", "")
                    }

            # 2. 抽取持有道具与灵魂物象
            cur.execute("SELECT name, properties FROM nodes WHERE category = 'item'")
            inv = []
            for row in cur.fetchall():
                name, prop_raw = row
                props = json.loads(prop_raw) if prop_raw else {}
                sec = props.get("hidden_secret", "")
                if props.get("is_soul_totem") or "totem" in name:
                    state["soul_totem"] = {
                        "name": name,
                        "physical_state": props.get("physical_state", "intact"),
                        "last_state_change_ch": props.get("last_state_change_ch", 1)
                    }
                inv.append(f"{name}" + (f"({sec})" if sec else ""))
            if inv:
                state["core_protagonist"]["inventory_active"] = inv[:10]

            # 3. 抽取紧急因果钩子
            cur.execute("SELECT source_id, target_id, rel_type, description, properties FROM edges WHERE rel_type IN ('ENEMY', 'CAUSAL_HOOK')")
            hooks = []
            for row in cur.fetchall():
                s_id, t_id, r_type, desc, prop_raw = row
                props = json.loads(prop_raw) if prop_raw else {}
                if props.get("resolution_status") == "UNRESOLVED":
                    hooks.append({
                        "source": s_id,
                        "target": t_id,
                        "type": r_type,
                        "summary": desc or f"{s_id} 与 {t_id} 的未决对立",
                        "status": "UNRESOLVED"
                    })
            if hooks:
                state["urgent_causal_hooks"] = hooks[:8]

            conn.close()
        except Exception:
            pass

    # 4. 从 memory.db 抽取伏笔线索 (兼容 plot_threads 与 plot_vault 表)
    mem_path = os.path.join(novel_dir, "memory.db")
    if os.path.exists(mem_path):
        try:
            m_conn = sqlite3.connect(mem_path)
            try:
                from pipeline.utils import configure_sqlite_resilience
                configure_sqlite_resilience(m_conn)
            except Exception:
                pass
            m_cur = m_conn.cursor()
            rows = []
            try:
                m_cur.execute("SELECT thread_name, planted_chapter, summary, status FROM plot_threads WHERE status = 'active'")
                rows = m_cur.fetchall()
            except Exception:
                try:
                    m_cur.execute("SELECT thread_name, planted_chapter, summary, status FROM plot_vault WHERE status = 'active'")
                    rows = m_cur.fetchall()
                except Exception:
                    pass
            for row in rows:
                t_name, p_ch, summ, stat = row
                exists = any(h.get("summary") == summ for h in state["urgent_causal_hooks"])
                if not exists:
                    state["urgent_causal_hooks"].append({
                        "hook_id": t_name,
                        "planted_ch": p_ch,
                        "summary": summ,
                        "status": stat
                    })
            m_conn.close()
        except Exception:
            pass

    save_state(novel_dir, state)
    return state

def assemble_narrative_context(novel_dir: str, current_start: int, prev_ch_text: str = "") -> str:
    """提取高密度、高叙事张力的前情全息上下文，彻底替代粗暴的 500 字尾截断"""
    state = load_state(novel_dir)

    ws = state.get("world_clock", {})
    mc = state.get("core_protagonist", {})
    cast = state.get("active_cast_state", {})
    hooks = state.get("urgent_causal_hooks", [])
    deltas = state.get("recent_plot_deltas", [])

    # 1. 组装物理微观现场
    loc_str = ws.get("current_location", "待定地点")
    time_str = ws.get("timeline_day", "当前时间")
    crisis_str = ws.get("active_crisis", "暂无紧迫危机")

    # 2. 组装主角与人际张力
    mc_name = mc.get("name", "主角")
    mc_realm = mc.get("realm", "未知境界")
    mc_status = mc.get("current_status", "正常")
    inv_str = ", ".join(mc.get("inventory_active", [])) if mc.get("inventory_active") else "无核心特殊道具"

    cast_lines = []
    for c_name, c_info in list(cast.items())[:6]:
        if isinstance(c_info, dict) and c_info.get("alive") is not False:
            cast_lines.append(f"- 【{c_name}】({c_info.get('realm', '境界未知')})：{c_info.get('status', '活跃')} | 身份: {c_info.get('identity', '无')}")
    cast_str = "\n".join(cast_lines) if cast_lines else "- 核心班底正常随行"

    # 3. 组装未决紧急伏笔
    hook_lines = []
    for h in hooks[:6]:
        if isinstance(h, dict):
            hook_lines.append(f"- 💥 【待引爆因果】：{h.get('summary', '')} (状态: {h.get('status', 'UNRESOLVED')})")
    hooks_str = "\n".join(hook_lines) if hook_lines else "- 暂无当前批次必须强制收网的紧急因果"

    # 4. 近期剧情增量或上一章结尾
    if deltas:
        recent_delta_str = "\n".join([f"- 第{d.get('ch', '?')}章：{d.get('core_action', '')}" for d in deltas[-3:]])
    elif prev_ch_text:
        recent_delta_str = f"上一章真实结尾实况：\n{prev_ch_text[-400:]}"
    else:
        recent_delta_str = "全书开篇第一批次，无历史剧情增量。"

    # 5. 组装灵魂物象状态
    totem = state.get("soul_totem", {})
    totem_str = f"- 【{totem.get('name', '未命名')}】物理状态: [{totem.get('physical_state', 'intact')}] (上次状态变更于第 {totem.get('last_state_change_ch', 1)} 章)" if totem else "- 暂无显式绑定的灵魂物象"

    return f"""
【🗺️ 世界微观物理现场与时空坐标】：
- 当前精确地点：{loc_str}
- 剧情时间流逝：{time_str}
- 即时逼近危机：{crisis_str}

【👤 主角即时生理/资产状态】：
- 主角：{mc_name}（境界：{mc_realm}）
- 生理与代价状态：{mc_status}
- 当前随身核心资产：{inv_str}

【🔮 核心灵魂物象物理状态】：
{totem_str}

【👥 核心在场人物与人际动态】：
{cast_str}

【📜 近期关键因果推进增量】：
{recent_delta_str}

【⏳ 本批次关键待闭环因果与伏笔】：
{hooks_str}
"""


def update_soul_totem_state(novel_dir: str, totem_name: str, new_state: str, chapter_num: int, reason: str = "") -> Dict[str, Any]:
    """更新项目知识图谱中的灵魂物象物理状态"""
    kg_path = os.path.join(novel_dir, "knowledge_graph.db")
    if os.path.exists(kg_path):
        from storage.knowledge_graph import NovelKnowledgeGraph
        kg = NovelKnowledgeGraph(kg_path)
        res = kg.update_soul_totem_state(totem_name, new_state, chapter_num, reason)
        kg.close()
        project_state_from_dbs(novel_dir, chapter_num)
        return res
    return {"totem": totem_name, "state": new_state, "chapter": chapter_num}


def get_soul_totem_state(novel_dir: str, totem_name: str = "") -> Optional[Dict[str, Any]]:
    """读取灵魂物象物理状态"""
    kg_path = os.path.join(novel_dir, "knowledge_graph.db")
    if os.path.exists(kg_path):
        from storage.knowledge_graph import NovelKnowledgeGraph
        kg = NovelKnowledgeGraph(kg_path)
        st = kg.get_soul_totem_state(totem_name)
        kg.close()
        return st
    return None


def record_character_trauma(novel_dir: str, character_name: str, chapter_num: int, trauma_detail: str = ""):
    """记录角色前史创伤触发记录"""
    kg_path = os.path.join(novel_dir, "knowledge_graph.db")
    if os.path.exists(kg_path):
        from storage.knowledge_graph import NovelKnowledgeGraph
        kg = NovelKnowledgeGraph(kg_path)
        kg.record_character_trauma_trigger(character_name, chapter_num, trauma_detail)
        kg.close()


def can_trigger_character_trauma(novel_dir: str, character_name: str, current_chapter: int, cooldown_chapters: int = 30) -> Tuple[bool, int, str]:
    """检查角色前史创伤是否处于冷却期"""
    kg_path = os.path.join(novel_dir, "knowledge_graph.db")
    if os.path.exists(kg_path):
        from storage.knowledge_graph import NovelKnowledgeGraph
        kg = NovelKnowledgeGraph(kg_path)
        res = kg.can_trigger_character_trauma(character_name, current_chapter, cooldown_chapters)
        kg.close()
        return res
    return True, 0, "允许触发（无知识库）"


def read_state_file(path: str) -> str:
    """读取状态文件内容（不存在则返回空 JSON）"""
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            return "{}"
    return "{}"


def write_state_file(content: str, path: str) -> None:
    """写入状态文件（含合法性校验与原子落盘）"""
    import re
    m = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL)
    if m:
        content = m.group(1).strip()
    try:
        json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"[StateTracker] 状态文件内容不是合法 JSON: {e}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def compact_state_snapshot(
    raw_state_str: str,
    cfg: Dict[str, Any],
    chapter_outline: str = "",
    chapter_num: int = 1
) -> str:
    """对全量状态进行 LangGraph 式剪枝与萃取，保持 Context < 1000字，防止上下文膨胀"""
    if not raw_state_str or raw_state_str.strip() in ("", "{}", "null"):
        return "（无历史状态，全书刚开始）"
    try:
        data = json.loads(raw_state_str)
        compact = {}

        core_cast_list = cfg.get("project", {}).get("core_cast", [])
        if "characters" in data:
            chars = data["characters"]
            active_chars = {}
            dead_list = []
            for name, info in chars.items():
                if not info.get("alive", True):
                    dead_list.append(name)
                    continue
                if name in core_cast_list or name in chapter_outline:
                    active_chars[name] = {
                        "identity": info.get("identity", ""),
                        "current_status": info.get("current_status", "")[:60],
                        "relationship": info.get("relationship_to_protagonist", "")[:40]
                    }
            if active_chars:
                compact["active_characters"] = active_chars
            if dead_list:
                compact["deceased_characters"] = dead_list[:8]

        if "resources" in data:
            active_res = {}
            for rname, rinfo in data["resources"].items():
                cnt = str(rinfo.get("current_count", ""))
                if "0" not in cnt and "已消耗" not in cnt:
                    active_res[rname] = {"count": cnt, "type": rinfo.get("type", "")}
            if active_res:
                compact["active_resources"] = active_res

        if "realm_tracking" in data:
            realms = data["realm_tracking"]
            c_realms = {}
            for rk in ["protagonist"] + core_cast_list:
                if rk in realms:
                    c_realms[rk] = realms[rk]
            compact["realm_tracking"] = c_realms

        if "skill_usage" in data:
            sk = data["skill_usage"]
            compact["skill_usage"] = {
                "today_used": sk.get("today_used", 0),
                "today_remaining": sk.get("today_remaining", 3),
                "total_uses": sk.get("total_uses", 0)
            }

        if "plot_threads" in data:
            active_threads = {}
            for tname, tinfo in data["plot_threads"].items():
                st = tinfo.get("state", tinfo.get("status", "active"))
                if st not in ["resolved", "closed", "completed"]:
                    active_threads[tname] = tinfo.get("current_state", tinfo.get("description", ""))[:60]
            if active_threads:
                compact["active_plot_threads"] = active_threads

        if "timeline" in data:
            compact["timeline"] = data["timeline"]

        if "core_artifact" in data:
            compact["core_artifact"] = data["core_artifact"]

        if "volume_thread_tracking" in data:
            compact["volume_thread_tracking"] = data["volume_thread_tracking"]

        return json.dumps(compact, ensure_ascii=False, indent=2)
    except Exception:
        return raw_state_str[:800]


def update_volume_thread_tracking(novel_dir: str, tracking_data: Dict[str, Any], chapter_num: int) -> bool:
    """更新状态文件与 SQLite 知识图谱中的卷级三线进度看板 (volume_thread_tracking)"""
    if not tracking_data:
        return False
    try:
        # 1. 更新 状态文件.json
        state = load_state(novel_dir)
        state["volume_thread_tracking"] = tracking_data
        save_state(novel_dir, state)

        # 2. 同步至 knowledge_graph.db
        kg_path = os.path.join(novel_dir, "knowledge_graph.db")
        if os.path.exists(kg_path):
            from storage.knowledge_graph import NovelKnowledgeGraph
            kg = NovelKnowledgeGraph(kg_path)
            vol_num = tracking_data.get("volume", 1)
            kg.record_volume_thread_tracking(vol_num, tracking_data, chapter_num)
            kg.close()
        return True
    except Exception:
        return False


def get_thread_tracking_alert(novel_dir: str) -> Optional[str]:
    """读取当前卷三线进度看板并检测是否生成动态纠偏预警指令"""
    path = get_state_file_path(novel_dir)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        vtt = data.get("volume_thread_tracking", {})
        if not vtt:
            return None

        explicit_alert = vtt.get("alert", "")
        if explicit_alert and explicit_alert != "无预警" and "无" not in explicit_alert:
            return explicit_alert

        threads = vtt.get("threads", {})
        for tname, tinfo in threads.items():
            if isinstance(tinfo, dict):
                missed = tinfo.get("consecutive_missed_chapters", 0)
                if missed >= 5:
                    label = "情感羁绊线" if "emotional" in tname else ("支线技术线" if "tech" in tname else "主线推进")
                    return f"【⚠️ 三线动态平衡纠偏】：{label}已连续 {missed} 章未推进，读者极易产生单一线疲劳！建议在下一块前 2 章强制规划对应的 D 类或 B/C 类章节！"
    except Exception:
        pass
    return None


if __name__ == "__main__":
    test_dir = os.path.dirname(os.path.abspath(__file__))
    s = load_state(test_dir)
    print("State loaded successfully:", s.get("chapter_cursor"))
