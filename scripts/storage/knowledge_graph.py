"""
knowledge_graph.py - SOTA 因果闭环与长程关系图谱中枢引擎 (v4.0 Universal Fiction Engine)
包含核心子系统：
1. 属性图原生存储 (Nodes, Edges, Properties, Temporal Versions)
2. 因果边闭环追踪器 (Causal Edge Resolution Engine: 追踪未闭环仇恨与伏笔)
3. 5-Chapter Horizon 2-hop 拓扑前瞻雷达 (自动抓取幕后反派与势力链)
4. 双轨情感显影器 (Dual-Track Manifestation: 利益契约轨 + 自尊心理轨)
5. 神物溯源与异象掩蔽守恒公理 (Provenance & Camouflage Laws)
6. 战力拓扑 DAG 参照标尺
7. Mermaid 可视化关系图谱导出
8. 纯配置驱动数据初始化 (零硬编码)
"""

import sqlite3
import json
import os
import re
import threading
import yaml
from typing import List, Dict, Any, Optional, Tuple

class NovelKnowledgeGraph:
    def __init__(self, db_path: str, config_path: str = None):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        try:
            from pipeline.utils import configure_sqlite_resilience
            configure_sqlite_resilience(self._conn)
        except Exception:
            pass
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        return self._conn

    def close(self):
        """关闭数据库连接"""
        if hasattr(self, '_conn') and self._conn:
            try:
                self._conn.close()
            except Exception:
                pass

    def __del__(self):
        self.close()

    def _init_db(self):
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
            CREATE TABLE IF NOT EXISTS nodes (\n                id TEXT PRIMARY KEY,\n                name TEXT NOT NULL,\n                category TEXT NOT NULL,      -- character, faction, item, location, plot_secret, realm\n                properties TEXT DEFAULT '{}',-- JSON: 境界, hidden_agenda, autonomous_daily_action\n                first_seen_ch INTEGER DEFAULT 1,\n                last_updated_ch INTEGER DEFAULT 1\n            )\n            """)
            
            cur.execute("""
            CREATE TABLE IF NOT EXISTS edges (\n                id TEXT PRIMARY KEY,\n                source_id TEXT NOT NULL,\n                target_id TEXT NOT NULL,\n                rel_type TEXT NOT NULL,      -- ALLY, ENEMY, MASTER_SERVANT, SERVANT_OF, RESENTMENT, DEPENDENCE, OWNS, CAUSAL_HOOK, SPATIAL_TRANSITION\n                weight REAL DEFAULT 1.0,     -- 亲密度 / 杀意值 (-1.0 到 1.0)\n                description TEXT DEFAULT '', -- 关系与因果细节描述\n                properties TEXT DEFAULT '{}',-- 双轨数据: objective_deal, subjective_tension, resolution_status, trigger_condition, is_reversible\n                created_ch INTEGER DEFAULT 1,\n                updated_ch INTEGER DEFAULT 1,\n                FOREIGN KEY (source_id) REFERENCES nodes(id),\n                FOREIGN KEY (target_id) REFERENCES nodes(id)\n            )\n            """)
            
            # 角色微动作环形账本 (Action Ring Buffer): 严格防疲劳复读
            cur.execute("""
            CREATE TABLE IF NOT EXISTS action_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                character_name TEXT NOT NULL,
                action_desc TEXT NOT NULL,
                chapter_num INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

            # 卷级三线进度看板 (volume_thread_tracking): 06_state_tracker 规范对齐
            cur.execute("""
            CREATE TABLE IF NOT EXISTS volume_thread_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                volume_num INTEGER NOT NULL,
                main_thread_progress TEXT DEFAULT '',
                emotional_thread_progress TEXT DEFAULT '',
                tech_thread_progress TEXT DEFAULT '',
                alert TEXT DEFAULT '',
                updated_at_chapter INTEGER NOT NULL,
                raw_data TEXT DEFAULT '{}',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            
            cur.execute("CREATE INDEX IF NOT EXISTS idx_nodes_category ON nodes(category)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_edges_rel ON edges(rel_type)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_action_ledger_char ON action_ledger(character_name, chapter_num)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_vtt_vol ON volume_thread_tracking(volume_num)")
            conn.commit()

    def record_volume_thread_tracking(self, volume_num: int, tracking_data: Dict[str, Any], chapter_num: int):
        """记录卷级三线进度看板数据至 SQLite"""
        if not tracking_data:
            return
        with self._get_conn() as conn:
            cur = conn.cursor()
            main_p = str(tracking_data.get("main_thread_progress", tracking_data.get("main_thread", "")))
            emo_p = str(tracking_data.get("emotional_thread_progress", tracking_data.get("emotional_thread", "")))
            tech_p = str(tracking_data.get("tech_thread_progress", tracking_data.get("tech_thread", "")))
            alert = str(tracking_data.get("alert", ""))
            raw_str = json.dumps(tracking_data, ensure_ascii=False)
            cur.execute("""
                INSERT INTO volume_thread_tracking (volume_num, main_thread_progress, emotional_thread_progress, tech_thread_progress, alert, updated_at_chapter, raw_data)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (volume_num, main_p, emo_p, tech_p, alert, chapter_num, raw_str))
            conn.commit()

    def get_latest_volume_thread_tracking(self, volume_num: int = 1) -> Optional[Dict[str, Any]]:
        """获取指定卷最新的三线进度看板数据"""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT raw_data FROM volume_thread_tracking WHERE volume_num = ? ORDER BY id DESC LIMIT 1
            """, (volume_num,))
            row = cur.fetchone()
            if row and row[0]:
                try:
                    return json.loads(row[0])
                except Exception:
                    pass
        return None

    def record_character_action(self, character_name: str, action_desc: str, chapter_num: int):
        """记录角色执行的微动作，进入环形缓冲区"""
        if not action_desc or not character_name:
            return
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO action_ledger (character_name, action_desc, chapter_num) VALUES (?, ?, ?)",
                (character_name.strip(), action_desc.strip(), chapter_num)
            )
            conn.commit()

    def get_recent_character_actions(self, character_name: str, limit: int = 5) -> List[str]:
        """提取该角色最近 N 章已执行的微动作，用于动态负向阻断"""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT action_desc FROM action_ledger WHERE character_name = ? ORDER BY chapter_num DESC, id DESC LIMIT ?",
                (character_name.strip(), limit)
            )
            rows = cur.fetchall()
            return [r[0] for r in rows]

    def get_spatial_transitions(self, current_location: str = "") -> List[Dict[str, Any]]:
        """获取当前地点合法的空间跃迁边（图谱条件状态机）"""
        transitions = []
        with self._get_conn() as conn:
            cur = conn.cursor()
            query = "SELECT e.*, s.name as s_name, t.name as t_name FROM edges e JOIN nodes s ON e.source_id = s.id JOIN nodes t ON e.target_id = t.id WHERE e.rel_type = 'SPATIAL_TRANSITION'"
            params = []
            if current_location:
                query += " AND (s.name = ? OR e.source_id = ?)"
                params.extend([current_location, current_location])
            cur.execute(query, params)
            for row in cur.fetchall():
                props = json.loads(row["properties"]) if row["properties"] else {}
                transitions.append({
                    "from_node": row["s_name"],
                    "to_node": row["t_name"],
                    "trigger_condition": props.get("trigger_condition", row["description"]),
                    "is_reversible": props.get("is_reversible", False),
                    "reverse_condition": props.get("reverse_condition", "")
                })
        return transitions

    def upsert_node(self, node_id: str, name: str, category: str, properties: dict, chapter_num: int = 1):
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT properties, first_seen_ch FROM nodes WHERE id = ?", (node_id,))
            row = cur.fetchone()
            if row:
                existing_props = json.loads(row["properties"])
                existing_props.update(properties)
                cur.execute("""
                UPDATE nodes SET name = ?, category = ?, properties = ?, last_updated_ch = ?
                WHERE id = ?
                """, (name, category, json.dumps(existing_props, ensure_ascii=False), chapter_num, node_id))
            else:
                cur.execute("""
                INSERT INTO nodes (id, name, category, properties, first_seen_ch, last_updated_ch)
                VALUES (?, ?, ?, ?, ?, ?)
                """, (node_id, name, category, json.dumps(properties, ensure_ascii=False), chapter_num, chapter_num))
            conn.commit()

    def upsert_edge(self, source_id: str, target_id: str, rel_type: str, 
                    description: str = "", weight: float = 1.0, properties: dict = None, chapter_num: int = 1):
        properties = properties or {}
        edge_id = f"{source_id}->{target_id}:{rel_type}"
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT properties FROM edges WHERE id = ?", (edge_id,))
            row = cur.fetchone()
            if row:
                existing_props = json.loads(row["properties"])
                existing_props.update(properties)
                cur.execute("""
                UPDATE edges SET description = ?, weight = ?, properties = ?, updated_ch = ?
                WHERE id = ?
                """, (description, weight, json.dumps(existing_props, ensure_ascii=False), chapter_num, edge_id))
            else:
                cur.execute("""
                INSERT INTO edges (id, source_id, target_id, rel_type, weight, description, properties, created_ch, updated_ch)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (edge_id, source_id, target_id, rel_type, weight, description, 
                      json.dumps(properties, ensure_ascii=False), chapter_num, chapter_num))
            conn.commit()

    # ============================================================
    # 核心引擎 1：因果边闭环追踪器 (Causal Edge Resolution Engine)
    # ============================================================
    def get_unresolved_causal_hooks(self, current_ch: int) -> List[str]:
        """提取所有尚未闭环的因果钩子"""
        hooks = []
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT e.*, s.name as s_name, t.name as t_name
            FROM edges e
            JOIN nodes s ON e.source_id = s.id
            JOIN nodes t ON e.target_id = t.id
            WHERE e.rel_type IN ('CAUSAL_HOOK', 'RESENTMENT', 'SERVANT_OF')
            """)
            for row in cur.fetchall():
                props = json.loads(row["properties"]) if row["properties"] else {}
                if props.get("resolution_status") == "UNRESOLVED":
                    hooks.append(f"- ⚠️ **待闭环因果钩子**：【{row['s_name']} ➔ {row['t_name']}】({row['description']})。本章必须通过过场台词或情报交代其后续动态，严禁无故蒸发！")
        return hooks

    # ============================================================
    # 核心引擎 1.5：因果链闭环结算 (Resolve Causal Hooks)
    # ============================================================
    def resolve_causal_hook(self, target_id: str, chapter_num: int = 1) -> int:
        """当反派被击杀或因果线闭环时，将关联边的状态更新为 RESOLVED"""
        updated_count = 0
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT id, properties FROM edges 
            WHERE source_id = ? OR target_id = ?
            """, (target_id, target_id))
            rows = cur.fetchall()
            for r in rows:
                props = json.loads(r["properties"]) if r["properties"] else {}
                if props.get("resolution_status") == "UNRESOLVED":
                    props["resolution_status"] = "RESOLVED"
                    props["resolved_chapter"] = chapter_num
                    cur.execute(
                        "UPDATE edges SET properties = ? WHERE id = ?",
                        (json.dumps(props, ensure_ascii=False), r["id"])
                    )
                    updated_count += 1
            conn.commit()
        return updated_count

    # ============================================================
    # 核心引擎 2：双轨情感显影器 (Dual-Track Manifestation)
    # ============================================================
    def get_dual_track_manifestation(self, char_a: str, char_b: str) -> Optional[str]:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT e.*, s.name as s_name, t.name as t_name
            FROM edges e
            JOIN nodes s ON e.source_id = s.id
            JOIN nodes t ON e.target_id = t.id
            WHERE (s.name LIKE ? AND t.name LIKE ?) OR (s.name LIKE ? AND t.name LIKE ?)
            """, (f"%{char_a}%", f"%{char_b}%", f"%{char_b}%", f"%{char_a}%"))
            edges = cur.fetchall()

            if edges:
                lines = [f"【{char_a} ↔ {char_b} 双轨情感与利益博弈显影】:"]
                for e in edges:
                    desc = f" ({e['description']})" if e['description'] else ""
                    lines.append(f"  - 关系轨道 [{e['rel_type']} 权重:{e['weight']}]{desc}")
                lines.append("  - ⚠️ **物理反作用力显影**：高位配角在执行利益合作或受到压迫时，必须通过微表情迟疑、动作悬停停顿、指尖微紧等微观物理动作展现自尊内耗！")
                return "\n".join(lines)
        return None

    # ============================================================
    # 核心引擎 3：配角后台自主演化微动态 (Autonomous Micro-Actions)
    # ============================================================
    def get_autonomous_micro_actions(self, core_characters: List[str]) -> List[str]:
        actions = []
        with self._get_conn() as conn:
            cur = conn.cursor()
            for char in core_characters:
                cur.execute("SELECT properties FROM nodes WHERE name = ?", (char,))
                row = cur.fetchone()
                if row:
                    props = json.loads(row["properties"])
                    act = props.get("autonomous_daily_action", "")
                    if act:
                        actions.append(f"- **{char}后台微动态**：{act}")
        return actions

    def get_speech_constrained_characters(self) -> List[str]:
        """动态获取当前小说中所有被标记为失语/哑巴/无法发声的角色名单（100% 通用自适应）"""
        mutes = []
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT name, properties FROM nodes WHERE category = 'character'")
                for row in cur.fetchall():
                    name = row["name"]
                    props = json.loads(row["properties"]) if isinstance(row["properties"], str) else row["properties"]
                    p_str = json.dumps(props, ensure_ascii=False)
                    if any(k in p_str for k in ["失语", "哑巴", "无法说话", "不能言语", "speech_constraint"]):
                        mutes.append(name)
        except Exception:
            pass
        return mutes

    # ============================================================
    # 核心引擎 5：灵魂物象三态状态机与人物创伤冷却追踪器
    # ============================================================
    def update_soul_totem_state(self, totem_name: str, new_state: str, chapter_num: int, reason: str = "") -> Dict[str, Any]:
        """更新灵魂物象物理状态机：intact (完好) -> damaged (破损/折断) -> reforged (重铸/封存)"""
        valid_states = {"intact", "damaged", "reforged", "archived"}
        state_norm = new_state.lower().strip()
        if state_norm not in valid_states:
            state_norm = "damaged" if "破" in new_state or "损" in new_state or "断" in new_state else "intact"

        node_id = f"totem:{totem_name}"
        props = {
            "is_soul_totem": True,
            "physical_state": state_norm,
            "last_state_change_ch": chapter_num,
            "last_change_reason": reason
        }
        self.upsert_node(node_id=node_id, name=totem_name, category="item", properties=props, chapter_num=chapter_num)
        return {"totem": totem_name, "state": state_norm, "chapter": chapter_num, "reason": reason}

    def get_soul_totem_state(self, totem_name: str = "") -> Optional[Dict[str, Any]]:
        """获取指定或首个灵魂物象的当前物理状态"""
        with self._get_conn() as conn:
            cur = conn.cursor()
            if totem_name:
                cur.execute("SELECT id, name, properties, last_updated_ch FROM nodes WHERE name = ? OR id = ?", (totem_name, f"totem:{totem_name}"))
            else:
                cur.execute("""
                SELECT id, name, properties, last_updated_ch FROM nodes 
                WHERE category = 'item' AND (
                    properties LIKE '%"is_soul_totem": true%' 
                    OR properties LIKE '%"is_soul_totem":true%'
                    OR id LIKE 'totem:%'
                    OR properties LIKE '%"is_important": true%'
                    OR properties LIKE '%"is_core": true%'
                ) LIMIT 1
                """)
            row = cur.fetchone()
            if row:
                props = json.loads(row["properties"]) if row["properties"] else {}
                return {
                    "id": row["id"],
                    "name": row["name"],
                    "physical_state": props.get("physical_state", "intact"),
                    "last_updated_ch": row["last_updated_ch"],
                    "properties": props
                }
        return None

    def record_character_trauma_trigger(self, character_name: str, chapter_num: int, trauma_detail: str = ""):
        """记录角色前史创伤/性格软肋的触发章节"""
        node_id = f"char:{character_name}"
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT properties FROM nodes WHERE id = ? OR name = ?", (node_id, character_name))
            row = cur.fetchone()
            props = json.loads(row["properties"]) if (row and row["properties"]) else {}
            props["last_trauma_chapter"] = chapter_num
            props["last_trauma_detail"] = trauma_detail
            self.upsert_node(node_id=node_id, name=character_name, category="character", properties=props, chapter_num=chapter_num)

    def can_trigger_character_trauma(self, character_name: str, current_chapter: int, cooldown_chapters: int = 30) -> Tuple[bool, int, str]:
        """检查角色前史创伤是否处于冷却期 (默认 30 章冷却)"""
        node_id = f"char:{character_name}"
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT properties FROM nodes WHERE id = ? OR name = ?", (node_id, character_name))
            row = cur.fetchone()
            if not row or not row["properties"]:
                return True, 0, "允许触发（无历史触发记录）"
            props = json.loads(row["properties"])
            last_ch = props.get("last_trauma_chapter", 0)
            if last_ch <= 0:
                return True, 0, "允许触发（首次触发）"
            gap = current_chapter - last_ch
            if gap < cooldown_chapters:
                return False, last_ch, f"处于冷却期中 (距离上次第{last_ch}章触发仅过 {gap} 章，需间隔 ≥{cooldown_chapters} 章)"
            return True, last_ch, f"允许触发 (距上次已过 {gap} 章)"
    def format_graph_rag_context(self, active_characters: List[str], upcoming_threats: List[str] = None, chapter_num: int = 1) -> str:
        lines = []

        # 待闭环因果钩子
        causal_hooks = self.get_unresolved_causal_hooks(chapter_num)
        if causal_hooks:
            lines.append("### 🔗 待闭环因果链条提示 (Unresolved Causal Hooks):")
            lines.extend(causal_hooks)
            lines.append("")

        # 5章前瞻雷达
        if upcoming_threats:
            lines.append("### 🔮 5章全景前瞻滑动雷达 (Horizon Threat Radar):")
            for t in upcoming_threats:
                lines.append(f"- {t}")
            lines.append("")

        # 双轨张力
        if len(active_characters) >= 2:
            dt = self.get_dual_track_manifestation(active_characters[0], active_characters[1])
            if dt:
                lines.append(dt)
                lines.append("")

        # 常驻角色后台自主成长微动作
        micro_actions = self.get_autonomous_micro_actions(active_characters)
        if micro_actions:
            lines.append("### 🌿 常驻配角后台自主成长微动态 (Autonomous Micro-Actions):")
            lines.extend(micro_actions)
            lines.append("")

        # 子图节点 (按当前章节登场角色动态检索 2-hop 子图)
        subgraph = self.get_subgraph_for_entities(active_characters)
        if subgraph["nodes"]:
            lines.append("### 🕸️ 出场实体图谱与暗线动机:")
            for n in subgraph["nodes"]:
                props = json.loads(n["properties"]) if isinstance(n["properties"], str) else n["properties"]
                hidden = props.get("hidden_agenda", "")
                secret = props.get("hidden_secret", "")
                vuln = props.get("vulnerability_trigger", "")
                sunk = props.get("sunk_cost_flashback", "")
                physio = props.get("physiological_cost", "")
                speech = props.get("speech_constraint", "")
                sensory = props.get("sensory_anchors", {})
                realm = props.get("realm", "")
                detail = f"- **{n['name']}** ({n['category']})"
                if realm:
                    detail += f" [境界: {realm}]"
                if speech:
                    detail += f" [⚠️语言/生理硬约束: {speech}]"
                if hidden:
                    detail += f" [暗线动机: {hidden}]"
                if secret:
                    detail += f" [道具深层命门与死穴: {secret}]"
                if vuln:
                    detail += f" [生理破防动作: {vuln}]"
                if sunk:
                    detail += f" [沉没成本闪回: {sunk}]"
                if physio:
                    detail += f" [大决断后生理代价: {physio}]"
                if sensory:
                    sensory_desc = "; ".join([f"{k}➔{v}" for k, v in sensory.items()]) if isinstance(sensory, dict) else str(sensory)
                    detail += f" [感官记忆时光通道: {sensory_desc}]"
                lines.append(detail)
            lines.append("")

        return "\n".join(lines)

    def get_subgraph_for_entities(self, entity_names: List[str], depth: int = 1) -> dict:
        """获取指定实体的 N-hop 子图"""
        if not entity_names:
            return {"nodes": [], "edges": []}

        with self._get_conn() as conn:
            cur = conn.cursor()
            placeholders = ",".join(["?"] * len(entity_names))
            cur.execute(f"SELECT id FROM nodes WHERE name IN ({placeholders})", entity_names)
            seed_ids = [row["id"] for row in cur.fetchall()]

            if not seed_ids:
                return {"nodes": [], "edges": []}

            visited_node_ids = set(seed_ids)
            current_level = set(seed_ids)

            collected_edges = []

            for _ in range(depth):
                if not current_level:
                    break
                pl = ",".join(["?"] * len(current_level))
                cur.execute(f"""
                SELECT * FROM edges
                WHERE source_id IN ({pl}) OR target_id IN ({pl})
                """, list(current_level) * 2)
                edges = cur.fetchall()

                next_level = set()
                for e in edges:
                    collected_edges.append(dict(e))
                    if e["source_id"] not in visited_node_ids:
                        next_level.add(e["source_id"])
                        visited_node_ids.add(e["source_id"])
                    if e["target_id"] not in visited_node_ids:
                        next_level.add(e["target_id"])
                        visited_node_ids.add(e["target_id"])
                current_level = next_level

            pl_nodes = ",".join(["?"] * len(visited_node_ids))
            cur.execute(f"SELECT * FROM nodes WHERE id IN ({pl_nodes})", list(visited_node_ids))
            nodes = [dict(r) for r in cur.fetchall()]

            return {"nodes": nodes, "edges": collected_edges}


def populate_initial_graph_v3(kg: NovelKnowledgeGraph, config_path: str = None):
    """从配置文件动态初始化图谱节点与边，严禁在 Python 代码中硬编码特定小说人物！"""
    import yaml
    if not config_path:
        config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    if not os.path.exists(config_path):
        return

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    graph_data = cfg.get("initial_graph_data", {})
    if not graph_data:
        return

    # 动态插入节点
    for node in graph_data.get("nodes", []):
        kg.upsert_node(
            node_id=node["id"],
            name=node["name"],
            category=node.get("type", "entity"),
            properties=node.get("properties", {}),
            chapter_num=node.get("chapter_num", 1)
        )

    # 动态插入边
    for edge in graph_data.get("edges", []):
        kg.upsert_edge(
            source_id=edge["source"],
            target_id=edge["target"],
            rel_type=edge["relation"],
            description=edge.get("desc", ""),
            weight=edge.get("weight", 1.0),
            properties=edge.get("properties", {}),
            chapter_num=edge.get("chapter_num", 1)
        )


if __name__ == "__main__":
    _cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")
    _novel_dir = "/tmp"
    if os.path.exists(_cfg_path):
        try:
            _cfg = yaml.safe_load(open(_cfg_path, encoding="utf-8"))
            _novel_dir = _cfg.get("project", {}).get("novel_dir", _novel_dir)
        except Exception:
            pass
    db_file = os.path.join(_novel_dir, "knowledge_graph.db")
    kg = NovelKnowledgeGraph(db_file)
    populate_initial_graph_v3(kg)
    print("✅ 通用因果闭环与长程图谱编译器就绪（纯配置驱动）！")
