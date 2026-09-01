# -*- coding: utf-8 -*-
"""
outline/chapter_generator.py - 分卷与分章细纲生成引擎
包含：
1. 卷信息计算与路由 (get_volume_info)
2. 主角心境演进状态机指令生成 (build_protagonist_arc_directive)
3. 链式滑动细纲生成引擎 (generate_chapter_outlines)
"""

import os
import re
from typing import Dict, Any, List, Optional, Tuple
from outline.master_generator import (
    extract_targeted_master_context,
    extract_macro_phase_anchor,
    extract_dark_night_prelude_chapter,
    extract_fallback_hooks_from_master
)


def format_chapter_three_act_ratios_guide(cfg: Dict[str, Any]) -> str:
    """从 config.yaml 动态读取微观三幕比例指导"""
    ratios = cfg.get("structure", {}).get("chapter_three_act_ratios", {})
    if not ratios:
        return """- **A类·智斗**：开端 20% ➔ 发展 50% ➔ 收束 30%
- **B类·动作**：开端 15% ➔ 发展 60% ➔ 收束 25%
- **C类·工业/造物**：开端 20% ➔ 发展 55% ➔ 收束 25%
- **D类·人物关系**：开端 25% ➔ 发展 45% ➔ 收束 30%
- **E类·过渡叙事**：开端 30% ➔ 发展 40% ➔ 收束 30%
- **F类·复合高潮**：开端 10% ➔ 发展 60% ➔ 收束 30%"""
    lines = []
    for k, v in ratios.items():
        name = v.get("name", k)
        act1 = v.get("act1", "20%")
        act2 = v.get("act2", "50%")
        act3 = v.get("act3", "30%")
        notes = v.get("notes", "")
        note_str = f" ({notes})" if notes else ""
        lines.append(f"- **{k}类·{name}**：开端 {act1} ➔ 发展 {act2} ➔ 收束 {act3}{note_str}")
    return "\n".join(lines)


def get_volume_info(target_ch: int, total_chapters: int = 1125, target_words: int = 2700000) -> Tuple[int, int, int]:
    """根据目标章节号推导所属卷号及该卷的起止章节号"""
    chapters_per_vol = 50
    if target_words >= 1500000:
        chapters_per_vol = 100
    elif target_words <= 500000:
        chapters_per_vol = 30

    vol_num = max(1, (target_ch - 1) // chapters_per_vol + 1)
    vol_start = (vol_num - 1) * chapters_per_vol + 1
    vol_end = min(total_chapters, vol_num * chapters_per_vol)
    return vol_num, vol_start, vol_end


def merge_chapter_outlines_deduplicated(file_path: str, new_outline_text: str) -> None:
    """原子级去重合并章节细纲文件：兼容多种 Markdown 标题格式，按章节号精准覆盖老旧版本，保持章节顺序严格单调递增"""
    import re
    existing_text = ""
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as rf:
                existing_text = rf.read()
        except Exception:
            pass

    # 1. 拆解现有与新增细纲为单章字典 {ch_num: content}
    # 宽容匹配: ### **第X章... 或 ### 第X章... 或 ## 第X章...
    chapters_map = {}
    pattern = r"(#{2,4}\s*\*?\*?第(\d+)章[：:\s*][^\n\r]+.*?(?=(?:\n#{2,4}\s*\*?\*?第\d+章|\Z)))"
    
    for match, ch_str in re.findall(pattern, existing_text, re.DOTALL):
        chapters_map[int(ch_str)] = match.strip()

    for match, ch_str in re.findall(pattern, new_outline_text, re.DOTALL):
        chapters_map[int(ch_str)] = match.strip()

    # 2. 按章节号升序重新排序组合
    sorted_chs = sorted(chapters_map.keys())
    merged_blocks = []
    for ch_num in sorted_chs:
        merged_blocks.append(chapters_map[ch_num])

    final_content = "\n\n---\n\n".join(merged_blocks) + "\n"
    from pipeline.utils import atomic_write
    atomic_write(file_path, final_content)


def build_protagonist_arc_directive(current_start: int, total_chapters: int, mc_name: str = "主角") -> str:
    """基于全书总进度百分比动态计算角色心境与博弈演进状态机"""
    ratio = current_start / max(1, total_chapters)
    if ratio <= 0.20:
        stage_title = "第一阶段（底层绝境·精密控局与果断反击）"
        mindset = f"{mc_name}处于底层绝境，冷峻精密、算力优先、谋定后动、绝不被动受辱，以物理公差与数据闭环构筑初期生存与权力壁垒"
        guilt = "冷静克制、算力优先，在严苛压迫中以公差漏洞或规则盲区实施果断反杀与立威"
        villain = "反派带着绝对的阶层俯视与规矩碾压，充满利益算计与信息差剥削"
        hook = "在日常细节中埋设环境资源、同伴习惯或底层暗线的微小伏笔"
    elif ratio <= 0.60:
        stage_title = "第二阶段（立基破局·守护班底与智斗反杀）"
        mindset = f"{mc_name}站稳脚跟，从被动求生转向主动布局与守护核心班底，展露领袖冷静与技术/谋略闭环"
        guilt = "转化为高效的行动焦虑与制度建设，以冷酷谋略和硬实力替代稚嫩情绪内耗"
        villain = "反派察觉威胁，阵营内部出现裂痕与多方内讧，开始动用家族死士或超前布局截杀"
        hook = "中线利益矛盾与隐藏身世/世界观更深黑幕线索浮出水面"
    else:
        stage_title = "第三阶段（登顶清算·主君威严与重塑秩序）"
        mindset = f"{mc_name}建立绝对威严与规则掌控力，行事杀伐决断、冷酷周密，绝无多余情绪消耗"
        guilt = "道心与战力统合，为前史沉没成本完成清算，建立新世界规则"
        villain = "终极对手暴露底牌与毁灭性执念，展开全盘宿命对决"
        hook = "全书前史伏笔与唯一钥匙进入集中收网闭环"

    return f"""
【🧠 本批次（第{current_start}章起）主角心境演进状态机 · {stage_title}】：
- **心态定位**：{mindset}；
- **情绪表现**：{guilt}；
- **反派博弈逻辑**：{villain}；
- **伏笔调度要求**：{hook}。
"""


def build_supporting_cast_arc_directive(current_start: int, total_chapters: int, cfg: Optional[Dict[str, Any]] = None) -> str:
    """基于全书进度动态推导核心副手/同袍的法定羁绊阶数状态机，消除细纲随机断层"""
    ratio = current_start / max(1, total_chapters)
    if ratio <= 0.15:
        stage_num = "一阶"
        stage_name = "怀疑戒备与冷硬审视（一阶初期）"
        attitude = "对主角抱有严重怀疑与冷硬审视，仅凭职责/命令/监视要求进行被动协防"
        distance = "接触保持冷峻距离感（三步开外，递物冷硬推拒或置于案角后离开），绝无主动温存"
    elif ratio <= 0.40:
        stage_num = "二阶"
        stage_name = "震撼折服与战术同袍（二阶进阶）"
        attitude = "目睹核心技术或谋略降维打击，从戒备转为震撼与专业折服，达成战术默契"
        distance = "维持冷硬同袍距离，开始接受无言关照（如递药膏/校准护具），以数据和战况交流"
    elif ratio <= 0.70:
        stage_num = "三阶"
        stage_name = "生死相托与铁血执行（三阶巅峰）"
        attitude = "将后背完全托付给主角，成为主角手中最锋利的执行之刃，无需言语心领神会"
        distance = "同生共死，敢于独率残部断后，坚定信奉主角必携降维力量归来"
    else:
        stage_num = "四/五阶"
        stage_name = "无冕之帅与政军共生（终极合流）"
        attitude = "统领全军大局，与主角形成不可分割的命运共同体"
        distance = "执掌最高军权，二人并肩屹立于新时代之巅"

    return f"""
【⚔️ 本批次（第{current_start}章起）核心副手羁绊演进状态机 · {stage_name}】：
- **法定羁绊阶数**：严格锁定于【{stage_num}】，严禁跨阶段突进或倒退！
- **副手心理定位**：{attitude}；
- **物理接触距离与阻尼**：{distance}。
"""


def generate_chapter_outlines(
    start_ch: int,
    end_ch: int,
    volume_num: int,
    client,
    model_name: str,
    cfg: Dict[str, Any],
    master_outline_path: str = "",
    genre_directives: str = "",
    total_chapters_book: int = 125,
    log_func=None
) -> str:
    """分批链式滑动生成细纲"""
    if log_func:
        log_func(f"[Auto-Outline] 启动链式滑动细纲生成引擎 (第 {start_ch} 章 ~ 第 {end_ch} 章，卷 {volume_num})...")

    master_text = ""
    if master_outline_path and os.path.exists(master_outline_path):
        try:
            with open(master_outline_path, "r", encoding="utf-8") as f:
                master_text = f.read()
        except Exception:
            pass

    novel_dir = cfg.get("project", {}).get("novel_dir", "") or cfg.get("project", {}).get("workspace_dir", "")
    from outline.block_planner import load_active_block_context
    block_context = load_active_block_context(novel_dir, volume_num, start_ch)
    block_section = f"\n【中观块级施工图约束（Prompt 1 输出）】：\n{block_context}\n" if block_context else ""

    tw = cfg.get("project", {}).get("target_words", 2700000)
    master_context = extract_targeted_master_context(master_text, start_ch, end_ch, tw)
    macro_phase = extract_macro_phase_anchor(master_text, start_ch, total_chapters_book)
    arc_directive = build_protagonist_arc_directive(start_ch, total_chapters_book)
    supporting_arc = build_supporting_cast_arc_directive(start_ch, total_chapters_book, cfg)

    axioms = cfg.get("gravity_axioms", [])
    axioms_str = "\n".join([f"- {a}" for a in axioms]) if axioms else "遵循因果守恒定律"

    full_genre_directives = f"{genre_directives}\n\n【必须遵守的因果重力公理】：\n{axioms_str}\n\n{arc_directive}\n\n{supporting_arc}"
    from pipeline.prompt_loader import load_prompt
    raw_system_prompt = load_prompt("03_chapter_outline", custom_dir=novel_dir)
    three_act_guide = format_chapter_three_act_ratios_guide(cfg)
    system_prompt = raw_system_prompt.replace("{dynamic_chapter_three_act_ratios_guide}", three_act_guide)

    # 提取当前批次各章节在中观施工图中的粗颗粒任务锚点
    targeted_block_tasks = []
    if block_context:
        for ch_idx in range(start_ch, end_ch + 1):
            m_task = re.search(rf"[-*]\s*\*\*第\s*{ch_idx}\s*章\*\*[:：\s]*([^\n\r]+)", block_context)
            if m_task:
                targeted_block_tasks.append(f"- **第{ch_idx}章必达任务**：{m_task.group(1).strip()}")
    
    targeted_tasks_str = "\n".join(targeted_block_tasks)
    targeted_tasks_section = f"\n【本批次（第{start_ch}~{end_ch}章）中观施工图强制任务锚点（必须100%遵照执行，严禁超前或篡改）】：\n{targeted_tasks_str}\n" if targeted_tasks_str else ""

    from pipeline.context_builder import build_chapter_type_advisory_directive
    type_advisory = build_chapter_type_advisory_directive(novel_dir, start_ch)
    type_advisory_section = f"\n{type_advisory}\n" if type_advisory else ""

    qimao_opening_constraint = ""
    if start_ch <= 3:
        qimao_opening_constraint = "\n【七猫黄金三章极速推进铁律（强制执行）】：\n- 第 1~3 章严禁任何 E 类（过渡叙事）！必须全部为 A 类（智斗算账）、B 类（动作反杀）、C 类（危机倒逼造物）或 F 类（复合高潮）；\n- 每一章结尾必须包含明确的翻页悬念钩子，前 3 章必须完成至少 1 次身份/危机反转！\n"
    elif start_ch <= 10:
        qimao_opening_constraint = "\n【开篇技术攻关缓释】：\n- 前 10 章纯 C 类造物不得多于 1 次，必须由外部生存危机（强敌压境/物资断绝）直接倒逼！\n"

    user_msg = f"""请在【中观块级施工图】和【全书总纲】的双重约束下，严格为【第{volume_num}卷】生成从【第{start_ch}章】到【第{end_ch}章】（共 {end_ch - start_ch + 1} 章）的标准12维精细写作细纲：
{targeted_tasks_section}
{type_advisory_section}
{qimao_opening_constraint}
{block_section}
【全书核心总纲上下文】：
{master_context}

【宏观三幕时空坐标】：
{macro_phase}

【强制约束】：
1. 每章核心事件必须 100% 对齐上述【中观施工图强制任务锚点】，严禁超前发明工业图纸（如第2章仅限地势走向，严禁出现煤铁断层）；
2. 角色出场与情感互动必须严格遵循施工图中的章节定位；
3. 输出严格按 Prompt 2 的 12 维规范生成 Markdown。
"""

    max_tokens_val = cfg.get("models", {}).get("planner", {}).get("max_tokens", 8192)
    from pipeline.utils import safe_chat_completion
    try:
        result = safe_chat_completion(
            client=client,
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_msg},
            ],
            temperature=0.5,
            max_tokens=max_tokens_val,
            max_retries=3,
            log_func=log_func
        )
        return result
    except Exception as e:
        if log_func:
            log_func(f"[ChapterGen] [ERROR] 第 {start_ch} ~ {end_ch} 章细纲生成失败: {e}", level="ERROR")
        raise e

