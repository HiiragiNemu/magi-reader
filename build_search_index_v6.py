# build_search_index_v6.py
import os
import json
import re
import hashlib

TARGET_PUBLIC_DIR = "website/public"
OUTPUT_FILE = os.path.join(TARGET_PUBLIC_DIR, "search_content.json")
DATA_DIR = os.path.join(TARGET_PUBLIC_DIR, "data")

TITLES = {}
titles_path = "titles.json"
if os.path.exists(titles_path):
    with open(titles_path, 'r', encoding='utf-8-sig') as f:
        TITLES = json.load(f)
    print(f"✅ 加载标题映射: {len(TITLES)} 条标题")

S0_PREFIX = "@S0\t"


def strip_lang_suffix_filename(file_name):
    stem = file_name
    if stem.endswith(".txt"):
        stem = stem[:-4]
    stem = re.sub(r"_(cn|jp)$", "", stem, flags=re.I)
    return stem


def safe_scene0_story_id(category, folder_name, file_stem):
    basis = f"{category}/{folder_name}/{file_stem}"
    digest = hashlib.sha1(basis.encode("utf-8")).hexdigest()[:8]
    clean_stem = re.sub(r"[^0-9A-Za-z_.-]+", "-", file_stem).strip("-") or "scene0"
    return f"{category}_{clean_stem}_{digest}"


def make_search_story_id(root, file_name):
    rel = os.path.relpath(root, DATA_DIR).replace("\\", "/")
    parts = rel.split("/") if rel != "." else []
    category = parts[0] if len(parts) >= 1 else "Unclassified"
    folder_name = parts[1] if len(parts) >= 2 else ""
    file_stem = strip_lang_suffix_filename(file_name)
    raw_id = file_stem.split('_')[0]

    if category.startswith("scene0_"):
        return safe_scene0_story_id(category, folder_name, file_stem)
    return raw_id


def normalize_scene0_extended_lines(content):
    """@S0\t{json} -> 普通「说话人: 文本」，避免搜索索引混入 JSON 噪声。"""
    normalized_lines = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith(S0_PREFIX):
            try:
                payload = json.loads(stripped[len(S0_PREFIX):])
                speaker = str(payload.get("speaker") or "旁白").strip() or "旁白"
                text = str(payload.get("text") or "").replace("\\n", " ").strip()
                if text:
                    normalized_lines.append(f"{speaker}: {text}")
                continue
            except Exception:
                pass
        normalized_lines.append(line)
    return "\n".join(normalized_lines)


def clean_content_for_search(content):
    content = normalize_scene0_extended_lines(content)
    # 去掉 Section 头
    content = re.sub(r'---.*?---', "", content, flags=re.DOTALL)
    # 去掉颜色标签：<red>text</red> 等
    content = re.sub(r"<(red|blue|yellow|black)>(.*?)</\1>", r"\2", content, flags=re.DOTALL)
    # 兼容旧脚本曾经只写开标签的情况：<red>text -> text
    content = re.sub(r"<(red|blue|yellow|black)>(.*?)", r"\2", content, flags=re.DOTALL)
    # 去掉 textBlack 标签：[textBlack:text] -> text
    content = re.sub(r"\[textBlack:(.*?)\]", r"\1", content, flags=re.DOTALL)
    return re.sub(r"\s+", " ", content).strip()


def main():
    print("正在构建搜索索引 (V6) - Scene0-safe IDs + @S0 清理...")
    search_index = []

    for root, _, files in os.walk(DATA_DIR):
        for file in files:
            if not file.endswith(".txt"):
                continue
            lang = "cn" if "_cn.txt" in file else "jp" if "_jp.txt" in file else None
            if not lang:
                continue

            file_stem = strip_lang_suffix_filename(file)
            raw_id = file_stem.split('_')[0]
            story_id = make_search_story_id(root, file)
            path = os.path.join(root, file)

            with open(path, "r", encoding="utf-8-sig") as f:
                content = clean_content_for_search(f.read())

            title = TITLES.get(file_stem) or TITLES.get(raw_id) or ""
            if title:
                content = f"{title} {content}"
            if content:
                search_index.append({"id": story_id, "c": content, "l": lang})

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(search_index, f, ensure_ascii=False, separators=(',', ':'))

    size_mb = os.path.getsize(OUTPUT_FILE) / 1024 / 1024
    print("✅ 索引构建完成！")
    print(f"  条目数: {len(search_index)}")
    print(f"  文件大小: {size_mb:.2f} MB")
    if size_mb < 30:
        print("⚠️ 注意：文件大小如果远小于 40MB，请先确认 TXT 内容是否已完整生成。")
    else:
        print("🎉 大小正常。")


if __name__ == "__main__":
    main()
