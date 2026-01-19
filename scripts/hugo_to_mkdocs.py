#!/usr/bin/env python3
"""
将Hugo格式的笔记转换为MkDocs格式

主要转换：
1. 拆分一级标题（书名）为目录
2. 拆分二级标题（章节）为单独文件
3. 转换Front Matter格式
4. 更新图片链接路径
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
import frontmatter

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
    return text.lower()

def extract_title_from_content(content: str) -> Tuple[str, str]:
    """从内容中提取标题
    
    返回: (title, remaining_content)
    """
    lines = content.split('\n')
    title = ""
    remaining_lines = []
    
    for line in lines:
        # 查找一级标题 (Hugo通常是 # 标题)
        if line.startswith('# ') and not title:
            title = line[2:].strip()
            # 继续处理，不添加到剩余内容
            continue
        # 查找旧格式标题
        elif re.match(r'^#+\s+.+$', line) and not title:
            title = re.sub(r'^#+\s+', '', line).strip()
            continue
        else:
            remaining_lines.append(line)
    
    # 如果没有找到标题，使用默认值
    if not title:
        title = "未命名笔记"
        logger.warning("未找到标题，使用默认值")
    
    return title, '\n'.join(remaining_lines)

def split_by_h2(content: str) -> List[Tuple[str, str]]:
    """按二级标题拆分内容
    
    返回: [(章节标题, 章节内容), ...]
    """
    sections = []
    
    # 使用正则匹配二级标题
    pattern = r'(^##\s+.+?$)(?=\n##\s+|\Z)'
    
    # 使用多行模式
    matches = list(re.finditer(pattern, content, re.MULTILINE | re.DOTALL))
    
    if not matches:
        # 如果没有二级标题，整个内容作为一个章节
        sections.append(("概述", content))
        return sections
    
    for i, match in enumerate(matches):
        section_content = match.group(0)
        
        # 提取标题
        lines = section_content.split('\n')
        if lines and lines[0].startswith('## '):
            section_title = lines[0][3:].strip()
            # 移除标题行，保留内容
            section_body = '\n'.join(lines[1:]).strip()
        else:
            section_title = f"章节-{i+1}"
            section_body = section_content
        
        sections.append((section_title, section_body))
    
    return sections

def convert_image_links(content: str, note_clean_name: str, image_base: str) -> str:
    """转换图片链接路径
    
    将Hugo格式的图片链接转换为MkDocs格式
    """
    # 处理Hugo格式的图片链接: ![alt](/post-images/笔记名/xxx.png)
    # 转换为: ![alt](/assets/images/clean-note-name/xxx.png)
    
    # 首先处理标准格式
    pattern1 = r'!\[(.*?)\]\(\s*/post-images/[^/]+/([^)\s]+)\s*\)'
    replacement1 = rf'![\1]({image_base}/{note_clean_name}/\2)'
    content = re.sub(pattern1, replacement1, content, flags=re.IGNORECASE)
    
    # 处理可能的不同格式
    pattern2 = r'!\[(.*?)\]\(\s*(\.\./)*static/post-images/[^/]+/([^)\s]+)\s*\)'
    replacement2 = rf'![\1]({image_base}/{note_clean_name}/\3)'
    content = re.sub(pattern2, replacement2, content, flags=re.IGNORECASE)
    
    # 处理相对路径（如果图片在src/images目录）
    pattern3 = r'!\[(.*?)\]\(\s*\.?/?images/[^/]+/([^)\s]+)\s*\)'
    replacement3 = rf'![\1]({image_base}/{note_clean_name}/\2)'
    content = re.sub(pattern3, replacement3, content, flags=re.IGNORECASE)
    
    return content

def create_mkdocs_frontmatter(title: str, original_frontmatter: Dict = None) -> str:
    """创建MkDocs格式的Front Matter"""
    frontmatter_lines = ["---"]
    
    # 添加标题
    frontmatter_lines.append(f"title: {title}")
    
    # 保留一些有用的原数据
    if original_frontmatter:
        # 保留日期（如果有）
        if 'date' in original_frontmatter:
            frontmatter_lines.append(f"date: {original_frontmatter['date']}")
        
        # 保留标签（转换为列表格式）
        if 'tags' in original_frontmatter:
            tags = original_frontmatter['tags']
            if isinstance(tags, list):
                frontmatter_lines.append(f"tags: {tags}")
            else:
                frontmatter_lines.append(f"tags: [{tags}]")
    
    # 添加一些默认值
    frontmatter_lines.append("template: article.html")
    frontmatter_lines.append("---\n")
    
    return '\n'.join(frontmatter_lines)

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
        with open(src_md_file, 'r', encoding='gbk') as f:
            content = f.read()
    
    # 解析Front Matter（如果有）
    original_frontmatter = {}
    try:
        post = frontmatter.loads(content)
        content_without_fm = post.content
        original_frontmatter = post.metadata
    except:
        content_without_fm = content
        logger.warning(f"无法解析Front Matter: {src_md_file.name}")
    
    # 提取标题
    title, remaining_content = extract_title_from_content(content_without_fm)
    
    # 如果没有从内容中找到标题，尝试从Front Matter获取
    if title == "未命名笔记" and 'title' in original_frontmatter:
        title = original_frontmatter['title']
    
    # 转换图片链接
    content_converted = convert_image_links(remaining_content, note_clean_name, image_base)
    
    # 按二级标题拆分内容
    sections = split_by_h2(content_converted)
    
    # 创建输出目录
    output_dir = output_base_dir / note_clean_name
    output_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"📖 转换: {src_md_file.name} -> {note_clean_name}/ ({len(sections)}个章节)")
    
    # 生成索引文件（第一个章节或概述）
    if sections:
        first_section_title, first_section_content = sections[0]
        
        # 创建索引文件
        index_content = create_mkdocs_frontmatter(title, original_frontmatter)
        index_content += f"# {title}\n\n"
        
        # 生成目录
        if len(sections) > 1:
            index_content += "## 目录\n\n"
            for i, (section_title, _) in enumerate(sections):
                section_filename = f"chapter-{i+1:02d}.md" if i > 0 else "index.md"
                index_content += f"{i+1}. [{section_title}]({section_filename})\n"
            index_content += "\n"
        
        # 添加第一个章节的内容
        index_content += first_section_content
        
        # 写入索引文件
        index_file = output_dir / "index.md"
        with open(index_file, 'w', encoding='utf-8') as f:
            f.write(index_content)
        
        # 生成其他章节文件
        for i, (section_title, section_content) in enumerate(sections[1:], 1):
            chapter_filename = f"chapter-{i+1:02d}.md"
            chapter_file = output_dir / chapter_filename
            
            # 章节的Front Matter
            chapter_fm = create_mkdocs_frontmatter(f"{title} - {section_title}", original_frontmatter)
            
            # 章节内容
            chapter_content = f"{chapter_fm}# {section_title}\n\n{section_content}\n"
            
            # 添加返回索引的链接
            chapter_content += f"\n\n---\n\n← [返回目录](index.md)"
            
            with open(chapter_file, 'w', encoding='utf-8') as f:
                f.write(chapter_content)
        
        logger.info(f"  ✅ 生成 {len(sections)} 个文件到 {note_clean_name}/")
    
    return len(sections)

@click.command()
@click.option('--src-dir', default='./src', help='源文件目录（Hugo格式）')
@click.option('--output-dir', default='./docs/reading-notes', help='输出目录（MkDocs格式）')
@click.option('--image-base', default='/assets/images', help='图片基础路径')
@click.option('--log-level', default='INFO', help='日志级别')
def main(src_dir: str, output_dir: str, image_base: str, log_level: str):
    """主函数：转换Hugo笔记为MkDocs格式"""
    
    # 设置日志级别
    logger.setLevel(getattr(logging, log_level.upper()))
    
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
            
            # 转换单篇笔记
            sections_count = convert_single_note(
                md_file, output_dir_path, note_clean_name, image_base
            )
            
            total_sections += sections_count
            success_count += 1
            
            logger.info(f"✅ 完成: {md_file.name} -> {note_clean_name}/ ({sections_count}章节)")
            
        except Exception as e:
            logger.error(f"❌ 转换失败 {md_file.name}: {e}")
    
    # 生成汇总报告
    logger.info(f"🎉 转换完成总结")
    logger.info(f"   成功转换: {success_count}/{len(md_files)} 篇笔记")
    logger.info(f"   生成章节: {total_sections} 个")
    logger.info(f"   输出目录: {output_dir_path}")
    
    # 显示生成的目录结构
    logger.info(f"📂 生成的目录结构:")
    for item in output_dir_path.iterdir():
        if item.is_dir():
            md_files_in_dir = list(item.glob("*.md"))
            logger.info(f"  📁 {item.name}/ ({len(md_files_in_dir)}个文件)")
            for md in md_files_in_dir[:3]:  # 只显示前3个文件
                logger.info(f"    📄 {md.name}")
            if len(md_files_in_dir) > 3:
                logger.info(f"    ... 还有 {len(md_files_in_dir)-3} 个文件")
    
    if success_count < len(md_files):
        logger.warning(f"⚠️  有 {len(md_files) - success_count} 篇笔记转换失败")
        sys.exit(1)

if __name__ == '__main__':
    main()