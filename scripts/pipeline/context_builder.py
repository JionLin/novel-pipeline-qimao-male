# -*- coding: utf-8 -*-
"""
pipeline/context_builder.py - 设定集与细纲上下文组装器
包含：
1. 卷大纲配置与单/多文件细纲切片加载 (get_outline_config / extract_chapter_outline / load_chapter_outline)
2. 章节标题提取 (extract_chapter_title)
3. 动态全书设定集组装 (build_novel_settings)
4. 上一章结尾物理连续提取 (read_tail)
5. 关键卡点章节计算 (get_climax_chapters)
"""

import os
import re
import glob
import json
from typing import Dict, Any, List, Optional, Tuple


def read_tail(
    novel_dir: str,
    ch_prefix: str,
    ch_suffix: str,
    chapter_num: int,
    tail_chars: int = 500
) -> str:
    """读取上一章的末尾 N 字符（前文连贯性凭证）"""
    if chapter_num <= 1:
        return ""
    prev_num = chapter_num - 1
    # 优先正文子目录，兼容根目录
    for d in [os.path.join(novel_dir, "正文"), novel_dir]:
        p = os.path.join(d, f"{ch_prefix}{prev_num}{ch_suffix}")
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    text = f.read().strip()
                # 排除可能包含的标题行与 XML 标记
                clean = re.sub(r"^#\s*第\d+章.*?\n", "", text).strip()
                clean = re.sub(r"<.*?>", "", clean).strip()
                return clean[-tail_chars:] if len(clean) > tail_chars else clean
            except Exception:
                return ""
    return ""


def get_outline_config(cfg: Dict[str, Any], chapter_num: int) -> dict:
    """根据章节号返回对应的卷配置（含 mode/file_pattern/outline 路径）"""
    for vol in cfg.get("volume_routing", []):
        lo, hi = vol["range"]
        if lo <= chapter_num <= hi:
            return vol
    raise ValueError(f"章节 {chapter_num} 超出已知卷级范围")


def extract_chapter_outline(outline_text: str, chapter_num: int) -> str:
    """
    单文件模式的大纲切片：严格锚定单章独立标题（排除卷范围与括号注解）
    支持：### **第X章：标题** / **第X章：标题** / 第X章：标题
    """
    start_patterns = [
        rf"(?:^|\n)\s*#{{1,4}}\s*\*{{0,2}}第{chapter_num}章[：:\s]",
        rf"(?:^|\n)\s*\*{{2}}第{chapter_num}章[：:\s]",
        rf"\|\s*第{chapter_num}章\s*\|",
        rf"(?:^|\n)\s*第{chapter_num:03d}章[：:\s]",
        rf"(?:^|\n)\s*第{chapter_num:02d}章[：:\s]",
        rf"(?:^|\n)\s*第{chapter_num}章[：:\s]",
    ]
    m_start = None
    for sp in start_patterns:
        m_start = re.search(sp, outline_text)
        if m_start:
            break
    if not m_start:
        raise ValueError(f"在大纲中找不到第{chapter_num}章的细纲")

    # 优先精确匹配第 N+1 章；若大纲跳号，则寻找任意后续章节标题作为截止点
    rest_text = outline_text[m_start.end():]
    next_patterns = [
        rf"(?:\n|^)\s*#{{1,4}}\s*\*{{0,2}}第{chapter_num + 1}章[：:\s]",
        rf"(?:\n|^)\s*\*{{2}}第{chapter_num + 1}章[：:\s]",
        rf"\|\s*第{chapter_num + 1}章\s*\|",
        rf"(?:\n|^)\s*第{chapter_num + 1:03d}章[：:\s]",
        rf"(?:\n|^)\s*第{chapter_num + 1:02d}章[：:\s]",
        rf"(?:\n|^)\s*第{chapter_num + 1}章[：:\s]",
        r"(?:\n|^)\s*#{1,4}\s*\*{0,2}第\d+章[：:\s]",
        r"(?:\n|^)\s*\*{2}第\d+章[：:\s]",
        r"\|\s*第\d+章\s*\|"
    ]
    m_next = None
    for np_ in next_patterns:
        m_next = re.search(np_, rest_text)
        if m_next:
            break
    if m_next:
        return outline_text[m_start.start():m_start.end() + m_next.start()].strip()
    else:
        return outline_text[m_start.start():].strip()


def load_chapter_outline(
    cfg: Dict[str, Any],
    chapter_num: int,
    log_func=None
) -> str:
    """
    加载第 chapter_num 章的细纲内容（统一入口）
    - multi_file 模式：按 file_pattern 找到该章独立细纲文件
    - single_file 模式：从 outline 文件切片，并支持从储备库自动滚动加载
    """
    outline_dir = cfg["project"]["outline_dir"]
    novel_dir = cfg.get("project", {}).get("novel_dir", outline_dir)
    vol = get_outline_config(cfg, chapter_num)
    mode = vol.get("mode", "single_file")

    if mode == "multi_file":
        fp = vol.get("file_pattern", "第{num:03d}章_*.md")
        pattern = fp.format(num=chapter_num) if "{num" in fp else fp.replace("{num}", str(chapter_num))
        if "{num" in pattern:
            pattern = fp.replace("{num:03d}", f"{chapter_num:03d}").replace("{num}", str(chapter_num))
        search_dir = vol.get("outline", "") or vol.get("file", "")
        search_dir = search_dir if (search_dir and os.path.isdir(search_dir)) else outline_dir
        matches = glob.glob(os.path.join(search_dir, pattern))
        if not matches:
            exact = os.path.join(search_dir, pattern.replace("*", ""))
            if os.path.exists(exact):
                matches = [exact]
        if not matches:
            raise ValueError(f"multi_file 模式下找不到第{chapter_num}章细纲文件（模式: {pattern}，目录: {search_dir}）")
        matches.sort()
        with open(matches[0], "r", encoding="utf-8") as rf:
            return rf.read()
    else:
        outline_file = vol.get("outline", "") or vol.get("file", "") or "大纲/第1卷_章节细纲.md"
        if not os.path.isabs(outline_file):
            outline_file = os.path.join(outline_dir, outline_file)

        if not os.path.exists(outline_file):
            # 智能多路径候选探测
            vol_id = vol.get('volume', 1)
            standard_candidates = [
                os.path.join(novel_dir, "大纲", f"第{vol_id}卷_章节细纲.md"),
                os.path.join(novel_dir, f"第{vol_id}卷_章节细纲.md"),
                os.path.join(novel_dir, "大纲.md"),
            ]
            found = False
            for sc in standard_candidates:
                if os.path.exists(sc):
                    outline_file = sc
                    found = True
                    break
            if not found:
                candidates = glob.glob(os.path.join(outline_dir, "**", "*.md"), recursive=True)
                for cand in candidates:
                    if f"第{vol_id}卷" in cand or f"卷{vol_id}" in cand or "细纲" in cand:
                        outline_file = cand
                        found = True
                        break
            if not os.path.exists(outline_file):
                # 若文件尚不存在，安全初始化空文件
                os.makedirs(os.path.dirname(outline_file), exist_ok=True)
                with open(outline_file, "w", encoding="utf-8") as wf:
                    wf.write(f"# 第{vol_id}卷_章节细纲\n\n")

        with open(outline_file, "r", encoding="utf-8") as rf:
            outline_text = rf.read()
        try:
            return extract_chapter_outline(outline_text, chapter_num)
        except ValueError as e:
            # 方案 B 动态滑动视距：尝试从储备库文件动态加载超前细纲并追加到活跃细纲池
            parent_dir = os.path.dirname(outline_file)
            reserve_files = glob.glob(os.path.join(parent_dir, "*储备*.md")) + glob.glob(os.path.join(outline_dir, "**", "*储备*.md"), recursive=True)
            for rf in set(reserve_files):
                if os.path.exists(rf) and rf != outline_file:
                    try:
                        with open(rf, "r", encoding="utf-8") as r_f:
                            rf_text = r_f.read()
                        ch_outline = extract_chapter_outline(rf_text, chapter_num)
                        if ch_outline:
                            with open(outline_file, "a", encoding="utf-8") as af:
                                af.write(f"\n\n---\n\n{ch_outline}\n")
                            msg = f"[滑动细纲] ✅ 自动从储备库 {os.path.basename(rf)} 滚动加载第 {chapter_num} 章细纲至活跃池！"
                            if log_func:
                                log_func(msg)
                            else:
                                print(msg)
                            return ch_outline
                    except Exception:
                        pass
            raise e


def extract_chapter_title(outline_text: str, chapter_num: int = 0, cfg: Optional[Dict[str, Any]] = None) -> str:
    """从细纲内容或配置中提取章节标题"""
    if chapter_num and cfg:
        custom_titles = cfg.get("title_style", {}).get("chapter_titles", {})
        if chapter_num in custom_titles:
            t = custom_titles[chapter_num]
            return re.sub(r"^第\d+章[：:]\s*", "", t).strip()
    patterns = [
        r'#\s*第\d+章[：:]\s*([^\n\r]+)',
        r'\*\*第\d+章[：:]\s*([^\*\n\r]+)\*\*',
        r'第\d+章[：:]\s*([^\n\r]+)',
    ]
    for pat in patterns:
        m = re.search(pat, outline_text)
        if m:
            title = m.group(1).strip()
            title = re.sub(r'^\*+|\*+$', '', title).strip()
            if title:
                return title
    return ""


def build_novel_settings(cfg: Dict[str, Any]) -> str:
    """从 master_outline（总纲）+ config.yaml 结构化提取核心设定集 <novel_settings>（高信噪比 AST 分块提取）"""
    parts = []
    master_outline = cfg.get("project", {}).get("master_outline", "")
    if master_outline and os.path.exists(master_outline):
        try:
            with open(master_outline, "r", encoding="utf-8") as f:
                master_text = f.read()
            
            # 1. 结构化大纲核心板块分块提取（世界观、核心主线、核心人设与金手指）
            sections_to_extract = [
                r"(?:^|\n)##\s*一[、.\s][^\n]*\n([\s\S]*?)(?=\n##\s+[^\n#]|\Z)",
                r"(?:^|\n)##\s*二[、.\s][^\n]*\n([\s\S]*?)(?=\n##\s+[^\n#]|\Z)",
                r"(?:^|\n)##\s*三[、.\s][^\n]*\n([\s\S]*?)(?=\n##\s+[^\n#]|\Z)",
                r"(?:^|\n)##\s*四[、.\s][^\n]*\n([\s\S]*?)(?=\n##\s+[^\n#]|\Z)",
            ]
            extracted_blocks = []
            for sec_pat in sections_to_extract:
                m_sec = re.search(sec_pat, master_text)
                if m_sec:
                    sec_content = m_sec.group(1).strip()
                    # 仅保留核心条款行（列表行、加粗标题行），过滤长篇展开
                    key_lines = [l.strip() for l in sec_content.split("\n") if l.strip().startswith(("-", "*", "**", "#"))]
                    if key_lines:
                        extracted_blocks.append("\n".join(key_lines[:8]))  # 限制每板块最多前8条核心公理
            
            if extracted_blocks:
                parts.append("【全书核心总纲世界观与主线公理】:\n" + "\n\n".join(extracted_blocks))
        except Exception:
            pass

    static_bs = cfg.get("static_backstory", {})
    if static_bs:
        for k, v in static_bs.items():
            if v:
                parts.append(f"【{k}】: {v}")

    protagonist_style = cfg.get("protagonist_style", {})
    if protagonist_style.get("enabled", False):
        desc = protagonist_style.get("description", "")
        reqs = protagonist_style.get("hard_requirements", [])
        parts.append(f"【主角行事风格】: {desc}")
        for r in reqs:
            parts.append(f"  - {r}")

    taboos = cfg.get("quality", {}).get("absolute_taboos", [])
    if taboos:
        parts.append("【绝对禁忌】:")
        for t in taboos:
            parts.append(f"  - {t}")

    # 注入灵魂物象状态与历史时间线
    novel_dir = cfg.get("project", {}).get("novel_dir", "")
    if novel_dir and os.path.exists(novel_dir):
        try:
            from storage.state_manager import get_soul_totem_state
            totem = get_soul_totem_state(novel_dir)
            if totem:
                t_props = totem.get("properties", {})
                totem_info = f"""【🔮 核心灵魂物象状态与历史追踪】：
- 物象名称：{totem.get('name', '未命名')}
- 当前物理状态：[{totem.get('physical_state', 'intact')}] (上次变更: 第 {totem.get('last_updated_ch', 1)} 章)
- 历史变更原因：{t_props.get('last_change_reason', '初始状态')}
- 远端/近端镜像要求：若本章涉及远端高位对弈者（皇帝/宿敌/掌门），必须描写该物象在其视线/御案中的物理在场细节！"""
                parts.append(totem_info)
        except Exception:
            pass

    return "\n".join(parts)


def get_climax_chapters(total_chapters: int) -> list[int]:
    """根据总章数计算全书核心卡点章节列表"""
    points = [10, 20, 30, 40, 50, 80, 100]
    fractions = [0.25, 0.50, 0.75, 0.90, 0.995]
    for frac in fractions:
        ch = int(total_chapters * frac)
        if ch > 100 and ch not in points:
            points.append(ch)
    points.sort()
    return points


def get_recent_chapter_types(novel_dir: str, current_ch: int, window: int = 3) -> List[Tuple[int, str]]:
    """提取当前章节前序 N 章的已定章节类型 (从大纲目录各细纲文件中解析)"""
    if current_ch <= 1 or not novel_dir or not os.path.exists(novel_dir):
        return []

    outline_files = glob.glob(os.path.join(novel_dir, "大纲", "*.md")) + glob.glob(os.path.join(novel_dir, "*.md"))
    outline_files = [f for f in outline_files if "大纲.md" not in os.path.basename(f) and "施工图" not in os.path.basename(f)]

    all_outlines_text = ""
    for f in sorted(outline_files):
        try:
            with open(f, "r", encoding="utf-8") as rf:
                all_outlines_text += "\n" + rf.read()
        except Exception:
            pass

    if not all_outlines_text:
        return []

    from outline.narrative_linter import extract_chapters_from_outline_text
    chapters = extract_chapters_from_outline_text(all_outlines_text)
    type_map = {}

    for ch_num, ch_text in chapters:
        m_json = re.search(r'```json\s*(.*?)\s*```', ch_text, re.DOTALL)
        ch_type = ""
        if m_json:
            try:
                mdata = json.loads(m_json.group(1).strip())
                ch_type = str(mdata.get("type", "")).strip().upper()
            except Exception:
                pass
        if not ch_type:
            m_t = re.search(r'####\s*1\.\s*章节类型[^\n]*\n\s*\[?([A-Fa-f])类', ch_text)
            if m_t:
                ch_type = m_t.group(1).upper()
        if ch_type:
            type_map[ch_num] = ch_type

    start_target = max(1, current_ch - window)
    recent_types = []
    for ch_idx in range(start_target, current_ch):
        if ch_idx in type_map:
            recent_types.append((ch_idx, type_map[ch_idx]))

    return recent_types


def build_chapter_type_advisory_directive(novel_dir: str, current_ch: int, window: int = 3) -> str:
    """基于前序章节类型滑动窗口，构建 JIT 细纲生成的动态熔断与配额建议横幅"""
    recent = get_recent_chapter_types(novel_dir, current_ch, window)
    if not recent:
        return ""

    history_lines = [f"- 第 {ch} 章: [{t}类]" for ch, t in recent]
    history_str = "\n".join(history_lines)

    lines = [
        "【📊 前序章节类型滑动窗口监控】:",
        history_str
    ]

    # 检查是否最近 2 章均为 C 类
    types_only = [t for _, t in recent]
    if len(types_only) >= 2 and types_only[-1] == "C" and types_only[-2] == "C":
        last_two_chs = [ch for ch, _ in recent[-2:]]
        lines.append(
            f"⚠️ **【触发强制类型熔断门禁】**：前两章（第 {last_two_chs[0]}、{last_two_chs[1]} 章）连续为 C 类(造物/突破)，"
            f"本批次（第 {current_ch} 章起）强制熔断，严禁输出 C 类！第 {current_ch} 章必须切换为 B 类 (动作) 或 D 类 (人物关系)！"
        )
    else:
        lines.append("ℹ️ 类型配额提示：遵循 C 类连续不超过 2 章，每 10 章内保持 B 类(动作)与 D 类(人物关系)均衡。")

    return "\n".join(lines) + "\n"


def get_dormant_entities_directive(novel_dir: str, current_chapter: int, threshold: int = 10) -> str:
    """
    查询知识图谱中超过 threshold 章未出场的核心实体 (人物/物象)，
    自动组装硬提醒指令，防止核心角色与物象在长篇中被遗忘。
    """
    if not novel_dir or not os.path.exists(novel_dir):
        return ""
    kg_db = os.path.join(novel_dir, "knowledge_graph.db")
    if not os.path.exists(kg_db):
        return ""

    import sqlite3
    from pipeline.utils import configure_sqlite_resilience
    try:
        conn = sqlite3.connect(kg_db)
        configure_sqlite_resilience(conn)
        cur = conn.cursor()
        cur.execute("""
            SELECT name, category, last_updated_ch, properties FROM nodes 
            WHERE category IN ('character', 'item') 
              AND last_updated_ch IS NOT NULL 
              AND last_updated_ch > 0
              AND ? - last_updated_ch >= ?
            ORDER BY last_updated_ch ASC LIMIT 3
        """, (current_chapter, threshold))
        rows = cur.fetchall()
        conn.close()

        if not rows:
            return ""

        reminders = []
        for name, category, last_ch, props in rows:
            cat_cn = "核心物象" if category == "item" else "核心角色"
            diff = current_chapter - last_ch
            reminders.append(f"  - 【{cat_cn}·{name}】（上次出场：第 {last_ch} 章，已沉寂 {diff} 章）：本章如有合适场景，建议安排 1 处微观动作、物理测量或侧面台词提及！")

        return "【🔮 知识图谱休眠实体主动唤醒】:\n" + "\n".join(reminders)
    except Exception:
        return ""


def get_due_plot_vault_directive(novel_dir: str, current_chapter: int) -> str:
    """
    查询 memory.db 的 plot_vault，提取当前处于活跃状态的长线暗线伏笔，
    下发到期或临界推进指令。
    """
    if not novel_dir or not os.path.exists(novel_dir):
        return ""
    mem_db = os.path.join(novel_dir, "memory.db")
    if not os.path.exists(mem_db):
        return ""

    import sqlite3
    from pipeline.utils import configure_sqlite_resilience
    try:
        conn = sqlite3.connect(mem_db)
        configure_sqlite_resilience(conn)
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(plot_vault)")
        cols = [r[1] for r in cur.fetchall()]
        title_col = "title" if "title" in cols else "thread_name"
        ch_col = "planted_ch" if "planted_ch" in cols else "planted_chapter"
        content_col = "content" if "content" in cols else "summary"

        cur.execute(f"""
            SELECT {title_col}, {ch_col}, {content_col} FROM plot_vault 
            WHERE status IN ('active', 'ACTIVE')
            ORDER BY {ch_col} ASC LIMIT 2
        """)
        rows = cur.fetchall()
        conn.close()

        if not rows:
            return ""

        hooks = []
        for title, p_ch, content in rows:
            hooks.append(f"  - 【暗线伏笔·{title}】（第 {p_ch} 章埋设）: {content[:45]}... (本章适度推进细节或安排回扣线索)")

        return "【📌 长程暗线伏笔推进与回扣提醒】:\n" + "\n".join(hooks)
    except Exception:
        return ""


def precompute_taste_and_rest_directives(chapter_outline: str, chapter_num: int) -> Dict[str, str]:
    """
    根据当章细纲场景特征，确定性预计算当章必填味觉与四类休整行为，
    将抽象规则转变为确定性填空参数。
    """
    # 1. 场景关联味觉派生
    taste_keywords_food = ["吃", "喝", "茶", "饼", "干粮", "酒", "肉", "粥", "水", "汤", "宴", "分食"]
    taste_keywords_industry = ["铁", "钢", "高炉", "焦炭", "火药", "硫磺", "硝", "酸", "锻打", "矿", "镗床", "枪", "机台"]
    taste_keywords_combat = ["杀", "战", "伏击", "刀", "箭", "血", "伤", "破军", "中伏", "突围", "搏杀"]

    if any(k in chapter_outline for k in taste_keywords_food):
        derived_taste = "饮食直接味觉（如：干冷麦饼在舌根泛起的粗粝麦麸微苦，或热茶顺喉而下的甘温解渴感）"
    elif any(k in chapter_outline for k in taste_keywords_industry):
        derived_taste = "工业材料物理微颗粒（如：焦煤粉尘吸入咽喉的微酸焦涩，或铁屑碎沫在舌尖残留的微冷铁锈腥味）"
    elif any(k in chapter_outline for k in taste_keywords_combat):
        derived_taste = "战火生理应激味觉（如：剧烈喘息导致口腔干涸黏腻、吞咽唾沫时的喉头紧绷，或嘴角渗入的一丝血沫腥甜）"
    else:
        derived_taste = "环境空气直接感知（如：吸入冰冷刺骨风雪时的喉管清冽刺痛，或汗水淌过唇边的淡淡微咸）"

    # 2. 四类生理休整池确定性轮换
    pool_idx = chapter_num % 4
    rest_pools = [
        "行为池 1·器具与数据维护（如：掏出量具校准工件公差、粗布擦拭工具并盖严机台、在牛皮本记录数据）",
        "行为池 2·物理温差与解压（如：冷水浸透布巾缚额、热毛巾敷膝、靠着窑壁/火盆烘干湿透护腕、啜饮热汤）",
        "行为池 3·身体自愈与创口处理（如：独自清洗换药包扎伤口、剔除指缝碎屑铁渣、按揉酸痛手腕）",
        "行为池 4·静默呼吸与感官数息（如：背靠木架闭目调匀呼吸、听风箱/雨滴节奏数息休整）"
    ]
    derived_rest = rest_pools[pool_idx]

    # 3. 数字推演与量具微观动作强绑定
    calc_keywords = ["计算", "推演", "里", "公差", "账目", "概率", "算力", "数据", "折算", "成", "分", "厘"]
    if any(k in chapter_outline for k in calc_keywords):
        derived_calc = "专属物象算力强绑定：本章涉及数字/里程/公差推演时，必须一对一绑定主角指腹在专属量具（如骨尺/卡尺/刻度槽）上滑动、微调的物理手部微观动作，严禁悬空无依托内心推理！"
    else:
        derived_calc = ""

    return {
        "taste_directive": derived_taste,
        "rest_directive": derived_rest,
        "calculation_directive": derived_calc
    }

