#!/usr/bin/env python3
"""
从Hugo仓库同步笔记和图片到MkDocs仓库的src目录
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
    logger.info(f"📄 复制Markdown文件: {src_path.name} -> {dst_path}")

def copy_images_to_src(img_source: Path, dst_base_dir: Path, note_name: str) -> int:
    """复制图片到src/images/目录，返回复制的图片数量"""
    if not img_source.exists():
        logger.warning(f"图片目录不存在: {img_source}")
        return 0
    
    # 清理笔记名称用于目录名
    # clean_note_name = sanitize_filename(note_name)
    
    # 目标目录：src/images/{note_name}/
    target_dir = dst_base_dir / "images" / note_name
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # 支持的图片格式
    image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp'}
    copied_count = 0
    
    try:
        # 遍历源目录
        for root, _, files in os.walk(img_source):
            for file in files:
                file_path = Path(root) / file
                
                # 检查是否为图片文件
                if file_path.suffix.lower() in image_extensions:
                    # 目标文件路径
                    dst_file = target_dir / file
                    
                    # 避免文件名冲突
                    counter = 1
                    original_dst = dst_file
                    while dst_file.exists():
                        stem = original_dst.stem
                        suffix = original_dst.suffix
                        dst_file = original_dst.parent / f"{stem}_{counter}{suffix}"
                        counter += 1
                    
                    # 复制文件
                    shutil.copy2(file_path, dst_file)
                    copied_count += 1
                    
                    logger.debug(f"  复制图片: {file} -> {dst_file.relative_to(dst_base_dir)}")
        
        if copied_count > 0:
            logger.info(f"🖼️  复制了 {copied_count} 个图片到: {target_dir.relative_to(dst_base_dir.parent)}")
        else:
            logger.warning(f"⚠️  图片目录为空: {img_source}")
            
    except Exception as e:
        logger.error(f"❌ 复制图片时出错: {e}")
    
    return copied_count

def sync_note(note_config: Dict, hugo_dir: Path, src_dir: Path) -> Dict:
    """同步单篇笔记到src目录"""
    result = {
        'note_copied': False,
        'images_copied': 0,
        'error': None
    }
    
    try:
        # 获取笔记信息
        source_path = hugo_dir / note_config['source']
        note_filename = Path(note_config['source']).name
        note_name = Path(note_filename).stem  # 不含扩展名
        
        # 1. 复制Markdown文件到src目录
        src_target = src_dir / note_filename
        copy_markdown_file(source_path, src_target)
        result['note_copied'] = True
        
        # 2. 复制图片到src/images/目录
        total_images = 0
        for img_dir in note_config.get('images', []):
            img_source = hugo_dir / img_dir
            copied = copy_images_to_src(img_source, src_dir, note_name)
            total_images += copied
        
        result['images_copied'] = total_images
        
        # 3. 保存元数据
        metadata = {
            'source': str(note_config['source']),
            'note_name': note_name,
            'images_copied': total_images,
            'images_dirs': note_config.get('images', []),
            'sync_timestamp': Path(__file__).stat().st_mtime
        }
        
        # 添加target_dir如果有的话
        if 'target_dir' in note_config:
            metadata['target_dir'] = note_config['target_dir']
        
        metadata_file = src_dir / f"{note_filename}.meta.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ 同步完成: {note_name} (图片: {total_images}个)")
        
    except Exception as e:
        logger.error(f"❌ 同步失败 {note_config.get('source', 'unknown')}: {e}")
        result['error'] = str(e)
    
    return result

@click.command()
@click.option('--hugo-dir', required=True, help='Hugo仓库本地路径')
@click.option('--config', required=True, help='同步配置JSON文件路径')
@click.option('--src-dir', default='./src', help='源文件目录（存放原始Markdown和图片）')
@click.option('--log-level', default='INFO', help='日志级别')
def main(hugo_dir: str, config: str, src_dir: str, log_level: str):
    """主函数：从Hugo同步笔记和图片到src目录"""
    # 设置日志级别
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # 转换路径
    hugo_dir_path = Path(hugo_dir).resolve()
    config_path = Path(config).resolve()
    src_dir_path = Path(src_dir).resolve()
    
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
    
    # 清理旧的src目录
    if src_dir_path.exists():
        logger.info(f"清理旧的src目录: {src_dir_path}")
        shutil.rmtree(src_dir_path)
    
    # 创建目录
    src_dir_path.mkdir(parents=True, exist_ok=True)
    (src_dir_path / "images").mkdir(parents=True, exist_ok=True)
    
    # 同步每篇笔记
    results = []
    total_images = 0
    
    for i, note_config in enumerate(notes_config, 1):
        logger.info(f"--- 处理第 {i}/{len(notes_config)} 篇 ---")
        try:
            result = sync_note(note_config, hugo_dir_path, src_dir_path)
            results.append(result)
            
            if result['error']:
                logger.error(f"处理失败: {result['error']}")
            else:
                total_images += result['images_copied']
                
        except Exception as e:
            logger.error(f"处理过程异常: {e}")
            results.append({'note_copied': False, 'images_copied': 0, 'error': str(e)})
    
    # 生成汇总报告
    success_count = sum(1 for r in results if r['note_copied'] and not r['error'])
    
    logger.info(f"🎉 同步完成总结")
    logger.info(f"   成功同步笔记: {success_count}/{len(notes_config)}")
    logger.info(f"   总共复制图片: {total_images}个")
    
    # 保存详细报告
    report = {
        'total_notes': len(notes_config),
        'success_notes': success_count,
        'total_images': total_images,
        'results': results,
        'src_dir': str(src_dir_path)
    }
    
    report_file = src_dir_path.parent / "sync-report.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    logger.info(f"📊 详细报告已保存: {report_file}")
    
    # 如果有失败的情况，退出码为1
    if success_count < len(notes_config):
        logger.warning(f"⚠️  有 {len(notes_config) - success_count} 篇笔记同步失败")
        sys.exit(1)

if __name__ == '__main__':
    main()