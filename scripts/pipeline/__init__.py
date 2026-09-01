# pipeline package
from .utils import (
    load_active_config,
    get_active_project_dir,
    set_active_project_dir,
    atomic_write,
    count_chinese_chars,
    extract_xml_tag,
    sanitize_vulgar_and_cliches,
    check_ai_cliches,
    check_anti_hardcoding_guard,
    configure_sqlite_resilience,
    apply_surgical_micro_patch,
)
from .prompt_loader import load_prompt
from .guards import validate_and_heal_core_triplet, post_chapter_triplet_audit_and_heal
from .context_builder import load_chapter_outline, extract_chapter_title, build_novel_settings
from .context_analyzer import get_retention_strategy, detect_dormant_foreshadowing, detect_ending_pattern, detect_monologue_ending_streak
from .jit_buffer import ensure_jit_sliding_outline_buffer
from storage.state_manager import read_state_file, write_state_file, compact_state_snapshot

__all__ = [
    "load_active_config",
    "get_active_project_dir",
    "set_active_project_dir",
    "atomic_write",
    "count_chinese_chars",
    "extract_xml_tag",
    "sanitize_vulgar_and_cliches",
    "check_ai_cliches",
    "check_anti_hardcoding_guard",
    "configure_sqlite_resilience",
    "apply_surgical_micro_patch",
    "load_prompt",
    "validate_and_heal_core_triplet",
    "post_chapter_triplet_audit_and_heal",
    "load_chapter_outline",
    "extract_chapter_title",
    "build_novel_settings",
    "get_retention_strategy",
    "detect_dormant_foreshadowing",
    "detect_ending_pattern",
    "detect_monologue_ending_streak",
    "ensure_jit_sliding_outline_buffer",
    "read_state_file",
    "write_state_file",
    "compact_state_snapshot",
]
