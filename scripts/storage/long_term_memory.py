#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LangGraph P4 落地：超长篇本地轻量级事实与伏笔向量检索库 (Long-Term World Store)
纯原生实现：基于 Python 内置 sqlite3 + FTS5 全文检索引擎 + BM25 排序。
零外部依赖，单文件 memory.db 落盘于小说项目目录。
"""

import os, sys, sqlite3, json, re, time, threading

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import yaml
_current_db_path = None
_memory_conn = None
_memory_lock = threading.Lock()

def get_db_path() -> str:
    """动态获取当前活跃小说的 memory.db 绝对路径（支持多书秒切，防止 import 缓存旧路径）"""
    try:
        from pipeline.utils import load_active_config
        c = load_active_config(script_dir=SCRIPT_DIR)
        novel_dir = c.get("project", {}).get("novel_dir", "")
        if novel_dir:
            return os.path.join(novel_dir, "memory.db")
    except Exception:
        pass
    return os.path.join(SCRIPT_DIR, "memory.db")

def get_db_conn():
    """获取 SQLite 数据库持久连接并初始化 FTS5 虚拟表（带动态路径自愈）"""
    global _memory_conn, _current_db_path
    active_path = get_db_path()
    with _memory_lock:
        if _memory_conn is None or _current_db_path != active_path:
            if _memory_conn is not None:
                try:
                    _memory_conn.close()
                except Exception:
                    pass
            _current_db_path = active_path
            os.makedirs(os.path.dirname(os.path.abspath(active_path)), exist_ok=True)
            _memory_conn = sqlite3.connect(active_path, check_same_thread=False)
            try:
                from pipeline.utils import configure_sqlite_resilience
                configure_sqlite_resilience(_memory_conn)
            except Exception:
                pass
            
            # 1. 实体事实表（地理、门派、法宝、人物长线档案）
            _memory_conn.execute("""
            CREATE TABLE IF NOT EXISTS entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                category TEXT, -- 'location', 'item', 'character', 'sect', 'lore'
                description TEXT,
                first_chapter INTEGER,
                last_updated_chapter INTEGER
            );
            """)

            # 2. 长线伏笔与暗线库
            _memory_conn.execute("""
            CREATE TABLE IF NOT EXISTS plot_vault (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_name TEXT UNIQUE,
                planted_chapter INTEGER,
                summary TEXT,
                status TEXT, -- 'active', 'resolved', 'dormant'
                related_entities TEXT
            );
            """)

            # 3. FTS5 全文检索引擎（毫秒级高精度召回）
            _memory_conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS fts_lore USING fts5(
                doc_id UNINDEXED,
                category UNINDEXED,
                title,
                content,
                tokenize = 'unicode61'
            );
            """)
            _memory_conn.commit()
        return _memory_conn

def index_entity(name: str, category: str, description: str, chapter_num: int):
    """录入或更新世界观实体"""
    conn = get_db_conn()
    with _memory_lock:
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO entities (name, category, description, first_chapter, last_updated_chapter)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            description=excluded.description,
            last_updated_chapter=excluded.last_updated_chapter;
        """, (name, category, description, chapter_num, chapter_num))

        # 同步更新 FTS5 索引
        cur.execute("DELETE FROM fts_lore WHERE title = ?", (name,))
        cur.execute("""
        INSERT INTO fts_lore (doc_id, category, title, content)
        VALUES (?, ?, ?, ?);
        """, (chapter_num, category, name, description))
        conn.commit()

def index_plot_thread(thread_name: str, planted_chapter: int, summary: str, status: str = "active"):
    """录入或更新长线伏笔"""
    conn = get_db_conn()
    with _memory_lock:
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO plot_vault (thread_name, planted_chapter, summary, status)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(thread_name) DO UPDATE SET
            summary=excluded.summary,
            status=excluded.status;
        """, (thread_name, planted_chapter, summary, status))

        # 同步到 FTS5
        cur.execute("DELETE FROM fts_lore WHERE title = ?", (thread_name,))
        cur.execute("""
        INSERT INTO fts_lore (doc_id, category, title, content)
        VALUES (?, 'plot_thread', ?, ?);
        """, (planted_chapter, thread_name, summary))
        conn.commit()

def query_relevant_lore(query_text: str, current_chapter: int = 1, top_k: int = 3, decay_lambda: float = 0.02) -> str:
    """
    根据本章细纲与关键词，融合 FTS5 BM25 与【时空衰减因子 (Temporal Decay)】高精度召回历史设定与伏笔：
    Final Score = |BM25| * exp(-lambda * (current_chapter - event_chapter))
    优先召回近期强关联事实，防止百章前的陈旧闭环抢占上下文。
    """
    import math
    db_file = get_db_path()
    if not os.path.exists(db_file):
        return ""

    # 提取中文关键词（2字以上词汇）
    keywords = re.findall(r'[\u4e00-\u9fff]{2,6}', query_text)
    if not keywords:
        return ""

    # 排除高频无意义词
    stop_words = {"场景", "地点", "人物", "登场", "核心", "事件", "对话", "细节", "感官", "描写", "情感", "落点", "钩子", "主角", "开始", "随后"}
    filtered_kws = [k for k in keywords if k not in stop_words][:8]
    if not filtered_kws:
        return ""

    fts_query = " OR ".join(f'"{k}"' for k in filtered_kws)

    conn = get_db_conn()
    with _memory_lock:
        cur = conn.cursor()
        try:
            cur.execute("""
            SELECT doc_id, category, title, content, rank
            FROM fts_lore
            WHERE fts_lore MATCH ?
            ORDER BY rank
            LIMIT ?;
            """, (fts_query, top_k * 3))
            rows = cur.fetchall()

            if not rows:
                return ""

            # 时空衰减重打分
            scored_candidates = []
            for doc_id, cat, title, content, bm25_rank in rows:
                # 解析章节号
                ch_num = current_chapter
                if isinstance(doc_id, int):
                    ch_num = doc_id
                elif isinstance(doc_id, str):
                    m_num = re.search(r'\d+', doc_id)
                    if m_num:
                        ch_num = int(m_num.group(0))

                delta_ch = max(0, current_chapter - ch_num)
                decay_factor = math.exp(-decay_lambda * delta_ch)
                # SQLite FTS5 rank 越小越相关(通常为负数)，取绝对值后乘衰减因子
                recency_score = abs(float(bm25_rank)) * decay_factor
                scored_candidates.append((recency_score, cat, title, content, ch_num))

            # 按衰减综合得分降序排序
            scored_candidates.sort(key=lambda x: x[0], reverse=True)
            top_results = scored_candidates[:top_k]

            lines = ["<long_term_lore_retrieval>"]
            lines.append("【长线记忆召回（从 memory.db 毫秒级时空衰减提取的关联前文设定）】：")
            for _, cat, title, content, ch_num in top_results:
                lines.append(f"- [{cat} | 第{ch_num}章] 《{title}》: {content.strip()[:100]}")
            lines.append("</long_term_lore_retrieval>")
            return "\n".join(lines)
        except Exception:
            return ""
