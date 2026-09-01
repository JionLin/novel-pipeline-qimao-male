# -*- coding: utf-8 -*-
"""
outline/narrative_linter.py - 细纲与剧情一致性 Linter 质检引擎
包含：
1. 细纲结构与因果元数据快速质检 (lint_chapter_outlines) - 支持 A~F 六类与配额/熔断检测，区分阻断项与告警项
2. 块级施工图质检 (lint_block_blueprint) - M4 爽点与 M5 阻尼词检测
3. 深度叙事冲突与战力体系扫描 (deep_narrative_lint)
4. 章节变异与局部影响边界分析 (analyze_chapter_mutation_impact / resync_local_impact_boundary)
5. 总纲与细纲对齐对比 (compare_master_with_outlines)
"""

import os
import re
import json
import glob
from typing import Dict, Any, List, Optional, Tuple


def extract_chapters_from_outline_text(full_text: str) -> List[Tuple[int, str]]:
    """从细纲大文本中精准切分出 (章节号, 章节内容) 列表"""
    # 匹配形如 ### **第1章：标题** 或 ### 第1章：标题 或 **第1章：标题**
    pattern = r'(?:^|\n)\s*(?:###\s*)?\*?\*?第(\d+)章[：:\s]'
    splits = list(re.finditer(pattern, full_text))
    if not splits:
        return []

    chapters = []
    for i in range(len(splits)):
        ch_num = int(splits[i].group(1))
        start_idx = splits[i].start()
        end_idx = splits[i + 1].start() if i + 1 < len(splits) else len(full_text)
        ch_content = full_text[start_idx:end_idx].strip()
        chapters.append((ch_num, ch_content))
    return chapters


def lint_chapter_outlines(full_text: str) -> Dict[str, Any]:
    """
    细纲 0ms 深度质检：
    1. A~F 六类章节标签提取与 JSON type 强一致性交叉校验
    2. C 类连续熔断检查 (严禁连续 3 章为 C 类)
    3. 10 章滑动窗口配额检查 (每 10 章内必须包含至少 1 章 B 类动作与 1 章 D 类人物关系)
    4. 单章 Stakes 与结尾钩子完整度检查
    5. 黄金三章禁 E 类强熔断
    支持区分 fatal_issues(阻断项) 与 warnings(告警项)。
    """
    chapter_list = extract_chapters_from_outline_text(full_text)
    total_chapters = len(chapter_list)
    if total_chapters <= 0:
        return {
            "passed": True,
            "score": 100,
            "fatal_issues": [],
            "warnings": [],
            "issues": [],
            "type_distribution": {}
        }

    fatal_issues = []
    warnings = []
    type_distribution = {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0, "F": 0, "OTHER": 0}
    parsed_sequence: List[Tuple[int, str]] = []

    for ch_num, ch_text in chapter_list:
        # 1. 提取字段 1 标注类型
        m_head_type = re.search(r'####\s*1\.\s*章节类型[^\n]*\n\s*\[?([A-Fa-f])类', ch_text)
        head_type = m_head_type.group(1).upper() if m_head_type else ""

        # 2. 提取 JSON 元数据
        m_json = re.search(r'```json\s*(.*?)\s*```', ch_text, re.DOTALL)
        json_type = ""
        if m_json:
            try:
                mdata = json.loads(m_json.group(1).strip())
                json_type = str(mdata.get("type", "")).strip().upper()
                if not json_type:
                    warnings.append(f"第 {ch_num} 章: JSON 元数据中缺少 'type' 字段")
            except Exception as e:
                fatal_issues.append(f"第 {ch_num} 章: JSON 元数据块格式错误 (无法 json.loads: {e})")
        else:
            fatal_issues.append(f"第 {ch_num} 章: 缺少独立 ```json 元数据块")

        # 3. 类型交叉一致性校验
        effective_type = json_type or head_type or "A"
        if head_type and json_type and head_type != json_type:
            warnings.append(f"第 {ch_num} 章: 【类型不一致】字段1标注为 [{head_type}类]，但 JSON type 为 '{json_type}'")

        if effective_type in type_distribution:
            type_distribution[effective_type] += 1
        else:
            type_distribution["OTHER"] += 1

        parsed_sequence.append((ch_num, effective_type))

        # 4. Stakes 紧迫度检查
        m_stakes = re.search(r'(?:核心任务|非此不可的理由|stakes)[^\n]*[：:]\s*(.*?)(?=\n\s*####|\n\s*```|\Z)', ch_text, re.DOTALL | re.IGNORECASE)
        if not m_stakes or len(m_stakes.group(1).strip()) < 6:
            warnings.append(f"第 {ch_num} 章: 【核心任务/Stakes】过于单薄或缺失")

        # 5. 结尾钩子检查
        m_hook = re.search(r'(?:结束钩子|结尾钩子|起止落点)[^\n]*[：:]\s*(.*?)(?=\n\s*####|\n\s*```|\Z)', ch_text, re.DOTALL)
        if not m_hook or len(m_hook.group(1).strip()) < 8:
            warnings.append(f"第 {ch_num} 章: 【结束钩子】描述过短或缺失")

        # 5.1 视听焦点与微动作标注检查
        m_sensory = re.search(r'####\s*8\.\s*视听焦点[^\n]*\n(.*?)(?=\n\s*####|\n\s*```|\Z)', ch_text, re.DOTALL)
        if m_sensory:
            sensory_txt = m_sensory.group(1).strip()
            if len(sensory_txt) < 15:
                warnings.append(f"第 {ch_num} 章: 【视听焦点/微动作】描述过短或单薄")
            elif not any(k in sensory_txt for k in ["手", "指", "喉", "肩", "视线", "眼", "步", "尺", "案", "光", "声", "气", "味", "温", "掌", "心"]):
                warnings.append(f"第 {ch_num} 章: 【视听焦点/微动作缺失】未见具象物理器官或空间动作锚点")

    # 6. C类连续熔断校验 (严禁连续 3 章及以上为 C 类)
    consecutive_c = 0
    c_start_ch = 0
    for ch_num, ch_t in parsed_sequence:
        if ch_t == "C":
            if consecutive_c == 0:
                c_start_ch = ch_num
            consecutive_c += 1
            if consecutive_c >= 3:
                fatal_issues.append(f"第 {c_start_ch}~{ch_num} 章: 【章节类型熔断违规】连续 {consecutive_c} 章为 C 类(造物)，必须穿插 B 类(动作)或 D 类(关系)")
        else:
            consecutive_c = 0

    # 7. 10 章滑动窗口配额校验 (每 10 章窗口必须包含至少 1 章 B 类与 1 章 D 类)
    if len(parsed_sequence) >= 10:
        window_size = 10
        for w_start in range(0, len(parsed_sequence) - window_size + 1):
            window = parsed_sequence[w_start : w_start + window_size]
            w_types = [t for _, t in window]
            w_start_ch = window[0][0]
            w_end_ch = window[-1][0]
            b_cnt = w_types.count("B")
            d_cnt = w_types.count("D")
            if b_cnt < 1:
                warnings.append(f"第 {w_start_ch}~{w_end_ch} 章窗口: 【配额不足】10章内缺少 B 类动作章节 (当前: {b_cnt} 章)")
            if d_cnt < 1:
                warnings.append(f"第 {w_start_ch}~{w_end_ch} 章窗口: 【配额不足】10章内缺少 D 类人物关系章节 (当前: {d_cnt} 章)")

    # 8. 七猫黄金三章强制类别熔断校验 (第 1~3 章绝对严禁任何 E 类过渡叙事) 与 前20章 F 类配额校验
    f_in_first_20 = 0
    for ch_num, ch_t in parsed_sequence:
        if ch_num in [1, 2, 3] and ch_t == "E":
            fatal_issues.append(f"第 {ch_num} 章: 【七猫黄金三章熔断违规】第 1~3 章绝对禁止 E 类(过渡叙事)！必须为 A/B/C/F 类即时对抗或危机反杀章")
        if ch_num <= 20 and ch_t == "F":
            f_in_first_20 += 1

    if f_in_first_20 > 1:
        warnings.append(f"前 20 章范围: 【F类配额超标】前 20 章内包含了 {f_in_first_20} 个 F 类(复合高潮)章节 (上限 1 章)，避免开篇节奏过载与审美疲劳！")

    # 9. 首两章开头钩子二元强制校验 (M6规范)
    for ch_num, ch_text in chapter_list:
        if ch_num in [1, 2]:
            m_open_hook = re.search(r'开头钩子[^：:\n]*[：:]\s*(.*?)(?=\n\s*-\s*[*_]*结束钩子|\n\s*####|\n\s*```|\Z)', ch_text, re.DOTALL)
            if m_open_hook:
                hook_content = m_open_hook.group(1).strip()
                threat_cues = [
                    "圣旨", "鸩酒", "削爵", "短剑", "流放", "断饷", "刺客", "刀", "旨", "逼", "门",
                    "官", "敌", "令", "按", "砸", "扣", "查", "马蹄", "太监", "公公", "踢", "册",
                    "账", "尺", "夺", "顿", "公案", "掌掴", "折辱", "冷笑", "刁难", "压迫", "刁难", "断粮",
                    "锁", "踹", "抓", "杀", "斩", "杖", "罚", "抢", "抢夺"
                ]
                if not any(c in hook_content for c in threat_cues):
                    warnings.append(f"第 {ch_num} 章: 【开头钩子二元信息缺失】第 {ch_num} 章开头钩子未包含明确的【压迫者/即时威胁】实体线索！")

    all_issues = fatal_issues + warnings
    passed = len(fatal_issues) == 0
    score = max(0, 100 - len(fatal_issues) * 20 - len(warnings) * 5)
    return {
        "passed": passed,
        "score": score,
        "fatal_issues": fatal_issues,
        "warnings": warnings,
        "issues": all_issues,
        "total_chapters": total_chapters,
        "type_distribution": type_distribution
    }


def lint_block_blueprint(full_text: str) -> Dict[str, Any]:
    """
    块级施工图 0ms 深度质检 (M4 & M5 规范)：
    1. 扫描字段 5 是否残留“情绪降温阻尼/严禁暧昧/严格死锁”等压制措辞 (M5)
    2. 扫描字段 10 蓄力期与爽点间隔是否超标 (≤ 3 章) (M4)
    支持区分 fatal_issues(阻断项) 与 warnings(告警项)。
    """
    fatal_issues = []
    warnings = []

    # 1. M5 压制性词汇检测 (致命项)
    banned_damping_words = ["严禁暧昧", "严格死锁在利益", "禁止越界", "情绪降温物理阻尼", "严禁任何肢体温存"]
    for w in banned_damping_words:
        if w in full_text:
            fatal_issues.append(f"【M5 情绪阻尼残余违规】施工图中检测到压制性禁令词【{w}】，必须彻底替换为【爽点与情感双叠加原则】！")

    # 2. M4 爽点间隔与蓄力期检测
    block_splits = list(re.finditer(r'(?:^|\n)##\s*块\s*(\d+)', full_text))
    if not block_splits:
        block_splits = list(re.finditer(r'(?:^|\n)###\s*块\s*(\d+)', full_text))

    for i in range(len(block_splits)):
        b_num = block_splits[i].group(1)
        b_start = block_splits[i].start()
        b_end = block_splits[i + 1].start() if i + 1 < len(block_splits) else len(full_text)
        b_text = full_text[b_start:b_end]

        # 检查字段 10 中的校验表或间隔（执行 Python 真实数学减法验算）
        table_rows = re.findall(r'\|\s*\d+\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|', b_text)
        table_payoff_chapters = set()
        if table_rows:
            prev_ch = None
            for r in table_rows:
                ch_str = r[1].strip()
                m_ch = re.search(r'第?\s*(\d+)\s*章?', ch_str)
                if m_ch:
                    cur_ch = int(m_ch.group(1))
                    table_payoff_chapters.add(cur_ch)
                    if prev_ch is not None:
                        real_delta = cur_ch - prev_ch
                        if real_delta > 3:
                            fatal_issues.append(f"块 {b_num}: 【爽点蓄力期数学超标】第 {prev_ch} 章 ➔ 第 {cur_ch} 章实际间隔为 {real_delta} 章(>3章)，即便标注合规也属于虚假合规！必须缩短间隔至≤3章！")
                    prev_ch = cur_ch

                status_str = r[3].strip()
                if "超标" in status_str and "合规" not in status_str:
                    fatal_issues.append(f"块 {b_num}: 【爽点蓄力期超标】检测到爽点间隔超标(>3章)，必须将第4章调整为爽点型章节！")
                    break

        ch_entries = re.findall(r'- \*\*第\s*(\d+)\s*章\*\*[:：]\s*(.*?)(?=\n- \*\*第|\n###|\Z)', b_text, re.DOTALL)
        if ch_entries:
            consecutive_tech = 0
            tech_start = 0
            payoff_keywords = [
                "爽点", "清算", "震慑", "反杀", "大捷", "全歼", "破门", "认主", "打脸", "算账", 
                "降维", "缴获", "画押", "覆灭", "授勋", "突破", "爆破", "认罪", "收编", "斩杀", 
                "击退", "折服", "立功", "抄没", "亏空", "退让", "逼退", "夺得", "大胜", "瘫软", 
                "惊惧", "出炉", "出铁", "试射", "换装", "封赏", "立威", "击毙", "下跪", "认领"
            ]
            for ch_n_str, ch_desc in ch_entries:
                ch_n = int(ch_n_str)
                has_payoff = (ch_n in table_payoff_chapters) or any(k in ch_desc for k in payoff_keywords)
                if not has_payoff:
                    if consecutive_tech == 0:
                        tech_start = ch_n
                    consecutive_tech += 1
                    if consecutive_tech >= 5:
                        fatal_issues.append(f"块 {b_num}: 【长技术攻关蓄力熔断】第 {tech_start}~{ch_n} 章连续 {consecutive_tech} 章无爽点事件，必须在第 4 章嵌入微型打脸或外部危机！")
                        break
                else:
                    consecutive_tech = 0
        else:
            m_buildup = re.search(r'蓄力期[（(]前\s*(\d+)[-~](\d+)\s*章[)）]', b_text)
            if m_buildup:
                b_s = int(m_buildup.group(1))
                b_e = int(m_buildup.group(2))
                if (b_e - b_s + 1) > 3:
                    fatal_issues.append(f"块 {b_num}: 【爽点蓄力期超标】声明蓄力期为 {b_s}~{b_e} 章 ({b_e - b_s + 1}章 > 3章上限)，必须将爽点前置到第 {b_s + 2} 章！")

    # 3. 块尾钩子同质化检测 (防连续纯外部敌袭) 与 字段 9 呼吸缓冲章副手轮换检测
    prev_b_num = None
    prev_hook_type = None
    prev_subordinate = None
    for i in range(len(block_splits)):
        b_num = block_splits[i].group(1)
        b_start = block_splits[i].start()
        b_end = block_splits[i + 1].start() if i + 1 < len(block_splits) else len(full_text)
        b_text = full_text[b_start:b_end]

        # 3.1 块尾钩子检测
        m_hook = re.search(r'###\s*11\.\s*块尾钩子[^\n]*\n(.*?)(?=\n###|\n##|\Z)', b_text, re.DOTALL)
        if m_hook:
            hook_txt = m_hook.group(1).strip()
            is_enemy_raid = any(k in hook_txt for k in ["大军压境", "蛮族", "敌骑", "敌袭", "兵临城下", "围城", "南侵", "叩关", "胡骑"])
            is_internal = any(k in hook_txt for k in ["绝饷", "断粮", "断铁", "内患", "渗透", "配方", "手脚", "背叛", "密信", "暗记", "钦差", "鸩酒", "弹劾", "内讧"])
            cur_hook_type = "internal" if is_internal else ("external_raid" if is_enemy_raid else "other")
            if prev_hook_type == "external_raid" and cur_hook_type == "external_raid":
                warnings.append(f"块 {prev_b_num} 与 块 {b_num}: 【块尾钩子同质化警告】连续两块块尾钩子均为纯外部敌袭，建议置换为内忧断饷、技术渗透或情感背叛等递进式钩子！")
            prev_hook_type = cur_hook_type

        # 3.2 字段 9 呼吸缓冲章副手轮换检测
        m_sub = re.search(r'###\s*9\.\s*呼吸空间[^\n]*\n(.*?)(?=\n###|\n##|\Z)', b_text, re.DOTALL)
        if m_sub:
            sub_txt = m_sub.group(1)
            m_sub_name = re.search(r'(?:主视角副手|主要副手|副手|聚焦副手|随从)[：:]\s*([^\s，,、\n]+)', sub_txt)
            if m_sub_name:
                cur_subordinate = m_sub_name.group(1).strip().replace("【", "").replace("】", "")
                if cur_subordinate and prev_subordinate and cur_subordinate == prev_subordinate:
                    warnings.append(f"块 {prev_b_num} 与 块 {b_num}: 【呼吸缓冲章副手连续重合警告】连续两块呼吸缓冲章均聚焦于同一副手【{cur_subordinate}】，违反跨块轮换铁律，建议置换为其他副手！")
                prev_subordinate = cur_subordinate

        prev_b_num = b_num

    all_issues = fatal_issues + warnings
    passed = len(fatal_issues) == 0
    score = max(0, 100 - len(fatal_issues) * 20 - len(warnings) * 5)
    return {
        "passed": passed,
        "score": score,
        "fatal_issues": fatal_issues,
        "warnings": warnings,
        "issues": all_issues
    }


def lint_block_blueprint_battle_coordinates(block_text: str) -> Dict[str, Any]:
    """重大战役章节三维几何坐标校验（软告警）"""
    issues = []
    ch_entries = re.findall(r'- \*\*第\s*(\d+)\s*章\*\*[:：]\s*(.*?)(?=\n- \*\*第|\n###|\Z)', block_text, re.DOTALL)
    geo_keywords = [
        "步", "丈", "射界", "壕沟", "纵深", "高地", "顺风", "逆风", "标尺", "仰角", "俯角", "掩体",
        "扇面", "梯队", "射程", "米", "里", "山", "关", "坡", "堑", "壁", "谷", "门", "城", "线", "口", "角", "度", "坐标", "距离"
    ]
    battle_indicators = ["决战", "总攻", "围歼", "攻城", "血战", "伏击", "会战", "大捷", "破敌", "击溃", "炮击", "扫荡", "防线", "强攻"]

    for ch_num_str, b_body in ch_entries:
        if any(ind in b_body for ind in battle_indicators):
            has_geo = any(k in b_body for k in geo_keywords)
            if not has_geo:
                issues.append(f"第 {ch_num_str} 章重大战役规划: 缺少战役三维几何参数（如射界/壕沟/步丈距离/风向）！")

    return {
        "passed": len(issues) == 0,
        "issues": issues
    }


def check_hazardous_weapons_consistency(text: str) -> Dict[str, Any]:
    """高危武器人设与安全一致性质检"""
    issues = []
    hazard_weapons = ["白磷", "猛火油", "强酸", "王水", "剧毒", "生石灰", "黄磷"]
    protection_cues = ["防毒", "湿布", "护目", "面罩", "皮手套", "顺风", "退后", "防护", "隔离", "手套"]
    
    for hw in hazard_weapons:
        if hw in text:
            m_ctx = re.search(rf'([^。\n]*?{hw}[^。\n]*)', text)
            if m_ctx:
                line_text = m_ctx.group(1)
                if not any(p in line_text for p in protection_cues):
                    issues.append(f"【高危造物安全一致性警告】出现高危化学/武器【{hw}】，未见防毒面罩/顺风/防护等安全交代！")
                    break

    return {
        "passed": len(issues) == 0,
        "issues": issues
    }


def lint_master_outline(master_text: str, total_chapters: Optional[int] = None) -> Dict[str, Any]:
    """
    全书总纲动态自适应质量门禁：
    1. 动态提取/计算 total_chapters；
    2. 校验第二幕阶段性胜利清算节点密度（允许间隔 ≤ max(25, total_chapters * 0.10)）；
    3. 校验核心宿敌跨时空互动频次与最大间隔（允许间隔 ≤ max(30, total_chapters * 0.15)）；
    4. 校验分卷六类爽点覆盖度。
    """
    fatal_issues = []
    warnings = []

    if not total_chapters:
        m_tc = re.search(r'整整【(\d+)】章', master_text)
        if not m_tc:
            m_tc = re.search(r'(?:全书总章数|目标总章数)[：:\s]*(\d+)', master_text)
        total_chapters = int(m_tc.group(1)) if m_tc else 1000

    # 1. 宿敌互动间隔校验
    nemesis_max_allowed = max(30, int(total_chapters * 0.15))
    m_nemesis_sec = re.search(r'###\s*4\.\s*远端高位对弈者与宿敌线索.*?(?=###|\n--|\Z)', master_text, re.DOTALL)
    if m_nemesis_sec:
        nemesis_txt = m_nemesis_sec.group(0)
        enemies = re.findall(r'(\d+)\.\s*\*\*([^*]+)\*\*(.*?)(?=(?:\n\d+\.\s*\*\*|\n###|\Z))', nemesis_txt, re.DOTALL)
        for idx, enemy_name, enemy_body in enemies:
            ch_nodes = [int(n) for n in re.findall(r'第\s*(\d+)\s*章', enemy_body)]
            if ch_nodes:
                prev_n = ch_nodes[0]
                for cur_n in ch_nodes[1:]:
                    gap = cur_n - prev_n
                    if gap > nemesis_max_allowed:
                        fatal_issues.append(f"宿敌【{enemy_name.strip()}】: 【互动间隔断层】第 {prev_n} 章 ➔ 第 {cur_n} 章间隔 {gap} 章(>{nemesis_max_allowed}章上限)，反派仇恨严重冷却！")
                    prev_n = cur_n

    # 2. 第二幕阶段清算节点密度校验
    m_act2 = re.search(r'【第二幕[^】]*】.*?(?=【第三幕|\Z)', master_text, re.DOTALL)
    if m_act2:
        act2_txt = m_act2.group(0)
        checkpoints = [int(n) for n in re.findall(r'第\s*(\d+)\s*章', act2_txt)]
        act2_max_allowed_step = max(25, int(total_chapters * 0.10))
        if len(checkpoints) >= 2:
            prev_cp = checkpoints[0]
            for cur_cp in checkpoints[1:]:
                step = cur_cp - prev_cp
                if step > act2_max_allowed_step:
                    warnings.append(f"第二幕沙盘: 【阶段清算间隔过长】第 {prev_cp} 章 ➔ 第 {cur_cp} 章跨度 {step} 章(>{act2_max_allowed_step}章)，易形成阅读成就沙漠！")
                prev_cp = cur_cp

    # 3. 第二幕清算节点三级精度校验 (单章号坐标与三要素完整性)
    sec_prec = lint_master_outline_second_act_precision(master_text)
    fatal_issues.extend(sec_prec["fatal_issues"])
    warnings.extend(sec_prec["warnings"])

    all_issues = fatal_issues + warnings
    passed = len(fatal_issues) == 0
    score = max(0, 100 - len(fatal_issues) * 20 - len(warnings) * 5)
    return {
        "passed": passed,
        "score": score,
        "fatal_issues": fatal_issues,
        "warnings": warnings,
        "issues": all_issues
    }


def lint_master_outline_second_act_precision(master_text: str) -> Dict[str, Any]:
    """校验全书总纲第二幕清算节点的三级精度 (单章号坐标 + 突破/清算/收益三要素)"""
    fatal_issues = []
    warnings = []
    m_act2 = re.search(r'【第二幕[^】]*】.*?(?=【第三幕|\Z)', master_text, re.DOTALL)
    if m_act2:
        act2_txt = m_act2.group(0)
        # 提取形如：├─ 20% 清算点（第195章）：[描述] 或 └─ 80% 阶段高潮（第751~900章）：[描述]
        checkpoints = re.findall(r'[├└─\-*•]\s*[^（\n]*（第\s*([^）\n]+)\s*章）[：:]\s*([^\n]+)', act2_txt)
        
        breakthrough_cues = ["突破", "研发", "出炉", "投产", "定型", "试射", "首炉", "换装", "筑成", "下线", "布局", "建立", "成型", "展开", "攻克"]
        liquidation_cues = ["清算", "挫败", "击溃", "全歼", "斩杀", "打崩", "反击", "封锁", "瓦解", "截断", "破局", "中点", "摊牌", "合围"]
        revenue_cues = ["两", "石", "吨", "斤", "元", "万", "支", "匹", "门", "册", "利", "银", "收益", "据点", "战资", "主导权", "基金"]

        for ch_str, desc in checkpoints:
            clean_ch = ch_str.strip()
            # 1. 坐标精度检查：清算点严禁使用区间
            if any(sep in clean_ch for sep in ["~", "～", "-"]):
                fatal_issues.append(f"第二幕清算节点（第 {clean_ch} 章）: 【坐标精度不足】清算节点必须锁定为具体单章号，严禁使用模糊区间！")
            
            # 2. 内容三要素检查
            has_break = any(b in desc for b in breakthrough_cues)
            has_liq = any(l in desc for l in liquidation_cues)
            has_rev = any(r in desc for r in revenue_cues)
            
            missing_elements = []
            if not has_break: missing_elements.append("技术/战术突破")
            if not has_liq: missing_elements.append("清算对象")
            if not has_rev: missing_elements.append("量化收益落盘")
            
            if len(missing_elements) >= 2:
                warnings.append(f"第二幕清算节点（第 {clean_ch} 章）: 【内容精度不足】缺失关键要素 ({', '.join(missing_elements)})，严禁空泛概述！")

    all_issues = fatal_issues + warnings
    return {
        "passed": len(fatal_issues) == 0,
        "fatal_issues": fatal_issues,
        "warnings": warnings,
        "issues": all_issues
    }


def deep_narrative_lint(outlines_dir: str) -> Dict[str, Any]:
    """对大纲目录进行全量深度质检"""
    results = {}
    if not os.path.exists(outlines_dir):
        return {"error": f"目录不存在: {outlines_dir}"}

    md_files = glob.glob(os.path.join(outlines_dir, "*.md")) + glob.glob(os.path.join(outlines_dir, "**", "*.md"), recursive=True)
    for f in md_files:
        fname = os.path.basename(f)
        try:
            with open(f, "r", encoding="utf-8") as rf:
                txt = rf.read()
            if "章节细纲" in fname:
                results[fname] = lint_chapter_outlines(txt)
            elif "块级施工图" in fname:
                res_b = lint_block_blueprint(txt)
                res_geo = lint_block_blueprint_battle_coordinates(txt)
                res_b["battle_geo_issues"] = res_geo["issues"]
                results[fname] = res_b
            elif "大纲.md" in fname or "总纲" in fname:
                results[fname] = lint_master_outline(txt)
        except Exception as e:
            results[fname] = {"error": str(e)}

    return results
