import os, sys
SCRIPTS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, SCRIPTS_ROOT)
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LangGraph Time Travel (时间旅行/剧情回滚工具) 命令行入口
用法:
  1. 查看所有历史检查点:
     python3 rollback.py list
  2. 回滚至指定章节:
     python3 rollback.py to <章节号>  (例如: python3 rollback.py to 30)
  3. 创建平行剧情分支:
     python3 rollback.py branch <章节号> <分支名>  (例如: python3 rollback.py branch 30 dark_ending)
"""

import sys, os
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from storage.checkpoints import list_checkpoints, rollback_to, branch_from

def main():
    if len(sys.argv) < 2:
        print("=" * 65)
        print("       ⌛ LangGraph Time Travel (小说时间旅行管理器)")
        print("=" * 65)
        print("命令格式:")
        print("  python3 rollback.py list                 # 列出所有可回滚的检查点")
        print("  python3 rollback.py to <章节号>          # 一键时光倒流回滚至该章")
        print("  python3 rollback.py branch <章号> <分支> # 基于某章创建平行宇宙分支")
        print("=" * 65)
        return

    cmd = sys.argv[1].lower()

    if cmd in ("list", "ls", "status"):
        cps = list_checkpoints()
        print("=" * 65)
        print(f"       ⌛ 历史检查点清单 (共 {len(cps)} 个快照)")
        print("=" * 65)
        if not cps:
            print("暂无已保存的检查点。")
            return
        for cp in cps:
            cnum = cp.get("chapter_num", 0)
            tstr = cp.get("timestamp", "")
            wc = cp.get("word_count", 0)
            branch = cp.get("branch", "main")
            print(f"  [Checkpoint #{cnum:03d}] | 汉字: {wc:4d} 字 | 时间: {tstr} | 分支: {branch}")
        print("=" * 65)

    elif cmd == "to":
        if len(sys.argv) < 3:
            print("❌ 错误：请指定要回滚的目标章节号！例如: python3 rollback.py to 20")
            return
        try:
            target_ch = int(sys.argv[2])
        except ValueError:
            print("❌ 错误：章节号必须为数字！")
            return

        print(f"⏳ 正在执行时间旅行回滚至 第 {target_ch} 章...")
        res = rollback_to(target_ch)
        print("=" * 65)
        print("🎉 【时间旅行成功】已精准回退至指定历史节点！")
        print("=" * 65)
        print(f"  - 目标章节: 第 {res['target_chapter']} 章 (已保留)")
        print(f"  - 下次启动: 将精准从 第 {res['next_chapter']} 章 开始生成")
        print(f"  - 归档移除: 第 {res['removed_chapters']} 章")
        print(f"  - 安全备份: {res['backup_dir']}")
        print(f"  - 状态同步: {res['restored_state_file']} 已恢复为第 {target_ch} 章结束时状态")
        print("=" * 65)

    elif cmd == "branch":
        if len(sys.argv) < 4:
            print("❌ 错误：请指定源章节号和分支名！例如: python3 rollback.py branch 30 dark_path")
            return
        src_ch = int(sys.argv[2])
        bname = sys.argv[3]
        print(f"🌱 正在从第 {src_ch} 章派生新分支 [{bname}]...")
        res = branch_from(src_ch, bname)
        print("=" * 65)
        print(f"🎉 【分支创建成功】平行宇宙已开启！")
        print("=" * 65)
        print(f"  - 分支名称: {res['branch_name']}")
        print(f"  - 起始源章: 第 {res['source_chapter']} 章")
        print(f"  - 分支目录: {res['branch_dir']}")
        print(f"  - 包含章节: 1 ~ {res['source_chapter']} 章")
        print("=" * 65)

    else:
        print(f"❌ 未知命令: {cmd}")

if __name__ == "__main__":
    main()
