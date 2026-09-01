# ============================================================
# Agent 3: 品控审核 Agent (Reviewer) — 七猫男频通用版 (v4.0 Universal)
# 严格对照单章七要素结构（场景/人物/事件/对话/感官/情感/钩子）
# ============================================================

import os
import re
from typing import Dict, Any, List, Optional
from pipeline.utils import (
    count_chinese_chars,
    extract_xml_tag,
    check_ai_cliches,
    check_dialogue_ratio,
    check_broken_paragraphs,
    check_entity_blacklist,
    check_catchphrase_blacklist,
    check_vulgar_villain_abuse,
    check_ending_slogans,
    is_stealth_or_solo_chapter
)
from pipeline.context_builder import extract_chapter_title
from pipeline.context_analyzer import detect_ending_pattern, detect_monologue_ending_streak
from pipeline.prompt_loader import load_prompt


def check_industrial_failure_chain(content: str, chapter_outline: str) -> List[str]:
    """
    检查涉及工业/研发/造物验证的 C 类章节正文是否具备‘尝试→偏差→修正’3步失效链 (0ms 本地快速拦截)
    """
    if not chapter_outline:
        return []
    is_c_class = any(k in chapter_outline for k in ["C类", "工业", "造物", "试制", "研发", "冶炼", "制药", "锻造", "图纸", "技术攻关"])
    if not is_c_class:
        return []

    layer1_keywords = ["试图", "尝试", "调配", "合模", "初试", "点火", "浇筑", "锻打", "推演", "起模", "下料", "试制", "试产", "试射", "配比", "熔炼", "打磨"]
    layer2_keywords = ["却", "裂纹", "偏差", "冒烟", "未达", "失误", "阻滞", "炸裂", "崩口", "焦糊", "不对", "过脆", "偏软", "溢出", "变形", "卡死", "不匀", "瑕疵", "报废", "失败", "渗漏", "发黑", "脆裂"]
    layer3_keywords = ["改用", "重新", "调整", "换作", "降温", "磨削", "再试", "掺入", "补火", "二次", "修正", "退火", "淬火", "减半", "加重", "配比", "重调", "刮削", "微调"]

    has_l1 = any(k in content for k in layer1_keywords)
    has_l2 = any(k in content for k in layer2_keywords)
    has_l3 = any(k in content for k in layer3_keywords)

    missed_count = (0 if has_l1 else 1) + (0 if has_l2 else 1) + (0 if has_l3 else 1)
    if missed_count >= 2:
        missing_parts = []
        if not has_l1: missing_parts.append("尝试层(初始操作)")
        if not has_l2: missing_parts.append("偏差层(物理挫折/公差缺陷)")
        if not has_l3: missing_parts.append("修正层(机理调整/参数重校)")
        return [f"【工业3步失效链违规】本章涉及工业研发或技术验证，但正文缺失【{'、'.join(missing_parts)}】，呈现无尘工业一试即成！必须补充真实试错与物理调试细节！"]
    return []


def check_anachronistic_tech(content: str, chapter_num: int, cfg: Dict[str, Any]) -> List[str]:
    """
    检查正文中是否出现了违反当前分卷科技树白名单的超代名词 (0ms 本地快速拦截)
    """
    hits = []
    progression = cfg.get("tech_tree_progression", {})
    if not progression:
        return hits

    current_vol_key = None
    if 1 <= chapter_num <= 100:
        current_vol_key = "vol_1_ch1_100"
    elif 101 <= chapter_num <= 200:
        current_vol_key = "vol_2_ch101_200"

    if current_vol_key and current_vol_key in progression:
        forbidden = progression[current_vol_key].get("forbidden_terms", [])
        for term in forbidden:
            if term and term in content:
                hits.append(term)
    return hits


def run_reviewer(
    chapter_output: str,
    chapter_outline: str,
    prev_tail: str,
    chapter_num: int,
    client,
    model_name: str,
    cfg: Dict[str, Any],
    log_func=None
) -> dict:
    """Reviewer 质检，返回 {'verdict': 'PASS'/'FAIL', 'feedback': '...', 'word_count': N}"""
    if log_func:
        log_func(f"[Reviewer] 开始质检...")

    novel_dir = cfg["project"]["novel_dir"]
    ch_prefix = cfg["project"]["chapter_prefix"]
    ch_suffix = cfg["project"]["chapter_suffix"]
    min_chars = cfg.get("quality", {}).get("min_chinese_chars", 2000)
    target_chars = cfg.get("quality", {}).get("target_chinese_chars", 2400)
    # 动态字数区间：开篇前3章与高潮章放宽至 3000，常规章 2800
    if chapter_num <= 3:
        max_chars = cfg.get("quality", {}).get("opening_max_chars", 3000)
    elif "复合高潮" in chapter_outline or "F类" in chapter_outline:
        max_chars = cfg.get("quality", {}).get("climax_max_chars", 3000)
    else:
        max_chars = cfg.get("quality", {}).get("max_chinese_chars", 2800)

    content = extract_xml_tag(chapter_output, "chapter_content")
    if not content:
        content = chapter_output
    wc = count_chinese_chars(content)
    if log_func:
        log_func(f"[Reviewer] 字数统计: {wc} 中文字符")

    # 1. 纯代码零成本快速熔断 (Fast-Fail Filter 0ms)
    fast_fail_reasons = []

    # 1.1 字数硬红线
    if wc < min_chars:
        fast_fail_reasons.append(f"纯正文字数不足：当前 {wc} 字，最低要求 {min_chars} 字（差 {min_chars - wc} 字）。")
    elif wc > max_chars + 250:
        fast_fail_reasons.append(f"字数严重超标：当前 {wc} 字，上限 {max_chars} 字（超 {wc - max_chars} 字）。")

    # 1.2 实体黑名单
    blacklist = cfg.get("entity_locks", {}).get("blacklist_entities", [])
    correct_sect = cfg.get("entity_locks", {}).get("faction_name", cfg.get("entity_locks", {}).get("sect_name", "主角势力"))
    banned_hits = check_entity_blacklist(content, blacklist)
    if banned_hits:
        fast_fail_reasons.append(f"命中禁止实体【{', '.join(banned_hits)}】！合法主势力名必须为【{correct_sect}】！")

    # 1.3 AI 八股套话拦截
    cliche_hits = check_ai_cliches(content)
    if len(cliche_hits) >= 3:
        fast_fail_reasons.append(f"命中大量 AI 八股套话 ({len(cliche_hits)}处: {', '.join(cliche_hits[:4])})，严禁使用八股模板！")

    # 1.4 低幼泼妇式辱骂拦截
    vulgar_hits = check_vulgar_villain_abuse(content)
    if len(vulgar_hits) >= 1:
        fast_fail_reasons.append(f"反派台词低幼化辱骂：命中粗暴叫骂词 {vulgar_hits}，必须替换为阶层伪善、假意关切或绵里藏针话术！")

    # 1.5 章末口号化宣言拦截
    slogan_hits = check_ending_slogans(content)
    if slogan_hits:
        fast_fail_reasons.append(f"章末口号化宣言违规：章末最后200字出现复仇口号 {slogan_hits}，必须改为当下时空的物理动作与环境留白！")

    # 1.6 结尾连续独白模式拦截
    if chapter_num > 0 and detect_ending_pattern(content) == "monologue":
        streak = detect_monologue_ending_streak(novel_dir, ch_prefix, ch_suffix, chapter_num)
        if streak >= 1:
            fast_fail_reasons.append(f"结尾模式重复：连续 {streak+1} 章使用'内心独白式宣言'结尾，必须换用悬念或反打脸钩子！")

    # 1.7 核心主角姓名一致性 0ms 快速熔断 (从 config.yaml 动态读取)
    char_locks = cfg.get("character_locks", [])
    mc_expected = char_locks[0]["name"] if char_locks and "name" in char_locks[0] else (cfg.get("project", {}).get("characters", ["主角"])[0])
    if mc_expected and mc_expected != "主角" and mc_expected not in content:
        fast_fail_reasons.append(f"核心主角名【{mc_expected}】在正文中完全缺失！严禁主角姓名漂移，请全篇彻底修正为【{mc_expected}】！")

    # 1.8 科技树分卷准入 0ms 快速熔断
    tech_hits = check_anachronistic_tech(content, chapter_num, cfg)
    if tech_hits:
        fast_fail_reasons.append(f"科技树分卷代差违规：第{chapter_num}章正文命中超代禁用词【{', '.join(tech_hits)}】！当前卷严禁跳代出现高阶化工产物，请替换为符合当前生产力水平的替代物（如提纯黑火药、拉火管、苦味酸粗品）！")

    # 1.9 七猫第 1 章开篇弹性公差反击与两屏 500 字 0ms 探针 (M7 规范)
    if chapter_num == 1:
        op_cfg = cfg.get("opening_pacing", {})
        fc_cfg = op_cfg.get("first_counter", {})
        max_counter_chars = fc_cfg.get("max_chars", 240)
        threat_max_chars = op_cfg.get("threat_appear_max_chars", 100)
        conf_window = op_cfg.get("confrontation_window_chars", 500)

        # 剥离 Markdown 标题与首尾换行，获取纯叙事正文
        clean_body = re.sub(r'^#\s+.*?\n+', '', content.strip())

        first_threat = clean_body[:threat_max_chars]
        first_counter = clean_body[:max_counter_chars]
        first_conf = clean_body[:conf_window]

        # 1. 前 threat_max_chars 字必须包含物理动作与压迫者/即时威胁
        threat_indicators = [
            "“", "”", "！", "？", "：", "跪", "受贬", "诏书", "圣旨", "死", "刀", "旨", "扣", "砸",
            "算账", "银两", "杀", "敌", "逼", "战", "大殿", "短剑", "鸩酒", "削爵", "断粮", "断饷",
            "暗器", "骨尺", "玉佩", "抽刀", "出鞘", "刺", "锁", "门槛", "冰冷", "嘲弄", "甩", "踏"
        ]
        custom_threats = op_cfg.get("threat_keywords", [])
        if custom_threats:
            threat_indicators.extend(custom_threats)
        has_threat_100 = any(ind in first_threat for ind in threat_indicators)
        if not has_threat_100:
            fast_fail_reasons.append(f"【七猫黄金开篇违规】第 1 章前 {threat_max_chars} 字内必须显形压迫者与即时生存剥夺威胁（利刃/毒酒/削爵/断粮/锁砸台阶）！")

        # 2. 前 max_counter_chars 字内主角必须做出至少 1 次反击动作或冷硬语言回应（严禁沉默受辱）
        counter_indicators = [
            "冷笑", "直视", "反问", "扣住", "反手", "改了宗法", "算不清", "烂账", "按住", "拔出",
            "顿在", "点在", "震慑", "算账", "冷硬", "声音冷", "抬眸", "冷声", "没有跪", "未跪",
            "不跪", "不退", "未退", "稳稳接住", "接住", "探出", "顿入", "斩", "断喝", "按律",
            "当场", "踏步", "截断", "挑入", "眼皮微抬", "抬手"
        ]
        custom_counters = fc_cfg.get("counter_keywords", [])
        if custom_counters:
            counter_indicators.extend(custom_counters)

        has_counter_win = (
            any(ind in first_counter for ind in counter_indicators) or
            bool(re.search(r'(?:不跪|未跪|没有跪|不退|接住|探出|顿|点|按|横|架|截|拔|抽|斩|断喝)', first_counter)) or
            ("“" in first_counter and any(k in first_counter for k in ["改了", "本王", "律", "算", "清", "命", "账", "短了", "量", "斩", "凭何", "休想"]))
        )
        if not has_counter_win:
            fast_fail_reasons.append(f"【七猫黄金开篇违规】第 1 章在弹性公差上限前（前 {max_counter_chars} 字内）主角必须做出至少 1 次反击性动作或冷硬语言回应，严禁被动挨打/沉默受辱超过 {max_counter_chars} 字！")

        # 3. 前 conf_window 字两屏整体冲突覆盖与非对抗描写三分类拦截
        has_conflict_500 = any(ind in first_conf for ind in threat_indicators)
        if not has_conflict_500:
            fast_fail_reasons.append(f"【七猫开篇二元对抗违规】第 1 章前 {conf_window} 字（移动端前两屏）缺少核心冲突与对抗二元信息，严禁以纯景物清单、纯心理感受或大段前史交代开篇！")

    # 1.10 C 类工业造物 3 步失效链 0ms 快速熔断 (防止无尘工业一试即成)
    ind_chain_hits = check_industrial_failure_chain(content, chapter_outline)
    if ind_chain_hits:
        fast_fail_reasons.extend(ind_chain_hits)

    # 1.11 三线节奏疲劳监控 (辅助审计)
    try:
        from pipeline.context_analyzer import detect_thread_fatigue
        thread_fatigue_alert = detect_thread_fatigue(novel_dir, chapter_num, cfg, chapter_outline)
        if thread_fatigue_alert and log_func:
            log_func(f"[Reviewer 审计] {thread_fatigue_alert}")
    except Exception:
        thread_fatigue_alert = None

    # 1.12 情感微动与非功能人性帧 0ms 代码探针 (5q 规范)
    if chapter_outline:
        m_emo = re.search(r'【情感微动[：:]\s*([^】]+)】', chapter_outline)
        if m_emo:
            emo_desc = m_emo.group(1).strip()
            emo_keywords = [w for w in re.findall(r'[\u4e00-\u9fa5]{2}', emo_desc) if w not in ["情感", "微动", "以及", "通过", "进行", "并且", "一个", "之后"]]
            if emo_keywords and not any(k in content for k in emo_keywords):
                if log_func:
                    log_func(f"[Reviewer 5q 预警] 细纲标注的情感微动【{emo_desc}】在正文中未检测到明显物理动作落地！")

    bodily_cues = ["伤疤", "老茧", "冻疮", "裂口", "粗布", "微温", "发僵", "发痒", "麦麸", "寒气", "指腹", "指尖", "擦拭", "烘烤", "嚼着", "敷", "摩挲", "创口"]
    has_human_frame = any(c in content for c in bodily_cues)
    if not has_human_frame and log_func:
        log_func("[Reviewer 5q 提示] 本章未检测到典型非功利身体记忆/生活质感词汇，建议在过渡间隙补充 50 字人性缓冲帧。")

    if fast_fail_reasons:
        feedback = "【代码秒级快速熔断】\n" + "\n".join(f"- {r}" for r in fast_fail_reasons)
        if log_func:
            log_func(f"[Reviewer] ⚡ 触发纯代码快速熔断 (0ms): {fast_fail_reasons[0]}")
        
        # 计算 fast-fail 时的 patch_action
        if all("AI 八股" in r or "辱骂" in r or "口号" in r for r in fast_fail_reasons):
            fast_action = "AUTO_SANITIZED"
        elif min_chars - 250 <= wc < min_chars and not any("主角名" in r or "实体" in r for r in fast_fail_reasons):
            fast_action = "APPEND_WRAPPER"
        else:
            fast_action = "FULL_REWRITE"

        return {
            "verdict": "FAIL",
            "feedback": feedback,
            "word_count": wc,
            "patch_action": fast_action,
            "raw": "",
            "analysis_report": ""
        }

    # 2. 调用模型进行五道红线深度质检
    expected_title = extract_chapter_title(chapter_outline, chapter_num, cfg)
    user_msg = f"""请审核以下章节稿件。

## 当前章节号
第{chapter_num}章

## 大纲要求的章节标题原文
<expected_title>{expected_title}</expected_title>

## 写手提交的稿件
{chapter_output}

## 本章大纲细纲
{chapter_outline}

## 上一章末尾500字
{prev_tail if prev_tail else "（无，这是第1章，跳过连贯性审核）"}

## 代码预检结果
<word_count_precheck>{wc}</word_count_precheck>
字数红线（{min_chars}-{max_chars}）：{"✅ 通过" if min_chars <= wc <= max_chars else f"❌ 不通过（当前{wc}字）"}

请严格按照你的五道红线进行审核，输出 XML 格式的审核报告。
"""
    sys_prompt = load_prompt("05_reviewer", custom_dir=novel_dir, log_func=log_func)
    from pipeline.utils import safe_chat_completion
    try:
        result = safe_chat_completion(
            client=client,
            model=model_name,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user",   "content": user_msg},
            ],
            temperature=cfg.get("models", {}).get("reviewer", {}).get("temperature", 0.1),
            max_tokens=cfg.get("models", {}).get("reviewer", {}).get("max_tokens", 4096),
            max_retries=3,
            log_func=log_func
        )
    except Exception as e:
        if log_func:
            log_func(f"[Reviewer] [ERROR] 审稿模型调用失败: {e}", level="ERROR")
        return {"verdict": "FAIL", "feedback": f"Reviewer API 异常: {e}", "word_count": wc, "raw": "", "analysis_report": ""}

    verdict = extract_xml_tag(result, "verdict").strip().upper()
    feedback = extract_xml_tag(result, "feedback")
    analysis_report = extract_xml_tag(result, "analysis_report")

    if wc < min_chars:
        verdict = "FAIL"
        feedback = f"【代码硬性判定】纯正文字数不足：当前 {wc} 字，最低要求 {min_chars} 字（差 {min_chars - wc} 字）。\n\n" + feedback
    elif wc > max_chars:
        verdict = "FAIL"
        feedback = f"【代码硬性判定】字数超标：当前 {wc} 字，上限 {max_chars} 字（超 {wc - max_chars} 字）。请精简冗余描写。\n\n" + feedback

    # 吸引力评分提取
    score_match = re.search(r"<total>(\d+)/15</total>", result)
    if score_match:
        total_score = int(score_match.group(1))
        if log_func:
            log_func(f"[Reviewer] 吸引力评分: {total_score}/15分")
        if total_score < 8:
            verdict = "FAIL"
            feedback += f"\n- 吸引力总分不达标 ({total_score}/15分，及格线为8分)。"

    verdict = verdict or "PASS"
    if log_func:
        if verdict == "FAIL":
            log_func(f"[Reviewer] [WARN] 第{chapter_num}章初审未通过 (FAIL)，触发自愈重写流程: {feedback[:100]}...", level="WARN")
        else:
            log_func(f"[Reviewer] 审核结果: PASS (第{chapter_num}章质检通过)")


    # 计算 patch_action 分级自愈策略
    patch_action = "NONE"
    if verdict == "FAIL":
        if fast_fail_reasons and all("AI 八股" in r or "辱骂" in r or "口号" in r for r in fast_fail_reasons):
            patch_action = "AUTO_SANITIZED"
        elif min_chars - 250 <= wc < min_chars and not any("主角名" in r or "实体" in r for r in fast_fail_reasons):
            patch_action = "APPEND_WRAPPER"
        else:
            patch_action = "FULL_REWRITE"

    return {
        "verdict": verdict or "PASS",
        "feedback": feedback,
        "word_count": wc,
        "patch_action": patch_action,
        "raw": result,
        "analysis_report": analysis_report
    }

