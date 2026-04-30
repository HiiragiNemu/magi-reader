import os
import json
import shutil
import re
import natsort
from collections import defaultdict

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

def clean_text_with_red(text):
    if not isinstance(text, str): return ""
    # 修复红字：保留内容，添加标签
    text = re.sub(r'\[textRed:(.*?)\]', r'<red>\1</red>', text)
    # 移除其他控制符，但保留换行
    text = text.replace('@', '\n').replace('[br]', '\n')
    text = re.sub(r'\[.*?\]', '', text)
    return text.strip()

def count_valid_sections(content):
    count = 0
    in_sec = False
    has_text = False
    for line in content.split('\n'):
        if line.startswith("---") and "[Section" in line:
            if in_sec and has_text: count += 1
            in_sec = True
            has_text = False
        elif in_sec and ":" in line and not line.startswith("---"):
            has_text = True
    if in_sec and has_text: count += 1
    return count

def extract_content_from_file(filepath):
    """
    智能读取：如果是 JSON，提取对话；如果是 TXT，直接读取并尝试修复红字。
    """
    if filepath.endswith('.json'):
        try:
            with open(filepath, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)
            
            # 提取 Section ID
            sec_match = re.search(r'-(\d+)(?:_|\.)', os.path.basename(filepath))
            sec_num = sec_match.group(1) if sec_match else "?"
            
            content = [f"\n--- [Section {sec_num}] (Source: {os.path.basename(filepath)}) ---\n"]
            
            story = data.get('story', {})
            group = story.get('group_1', []) if isinstance(story, dict) else story
            if isinstance(group, list):
                for item in group:
                    if not isinstance(item, dict): continue
                    text = None
                    speaker = "旁白"
                    # 尝试读取文本
                    if 'narration' in item: text = item['narration']
                    elif 'progressFnarration' in item: text = item['progressFnarration']
                    else:
                        for pos in ['Left', 'Right', 'Center']:
                            for k in [f'text{pos}', f'textAv{pos}']:
                                if k in item:
                                    text = item[k]
                                    speaker = item.get(k.replace('text', 'name'), "")
                                    break
                            if text: break
                    
                    if text:
                        content.append(f"{speaker or '旁白'}: {clean_text_with_red(str(text))}\n")
            return "".join(content)
        except: return ""
        
    elif filepath.endswith('.txt'):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                raw = f.read()
            # 即使是 TXT，也尝试修复红字（如果 TXT 里保留了原始标签）
            # 但通常 TXT 里已经是清洗过的了，这里假设它是旧版清洗过的，可能丢失了红字
            # 如果要完美修复，必须回溯到 JSON。
            # 这里我们假设源目录里混杂了 JSON 和 TXT。优先用 JSON。
            return raw
        except: return ""
    return ""

def process_merge_group(base_dir, lang_key):
    print(f"--- 处理合并与索引 [{lang_key}] ---")
    
    # 遍历目录
    for root, dirs, files in os.walk(base_dir):
        if "WEBSITE_DATA" in root: continue
        
        # S0 单独处理（略过，假设 S0 已经是完美的单文件了，直接复制）
        if "Scene0" in root or "S0" in root:
            for f in files:
                if f.endswith('.txt') and ("_main" in f or "_sub" in f):
                    # 复制并注册 S0
                    rel_path = os.path.relpath(root, base_dir)
                    cat = get_category(rel_path)
                    folder = os.path.basename(root)
                    
                    dest_rel = os.path.join(cat, folder)
                    os.makedirs(os.path.join(TARGET_DATA_DIR, dest_rel), exist_ok=True)
                    
                    # 命名：905101-905132_010-020_cn.txt
                    # 从文件名提取 ID
                    raw_id = f.replace('.txt', '')
                    
                    dest_name = f"{raw_id}_{lang_key}.txt"
                    shutil.copy2(os.path.join(root, f), os.path.join(TARGET_DATA_DIR, dest_rel, dest_name))
                    
                    # 注册
                    if raw_id not in story_map:
                        story_map[raw_id] = {
                            "id": raw_id, "category": cat, "folder": folder,
                            "cn_path": "", "jp_path": "", "cn_secs": 0, "jp_secs": 0,
                            "filename_cn": f, "filename_jp": ""
                        }
                    
                    web_path = f"/data/{sanitize_path(dest_rel)}/{dest_name}"
                    secs = count_valid_sections(extract_content_from_file(os.path.join(root, f)))
                    
                    if lang_key == "cn":
                        story_map[raw_id]["cn_path"] = web_path
                        story_map[raw_id]["cn_secs"] = secs
                        story_map[raw_id]["filename_cn"] = f
                    else:
                        story_map[raw_id]["jp_path"] = web_path
                        story_map[raw_id]["jp_secs"] = secs
                        story_map[raw_id]["filename_jp"] = f
            continue

        # === 常规剧情合并逻辑 ===
        # 1. 收集该文件夹下的所有源文件 (优先找 JSON，没有再找 TXT)
        #    为了解决红字问题，必须回溯 JSON
        json_files = natsort.natsorted([f for f in files if f.endswith('.json')])
        txt_files = natsort.natsorted([f for f in files if f.endswith('.txt') and "_combined" in f])
        
        # 如果有 JSON，忽略 TXT（重新生成）
        source_files = json_files if json_files else txt_files
        if not source_files: continue
        
        # 2. 分组 (按前5位 ID)
        # 511901, 511902 -> 51190 (Group)
        groups = defaultdict(list)
        for f in source_files:
            match = re.match(r'^(\d+)', f)
            if not match: continue
            fid = match.group(1)
            
            # 策略：如果长度 >= 6 (如 511901)，取前5位作为组名
            # 如果长度 < 6 (如 101101)，取前6位（即本身）作为组名 -> 不合并
            if len(fid) >= 6 and fid.startswith('5'): # 只针对活动剧情做这种激进合并
                group_key = fid[:5]
            else:
                group_key = fid # 不合并，每个文件单独一组
            
            groups[group_key].append(f)
            
        # 3. 处理每一组
        for g_key, g_files in groups.items():
            if not g_files: continue
            
            # 排序
            g_files = natsort.natsorted(g_files)
            
            # 生成新内容
            combined_content = ""
            for f in g_files:
                combined_content += extract_content_from_file(os.path.join(root, f))
            
            # 生成新文件名
            # 单文件: 101101_1-7_cn.txt
            # 多文件: 511901-09_1-9_cn.txt
            
            first = g_files[0]
            last = g_files[-1]
            
            # 提取 ID 和 Section
            p = re.compile(r'^(\d+)-?(\d+)?')
            m1 = p.match(first)
            m2 = p.match(last)
            
            id1 = m1.group(1) if m1 else g_key
            id2 = m2.group(1) if m2 else g_key
            
            # 尝试提取文件名中的 Section 范围 (如果源文件是 TXT)
            # 或者是从 JSON 文件名推断 (通常 JSON 不带范围，只带序号)
            # 这里简化：如果是合并组，ID 变为 511901-09
            
            if id1 == id2:
                final_id = id1
            else:
                # 简化的合并 ID 显示：511901-09 (取后两位)
                final_id = f"{id1}-{id2[-2:]}"

            # 写入
            rel_path = os.path.relpath(root, base_dir)
            cat = get_category(rel_path)
            folder = os.path.basename(root)
            
            dest_rel = os.path.join(cat, folder)
            os.makedirs(os.path.join(TARGET_DATA_DIR, dest_rel), exist_ok=True)
            
            dest_name = f"{final_id}_{lang_key}.txt"
            
            with open(os.path.join(TARGET_DATA_DIR, dest_rel, dest_name), 'w', encoding='utf-8') as f:
                f.write(combined_content)
                
            # 注册
            if final_id not in story_map:
                story_map[final_id] = {
                    "id": final_id, "category": cat, "folder": folder,
                    "cn_path": "", "jp_path": "", "cn_secs": 0, "jp_secs": 0,
                    "filename_cn": "", "filename_jp": ""
                }
            
            web_path = f"/data/{sanitize_path(dest_rel)}/{dest_name}"
            secs = count_valid_sections(combined_content)
            
            if lang_key == "cn":
                story_map[final_id]["cn_path"] = web_path
                story_map[final_id]["cn_secs"] = secs
                # 记录原始文件名范围，方便前端显示 (如 #01-09)
                story_map[final_id]["filename_cn"] = f"{id1}_{id2}.txt" 
            else:
                story_map[final_id]["jp_path"] = web_path
                story_map[final_id]["jp_secs"] = secs
                story_map[final_id]["filename_jp"] = f"{id1}_{id2}.txt"

# === 执行 ===
if os.path.exists(TARGET_DATA_DIR): shutil.rmtree(TARGET_DATA_DIR)
os.makedirs(TARGET_DATA_DIR)

process_merge_group(DIR_JP, "jp")
process_merge_group(DIR_CN, "cn")

final_list = []
for k, v in story_map.items():
    p = 0
    if v["jp_secs"] > 0:
        p = min(100, round((v["cn_secs"] / v["jp_secs"]) * 100))
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
        "filename_cn": v["filename_cn"] or v["filename_jp"] # 确保有文件名
    })

final_list.sort(key=lambda x: x["id"])

with open(os.path.join(TARGET_PUBLIC_DIR, "story_index.json"), "w", encoding="utf-8") as f:
    json.dump(final_list, f, ensure_ascii=False, indent=2)

print("V11 构建完成。红字已修复，长剧情已合并。")