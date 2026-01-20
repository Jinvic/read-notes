#!/usr/bin/env python3
# scripts/copy_images.py
import shutil
from pathlib import Path

def copy_images():
    src_images = Path("src/images")
    dst_images = Path("docs/assets/images")
    
    if src_images.exists():
        # 确保目标目录存在
        dst_images.mkdir(parents=True, exist_ok=True)
        
        # 复制所有图片
        for item in src_images.rglob("*"):
            if item.is_file() and item.suffix.lower() in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp']:
                # 保持目录结构
                relative_path = item.relative_to(src_images)
                dst_path = dst_images / relative_path
                
                # 确保目标目录存在
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                
                # 复制文件
                shutil.copy2(item, dst_path)
                print(f"复制: {relative_path}")
        
        print("✅ 图片复制完成")
    else:
        print("⚠️  源图片目录不存在")

if __name__ == "__main__":
    copy_images()