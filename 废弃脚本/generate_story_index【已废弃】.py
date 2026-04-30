import os
import json
import shutil
import re
import natsort

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

def count_sections(filepath):
    """核心算法：计算有效 Section 数量"""
    if not os.path.exists(filepath): return 0
    count = 0
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith("---") and "[Section" in line:
                    count += 1
        return count
    except: return 0

def scan_directory(base_dir, lang_key):
    print(f"--- 扫描 [{lang_key}] ---")
    for root, dirs, files in os.walk(base_dir):
        if "WEBSITE_DATA" in root: continue

        for file in files:
            if not file.endswith(".txt"): continue
            
            # 兼容：允许所有 txt，不再强制 _combined
            # 但要排除 readme 之类的干扰
            if not re.match(r'^\d+', file): continue

            # 提取 ID (文件名第一个下划线前的部分)
            # 101101_1-7.txt -> 101101
            # 9051-9052_1-10.txt -> 9051-9052
            raw_id = file.split('_')[0]
            
            rel_path = os.path.relpath(root, base_dir)
            path_parts = rel_path.split(os.sep)
            
            # 获取分类和文件夹名
            category = get_category(rel_path)
            folder_name = os.path.basename(root)
            
            # 复制目标
            dest_rel = os.path.join(category, folder_name)
            dest_full = os.path.join(TARGET_DATA_DIR, dest_rel)
            os.makedirs(dest_full, exist_ok=True)
            
            # 为了前端方便，这里统一加上 _{lang} 后缀
            # 如果源文件本身已经有 _cn/_jp 后缀（如S0），要注意不要重复
            if file.endswith(f"_{lang_key}.txt"):
                dest_filename = file
            else:
                # 101101_1-7.txt -> 101101_1-7_cn.txt
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
                    "cn_secs": 0, "jp_secs": 0,
                    "filename_cn": "" # 用于前端显示真实名字
                }
            
            web_path = f"/data/{sanitize_path(dest_rel)}/{dest_filename}"
            secs = count_sections(os.path.join(root, file))
            
            if lang_key == "cn":
                story_map[raw_id]["cn_path"] = web_path
                story_map[raw_id]["cn_secs"] = secs
                story_map[raw_id]["folder"] = folder_name
                story_map[raw_id]["filename_cn"] = file # 记录原始文件名
            else:
                story_map[raw_id]["jp_path"] = web_path
                story_map[raw_id]["jp_secs"] = secs

# === 执行 ===
if os.path.exists(TARGET_DATA_DIR): shutil.rmtree(TARGET_DATA_DIR)
os.makedirs(TARGET_DATA_DIR)

scan_directory(DIR_JP, "jp")
scan_directory(DIR_CN, "cn")

final_list = []
for k, v in story_map.items():
    p = 0
    if v["jp_secs"] > 0:
        if v["cn_secs"] >= v["jp_secs"]: p = 100
        else: p = round((v["cn_secs"] / v["jp_secs"]) * 100)
    elif v["cn_secs"] > 0:
        p = 100
        
    final_list.append({
        "id": v["id"],
        "category": v["category"],
        "folder": v["folder"],
        "percent": p,
        "has_cn": bool(v["cn_path"]),
        "has_jp": bool(v["jp_path"]),
        "path_cn": v["cn_path"],
        "path_jp": v["jp_path"],
        "filename_cn": v["filename_cn"]
    })

final_list.sort(key=lambda x: x["id"])

with open(os.path.join(TARGET_PUBLIC_DIR, "story_index.json"), "w", encoding="utf-8") as f:
    json.dump(final_list, f, ensure_ascii=False, indent=2)

print("Index Generated.")