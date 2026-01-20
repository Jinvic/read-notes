#!/usr/bin/env python3
"""
将Hugo格式的笔记转换为MkDocs格式（忽略Front Matter）
index.md只包含：书名、目录、书名到第一章之前的内容
"""

import os
import sys
import json
import re
import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import click

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def load_metadata(src_md_file: Path) -> Optional[Dict]:
    """加载笔记的元数据"""
    meta_file = src_md_file.parent / f"{src_md_file.name}.meta.json"
    if meta_file.exists():
        try:
            with open(meta_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.warning(f"无法解析元数据文件 {meta_file}: {e}")
    return None

def sanitize_for_filename(text: str) -> str:
    """清理文本，使其适合作为文件名"""
    # 移除特殊字符
    text = re.sub(r'[《》【】()（）<>:"/\\|?*]', '', text)
    # 替换空格和标点
    text = re.sub(r'[\s,，。\.、;；:：!！?？]+', '-', text)
    # 移除首尾的连字符
    text = text.strip('-')
    # 限制长度
    if len(text) > 50:
        text = text[:50]
    return text

def remove_frontmatter(content: str) -> str:
    """移除Front Matter，只保留正文"""
    lines = content.split('\n')
    
    # 检查是否有Front Matter (以---开头和结尾)
    if len(lines) >= 3 and lines[0] == '---':
        for i in range(1, len(lines)):
            if lines[i] == '---':
                # 找到结束标记，返回之后的内容
                return '\n'.join(lines[i+1:]).strip()
    
    # 没有Front Matter，返回原内容
    return content.strip()

def extract_title_and_content(content: str) -> Tuple[str, str]:
    """从内容中提取标题和剩余内容"""
    lines = content.split('\n')
    title = ""
    remaining_lines = []
    
    for line in lines:
        # 查找一级标题 (# 标题)
        if line.startswith('# ') and not title:
            title = line[2:].strip()
            continue  # 不添加到剩余内容
        # 查找其他格式的标题
        elif re.match(r'^#+\s+.+$', line) and not title:
            # 取第一个标题作为书名
            title = re.sub(r'^#+\s+', '', line).strip()
            continue
        else:
            remaining_lines.append(line)
    
    # 如果没有找到标题，使用默认值
    if not title:
        title = "未命名笔记"
        logger.warning("未找到标题，使用默认值")
    
    return title, '\n'.join(remaining_lines).strip()

def split_content_by_h2(content: str) -> Tuple[str, List[Tuple[str, str]]]:
    """
    将内容拆分为：书名到第一章之前的内容 + 章节列表
    
    返回: (before_first_chapter, [(章节标题, 章节内容), ...])
    """
    lines = content.split('\n')
    
    # 找到第一个二级标题的位置
    first_h2_index = -1
    for i, line in enumerate(lines):
        if line.startswith('## '):
            first_h2_index = i
            break
    
    # 如果没有二级标题
    if first_h2_index == -1:
        # 整个内容作为"before_first_chapter"，没有章节
        return content.strip(), []
    
    # 拆分内容
    before_first_chapter = '\n'.join(lines[:first_h2_index]).strip()
    
    # 提取所有章节
    sections = []
    current_section_title = ""
    current_section_lines = []
    
    for i in range(first_h2_index, len(lines)):
        line = lines[i]
        
        if line.startswith('## '):
            # 如果是新的章节开始
            if current_section_title:  # 保存上一个章节
                section_content = '\n'.join(current_section_lines).strip()
                sections.append((current_section_title, section_content))
                current_section_lines = []
            
            # 开始新章节
            current_section_title = line[3:].strip()
        else:
            current_section_lines.append(line)
    
    # 添加最后一个章节
    if current_section_title:
        section_content = '\n'.join(current_section_lines).strip()
        sections.append((current_section_title, section_content))
    
    return before_first_chapter, sections

def convert_image_links(content: str, note_clean_name: str, image_base: str) -> str:
    """转换图片链接路径"""
    # 定义图片扩展名
    image_extensions = r'\.(png|jpg|jpeg|gif|svg|webp|bmp)'
    
    # 模式1: ![alt](/post-images/笔记名/图片名.扩展名)
    pattern1 = rf'!\[(.*?)\]\(\s*/post-images/[^/]+/([^)\s]+{image_extensions})\s*\)'
    replacement1 = rf'![\1]({image_base}/{note_clean_name}/\2)'
    content = re.sub(pattern1, replacement1, content, flags=re.IGNORECASE)
    
    # 模式2: ![alt](../static/post-images/笔记名/图片名.扩展名)
    pattern2 = rf'!\[(.*?)\]\(\s*(\.\./)*static/post-images/[^/]+/([^)\s]+{image_extensions})\s*\)'
    replacement2 = rf'![\1]({image_base}/{note_clean_name}/\3)'
    content = re.sub(pattern2, replacement2, content, flags=re.IGNORECASE)
    
    # 模式3: 处理已经在本地的图片（src/images/...）
    pattern3 = rf'!\[(.*?)\]\(\s*\.?/?images/[^/]+/([^)\s]+{image_extensions})\s*\)'
    replacement3 = rf'![\1]({image_base}/{note_clean_name}/\2)'
    content = re.sub(pattern3, replacement3, content, flags=re.IGNORECASE)
    
    # 模式4: 处理常见的Hugo图片路径
    pattern4 = rf'!\[(.*?)\]\(\s*([^)]*post-images[^/]+/[^)\s]+{image_extensions})\s*\)'
    def replace_func4(match):
        alt = match.group(1)
        img_path = match.group(2)
        img_name = os.path.basename(img_path)
        return f'![{alt}]({image_base}/{note_clean_name}/{img_name})'
    
    content = re.sub(pattern4, replace_func4, content, flags=re.IGNORECASE)
    
    return content

def create_mkdocs_frontmatter(title: str) -> str:
    """创建简单的MkDocs格式的Front Matter"""
    return f"""---
title: {title}
---

"""

def convert_single_note(src_md_file: Path, output_base_dir: Path, 
                       note_clean_name: str, image_base: str) -> int:
    """转换单篇笔记，返回生成的章节数"""
    
    # 加载元数据
    metadata = load_metadata(src_md_file)
    
    # 读取Markdown文件
    try:
        with open(src_md_file, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        # 尝试其他编码
        try:
            with open(src_md_file, 'r', encoding='gbk') as f:
                content = f.read()
        except:
            logger.error(f"无法读取文件编码: {src_md_file}")
            return 0
    
    # 1. 移除Front Matter
    content_no_fm = remove_frontmatter(content)
    
    # 2. 提取标题
    title, remaining_content = extract_title_and_content(content_no_fm)
    
    # 3. 转换图片链接
    content_converted = convert_image_links(remaining_content, note_clean_name, image_base)
    
    # 4. 拆分内容：书名到第一章之前的内容 + 章节列表
    before_first_chapter, sections = split_content_by_h2(content_converted)
    
    # 5. 创建输出目录
    output_dir = output_base_dir / note_clean_name
    output_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"📖 转换: {src_md_file.name}")
    logger.info(f"  标题: {title}")
    logger.info(f"  章节数: {len(sections)}")
    logger.info(f"  输出到: {note_clean_name}/")
    
    # 6. 生成index.md（书名 + 目录 + 书名到第一章之前的内容）
    index_content = create_mkdocs_frontmatter(title)
    index_content += f"# {title}\n\n"
    
    # 添加书名到第一章之前的内容
    if before_first_chapter:
        index_content += before_first_chapter + "\n\n"
    
    # 生成目录（如果有章节）
    if sections:
        index_content += "## 目录\n\n"
        for i, (section_title, _) in enumerate(sections):
            chapter_filename = f"chapter-{i+1:02d}.md"
            index_content += f"{i+1}. [{section_title}]({chapter_filename})\n"
        index_content += "\n"
        
        # 添加"开始阅读"链接
        if sections:
            index_content += f"> 开始阅读：[{sections[0][0]}](chapter-01.md)\n\n"
    
    # 写入index.md
    index_file = output_dir / "index.md"
    with open(index_file, 'w', encoding='utf-8') as f:
        f.write(index_content)
    
    # 7. 生成章节文件
    for i, (section_title, section_content) in enumerate(sections):
        chapter_num = i + 1
        chapter_filename = f"chapter-{chapter_num:02d}.md"
        chapter_file = output_dir / chapter_filename
        
        # 章节内容
        chapter_content = create_mkdocs_frontmatter(f"{title} - {section_title}")
        chapter_content += f"# {section_title}\n\n{section_content}\n"
        
        # 添加导航链接
        chapter_content += "\n\n---\n\n"
        
        # 构建导航链接
        nav_links = []
        
        # 上一页链接
        if chapter_num == 1:
            nav_links.append("[← 返回目录](index.md)")
        else:
            nav_links.append(f"[← 上一章](chapter-{chapter_num-1:02d}.md)")
        
        # 目录链接
        nav_links.append("[目录](index.md)")
        
        # 下一页链接
        if chapter_num < len(sections):
            nav_links.append(f"[下一章 →](chapter-{chapter_num+1:02d}.md)")
        
        chapter_content += " | ".join(nav_links)
        
        with open(chapter_file, 'w', encoding='utf-8') as f:
            f.write(chapter_content)
        
        logger.debug(f"  生成章节: {chapter_filename} - {section_title}")
    
    total_files = 1 + len(sections)  # index.md + 章节文件
    logger.info(f"  ✅ 生成 {total_files} 个文件 (index.md + {len(sections)}章节)")
    
    return len(sections)

@click.command()
@click.option('--src-dir', default='./src', help='源文件目录（Hugo格式）')
@click.option('--output-dir', default='./docs/reading-notes', help='输出目录（MkDocs格式）')
@click.option('--image-base', default='../assets/images', help='图片基础路径')
@click.option('--log-level', default='INFO', help='日志级别')
def main(src_dir: str, output_dir: str, image_base: str, log_level: str):
    """主函数：转换Hugo笔记为MkDocs格式"""
    
    # 设置日志级别
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f'无效的日志级别: {log_level}')
    logging.getLogger().setLevel(numeric_level)
    
    # 转换路径
    src_dir_path = Path(src_dir).resolve()
    output_dir_path = Path(output_dir).resolve()
    
    # 验证源目录
    if not src_dir_path.exists():
        logger.error(f"源目录不存在: {src_dir_path}")
        sys.exit(1)
    
    # 清理输出目录
    if output_dir_path.exists():
        logger.info(f"清理旧的输出目录: {output_dir_path}")
        shutil.rmtree(output_dir_path)
    
    # 创建输出目录
    output_dir_path.mkdir(parents=True, exist_ok=True)
    
    # 查找所有Markdown文件
    md_files = list(src_dir_path.glob("*.md"))
    if not md_files:
        logger.error(f"未找到Markdown文件: {src_dir_path}")
        sys.exit(1)
    
    logger.info(f"📋 开始转换 {len(md_files)} 篇笔记")
    logger.info(f"源目录: {src_dir_path}")
    logger.info(f"输出目录: {output_dir_path}")
    
    total_sections = 0
    success_count = 0
    
    for md_file in md_files:
        logger.info(f"--- 处理: {md_file.name} ---")
        
        try:
            # 获取笔记的clean name
            metadata = load_metadata(md_file)
            if metadata and 'clean_name' in metadata:
                note_clean_name = metadata['clean_name']
            elif metadata and 'target_dir' in metadata:
                note_clean_name = metadata['target_dir']
            else:
                # 从文件名生成clean name
                note_name = md_file.stem
                note_clean_name = sanitize_for_filename(note_name)
            
            logger.debug(f"笔记clean name: {note_clean_name}")
            
            # 转换单篇笔记
            sections_count = convert_single_note(
                md_file, output_dir_path, note_clean_name, image_base
            )
            
            if sections_count >= 0:
                total_sections += sections_count
                success_count += 1
                logger.info(f"✅ 完成: {md_file.name} -> {note_clean_name}/ ({sections_count}章节)")
            else:
                logger.warning(f"⚠️  转换异常: {md_file.name}")
            
        except Exception as e:
            logger.error(f"❌ 转换失败 {md_file.name}: {e}", exc_info=True)
    
    # 生成汇总报告
    logger.info(f"🎉 转换完成总结")
    logger.info(f"   成功转换: {success_count}/{len(md_files)} 篇笔记")
    logger.info(f"   生成章节: {total_sections} 个")
    logger.info(f"   输出目录: {output_dir_path}")
    
    # 显示生成的目录结构
    if output_dir_path.exists():
        logger.info(f"📂 生成的目录结构:")
        for item in sorted(output_dir_path.iterdir()):
            if item.is_dir():
                md_files_in_dir = list(item.glob("*.md"))
                if md_files_in_dir:
                    logger.info(f"  📁 {item.name}/ ({len(md_files_in_dir)}个文件)")
                    # 显示文件详情
                    for md in sorted(md_files_in_dir):
                        size = md.stat().st_size
                        if md.name == "index.md":
                            logger.info(f"    📄 {md.name} (目录页, {size} bytes)")
                        else:
                            # 读取文件第一行获取章节标题
                            try:
                                with open(md, 'r', encoding='utf-8') as f:
                                    first_line = f.readline().strip()
                                    if first_line.startswith('# '):
                                        chapter_title = first_line[2:].strip()
                                        logger.info(f"    📄 {md.name} - {chapter_title} ({size} bytes)")
                                    else:
                                        logger.info(f"    📄 {md.name} ({size} bytes)")
                            except:
                                logger.info(f"    📄 {md.name} ({size} bytes)")
    
    if success_count < len(md_files):
        logger.warning(f"⚠️  有 {len(md_files) - success_count} 篇笔记转换失败")
        sys.exit(1)

if __name__ == '__main__':
    main()