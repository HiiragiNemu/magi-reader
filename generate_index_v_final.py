import os
import json
import shutil
import re

# === 配置 ===
DIR_JP = "magireco-source-master/Scenarios_full"
DIR_CN = "magireco-translate-data-master/Scenarios_full"
TARGET_PUBLIC_DIR = "website/public"
TARGET_DATA_DIR = os.path.join(TARGET_PUBLIC_DIR, "data")

story_map = {}

def sanitize_path(p):
    return p.replace("\\", "/")

def get_category(path):
    if "main_story" in path: return "main_story"
    if "event_story" in path: return "event_story"
    if "character_story" in path: return "character_story"
    if "costume_story" in path: return "costume_story"
    if "login_story" in path: return "login_story"
    if "mirror_story" in path: return "mirror_story"
    if "Scene0" in path or "S0" in path:
        if "支线" in path or "sub" in path.lower(): return "scene0_sub"
        return "scene0_main"
    return "Unclassified"

def scan_directory(base_dir, lang_key):
    print(f"--- 扫描 [{lang_key}] ---")
    for root, dirs, files in os.walk(base_dir):
        if "WEBSITE_DATA" in root: continue

        for file in files:
            if not file.endswith(".txt"): continue
            
            # 提取 ID (兼容所有格式)
            # 101101_1-7.txt -> 101101
            # 511901-09... -> 511901-09
            # 9051_main.txt -> 9051
            raw_id = file.split('_')[0]
            if not raw_id: continue # 防止空ID

            rel_path = os.path.relpath(root, base_dir)
            path_parts = rel_path.split(os.sep)
            
            # 获取分类和文件夹名
            category = get_category(rel_path)
            folder_name = os.path.basename(root)
            
            # 复制目标
            dest_rel = os.path.join(category, folder_name)
            dest_full = os.path.join(TARGET_DATA_DIR, dest_rel)
            os.makedirs(dest_full, exist_ok=True)
            
            # 复制并加上后缀，避免冲突
            if file.endswith(f"_{lang_key}.txt"):
                dest_filename = file
            else:
                base_name = file.replace(".txt", "")
                dest_filename = f"{base_name}_{lang_key}.txt"

            shutil.copy2(os.path.join(root, file), os.path.join(dest_full, dest_filename))
            
            # 注册
            if raw_id not in story_map:
                story_map[raw_id] = {
                    "id": raw_id,
                    "category": category,
                    "folder": folder_name,
                    "cn_path": "", "jp_path": "",
                    "has_cn": False, "has_jp": False,
                    "filename_cn": "", "filename_jp": "" # 初始化为空
                }
            
            web_path = f"/data/{sanitize_path(dest_rel)}/{dest_filename}"
            
            if lang_key == "cn":
                story_map[raw_id]["cn_path"] = web_path
                story_map[raw_id]["has_cn"] = True
                story_map[raw_id]["filename_cn"] = file # 记录原始文件名！
            else:
                story_map[raw_id]["jp_path"] = web_path
                story_map[raw_id]["has_jp"] = True
                story_map[raw_id]["filename_jp"] = file # 记录原始文件名！

# === 执行 ===
if os.path.exists(TARGET_DATA_DIR): shutil.rmtree(TARGET_DATA_DIR)
os.makedirs(TARGET_DATA_DIR)

scan_directory(DIR_JP, "jp")
scan_directory(DIR_CN, "cn")

final_list = []
for k, v in story_map.items():
    # 简单汉化率：有中文就是100，无中文就是0
    # 如果你需要之前的行数计算，可以把那个 count_sections 函数加回来
    p = 100 if v["has_cn"] else 0
        
    final_list.append({
        "id": v["id"],
        "category": v["category"],
        "folder": v["folder"],
        "percent": p,
        "has_cn": v["has_cn"],
        "has_jp": v["has_jp"],
        "path_cn": v["cn_path"],
        "path_jp": v["jp_path"],
        "filename_cn": v["filename_cn"],
        "filename_jp": v["filename_jp"]
    })

final_list.sort(key=lambda x: x["id"])

with open(os.path.join(TARGET_PUBLIC_DIR, "story_index.json"), "w", encoding="utf-8") as f:
    json.dump(final_list, f, ensure_ascii=False, indent=2)

print("Index Generated.")