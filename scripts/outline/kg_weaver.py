# -*- coding: utf-8 -*-
"""
outline/kg_weaver.py - 知识图谱数据库与大纲实体织网引擎
包含：
1. 从总纲提取与初始化物象/实体知识图谱 (init_kg_from_master_outline)
2. 将多章细纲深度织入 SQLite 图数据库 (weave_outlines_into_graph_v5)
3. 大纲与状态文件双向同步 (sync_outlines_with_state)
4. 导出图谱初始数据至 YAML (export_kg_initial_data)
"""

import os
import re
import json
import yaml
from typing import Dict, Any, List, Optional


def extract_artifact_from_master_text(master_text: str) -> Optional[Dict[str, Any]]:
    """从全书总纲文本中提取灵魂物象(core_artifact)名称、初始形态与 5 大里程碑"""
    if not master_text:
        return None

    # 1. 匹配物象名称（优先匹配 指定物象 / 核心贯穿物象 / 灵魂物象名称）
    m_name = re.search(r'(?:指定物象|核心贯穿物象|灵魂物象名称|物象名称|核心物象|灵魂物象)[*\s]*[：:\s]+[*\s]*[【\[（(]*([^】\]）)\n\r*]+)', master_text)
    totem_name = ""
    if m_name:
        candidate = m_name.group(1).strip().replace("**", "").replace("`", "").replace("【", "").replace("】", "")
        if not any(k in candidate for k in ["节拍器", "演变公理", "三态", "规范", "强制"]):
            totem_name = re.split(r'[（(，,/、]', candidate)[0].strip()

    if not totem_name:
        # 回退匹配：在【核心物象强制节拍器】或【灵魂物象】板块内匹配加粗实体名
        m_sec = re.search(r'【(?:核心物象强制节拍器|物象强制节拍器|灵魂物象)[^】]*】\s*\n(.*?)(?=\n###|\n--|\Z)', master_text, re.DOTALL)
        if m_sec:
            sec_text = m_sec.group(1)
            m_bold = re.search(r'【([^】]+)】|\*\*([^*]+)\*\*', sec_text)
            if m_bold:
                candidate = (m_bold.group(1) or m_bold.group(2)).strip()
                if not any(k in candidate for k in ["节拍器", "演变", "公理", "规范", "强制"]):
                    totem_name = candidate

    if not totem_name:
        return None

    # 2. 匹配初始物理形态与破损痕迹
    initial_desc = ""
    m_desc = re.search(r'(?:初始物理形态|破损痕迹|初始形态|物理特征|物象初始状态)[*\s]*[：:\s]+[*\s]*([^\\n\\r]+)', master_text)
    if m_desc:
        initial_desc = m_desc.group(1).strip().replace("**", "").replace("`", "")

    # 判断初始状态
    initial_state = "damaged" if any(k in initial_desc for k in ["破", "损", "断", "裂", "残", "锈", "缺"]) else "intact"

    # 3. 提取 5 大演进里程碑
    milestones = []
    m_ms_block = re.search(r'(?:5大物象演进里程碑|物象演进里程碑|里程碑演进|5大演进窗口|5大强制时间窗口与物理质变)[：:\s]*\n(.*?)(?=\n###|\n--|\n\*\s*\*\*跨卷|\Z)', master_text, re.DOTALL)
    if m_ms_block:
        ms_text = m_ms_block.group(1)
        lines = [ln.strip() for ln in ms_text.split("\n") if ln.strip()]
        for ln in lines:
            if re.match(r'^(?:\d+[\.、]|\-|\*|窗口\d+)', ln):
                clean_ln = re.sub(r'^(?:\d+[\.、]|\-|\*|窗口\d+[：:]?)\s*', '', ln).strip()
                if clean_ln:
                    milestones.append(clean_ln)

    return {
        "name": totem_name,
        "initial_state": initial_state,
        "description": initial_desc,
        "milestones": milestones
    }


def init_kg_from_master_outline(master_text: str, novel_dir: str, cfg: Dict[str, Any], log_func=None) -> bool:
    """从 config.yaml initial_graph_data 与总纲提取核心物象/实体/关系，初始化 knowledge_graph.db"""
    kg_db_path = os.path.join(novel_dir, "knowledge_graph.db")
    try:
        from storage.knowledge_graph import NovelKnowledgeGraph
        os.makedirs(novel_dir, exist_ok=True)
        kg = NovelKnowledgeGraph(kg_db_path)

        # 1. 注入初始预设节点与关系 (从 config.yaml 或 character_locks)
        char_locks = cfg.get("character_locks", [])
        for c in char_locks:
            c_name = c.get("name", "")
            if c_name:
                try:
                    kg.upsert_node(
                        node_id=c_name,
                        name=c_name,
                        category="character",
                        properties={"legal_identity": c.get("legal_identity", ""), "role": c.get("role", "")},
                        chapter_num=1
                    )
                except Exception:
                    pass

        for c_name in cfg.get("project", {}).get("characters", []):
            if c_name:
                try:
                    kg.upsert_node(
                        node_id=c_name,
                        name=c_name,
                        category="character",
                        properties={},
                        chapter_num=1
                    )
                except Exception:
                    pass

        chars = cfg.get("project", {}).get("characters", [])
        protagonist = chars[0] if chars else (char_locks[0]["name"] if char_locks else "")
        if protagonist and char_locks:
            for c in char_locks:
                c_name = c.get("name", "")
                if c_name and c_name != protagonist:
                    rel = "ENEMY" if any(k in c.get("role", "") or k in c.get("legal_identity", "") for k in ["反派", "宿敌", "敌", "蛮王", "至尊"]) else "ALLY"
                    try:
                        kg.upsert_edge(
                            source_id=protagonist,
                            target_id=c_name,
                            rel_type=rel,
                            weight=0.8 if rel == "ALLY" else -0.8,
                            description=f"核心关系: {c.get('legal_identity', '')}",
                            chapter_num=1
                        )
                    except Exception:
                        pass

        init_data = cfg.get("initial_graph_data", {})
        if init_data and ("nodes" in init_data or "edges" in init_data):
            for n in init_data.get("nodes", []):
                try:
                    kg.upsert_node(
                        node_id=n["id"],
                        name=n["name"],
                        category=n.get("type", n.get("category", "character")),
                        properties=n.get("properties", {}),
                        chapter_num=n.get("chapter_num", 1)
                    )
                except Exception:
                    pass
            for e in init_data.get("edges", []):
                try:
                    kg.upsert_edge(
                        source_id=e["source"],
                        target_id=e["target"],
                        rel_type=e.get("relation", "ALLY"),
                        weight=float(e.get("weight", 0.5)),
                        description=e.get("desc", ""),
                        properties=e.get("properties", {})
                    )
                except Exception:
                    pass

        # 2. 从总纲中解析核心物象并沉淀至图谱的 soul_totem
        artifact_info = extract_artifact_from_master_text(master_text)
        if artifact_info and artifact_info.get("name"):
            totem_name = artifact_info["name"]
            init_state = artifact_info["initial_state"]
            desc = artifact_info["description"]
            milestones = artifact_info["milestones"]

            node_id = totem_name
            props = {
                "is_soul_totem": True,
                "is_core": True,
                "physical_state": init_state,
                "description": desc,
                "milestones": milestones,
                "last_state_change_ch": 1,
                "last_change_reason": "总纲灵魂物象初始设定"
            }
            kg.upsert_node(node_id=node_id, name=totem_name, category="item", properties=props, chapter_num=1)
            kg.update_soul_totem_state(totem_name, init_state, chapter_num=1, reason="总纲初始物象设定")

            # 建立主角与核心物象的绑定关系边
            chars = cfg.get("project", {}).get("characters", [])
            if chars:
                protagonist = chars[0]
                try:
                    kg.upsert_edge(
                        source_id=protagonist,
                        target_id=totem_name,
                        rel_type="OWNS",
                        weight=1.0,
                        description=f"核心传承灵魂物象/{desc}",
                        properties={"is_soul_totem_link": True},
                        chapter_num=1
                    )
                except Exception:
                    pass

            if log_func:
                log_func(f"[KG Init] ✅ 灵魂物象 [{totem_name}] 及 5 大演进里程碑已成功编织进知识图谱！")

        kg.close()
        if log_func:
            log_func(f"[KG Init] ✅ 知识图谱已根据总纲与预设数据完成全量初始化！")
        return True
    except Exception as e:
        if log_func:
            log_func(f"[KG Init 提示] 图谱初始化跳过: {e}")
        return False


def weave_outlines_into_graph_v5(outlines_dir: str, novel_dir: str, log_func=None) -> int:
    """扫描所有分卷细纲中的 ```json 元数据块与物象登场记录，批量织入 SQLite 图数据库"""
    kg_db_path = os.path.join(novel_dir, "knowledge_graph.db")
    try:
        from storage.knowledge_graph import NovelKnowledgeGraph
        kg = NovelKnowledgeGraph(kg_db_path)
        count = 0
        if not os.path.exists(outlines_dir):
            kg.close()
            return 0

        md_files = [os.path.join(outlines_dir, f) for f in os.listdir(outlines_dir) if f.endswith(".md")]
        for f in md_files:
            try:
                with open(f, "r", encoding="utf-8") as rf:
                    text = rf.read()
                
                # 1. 扫描 JSON 元数据块
                json_blocks = re.findall(r'```json\s*(.*?)\s*```', text, re.DOTALL)
                for jb in json_blocks:
                    try:
                        data = json.loads(jb.strip())
                        ch_num = data.get("chapter", 1)
                        for item in data.get("items", []):
                            kg.upsert_node(f"item:{item['name']}", item["name"], "item", item, chapter_num=ch_num)
                            count += 1
                        for rel in data.get("relations", []):
                            kg.upsert_edge(rel["source"], rel["target"], rel.get("type", "ALLY"), description=rel.get("desc", ""), chapter_num=ch_num)
                            count += 1
                        
                        # 物象微在场 / 状态变迁回写
                        if "soul_totem" in data and isinstance(data["soul_totem"], dict):
                            t_info = data["soul_totem"]
                            t_name = t_info.get("name", "")
                            t_st = t_info.get("state", "intact")
                            t_rs = t_info.get("reason", f"第 {ch_num} 章细纲演进")
                            if t_name:
                                kg.update_soul_totem_state(t_name, t_st, ch_num, t_rs)
                                count += 1
                    except Exception:
                        pass
            except Exception:
                pass
        kg.close()
        if log_func:
            log_func(f"[KG Weaver] ✅ 成功将 {count} 处大纲实体与因果边织入图数据库！")
        return count
    except Exception as e:
        if log_func:
            log_func(f"[KG Weaver 警告] 织网异常: {e}")
        return 0


def sync_outlines_with_state(outlines_dir: str, state_path: str, log_func=None) -> Dict[str, Any]:
    """大纲元数据与状态文件(state_file.json)双向同步"""
    state_data: Dict[str, Any] = {}
    if os.path.exists(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as sf:
                state_data = json.load(sf)
        except Exception:
            state_data = {}

    if not os.path.exists(outlines_dir):
        return state_data

    # 扫描细纲中最新的物象状态与伏笔
    latest_totem = {}
    md_files = sorted([os.path.join(outlines_dir, f) for f in os.listdir(outlines_dir) if f.endswith(".md")])
    for f in md_files:
        try:
            with open(f, "r", encoding="utf-8") as rf:
                text = rf.read()
            json_blocks = re.findall(r'```json\s*(.*?)\s*```', text, re.DOTALL)
            for jb in json_blocks:
                try:
                    data = json.loads(jb.strip())
                    if "soul_totem" in data and isinstance(data["soul_totem"], dict):
                        latest_totem = data["soul_totem"]
                except Exception:
                    pass
        except Exception:
            pass

    if latest_totem:
        state_data["soul_totem"] = latest_totem
        try:
            with open(state_path, "w", encoding="utf-8") as wf:
                json.dump(state_data, wf, ensure_ascii=False, indent=2)
            if log_func:
                log_func(f"[KG State Sync] ✅ 成功将细纲物象状态同步至状态看板: {latest_totem.get('name')}")
        except Exception as e:
            if log_func:
                log_func(f"[KG State Sync 警告] 写入状态文件失败: {e}")

    return state_data


def export_kg_initial_data(novel_dir: str, config_path: str = "", log_func=None) -> Dict[str, Any]:
    """从图数据库导出当前实体骨架，并支持安全写回 config.yaml 的 initial_graph_data"""
    kg_db_path = os.path.join(novel_dir, "knowledge_graph.db")
    if not os.path.exists(kg_db_path):
        return {"nodes": [], "edges": []}

    try:
        from storage.knowledge_graph import NovelKnowledgeGraph
        kg = NovelKnowledgeGraph(kg_db_path)
        with kg._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, name, category, properties, first_seen_ch FROM nodes")
            node_rows = cur.fetchall()
            nodes = []
            for r in node_rows:
                props = json.loads(r["properties"]) if r["properties"] else {}
                nodes.append({
                    "id": r["id"],
                    "name": r["name"],
                    "category": r["category"],
                    "chapter_num": r["first_seen_ch"],
                    "properties": props
                })

            cur.execute("SELECT source_id, target_id, rel_type, weight, description, properties FROM edges")
            edge_rows = cur.fetchall()
            edges = []
            for r in edge_rows:
                props = json.loads(r["properties"]) if r["properties"] else {}
                edges.append({
                    "source": r["source_id"],
                    "target": r["target_id"],
                    "relation": r["rel_type"],
                    "weight": r["weight"],
                    "desc": r["description"],
                    "properties": props
                })

        kg.close()
        export_data = {"nodes": nodes, "edges": edges}

        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as cf:
                    cfg_obj = yaml.safe_load(cf) or {}
                cfg_obj["initial_graph_data"] = export_data
                with open(config_path, "w", encoding="utf-8") as cf:
                    yaml.dump(cfg_obj, cf, allow_unicode=True, sort_keys=False)
                if log_func:
                    log_func(f"[KG Export] ✅ 成功将图数据库 {len(nodes)} 个节点与 {len(edges)} 条边导出至 {config_path}")
            except Exception as e:
                if log_func:
                    log_func(f"[KG Export 警告] 回写 config.yaml 失败: {e}")

        return export_data
    except Exception as e:
        if log_func:
            log_func(f"[KG Export 异常] 导出失败: {e}")
        return {"nodes": [], "edges": []}
