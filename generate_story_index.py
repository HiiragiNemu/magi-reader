import os
import json
import shutil
import re
import hashlib
import natsort

# === 配置 ===
DIR_JP = "magireco-source-master/Scenarios_full"
DIR_CN = "magireco-translate-data-master/Scenarios_full"
TARGET_PUBLIC_DIR = "website/public"
TARGET_DATA_DIR = os.path.join(TARGET_PUBLIC_DIR, "data")
TITLES_PATH = "titles.json"  # 确保此文件在脚本同级目录

story_map = {}
TITLES = {}

if os.path.exists(TITLES_PATH):
    with open(TITLES_PATH, 'r', encoding='utf-8-sig') as f:
        TITLES = json.load(f)
    print(f"✅ 已加载标题库: {len(TITLES)} 条")


def sanitize_path(p):
    return p.replace("\\", "/")


def decode_hash_u(s):
    """兼容 ZIP/仓库中可能出现的 #U4e3b#U7ebf 形式中文路径。"""
    def repl(m):
        try:
            return chr(int(m.group(1), 16))
        except ValueError:
            return m.group(0)
    return re.sub(r"#U([0-9a-fA-F]{4,6})", repl, s)


def get_category(path):
    decoded_path = decode_hash_u(path).replace("\\", "/")
    lower = decoded_path.lower()
    if "main_story" in lower:
        return "main_story"
    if "event_story" in lower:
        return "event_story"
    if "character_story" in lower:
        return "character_story"
    if "costume_story" in lower:
        return "costume_story"
    if "login_story" in lower:
        return "login_story"
    if "mirror_story" in lower:
        return "mirror_story"
    if "scene0" in lower or "s0" in lower:
        if "支线" in decoded_path or "sub" in lower:
            return "scene0_sub"
        return "scene0_main"
    return "Unclassified"


def strip_lang_suffix_filename(file_name):
    stem = file_name
    if stem.endswith(".txt"):
        stem = stem[:-4]
    stem = re.sub(r"_(cn|jp)$", "", stem, flags=re.I)
    return stem


def safe_scene0_story_id(category, folder_name, file_stem):
    """
    Scene0 主线/支线存在大量相同 raw_id，例如 902101 同时存在于主线和支线。
    旧脚本用 raw_id 做 story_map key，会把这些条目合并/覆盖。

    这里仅对 Scene0 使用稳定唯一 ID；普通剧情仍沿用旧 raw_id，减少影响面。
    ID 必须是 URL 路径安全的 ASCII 字符，因为前端使用 /reader/${story.id}。
    """
    basis = f"{category}/{folder_name}/{file_stem}"
    digest = hashlib.sha1(basis.encode("utf-8")).hexdigest()[:8]
    # file_stem 基本是数字/下划线/横线；再保险清理一次。
    clean_stem = re.sub(r"[^0-9A-Za-z_.-]+", "-", file_stem).strip("-") or "scene0"
    return f"{category}_{clean_stem}_{digest}"


def make_story_key(category, folder_name, file_stem, raw_id):
    if category.startswith("scene0_"):
        return safe_scene0_story_id(category, folder_name, file_stem)
    return raw_id


def extract_sections(filepath):
    """
    稳定提取章节锚点。
    兼容：
    - --- [Section 010] (Source: 901101-010_homura.json) ---
    - ---[Section 020] (Source: 901304-020.json) ---
    - --- [Section 010 - Branch 2] (Source: xxx.json) ---
    """
    headers = []
    if not os.path.exists(filepath):
        return headers

    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            for line in f:
                line = line.strip()
                if not (line.startswith('---') and 'Section' in line):
                    continue

                source_match = re.search(r'\(Source:\s*([^\)]+?)\s*\)', line)
                file_id = ""
                if source_match:
                    file_id = os.path.splitext(source_match.group(1).strip())[0]

                sec_match = re.search(r'Section\s*(\d+)', line, flags=re.I)
                branch_match = re.search(r'(?:Branch|group_)\s*_?\s*(\d+)', line, flags=re.I)
                if not sec_match:
                    continue

                base_sec = f"Section {sec_match.group(1)}"
                if branch_match:
                    base_sec += f" - Branch {branch_match.group(1)}"

                title_part = ""
                if file_id and file_id in TITLES:
                    title_part = f" : {TITLES[file_id]}"

                headers.append(f"{file_id} {base_sec}{title_part}".strip())
    except Exception:
        pass
    return headers


def scan_directory(base_dir, lang_key):
    print(f"--- 扫描 [{lang_key}] ---")
    if not os.path.exists(base_dir):
        print(f"⚠️ 目录不存在，跳过: {base_dir}")
        return

    for root, dirs, files in os.walk(base_dir):
        if "WEBSITE_DATA" in root:
            continue

        for file in files:
            if not file.endswith(".txt"):
                continue

            file_stem = strip_lang_suffix_filename(file)
            raw_id = file_stem.split('_')[0]
            if not raw_id:
                continue

            rel_path = os.path.relpath(root, base_dir)
            category = get_category(rel_path)
            folder_name = os.path.basename(root)
            story_key = make_story_key(category, folder_name, file_stem, raw_id)

            dest_rel = os.path.join(category, folder_name)
            dest_full = os.path.join(TARGET_DATA_DIR, dest_rel)
            os.makedirs(dest_full, exist_ok=True)

            if file.endswith(f"_{lang_key}.txt"):
                dest_filename = file
            else:
                dest_filename = f"{file_stem}_{lang_key}.txt"

            full_src_path = os.path.join(root, file)
            shutil.copy2(full_src_path, os.path.join(dest_full, dest_filename))

            if story_key not in story_map:
                mapped_title = TITLES.get(file_stem) or TITLES.get(raw_id) or ""
                story_map[story_key] = {
                    "id": story_key,
                    "raw_id": raw_id,
                    "file_stem": file_stem,
                    "category": category,
                    "folder": folder_name,
                    "cn_path": "",
                    "jp_path": "",
                    "has_cn": False,
                    "has_jp": False,
                    "sections": [],
                    "title": mapped_title,
                    "filename_cn": "",
                    "filename_jp": "",
                }

            web_path = f"/data/{sanitize_path(dest_rel)}/{dest_filename}"
            current_sections = extract_sections(full_src_path)

            if lang_key == "cn":
                story_map[story_key]["cn_path"] = web_path
                story_map[story_key]["has_cn"] = True
                story_map[story_key]["filename_cn"] = file
                if current_sections:
                    story_map[story_key]["sections"] = current_sections
            else:
                story_map[story_key]["jp_path"] = web_path
                story_map[story_key]["has_jp"] = True
                story_map[story_key]["filename_jp"] = file
                if not story_map[story_key]["sections"] and current_sections:
                    story_map[story_key]["sections"] = current_sections


# === 执行 ===
if os.path.exists(TARGET_DATA_DIR):
    shutil.rmtree(TARGET_DATA_DIR)
os.makedirs(TARGET_DATA_DIR)

scan_directory(DIR_JP, "jp")
scan_directory(DIR_CN, "cn")

final_list = []
for _k, v in story_map.items():
    p = 100 if v["has_cn"] else 0
    final_list.append({
        "id": v["id"],
        "raw_id": v.get("raw_id", v["id"]),
        "file_stem": v.get("file_stem", v["id"]),
        "category": v["category"],
        "folder": v["folder"],
        "percent": p,
        "has_cn": v["has_cn"],
        "has_jp": v["has_jp"],
        "path_cn": v["cn_path"],
        "path_jp": v["jp_path"],
        "title": v["title"],
        "sections": v["sections"],
        "filename_cn": v["filename_cn"],
        "filename_jp": v["filename_jp"],
    })


def custom_sort_key(item):
    # Scene0 的 id 带 hash，因此排序用 file_stem/raw_id；普通剧情保持旧逻辑。
    id_val = item.get("file_stem") or item.get("raw_id") or item["id"]
    match = re.match(r'^(\d+)', id_val)
    num = int(match.group(1)) if match else 0

    if id_val.startswith('51701'):
        return (item.get("category", ""), num + 100000, id_val)
    return (item.get("category", ""), num, id_val)


final_list = natsort.natsorted(final_list, key=custom_sort_key)

with open(os.path.join(TARGET_PUBLIC_DIR, "story_index.json"), "w", encoding="utf-8") as f:
    json.dump(final_list, f, ensure_ascii=False, indent=2)

print("Index Generated with Scene0-safe IDs, Titles & Sections.")
print(f"条目数: {len(final_list)}")
