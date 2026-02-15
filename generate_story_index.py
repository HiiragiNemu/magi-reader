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
TITLES_PATH = "titles.json" # 确保此文件在脚本同级目录

story_map = {}
TITLES = {}

# ★ 修复1: 加载标题库
if os.path.exists(TITLES_PATH):
    with open(TITLES_PATH, 'r', encoding='utf-8') as f:
        TITLES = json.load(f)
    print(f"✅ 已加载标题库: {len(TITLES)} 条")

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

def extract_sections(filepath):
    """
    ★ 终极修复版: 构造形如 "505901-1 Section 1 : 序" 的完整展示字符串
    """
    headers = []
    if not os.path.exists(filepath): return headers
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                # 匹配标准头: --- [Section 1] (Source: 505901-1.json) ---
                # 或分支头: --- [Section 1 - Branch 2] (Source: 505901-1.json) ---
                if line.startswith("---") and "[Section" in line:
                    
                    # 1. 提取文件名 (用于显示 505901-1)
                    # 从 (Source: xxxxx.json) 中提取
                    source_match = re.search(r'Source:\s*([\w\d\-\.]+)', line)
                    file_id = ""
                    if source_match:
                        # 去掉 .json 后缀
                        file_id = source_match.group(1).replace('.json', '')

                    # 2. 提取 Section 核心部分 (用于显示 Section 1 - Branch 2)
                    # 去掉 "--- [" 和 "] (Source..."
                    base_sec = re.sub(r'--- \[|\] \(Source.*', '', line).strip()
                    
                    # 3. 查找中文标题 (用于显示 序/叶月1)
                    title_part = ""
                    # 只有当 file_id 存在且在 titles.json 里有定义时才显示
                    if file_id and file_id in TITLES:
                        title_part = f" : {TITLES[file_id]}"
                    
                    # 4. 组合最终字符串
                    # 格式: "505901-1 Section 1 : 序"
                    # 如果是分支，可能是 "505901-1 Section 1 - Branch 2 : 序"
                    full_display = f"{file_id} {base_sec}{title_part}".strip()
                    
                    headers.append(full_display)
    except: pass
    return headers

def scan_directory(base_dir, lang_key):
    print(f"--- 扫描 [{lang_key}] ---")
    for root, dirs, files in os.walk(base_dir):
        if "WEBSITE_DATA" in root: continue

        for file in files:
            if not file.endswith(".txt"): continue
            
            # ★ 修复3: 更智能的 ID 提取
            # 优先使用文件名（去后缀）作为 Key 来匹配标题
            file_stem = file.replace("_cn.txt", "").replace("_jp.txt", "").replace(".txt", "")
            
            # ID用于分组，还是保持原样取第一部分，避免同一章节的不同分卷被拆散
            raw_id = file.split('_')[0] 
            if not raw_id: continue

            rel_path = os.path.relpath(root, base_dir)
            
            category = get_category(rel_path)
            folder_name = os.path.basename(root)
            
            # 复制文件操作 (保持不变)
            dest_rel = os.path.join(category, folder_name)
            dest_full = os.path.join(TARGET_DATA_DIR, dest_rel)
            os.makedirs(dest_full, exist_ok=True)
            
            if file.endswith(f"_{lang_key}.txt"):
                dest_filename = file
            else:
                base_name = file.replace(".txt", "")
                dest_filename = f"{base_name}_{lang_key}.txt"

            full_src_path = os.path.join(root, file)
            shutil.copy2(full_src_path, os.path.join(dest_full, dest_filename))
            
            # 初始化数据结构
            if raw_id not in story_map:
                # ★ 修复4: 在此处匹配标题
                # 尝试匹配: 1. 完整文件名(310011_1-4) 2. 原始ID(505901-1)
                mapped_title = TITLES.get(file_stem) or TITLES.get(raw_id) or ""
                
                story_map[raw_id] = {
                    "id": raw_id,
                    "category": category,
                    "folder": folder_name,
                    "cn_path": "", "jp_path": "",
                    "has_cn": False, "has_jp": False,
                    "sections": [], # ★ 新增: 存储章节列表
                    "title": mapped_title, # ★ 新增: 存储中文标题
                    "filename_cn": "", "filename_jp": "" 
                }
            
            web_path = f"/data/{sanitize_path(dest_rel)}/{dest_filename}"
            
            # ★ 修复5: 提取章节列表 (优先使用中文文件的章节结构)
            current_sections = extract_sections(full_src_path)
            
            if lang_key == "cn":
                story_map[raw_id]["cn_path"] = web_path
                story_map[raw_id]["has_cn"] = True
                story_map[raw_id]["filename_cn"] = file
                # 如果有中文，优先用中文的章节结构（可能更准确或有翻译）
                if current_sections:
                    story_map[raw_id]["sections"] = current_sections
            else:
                story_map[raw_id]["jp_path"] = web_path
                story_map[raw_id]["has_jp"] = True
                story_map[raw_id]["filename_jp"] = file
                # 如果还没有章节信息（即没有中文版），才用日文的
                if not story_map[raw_id]["sections"] and current_sections:
                    story_map[raw_id]["sections"] = current_sections

# === 执行 ===
if os.path.exists(TARGET_DATA_DIR): shutil.rmtree(TARGET_DATA_DIR)
os.makedirs(TARGET_DATA_DIR)

scan_directory(DIR_JP, "jp")
scan_directory(DIR_CN, "cn")

final_list = []
for k, v in story_map.items():
    # 简单的进度计算
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
        "title": v["title"],       # 传递标题
        "sections": v["sections"], # 传递章节
        "filename_cn": v["filename_cn"],
        "filename_jp": v["filename_jp"]
    })

final_list = natsort.natsorted(final_list, key=lambda x: x["id"])
with open(os.path.join(TARGET_PUBLIC_DIR, "story_index.json"), "w", encoding="utf-8") as f:
    json.dump(final_list, f, ensure_ascii=False, indent=2)

print("Index Generated with Titles & Sections.")