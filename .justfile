set shell := ["powershell.exe", "-c"]

process:
    python scripts/hugo_to_mkdocs.py \
        --src-dir ./src \
        --output-dir ./docs \
        --image-base ../assets/images \
        --log-level INFO

    python scripts/copy_images.py
    python scripts/copy_readme.py

serve:
    mkdocs serve

build:
    mkdocs build