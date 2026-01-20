#!/usr/bin/env python3
"""
复制README.md到docs目录
"""

import shutil
from pathlib import Path

def main():
    # 源文件和目标文件路径
    src = Path("readme.md")
    dst = Path("docs/index.md")
    
    # 检查源文件是否存在
    if not src.exists():
        print(f"❌ 源文件不存在: {src}")
        return
    
    # 确保目标目录存在
    dst.parent.mkdir(parents=True, exist_ok=True)
    
    # 复制文件
    try:
        shutil.copy2(src, dst)
        print(f"✅ 已复制: {src} -> {dst}")
    except Exception as e:
        print(f"❌ 复制失败: {e}")

if __name__ == "__main__":
    main()