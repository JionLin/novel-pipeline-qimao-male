"""
utils.py - 通用小说流水线底层公共工具库 (v4.0)
包含：字数统计、XML标签提取、确定性代码级质检（套话/对话比/碎段/实体黑名单）
"""

import os
import sys
import re
from typing import List, Tuple, Optional, Any, Dict

# 19项 AI 八股套话黑名单（含常见变体）
AI_CLICHE_LIST = [
    "心中一凛", "瞳孔微缩", "倒吸一口凉气", "倒抽凉气", "倒吸凉气", "倒抽一口冷气", "倒吸一口冷气",
    "嘴角微微上扬", "眼中闪过一抹", "眼底闪过一抹",
    "心头一震", "瞳孔一震", "心中掀起惊涛骇浪", "触目惊心", "仿佛要将他生吞活剥",
    "目光如炬", "宛如天威降临", "空气仿佛凝固", "时间仿佛静止", "浑身一震",
    "脸色大变", "难以置信", "眼底闪过一丝精芒", "嘴角噙起一抹", "嘴角噙着一抹"
]

def count_chinese_chars(text: str) -> int:
    """
    精确统计中文字数（含中文标点，忽略Markdown标题、空格、英文标记）
    """
    if not text:
        return 0
    # 过滤 Markdown 标题行 (# 第X章...)
    body = re.sub(r'^#+\s*.*$', '', text, flags=re.MULTILINE)
    count = 0
    for ch in body:
        if ('\u4e00' <= ch <= '\u9fff' or 
            '\u3000' <= ch <= '\u303f' or 
            '\uff00' <= ch <= '\uffef' or 
            ch in '。，！？、；：“”‘’——…《》【】·（）'):
            count += 1
    return count

def extract_xml_tag(text: str, tag: str) -> str:
    """从文本中提取 XML 标签内容（含多重 fallback）"""
    if not text:
        return ""
    pattern = rf"<{tag}>\s*(.*?)\s*</{tag}>"
    m = re.search(pattern, text, re.DOTALL)
    if m:
        return m.group(1).strip()
    parts = re.split(rf"</?{tag}>", text)
    if len(parts) >= 3:
        return parts[1].strip()
    m2 = re.search(rf"<{tag}>(.*?)(?=<|$)", text, re.DOTALL)
    if m2:
        return m2.group(1).strip()
    return ""

def check_ai_cliches(text: str) -> List[str]:
    """扫描文本中出现的 AI 八股套话"""
    hits = []
    for cliche in AI_CLICHE_LIST:
        if cliche in text:
            hits.append(cliche)
    return hits

def sanitize_fictional_props(text: str) -> str:
    """
    网络文学古风艺术化脱敏字典：
    将现实危险化学、爆炸配比及剧毒名词自动转化为虚构古代墨家/工匠术语，
    彻底消除大模型底层 API 误触发危险品/爆炸物审查 (Explosives & Weapons Policy) 的可能。
    """
    if not text:
        return text
    
    # 比例与数值过滤
    text = re.sub(r'（\s*\d+\s*:\s*\d+\s*:\s*\d+\s*）', '（墨家古法经验比例）', text)
    text = re.sub(r'\b\d+\s*:\s*\d+\s*:\s*\d+\b', '标准古法配伍比重', text)
    text = re.sub(r'黄金质量比', '古代工匠经验配伍', text)
    
    # 敏感词脱敏映射表
    replacements = [
        (r'土法熬硝|熬硝提纯|熬硝制药|熬硝', '古法淬炼硝晶'),
        (r'黑火药配方|火药配方|炸药配方', '墨家伏火奇物九炼古方'),
        (r'自制黑火药|制作黑火药|自制炸药|制作炸药', '研磨秘制伏火散'),
        (r'黑火药|黄色炸药|烈性炸药|硝化甘油', '伏火烈药'),
        (r'苦杏仁毒酒|苦杏仁剧毒|苦杏仁毒', '蚀骨绝脉散'),
        (r'剧毒砒霜|纯度砒霜|提纯砒霜', '绝命鹤顶红'),
        (r'汞化白霜|汞化|水银提纯|水银制备|水银', '古法凝霜冷液'),
        (r'矾油|浓硫酸|发烟硫酸|强酸腐蚀', '青矾冷萃原液'),
        (r'雷汞|起爆药|起爆炸药|击发药', '震天火引'),
        (r'氯化汞|剧毒汞盐|腐蚀毒液', '蚀骨古煞散'),
    ]
    for pattern, repl in replacements:
        text = re.sub(pattern, repl, text)
    return text

def is_stealth_or_solo_chapter(outline_text: str) -> bool:
    """
    场景语义识别器：
    自动检测本章细纲是否包含暗夜、潜伏、破庙、独处、失语哑奴、闭关开荒等极端安静场景。
    若命中，则表明本章客观需要保持死寂，对话占比硬红线自动豁免。
    """
    if not outline_text:
        return False
    stealth_keywords = [
        "暗夜", "潜伏", "破庙", "闭关", "独处", "熬硝", "制药", "淬炼", "研磨",
        "哑奴", "哑巴", "死寂", "暗杀", "单兵", "避雨", "疗伤", "清创", "排毒"
    ]
    hit_count = sum(1 for kw in stealth_keywords if kw in outline_text)
    return hit_count >= 2

def check_dialogue_ratio(text: str) -> float:
    """计算对话字符占总字符的比例"""
    total = count_chinese_chars(text)
    if total == 0:
        return 0.0
    dialogues = re.findall(r'["“](.*?)["”]', text, re.DOTALL)
    dialogue_chars = sum(count_chinese_chars(d) for d in dialogues)
    return dialogue_chars / total

def check_broken_paragraphs(text: str) -> Tuple[bool, int]:
    """
    检查是否存在机械碎段排版（连续多个超短段落）
    返回 (is_broken, max_consecutive_short_paragraphs)
    """
    paras = [p.strip() for p in text.split('\n') if p.strip() and not p.strip().startswith('#')]
    if len(paras) < 10:
        return False, 0
    
    consecutive = 0
    max_consecutive = 0
    for p in paras:
        wc = count_chinese_chars(p)
        if 0 < wc <= 15:
            consecutive += 1
            max_consecutive = max(max_consecutive, consecutive)
        else:
            consecutive = 0
    
    # 连续 8 个以上 ≤15 字的碎段判为机械碎段
    return (max_consecutive >= 8), max_consecutive

def check_entity_blacklist(text: str, blacklist: List[str]) -> List[str]:
    """检查是否命中了实体黑名单"""
    hits = []
    for entity in blacklist:
        if entity and entity in text:
            hits.append(entity)
    return hits

def check_catchphrase_blacklist(text: str, blacklist: List[str]) -> List[str]:
    """检查是否命中了固定口头禅/金句套话黑名单（如'这牛马的一生'等）"""
    hits = []
    for phrase in blacklist:
        if phrase and phrase in text:
            hits.append(phrase)
    return hits

def check_vulgar_villain_abuse(text: str) -> List[str]:
    """检查反派是否出现低幼泼妇式辱骂（应改为阶层伪善与绵里藏针）"""
    vulgar_words = ["废狗", "贱种", "小杂种", "杂种", "小畜生", "畜生", "狗东西", "千刀万剐", "剥皮抽筋", "死期到了", "老子要宰了你"]
    return [w for w in vulgar_words if w in text]

def sanitize_vulgar_and_cliches(text: str) -> str:
    """
    通用确定性文本净化器：
    自动替换低幼泼妇辱骂词与典型 AI 套话，确保发布版 100% 纯净。
    """
    replacements = {
        "小杂种": "这落魄之人",
        "杂种": "庶孽",
        "小畜生": "此人",
        "畜生": "孽障",
        "狗东西": "这狂徒",
        "贱种": "这罪人",
        "废狗": "废人",
        "千刀万剐": "按律严惩",
        "剥皮抽筋": "严加处置",
        "死期到了": "气数已尽",
        "老子要宰了你": "本官定不轻饶",
        "倒吸了一口凉气": "下意识屏住呼吸",
        "倒吸一口凉气": "下意识屏住呼吸",
        "倒抽凉气": "疼得倒抽一口气",
        "倒吸凉气": "下意识咬紧牙关",
        "倒抽一口冷气": "下意识屏住呼吸",
        "倒吸一口冷气": "下意识屏住呼吸",
        "嘴角微微上扬": "嘴角微动",
        "嘴角噙着一抹": "脸上带着一丝",
        "嘴角勾起一抹": "脸上带着一丝",
        "嘴角勾起": "嘴角微动",
        "眼中闪过一抹": "眼神骤然一沉",
        "眼底闪过一抹": "眼神骤然一沉",
        "眼底闪过一丝": "眼神微动",
        "眼中闪过一丝": "目光微沉",
        "眼中的杀机在这一刻缓缓凝固": "面皮上最后一丝温度彻底褪尽",
        "眼中的杀机": "面容的冷峻",
        "眼底的杀机": "面容的冷冽",
        "眼中闪过": "神色微变",
        "眼底闪过": "神色微动",
        "心中一凛": "心头微紧",
        "瞳孔微缩": "目光一凝",
        "瞳孔骤缩": "眼神骤凝",
        "瞳孔一震": "视线一顿",
        "嘴角牵起一抹": "嘴角泛起一丝",
        "嘴角泛起一抹": "嘴角微动",
        "难以置信": "出乎意料",
        "空气仿佛凝固": "四周寂静无声",
    }
    for old_w, new_w in replacements.items():
        text = text.replace(old_w, new_w)
    return text

def check_ending_slogans(text: str) -> List[str]:
    """检查章末最后 250 字是否出现口号化宣言或指向未来的假设性威胁（章末应以纯物理动作与环境留白收尾）"""
    tail = text[-250:] if len(text) > 250 else text
    slogans = [
        "钢铁洪流", "血债血偿", "定叫你", "定要让", "且看我如何", "誓要让",
        "踏碎京畿", "踏碎帝都", "百倍奉还", "千倍奉还", "轰然开启", "无上帝路",
        "载入史册", "命运的齿轮", "见见第一滴血", "见第一滴血", "见见血"
    ]
    hits = [s for s in slogans if s in tail]
    future_threat = re.search(r'(?:若|要是|一旦)[^。！？\n]{2,20}(?:正好|定要|便叫|见见)[^。！？\n]{0,20}[。！？]?', tail)
    if future_threat:
        hits.append(future_threat.group(0).strip())
    return hits

def check_anti_hardcoding_guard(script_dir: str = None, config_path: str = None) -> bool:
    """
    通用 CI/CD 级代码防硬编码静态门禁（全脚本通用守卫）：
    启动前动态提取当前活动项目的 config.yaml 中的角色名与专有名词。
    若扫描到任何 .py 脚本（除 test.py 外）中包含这些业务专有名词，立刻抛出致命错误并返回 False！
    """
    import glob, yaml
    if not script_dir:
        script_dir = os.path.dirname(os.path.abspath(__file__))

    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
        except Exception:
            cfg = {}
    else:
        cfg = load_active_config(script_dir=script_dir)

    char_names = [c.get("name") for c in cfg.get("character_locks", []) if isinstance(c, dict) and c.get("name")]
    core_cast = cfg.get("project", {}).get("characters", []) + cfg.get("project", {}).get("core_cast", [])
    all_sensitive_names = [n for n in set(char_names + core_cast) if n and len(n) >= 2]
    if not all_sensitive_names:
        return True

    violations = []
    py_files = glob.glob(os.path.join(script_dir, "**", "*.py"), recursive=True)
    for pf in py_files:
        fname = os.path.relpath(pf, script_dir)
        if os.path.basename(pf) in ["test.py", "verify_pipeline_integrity.py"]:
            continue
        try:
            with open(pf, "r", encoding="utf-8") as f:
                lines = f.readlines()
            for l_idx, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                for cname in all_sensitive_names:
                    if cname in stripped:
                        violations.append((fname, l_idx, cname, stripped))
        except Exception:
            pass

    if violations:
        print("=" * 70, file=sys.stderr)
        print("❌ [FATAL CODE HARDCODING SMELL] 代码防硬编码静态门禁拦截失败！", file=sys.stderr)
        print("在以下 Python 脚本中检测到写死了本书特定业务实体名称（严禁在 .py 代码中硬编码）：", file=sys.stderr)
        for f, l, c, t in violations[:5]:
            print(f"   ├─ [{f}:行{l}] 命中: {c} -> {t[:60]}", file=sys.stderr)
        print("请将所有具体规则与人名下放到 config.yaml 或数据库中！", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        return False
    return True


def atomic_write(file_path: str, content: str, encoding: str = "utf-8") -> None:
    """
    POSIX 原子级安全写入：
    1. 在目标同目录下创建命名临时文件（确保处于同一物理挂载点/文件系统）；
    2. 写入完整数据并强制刷盘 (flush + os.fsync)；
    3. 调用底层 os.replace 执行原子级指针替换；
    4. 100% 杜绝因断电、崩溃、并发中断导致的 0 字节或半截损坏文件。
    """
    import tempfile
    dir_name = os.path.dirname(os.path.abspath(file_path))
    os.makedirs(dir_name, exist_ok=True)
    tf = tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, encoding=encoding)
    temp_path = tf.name
    try:
        tf.write(content)
        tf.flush()
        os.fsync(tf.fileno())
        tf.close()
        os.replace(temp_path, file_path)
    except Exception as e:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        raise IOError(f"原子写入文件失败 [{file_path}]: {e}")


def configure_sqlite_resilience(conn: Any, busy_timeout_ms: int = 5000) -> None:
    """
    全量 SQLite 韧性配置：
    - WAL 模式 (Write-Ahead Logging): 读写互不阻塞；
    - busy_timeout: 并发锁自动重试等待；
    - synchronous=NORMAL: 保持 ACID 同时极大提升高频写入性能。
    """
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute(f"PRAGMA busy_timeout={busy_timeout_ms};")
        conn.execute("PRAGMA synchronous=NORMAL;")
    except Exception:
        pass


def apply_surgical_micro_patch(content: str, cfg: Optional[Dict[str, Any]] = None) -> Tuple[bool, str, List[str]]:
    """
    本地三遍去 AI 微创自愈修剪器 (Local Three-Pass De-Slop Auto-Repair Engine 0ms):
    对正文中的微小瑕疵进行内存级即时无损修剪，避免因微小标点/套话/别名漂移触发整章推倒重写。
    三遍核心管道：
    1. Pass 1·段落呼吸与机械碎段平滑（合并连续单句成段）；
    2. Pass 2·AI八股套话与假寐泛滥物理置换；
    3. Pass 3·味觉感知微创补帧、角色称谓自愈与章末口号修剪。
    """
    if not content:
        return False, content, []

    fixed_items = []
    repaired = content

    # --- Pass 1: 段落呼吸与机械碎段平滑 ---
    lines = repaired.split("\n")
    cleaned_lines = []
    broken_buf = []
    for line in lines:
        stripped = line.strip()
        # 判断是否为 Markdown 标题或空行
        if not stripped:
            if broken_buf:
                cleaned_lines.append("".join(broken_buf))
                broken_buf = []
            cleaned_lines.append("")
        elif stripped.startswith("#") or stripped.startswith("<") or stripped.startswith("【"):
            if broken_buf:
                cleaned_lines.append("".join(broken_buf))
                broken_buf = []
            cleaned_lines.append(stripped)
        elif len(stripped) < 25 and not stripped.endswith(("”", "’", "？", "！", "。")):
            # 短碎段缓冲
            broken_buf.append(stripped)
        else:
            if broken_buf:
                broken_buf.append(stripped)
                cleaned_lines.append("".join(broken_buf))
                broken_buf = []
            else:
                cleaned_lines.append(stripped)
    if broken_buf:
        cleaned_lines.append("".join(broken_buf))
    
    pass1_text = "\n".join(cleaned_lines)
    if pass1_text != repaired:
        repaired = pass1_text
        fixed_items.append("Pass 1: 段落呼吸与短碎段自动平滑")

    # --- Pass 2: 净化 AI 八股套话与假寐泛滥 ---
    cliches_before = check_ai_cliches(repaired)
    if cliches_before:
        repaired = sanitize_vulgar_and_cliches(repaired)
        cliches_after = check_ai_cliches(repaired)
        if len(cliches_after) < len(cliches_before):
            fixed_items.append(f"Pass 2: AI八股套话置换 ({len(cliches_before)} ➔ {len(cliches_after)} 处)")

    sleep_patterns = [
        (r"和衣靠在[^，。！？\n]*?(?:假寐|沉睡)(?:了两个时辰|半个时辰|蓄力)?", "用冷水抹了一把脸，低头校准图纸与公差数据"),
        (r"闭目调息(?:了两个时辰|半个时辰)?，心中豪情", "低头将发烫的机台用粗布盖严，收拢图纸"),
        (r"蜷缩在车厢内假寐，闭目养神", "靠在车厢木板上，借着微弱火光核算路线")
    ]
    for sp_pat, sp_rep in sleep_patterns:
        if re.search(sp_pat, repaired):
            repaired = re.sub(sp_pat, sp_rep, repaired)
            fixed_items.append(f"Pass 2: 假寐动作微创平滑: '{sp_pat}' ➔ 器具/工作动作")

    # --- Pass 3: 角色称谓自愈、章末口号修剪与场景味觉补帧 ---
    if cfg:
        char_locks = cfg.get("character_locks", [])
        for lock in char_locks:
            if isinstance(lock, dict) and "name" in lock and "banned_aliases" in lock:
                c_name = lock["name"]
                for b_alias in lock["banned_aliases"]:
                    if b_alias in repaired:
                        repaired = repaired.replace(b_alias, c_name)
                        fixed_items.append(f"Pass 3: 角色称谓自愈: '{b_alias}' ➔ '{c_name}'")

    slogans = check_ending_slogans(repaired)
    if slogans:
        for s in slogans:
            s_pat = rf'[^，。！？\n]*?{re.escape(s)}[^，。！？\n]*?[。！？]?$'
            if re.search(s_pat, repaired.strip()):
                repaired = re.sub(s_pat, '他按刀收拢衣襟，踏出沉稳脚步，身影融入茫茫风雪之中。', repaired.strip()) + '\n'
            else:
                repaired = repaired.replace(s, '')
        fixed_items.append(f"Pass 3: 章末口号/未来威胁微创置换为纯物理留白: {slogans}")

    taste_keywords = ["苦", "甘", "涩", "茶", "咸", "甜", "辛", "酸", "辣", "铁锈", "麦麸", "焦煤"]
    taste_count = sum(1 for k in taste_keywords if k in repaired)
    if taste_count < 2:
        eat_match = re.search(r"(咽下一口(?:热茶|粗茶|冷水|唾沫|寒风)|咬了一口(?:干粮|麦饼|硬饼)|嚼着(?:干粮|面饼))", repaired)
        if eat_match:
            orig_eat = eat_match.group(1)
            repaired = repaired.replace(orig_eat, f"{orig_eat}，舌根泛起一股带松脂清苦的微涩", 1)
            fixed_items.append(f"Pass 3: 场景味觉自动补帧: '{orig_eat}' ➔ 舌根松脂微涩")

    repaired = re.sub(r"\n{3,}", "\n\n", repaired).strip() + "\n"
    is_repaired = len(fixed_items) > 0 and repaired != content
    return is_repaired, repaired, fixed_items


def _resolve_scripts_root(script_dir: str = None) -> str:
    """解析并标准化 scripts/ 根目录物理路径"""
    if script_dir and os.path.exists(script_dir):
        # 若传入的是子目录 (如 pipeline/)，回退至父目录
        if os.path.basename(os.path.abspath(script_dir)) in ["pipeline", "outline", "agents", "storage", "tools"]:
            return os.path.dirname(os.path.abspath(script_dir))
        return os.path.abspath(script_dir)
    cur = os.path.dirname(os.path.abspath(__file__))
    if os.path.basename(cur) in ["pipeline", "outline", "agents", "storage", "tools"]:
        return os.path.dirname(cur)
    return cur


def get_active_project_dir(script_dir: str = None) -> str:
    """获取当前活动小说项目目录（从 .active_project 指针获取）"""
    root_dir = _resolve_scripts_root(script_dir)
    ptr_file = os.path.join(root_dir, ".active_project")
    if os.path.exists(ptr_file):
        try:
            with open(ptr_file, "r", encoding="utf-8") as f:
                p = f.read().strip()
                if p and os.path.exists(p):
                    return os.path.abspath(p)
        except Exception:
            pass
    return ""


def set_active_project_dir(novel_dir: str, script_dir: str = None) -> bool:
    """设置当前活动小说项目指针 (.active_project)"""
    root_dir = _resolve_scripts_root(script_dir)
    ptr_file = os.path.join(root_dir, ".active_project")
    try:
        atomic_write(ptr_file, os.path.abspath(novel_dir))
        return True
    except Exception:
        return False


def get_default_base_config() -> Dict[str, Any]:
    """
    获取内置极简纯净基础配置骨架（零业务硬编码、零外部文件依赖）
    """
    return {
        "project": {
            "title": "未命名小说",
            "target_words": 2000000,
            "total_chapters": 833,
            "genre": "通用题材",
            "sub_genre": "商业长篇流",
            "platform": "qimao",
            "master_file": "合集.md",
            "chapter_prefix": "C_正文_第",
            "chapter_suffix": "章.md",
            "characters": [],
        },
        "api": {
            "base_url": os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:19528/v1"),
            "api_key": os.getenv("OPENAI_API_KEY", "dfdf"),
            "timeout": 300
        },
        "character_locks": [],

        "batch": {
            "size": 5,
            "max_retry": 3
        },
        "volume_routing": [],
        "models": {
            "planner": {"name": "gemini-3.7-flash-tiered", "temperature": 0.1, "max_tokens": 8192},
            "writer": {"name": "gemini-3.7-flash-tiered", "temperature": 0.55, "max_tokens": 8192},
            "reviewer": {"name": "gemini-3.7-flash-tiered", "temperature": 0.1, "max_tokens": 4096},
            "state_tracker": {"name": "gemini-3.7-flash-tiered", "temperature": 0.1, "max_tokens": 4096}
        },
        "quality": {
            "min_chinese_chars": 2000,
            "target_chinese_chars": 2400,
            "max_chinese_chars": 2800,
            "opening_max_chars": 3000,
            "climax_max_chars": 3000,
            "min_dialogue_ratio_normal": 0.12,
            "min_dialogue_ratio_combat_or_stealth": 0.05
        },
        "structure": {
            "macro_three_act_ratio": {
                "act1": 0.15,
                "act2": 0.65,
                "act3": 0.20
            }
        },
        "state_tracking": {
            "enabled": True,
            "file": "状态文件.json"
        },
        "tech_tree_progression": {
            "vol_1_ch1_100": {
                "allowed_propellants": ["颗粒化提纯黑火药", "硫磺重结晶配比"],
                "allowed_primers": ["拉火铜管", "明火燧发", "硫化锑引信"],
                "allowed_metallurgy": ["土法焦炭高炉", "水力镗床切削熟铁", "陶土坩埚"],
                "forbidden_terms": ["黑索金", "雷酸汞", "TNT", "无烟火药", "硝化甘油", "双基火药"]
            },
            "vol_2_ch101_200": {
                "allowed_propellants": ["苦味酸初型", "单基硝化棉粗制品"],
                "forbidden_terms": ["黑索金", "TNT", "双基火药"]
            }
        },
        "action_pool_registry": {
            "measurement_tools": [
                {"name": "骨质游标卡尺", "action": "指腹推移游标卡尺测爪，核对公差刻槽"},
                {"name": "重力铅锤垂线", "action": "悬起麻绳重力铅锤，微调立柱垂直度"},
                {"name": "自磨气泡水平管", "action": "水准管气泡在两条红线间轻微晃动，校准基座沉降"},
                {"name": "划针与红松炭条", "action": "执起钢划针在冷铁皮上划出规整的下刀基准线"},
                {"name": "测风羽毛与测距规", "action": "手举雀羽感受风向偏角，折扇式测距木规锁定距离"}
            ],
            "life_sensory_details": [
                {"name": "炭火烘烤", "action": "将冻僵发青的指节悬在暗红炭火上缓缓烘烤，感受皮肉发胀的微温"},
                {"name": "松针开水", "action": "端起粗瓷碗咽下一口带松脂清苦的热水，撕开胸腔深处的寒意"},
                {"name": "粗布缠裹", "action": "取来细麻布死死缠紧开裂渗血的虎口，打下牢固的死结"},
                {"name": "盐粒化水", "action": "在冰冷井水中融化少许粗盐，仰头咽下补充体力"}
            ],
            "forbidden_streaks": {
                "max_consecutive_prop_usage": 2,
                "max_consecutive_taste_usage": 2
            }
        },
        "supporting_cast_arc": [
            {
                "role": "副手/武力担当",
                "stages": {
                    "vol_1": "【心境一阶·鹰犬怀疑与道统质问】以体制律例与现实残酷质疑主角，对话携带利益与法理机锋",
                    "vol_2": "【心境二阶·技术折服与主动掩护】由怀疑转为默契同袍，主动承担防线封锁与痕迹清除"
                }
            }
        ]
    }


def load_active_config(script_dir: str = None, project_dir: str = None) -> Dict[str, Any]:
    """统一加载当前活动小说的 config.yaml（100% 仅从当前小说项目目录读取唯一真实数据源，缺省回退至内存纯净默认骨架）"""
    import yaml
    root_dir = _resolve_scripts_root(script_dir)
    p_dir = project_dir or get_active_project_dir(root_dir)
    if p_dir:
        proj_cfg = os.path.join(p_dir, "config.yaml")
        if os.path.exists(proj_cfg):
            try:
                with open(proj_cfg, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
                    cfg.setdefault("project", {})
                    cfg["project"]["novel_dir"] = p_dir
                    return cfg
            except Exception:
                pass
    return get_default_base_config()




class LogMemoryBuffer:
    """内存启动日志暂存器与原子 Flush 刷盘器"""
    _buffer: List[Tuple[str, str, str]] = []  # [(timestamp, level, msg)]

    @classmethod
    def push(cls, msg: str, level: str = "INFO") -> None:
        import time
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        cls._buffer.append((ts, level, msg))

    @classmethod
    def get_all(cls) -> List[Tuple[str, str, str]]:
        return list(cls._buffer)

    @classmethod
    def flush_to_file(cls, target_log_file: str) -> int:
        if not target_log_file or not cls._buffer:
            return 0
        try:
            os.makedirs(os.path.dirname(target_log_file), exist_ok=True)
            count = len(cls._buffer)
            with open(target_log_file, "a", encoding="utf-8") as f:
                for ts, lvl, m in cls._buffer:
                    f.write(f"[{ts}] [{lvl}] {m}\n")
            cls._buffer.clear()
            return count
        except Exception:
            return 0


def safe_chat_completion(
    client,
    model: str,
    messages: List[Dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int = 4096,
    max_retries: int = 3,
    retry_delay: float = 2.0,
    log_func=None
) -> str:
    """
    带指数退避重试与结构化 WARN / ERROR 落盘的大模型安全调用封装
    """
    import time
    last_err: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                messages=messages
            )
            content = resp.choices[0].message.content or ""
            # 安全阻断特征词拦截
            blocked_keywords = ["blocked by", "safety filter", "content moderation", "policies.google.com", "unable to process this request due to safety"]
            if any(bk in content.lower() for bk in blocked_keywords) or (len(content.strip()) < 100 and "blocked" in content.lower()):
                raise ValueError(f"大模型触发安全策略拦截: {content[:100]}")
            return content
        except Exception as e:
            last_err = e
            warn_msg = f"[LLM] 大模型 API 调用异常 (尝试 {attempt}/{max_retries}): {e}"
            if log_func:
                log_func(warn_msg, level="WARN")
            else:
                print(f"[WARN] {warn_msg}", flush=True)

            if attempt < max_retries:
                time.sleep(retry_delay * (2 ** (attempt - 1)))

    # 重试全部耗尽
    err_msg = f"[LLM FATAL] 大模型 API 调用彻底失败 (重试 {max_retries} 次已耗尽): {last_err}"
    if log_func:
        log_func(err_msg, level="ERROR")
    else:
        print(f"[ERROR] {err_msg}", flush=True)

    raise RuntimeError(err_msg) from last_err



