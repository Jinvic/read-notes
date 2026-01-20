# 读书笔记

这个项目用于将Hugo博客中的读书笔记同步到MkDocs文档站。

由于同步逻辑没有很细化，可能存在一些引用/格式问题。推荐阅读[源站](https://blog.jinvic.top/categories/%E7%AC%94%E8%AE%B0/)。

## 工作流程

1. Hugo仓库更新读书笔记
2. 自动同步到本仓库的src目录
3. 转换为MkDocs格式到docs目录
4. 部署到GitHub Pages

## 目录结构

- `src/` - 从Hugo同步的原始文件
- `docs/` - MkDocs格式的笔记
- `scripts/` - 同步和转换脚本
- `.github/workflows/` - GitHub Actions工作流

## 使用

```bash
# 安装依赖
pip install -r requirements.txt

# 格式转换
python scripts/hugo_to_mkdocs.py \
    --src-dir ./src \
    --output-dir ./docs \
    --image-base ../assets/images \
    --log-level INFO
python scripts/copy_images.py
python scripts/copy_readme.py

# 本地预览
mkdocs serve
```
