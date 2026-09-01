# -*- coding: utf-8 -*-
"""
agent_1_planner.py - 核心策划 Agent (Planner)
纯 Python 规则与模板编译器，零 Token 消耗、零延迟生成标准 XML 任务书。
"""

import os
import re
import glob
import yaml
from typing import Dict, Any, List, Optional
from pipeline.context_builder import extract_chapter_title, load_chapter_outline
from pipeline.context_analyzer import get_retention_strategy, detect_dormant_foreshadowing


def resolve_dynamic_character_dossiers_context(chapter_num: int, chapter_outline: str, novel_dir: str, state_snapshot: Any) -> str:
    """按需加载本章登场角色的阶段微动作与怪癖保活指令 (0 业务硬编码)"""
    if isinstance(state_snapshot, str):
        import json
        try:
            state_snapshot = json.loads(state_snapshot)
        except Exception:
            state_snapshot = {}
    elif not isinstance(state_snapshot, dict):
        state_snapshot = {}

    dossier_dir = os.path.join(novel_dir, "人物设定")
    if not os.path.exists(dossier_dir):
        return ""

    cues = []
    for yaml_file in glob.glob(os.path.join(dossier_dir, "*.yaml")):
        char_name = os.path.splitext(os.path.basename(yaml_file))[0]
        if char_name in chapter_outline:
            try:
                with open(yaml_file, "r", encoding="utf-8") as f:
                    c_data = yaml.safe_load(f) or {}
                # 1. 搭档多阶段动作提取
                if "stages" in c_data and c_data["stages"]:
                    cur_stage = None
                    for st in c_data["stages"]:
                        rng = st.get("chapter_range", [1, 99999])
                        if rng[0] <= chapter_num <= rng[1]:
                            cur_stage = st
                            break
                    if not cur_stage:
                        cur_stage = c_data["stages"][-1]
                    
                    st_num = cur_stage.get("stage", 1)
                    st_name = cur_stage.get("stage_name", "")
                    anch = cur_stage.get("physical_anchor", "专属道具")
                    act_m = cur_stage.get("action_matrix", {})
                    
                    if any(k in chapter_outline for k in ["算账", "清点", "数字", "公差", "粮食", "银两", "账册"]):
                        acts = act_m.get("accounting_scene", [])
                    elif any(k in chapter_outline for k in ["休整", "呼吸", "日常", "温存", "热汤", "分食", "围炉"]):
                        acts = act_m.get("daily_scene", [])
                    else:
                        acts = act_m.get("tension_scene", [])
                    
                    chosen_act = acts[chapter_num % len(acts)] if acts else f"指节按在{anch[:8]}"
                    cues.append(f"    - 【{char_name}】（第{st_num}阶·{st_name}）：随身信物【{anch}】，本章专属微动作：【{chosen_act}】（请按本阶段情感层次描写，严禁使用旧阶段已被淘汰的习惯）；")

                # 2. 副手怪癖提取与保活
                if c_data.get("role") == "副手":
                    body_part = c_data.get("signature_body_part", "手指")
                    action = c_data.get("signature_action", "摸索道具")
                    habits = c_data.get("habits", "")
                    
                    last_ch = state_snapshot.get("character_quirks", {}).get(char_name, 0)
                    idle_gap = chapter_num - last_ch if last_ch > 0 else 0
                    must_keepalive = " ⚠️【怪癖保活工单：本章必须描写此细节】" if idle_gap >= 4 else ""
                    cues.append(f"    - 【{char_name}】（核心副手）：专属部位【{body_part}】，动作习惯【{action or habits[:30]}】{must_keepalive}；")

            except Exception:
                pass

    if not cues:
        return ""

    return "\n  <character_dynamic_texture_focus>\n" + "\n".join(cues) + "\n  </character_dynamic_texture_focus>"


def run_planner(
    chapter_num: int,
    prev_tail: str,
    chapter_outline: str,
    cfg: Dict[str, Any],
    outline_file: str = "",
    state_snapshot: str = "",
    novel_settings: str = "",
    log_func=None
) -> str:
    """Planner：纯 Python 规则与模板编译器，零 Token 消耗、零延迟生成标准 XML 任务书"""
    if log_func:
        log_func(f"[Planner] 编译第{chapter_num}章任务书 (Python 模板引擎)...")

    novel_dir = cfg["project"]["novel_dir"]

    # 提取角色名单与动态身份锁
    chars_match = re.search(r'登场人物[：:]\s*(.*?)(?=\n|$)', chapter_outline)
    chars_str = chars_match.group(1).strip() if chars_match else ""
    if not chars_str:
        chars_list = re.findall(r'[\u4e00-\u9fff]{2,4}', chapter_outline)
        chars_str = "、".join(list(dict.fromkeys(chars_list))[:5])

    char_locks = cfg.get("character_locks", [])
    mc_name = char_locks[0]["name"] if char_locks and "name" in char_locks[0] else (cfg.get("project", {}).get("characters", ["主角"])[0])
    if char_locks:
        char_lock_lines = [
            f"    - 【{c['name']}】：法定身份为【{c.get('legal_identity', '')}】"
            + (f"，严禁写错为 {c['banned_aliases']}" if 'banned_aliases' in c else "")
            for c in char_locks
        ]
        char_lock_str = "\n".join(char_lock_lines)
    else:
        char_lock_str = f"    - 核心登场人物：{chars_str}"

    # 提取标题
    expected_title_short = extract_chapter_title(chapter_outline, chapter_num, cfg)

    # 动态本章专有高光指令
    ch_directives = list(cfg.get("chapter_directives", {}).get(chapter_num, []))

    # 1. 第 1 章超前物象在场与开篇弹性反击自动注入 (From Knowledge Graph & M7)
    if chapter_num == 1:
        op_cfg = cfg.get("opening_pacing", {})
        fc_cfg = op_cfg.get("first_counter", {})
        min_c = fc_cfg.get("min_chars", 160)
        max_c = fc_cfg.get("max_chars", 240)
        target_c = fc_cfg.get("target_chars", 200)
        threat_max = op_cfg.get("threat_appear_max_chars", 100)

        ch_1_fast_counter = f"【⚡ 黄金开篇反击弹性指令（基准 {target_c} 字 ±20%，即 [{min_c}, {max_c}] 字区间）】：前 {threat_max} 字内必须显形压迫者与即时生存威胁（利刃/鸩酒/削爵/砸锁），在第 {min_c}~{max_c} 字弹性公差区间内主角必须在物象顿地同时做出第一次冷硬反击或语言亮剑（算账/直视/反问），既留足动作中间帧，又严禁被动受辱或沉默超过 {max_c} 字！"
        if not any("黄金开篇" in d and "反击" in d for d in ch_directives):
            ch_directives.append(ch_1_fast_counter)

        ch_1_interactive_eval = "【📐 勘测现场短句交互打断指令】：仓底勘测与算账推演严禁单人连续独白超过 300 字，必须拆分为短句并由随从短问打断（如随从询问白粉何物，主角再递进抛出第二层数据杀招）！"
        if not any("勘测现场短句交互打断指令" in d for d in ch_directives):
            ch_directives.append(ch_1_interactive_eval)

        ch_1_active_hook = "【⚔️ 章末主动宣战姿态指令】：章末在立柱刻下白痕定格后，主角必须展现主动进攻或主动宣战的强硬对白与姿态，杜绝纯被动防守扎营收束！"
        if not any("章末主动宣战姿态指令" in d for d in ch_directives):
            ch_directives.append(ch_1_active_hook)

        try:
            from storage.state_manager import get_soul_totem_state
            totem_data = get_soul_totem_state(novel_dir)
            if totem_data and totem_data.get("name"):
                t_name = totem_data["name"]
                totem_rule = f"【🔮 首章贯穿物象微在场硬性任务】：全书核心灵魂物象为【{t_name}】。本章正文前500字必须通过前史受辱回忆、圣旨封蜡上的物象图样或随身残温触感，安排 1 处微痕迹在场（为后文正式赐予/登场蓄力，严禁遗漏）！"
                if not any("首章贯穿物象" in d for d in ch_directives):
                    ch_directives.append(totem_rule)
        except Exception:
            pass

    # 2. 知识图谱休眠实体主动唤醒与暗线伏笔催收
    try:
        from pipeline.context_builder import get_dormant_entities_directive, get_due_plot_vault_directive, precompute_taste_and_rest_directives
        dormant_rem = get_dormant_entities_directive(novel_dir, chapter_num, threshold=10)
        if dormant_rem and not any("休眠实体" in d for d in ch_directives):
            ch_directives.append(dormant_rem)

        pv_rem = get_due_plot_vault_directive(novel_dir, chapter_num)
        if pv_rem and not any("暗线伏笔" in d for d in ch_directives):
            ch_directives.append(pv_rem)

        # 3. 场景关联确定性味觉与四类休整行为预计算注入
        pre_params = precompute_taste_and_rest_directives(chapter_outline, chapter_num)
        taste_dir = f"【👅 本章预计算必填味觉】：{pre_params['taste_directive']}"
        rest_dir = f"【🛌 本章预计算必填休整】：{pre_params['rest_directive']}"
        if not any("本章预计算必填味觉" in d for d in ch_directives):
            ch_directives.append(taste_dir)
        if not any("本章预计算必填休整" in d for d in ch_directives):
            ch_directives.append(rest_dir)
        if pre_params.get("calculation_directive") and not any("专属物象算力强绑定" in d for d in ch_directives):
            ch_directives.append(f"【📏 {pre_params['calculation_directive']}】")

        # 4. 微观动作与道具跨章动态冷却节流
        from pipeline.context_analyzer import detect_action_prop_streak
        action_throttle = detect_action_prop_streak(novel_dir, chapter_num, cfg)
        if action_throttle and not any("动作与道具跨章动态节流" in d for d in ch_directives):
            ch_directives.append(action_throttle)

        # 5. 三线类型 (thread_type) 强解析与正文驱动红线注入
        m_thread = re.search(r'["\']thread_type["\']\s*:\s*["\']([^"\']+)["\']', chapter_outline)
        if not m_thread:
            m_thread = re.search(r'thread_type[：:\s]+([^\n\r]+)', chapter_outline)
        if m_thread:
            ttype = m_thread.group(1).strip()
            if "情感" in ttype and not any("三线类型·情感羁绊" in d for d in ch_directives):
                ch_directives.append(f"【🎭 三线类型·情感羁绊驱动】：本章被归类为【{ttype}】，正文前 2000 字内必须出现至少 1 处非功能性生活对白或静默触碰，且两人互动必须伴随具体可触摸信物的物理传递/擦拭（M1规范），严禁写成纯技术攻关！")
            elif "主线" in ttype and not any("三线类型·主线推进" in d for d in ch_directives):
                ch_directives.append(f"【⚡ 三线类型·主线推进驱动】：本章被归类为【{ttype}】，本章必须产生可量化的势力版图、关键物资或权力状态变更！")
            elif "技术" in ttype and not any("三线类型·支线技术" in d for d in ch_directives):
                ch_directives.append(f"【🔬 三线类型·支线技术驱动】：本章被归类为【{ttype}】，技术攻关必须呈现具体物理参数/公差突破，并绑定外部危机！")

        # 6. 技术攻关连续无爽点蓄力熔断检测与预警注入 (02_block_blueprint 规范对齐)
        try:
            from pipeline.context_analyzer import detect_tech_streak_without_face_slap
            tech_fuse_alert = detect_tech_streak_without_face_slap(novel_dir, chapter_num, cfg, chapter_outline)
            if tech_fuse_alert and not any("爽点蓄力熔断提醒" in d for d in ch_directives):
                ch_directives.append(tech_fuse_alert)
        except Exception:
            pass

        # 7. 核心随从/副手专属生活质感物理载体候选池自动注入 (0 业务硬编码)
        try:
            subordinate_cues = []
            for lock in char_locks:
                c_name = lock.get("name", "")
                c_role = lock.get("role", "")
                c_habits = lock.get("habits", "") or lock.get("habit", "") or lock.get("quirks", "")
                c_props = lock.get("props", "") or lock.get("items", "") or lock.get("features", "")
                if c_name and c_name != mc_name and (c_habits or c_props or "随从" in c_role or "副手" in c_role or "同袍" in c_role):
                    detail_items = []
                    if c_props:
                        detail_items.append(f"专属私物/工具: {c_props}")
                    if c_habits:
                        detail_items.append(f"习惯/特征: {c_habits}")
                    cue_str = f"【{c_name}】(" + "; ".join(detail_items or ["特征体态"]) + ")"
                    subordinate_cues.append(cue_str)
            if subordinate_cues and not any("随从专属生活质感物理载体" in d for d in ch_directives):
                cues_directive = "【👥 核心随从专属生活质感物理载体候选池】：描写本章副手微观表情/体态偏移时，必须直接选用以下角色的专属载体作为物理落点（严禁写通用受惊表情）：\n" + "\n".join(f"  - {c}" for c in subordinate_cues)
                ch_directives.append(cues_directive)
        except Exception:
            pass
    except Exception:
        pass

    ch_directives_xml = "\n".join([f"    - {d}" for d in ch_directives]) if ch_directives else "    - 严格遵循大纲推进，保证高潮反转与情感张力"

    # 5-Chapter Horizon 雷达扫描 (具备多路径与跨分卷自适应容错)
    upcoming_threats = []
    try:
        max_horizon = min(chapter_num + 5, cfg.get("project", {}).get("total_chapters", chapter_num + 5))
        for fut_ch in range(chapter_num + 1, min(chapter_num + 4, max_horizon + 1)):
            fut_outline = None
            try:
                fut_outline = load_chapter_outline(cfg, fut_ch)
            except Exception:
                pass
            if fut_outline:
                m_chars = re.search(r'登场人物[：:]\s*(.*?)(?=\n|$)', fut_outline)
                m_events = re.search(r'核心事件[：:]\s*(.*?)(?=\n|$)', fut_outline)
                chars_str = m_chars.group(1).strip() if m_chars else ""
                events_str = m_events.group(1).strip() if m_events else ""
                if not chars_str:
                    chars_found = re.findall(r'[\u4e00-\u9fff]{2,4}', fut_outline[:200])
                    chars_str = "、".join(list(dict.fromkeys(chars_found))[:3]) if chars_found else ""
                if not events_str:
                    events_str = extract_chapter_title(fut_outline, fut_ch, cfg) or "剧情推进"
                if chars_str or events_str:
                    upcoming_threats.append(
                        f"第{fut_ch}章预告登场：【{chars_str or '关键人物'}】(事件: {events_str[:35]}...)。本章适度在台词或侧面议论中提及一次做草蛇灰线铺垫！"
                    )
    except Exception as e:
        if log_func:
            log_func(f"[Planner 提示] 5-Chapter Horizon 扫描未发现后续细纲或解析异常: {e}")

    # 知识图谱 RAG 上下文
    kg_context_section = ""
    kg = None
    try:
        from storage.knowledge_graph import NovelKnowledgeGraph
        kg_db_path = os.path.join(novel_dir, "knowledge_graph.db")
        if os.path.exists(kg_db_path):
            kg = NovelKnowledgeGraph(kg_db_path)
            characters_in_outline = re.findall(r'[\u4e00-\u9fff]{2,4}', chapter_outline)
            kg_context_section = kg.format_graph_rag_context(characters_in_outline, upcoming_threats, chapter_num=chapter_num)
    except Exception as e:
        if log_func:
            log_func(f"[Planner 警告] 知识图谱 RAG 检索异常: {e}")
    finally:
        if kg is not None:
            try:
                kg.close()
            except Exception:
                pass

    # 长期记忆事实与伏笔召回 (带时空衰减算法)
    ltm_context_section = ""
    try:
        from storage.long_term_memory import query_relevant_lore
        ltm_context_section = query_relevant_lore(chapter_outline, current_chapter=chapter_num)
    except Exception as e:
        if log_func:
            log_func(f"[Planner 提示] 长期记忆检索跳过: {e}")

    # 战斗微状态机上下文
    battle_context_section = ""
    try:
        from storage.battle_state import get_active_battle_context
        battle_context_section = get_active_battle_context(chapter_num, custom_novel_dir=novel_dir)
    except Exception as e:
        if log_func:
            log_func(f"[Planner 提示] 战斗子图检索跳过: {e}")

    # 沉寂伏笔与未决因果主动唤醒提醒
    foreshadowing_reminder = detect_dormant_foreshadowing(state_snapshot, chapter_num, novel_dir)

    # 中观块级施工图约束注入 (Prompt 1 产物)
    block_blueprint_context = ""
    try:
        from outline.block_planner import load_active_block_context
        # 推导卷号
        tw_val = cfg.get("project", {}).get("target_words", 2700000)
        from outline.chapter_generator import get_volume_info
        vol_calc, _, _ = get_volume_info(chapter_num, max(50, tw_val // 2400), tw_val)
        block_blueprint_context = load_active_block_context(novel_dir, vol_calc, chapter_num)
    except Exception:
        pass

    # 留存推进策略
    retention_strategy_text = get_retention_strategy(chapter_num, cfg.get("retention_strategy", {}))

    # 呼吸空间主线阻断锁检测与主视角轮换
    is_breathing_buffer = any(kw in chapter_outline for kw in ["缓冲", "呼吸空间", "日常", "温存", "质感章", "低强度"])
    breathing_buffer_lock_str = ""
    if is_breathing_buffer:
        assigned_sidekick_str = ""
        rotation = cfg.get("output_constraints", {}).get("breathing_chapter_rotation", [])
        if rotation:
            rot_idx = (chapter_num // 15) % len(rotation)
            assigned_sidekick = rotation[rot_idx]
            assigned_sidekick_str = f"\n      4. 本章生活质感主视角副手：【{assigned_sidekick}】（必须聚焦其视角展开生活切片与微观互动，严禁单一副手霸屏）；"
        breathing_buffer_lock_str = f"""
  <breathing_buffer_lock>
    - ⚠️ 【最高红线·呼吸空间主线阻断锁生效中】：
      1. 主线推进度与大冲突升级严格锁定为 0，本章严禁发生战斗或重大工业突破；
      2. 正文必须包含至少 300 字纯粹生活五感与人物温度细节（如围炉烤火、分食干粮、整理工具、老匠人传授手艺）；
      3. 让读者从连续紧绷的情绪中获得沉浸式喘息与世界质感沉淀！{assigned_sidekick_str}
  </breathing_buffer_lock>"""

    # 动态角色档案阶段微动作与保活指令注入
    dynamic_dossier_section = resolve_dynamic_character_dossiers_context(chapter_num, chapter_outline, novel_dir, state_snapshot)

    # 动态因果公理注入
    gravity_axioms = cfg.get("gravity_axioms", [])
    if gravity_axioms:
        gravity_rules_str = "\n".join([f"    - {rule}" for rule in gravity_axioms])
    else:
        gravity_rules_str = "    - 保持情绪波浪线，每章必有即时爽点或微观破局。"

    min_wc = cfg.get("quality", {}).get("min_chinese_chars", 2000)
    target_wc = cfg.get("quality", {}).get("target_chinese_chars", 2400)
    max_wc = cfg.get("quality", {}).get("max_chinese_chars", 2800)

    task_xml = f"""<writing_task chapter="{chapter_num}">
  <!-- 1. 静态世界观与行文公理前缀 (PROMPT CACHING STATIC INVARIANTS) -->
  <static_world_and_guidelines>
    <characters_lock>
      - 唯一法定核心主角：【{mc_name}】（绝对严禁出现任何其他历史同类小说的错误主角姓名，全篇主视角与称谓必须100%锁定！）
{char_lock_str}
      - 铁律：除上述名单与大纲明确指派角色外，严禁凭空捏造带姓名的龙套！
    </characters_lock>{dynamic_dossier_section}

    <novel_settings>
{novel_settings}
    </novel_settings>

    <ecological_consistency_directives>
{gravity_rules_str}
    </ecological_consistency_directives>

    <writing_instructions>
      1. 字数黄金区间：{target_wc - 200}-{max_wc} 字（中枢 {target_wc} 字，底线 {min_wc} 字，防注水也防草率收尾）
      2. 视角铁律：主角有限视角，0上帝全知观察哨
      3. 情绪为王：专注于为读者制造心跳加速的紧张感或扬眉吐气的暴爽感！
    </writing_instructions>
  </static_world_and_guidelines>

  <!-- 2. 中观与上下文关联数据 (SEMI-STATIC CONTEXT & KNOWLEDGE GRAPH) -->
  <contextual_memory>
    <block_blueprint_context>
{block_blueprint_context if block_blueprint_context else '    - （当前章节中观块级施工图未定义）'}
    </block_blueprint_context>

    <knowledge_graph_context>
{kg_context_section if kg_context_section else '    - （当前知识图谱暂无高危剧情冲突警告）'}
    </knowledge_graph_context>

    <long_term_memory_context>
{ltm_context_section if ltm_context_section else '    - （暂无深层设定召回）'}
    </long_term_memory_context>

    <battle_subgraph>
{battle_context_section if battle_context_section else '    - （当前无跨章持久战进行中）'}
    </battle_subgraph>

    <state_snapshot>
{state_snapshot if state_snapshot else '{}'}
    </state_snapshot>
  </contextual_memory>

  <!-- 3. 本章动态任务与前文衔接载荷 (DYNAMIC CHAPTER PAYLOAD) -->
  <chapter_payload>
    <chapter_number>第{chapter_num}章</chapter_number>
    <chapter_title>第{chapter_num}章：{expected_title_short}</chapter_title>
    {breathing_buffer_lock_str}

    <outline_verification>
      - 本章归属大纲文件: {os.path.basename(outline_file) if outline_file else '分卷细纲'}
      - 核验状态: 已通过防穿透严格校验 (第{chapter_num}章)
    </outline_verification>

    <previous_chapter_tail>
{prev_tail if prev_tail else '（第一章，无前文衔接要求）'}
    </previous_chapter_tail>

    <current_chapter_outline>
{chapter_outline}
    </current_chapter_outline>

    <chapter_highlight>
      <emotion_wave>单章锁定核心情绪发动机（压抑蓄力 / 智谋信息差 / 暴爽核爆 / 战后收获）。单章只打一发核心子弹，严禁走马观花赶场子！</emotion_wave>
      <villain_hubris>给反派充分展现嚣张与阶层优越的舞台，压簧越深，反杀越爽</villain_hubris>
      <mc_counterattack>主角反击干脆利落、直击命门、连本带利清算，提供极致生理爽感</mc_counterattack>
    </chapter_highlight>

    <director_lens_scheduling>
      <pacing_rule>大事件允许跨章连爆（压抑 ➔ 破局 ➔ 斩首 ➔ 分赃），日常章允许纯粹松弛造物与生活留白</pacing_rule>
    </director_lens_scheduling>

    <chapter_specific_directives>
{ch_directives_xml}
    </chapter_specific_directives>

    <retention_strategy>
      {retention_strategy_text}
    </retention_strategy>

    <foreshadowing_reminder>
{foreshadowing_reminder}
    </foreshadowing_reminder>

    <hook_chain>
      <ending_hook_type>自然悬念或有力定格（具体行动目标 / 危机暗面 / 温暖宁静）</ending_hook_type>
    </hook_chain>
  </chapter_payload>
</writing_task>"""

    if log_func:
        log_func(f"[Planner] 任务书编译完成 (纯Python引擎，零API开销，生成 {len(task_xml)} 字符)")
    return task_xml
