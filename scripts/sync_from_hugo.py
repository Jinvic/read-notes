#!/usr/bin/env python3
"""
从Hugo仓库同步笔记和图片到MkDocs仓库
"""

import os
import sys
import json
import shutil
import logging
from pathlib import Path
from typing import Dict, List, Optional
import click

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def sanitize_filename(filename: str) -> str:
    """清理文件名中的特殊字符"""
    import re
    # 替换中文括号和特殊字符
    filename = filename.replace('《', '').replace('》', '')
    filename = filename.replace('(', '-').replace(')', '-')
    filename = re.sub(r'[<>:"/\\|?*]', '-', filename)
    filename = re.sub(r'\s+', '-', filename)  # 空格转连字符
    filename = filename.strip('-')
    return filename

def copy_markdown_file(src_path: Path, dst_path: Path) -> None:
    """复制Markdown文件"""
    if not src_path.exists():
        logger.error(f"源文件不存在: {src_path}")
        return
    
    # 确保目标目录存在
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 复制文件
    shutil.copy2(src_path, dst_path)
    logger.info(f"📄 复制Markdown文件: {src_path} -> {dst_path}")

def copy_image_directory(src_dir: Path, dst_dir: Path, note_name: str) -> None:
    """复制图片目录"""
    if not src_dir.exists():
        logger.warning(f"图片目录不存在: {src_dir}")
        return
    
    # 清理笔记名称用于目录名
    clean_note_name = sanitize_filename(note_name)
    
    # 目标目录：docs/assets/images/{clean_note_name}/
    target_dir = dst_dir / clean_note_name
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # 复制所有图片文件
    image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp'}
    copied_count = 0
    
    for root, _, files in os.walk(src_dir):
        for file in files:
            if Path(file).suffix.lower() in image_extensions:
                src_file = Path(root) / file
                dst_file = target_dir / file
                
                # 确保不覆盖同名文件（如果有冲突，添加前缀）
                counter = 1
                original_dst = dst_file
                while dst_file.exists():
                    stem = original_dst.stem
                    suffix = original_dst.suffix
                    dst_file = original_dst.parent / f"{stem}_{counter}{suffix}"
                    counter += 1
                
                shutil.copy2(src_file, dst_file)
                copied_count += 1
                logger.debug(f"  复制图片: {src_file.name} -> {dst_file}")
    
    if copied_count > 0:
        logger.info(f"🖼️  复制了 {copied_count} 个图片到: {target_dir}")
    else:
        logger.warning(f"⚠️  图片目录为空: {src_dir}")

def sync_note(note_config: Dict, hugo_dir: Path, src_dir: Path, docs_dir: Path, skip_conversion: bool = False):
    """同步单篇笔记"""
    try:
        # 获取笔记信息
        source_path = hugo_dir / note_config['source']
        note_filename = Path(note_config['source']).name
        note_name = Path(note_filename).stem  # 不含扩展名
        
        # 确定目标文件名
        if 'target_dir' in note_config:
            target_dir_name = note_config['target_dir']
        else:
            target_dir_name = sanitize_filename(note_name)
        
        # 1. 复制Markdown文件到src目录
        src_target = src_dir / note_filename
        copy_markdown_file(source_path, src_target)
        
        # 2. 复制图片到docs/assets/images/
        # 如果不跳过转换，则复制图片到docs目录
        if not skip_conversion:
            image_base_dir = docs_dir / "assets" / "images"
            for img_dir in note_config.get('images', []):
                img_source = hugo_dir / img_dir
                copy_image_directory(img_source, image_base_dir, note_name)
        else:
            logger.info(f"跳过图片复制（仅同步模式）")
        
        # 记录元数据供后续转换使用
        metadata = {
            'source': note_config['source'],
            'src_file': str(src_target.relative_to(src_dir)),
            'note_name': note_name,
            'clean_name': target_dir_name,
            'images_copied': True
        }
        
        # 保存元数据
        metadata_file = src_dir / f"{note_filename}.meta.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
            
        logger.info(f"✅ 同步完成: {note_name}")
        
    except Exception as e:
        logger.error(f"❌ 同步失败 {note_config.get('source', 'unknown')}: {e}")
        raise

@click.command()
@click.option('--hugo-dir', required=True, help='Hugo仓库本地路径')
@click.option('--config', required=True, help='同步配置JSON文件路径')
@click.option('--src-dir', default='./src', help='源文件目录（存放原始Markdown）')
@click.option('--docs-dir', default='./docs', help='输出目录（MkDocs docs目录）')
@click.option('--skip-conversion', is_flag=True, help='跳过转换步骤，只同步原始文件')
@click.option('--log-level', default='INFO', help='日志级别')
def main(hugo_dir: str, config: str, src_dir: str, docs_dir: str, skip_conversion: bool, log_level: str):
    """主函数"""
    # 设置日志级别
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # 转换路径
    hugo_dir_path = Path(hugo_dir).resolve()
    config_path = Path(config).resolve()
    src_dir_path = Path(src_dir).resolve()
    docs_dir_path = Path(docs_dir).resolve()
    
    # 验证路径
    if not hugo_dir_path.exists():
        logger.error(f"Hugo目录不存在: {hugo_dir_path}")
        sys.exit(1)
    
    if not config_path.exists():
        logger.error(f"配置文件不存在: {config_path}")
        sys.exit(1)
    
    # 加载配置
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            notes_config = json.load(f)
        
        if not isinstance(notes_config, list):
            logger.error("配置文件格式错误：应为JSON数组")
            sys.exit(1)
            
    except json.JSONDecodeError as e:
        logger.error(f"JSON解析错误: {e}")
        sys.exit(1)
    
    logger.info(f"📋 开始同步 {len(notes_config)} 篇笔记")
    
    # 清理旧的src目录（可选）
    if src_dir_path.exists():
        logger.info(f"清理旧的src目录: {src_dir_path}")
        shutil.rmtree(src_dir_path)
    
    # 创建目录
    src_dir_path.mkdir(parents=True, exist_ok=True)
    (docs_dir_path / "assets" / "images").mkdir(parents=True, exist_ok=True)
    
    # 同步每篇笔记
    success_count = 0
    for i, note_config in enumerate(notes_config, 1):
        logger.info(f"--- 处理第 {i}/{len(notes_config)} 篇 ---")
        try:
            sync_note(note_config, hugo_dir_path, src_dir_path, docs_dir_path, skip_conversion)
            success_count += 1
        except Exception as e:
            logger.error(f"处理失败: {e}")
            # 继续处理其他笔记
    
    logger.info(f"🎉 同步完成：成功 {success_count}/{len(notes_config)} 篇")
    
    # 生成汇总报告
    report = {
        'total': len(notes_config),
        'success': success_count,
        'failed': len(notes_config) - success_count,
        'timestamp': datetime.now().isoformat()
    }
    
    report_file = docs_dir_path / "sync-report.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    
    if success_count < len(notes_config):
        logger.warning(f"⚠️  有 {len(notes_config) - success_count} 篇笔记同步失败")
        sys.exit(1)

if __name__ == '__main__':
    from datetime import datetime
    main()