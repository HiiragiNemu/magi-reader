import os
import re
import json
import natsort

# === 目标目录 ===
TARGET_DIRS = [
    "magireco-source-master/Scenarios_full",
    "magireco-translate-data-master/Scenarios_full"
]

def clean_text_with_red(text):
    if not isinstance(text, str): return ""
    # 修复红字：保留内容，添加标签
    text = re.sub(r'\[textRed:(.*?)\]', r'<red>\1</red>', text)
    # 修复蓝色字体 (如果有)
    text = re.sub(r'\[textBlue:(.*?)\]', r'<blue>\1</blue>', text)
    # 清理其他控制符
    text = text.replace('@', '\n').replace('[br]', '\n')
    text = re.sub(r'\[.*?\]', '', text)
    return text.strip()

def extract_from_json(json_path):
    try:
        with open(json_path, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
        
        # 获取文件名中的 Section 号
        fname = os.path.basename(json_path)
        # 匹配 -1.json 或 _1.json
        sec_match = re.search(r'[-_](\d+)(?:_|\.)', fname)
        sec_num = sec_match.group(1) if sec_match else "?"
        
        lines = [f"\n--- [Section {sec_num}] (Source: {fname}) ---\n"]
        
        story = data.get('story', {})
        group = story.get('group_1', []) if isinstance(story, dict) else story
        
        if isinstance(group, list):
            for item in group:
                if not isinstance(item, dict): continue
                text = None
                speaker = "旁白"
                
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
                    lines.append(f"{speaker or '旁白'}: {clean_text_with_red(str(text))}\n")
        return "".join(lines)
    except Exception as e:
        # print(f"JSON读取错误: {json_path}")
        return ""

def process_txt_file(root, txt_filename):
    txt_path = os.path.join(root, txt_filename)
    
    # 1. 解析文件名
    # 格式 A: 101102_1-8.txt (ID_Start-End)
    # 格式 B: 101102.txt (ID)
    # 格式 C: 511901-09_1-9.txt (RangeID_RangeSec)
    
    # 尝试提取 ID 前缀
    match_id = re.match(r'^(\d+)', txt_filename)
    if not match_id: return # 跳过非数字开头的文件
    
    base_id = match_id.group(1) # 101102 或 511901
    
    # 尝试提取 Section 范围
    match_range = re.search(r'_(\d+)-(\d+)\.txt$', txt_filename)
    
    target_jsons = []
    
    # 扫描同目录下的 JSON
    all_files = os.listdir(root)
    json_candidates = natsort.natsorted([f for f in all_files if f.endswith(".json") and f.startswith(base_id[:4])])
    
    if not json_candidates:
        # 没有 JSON，只能原地修 TXT
        with open(txt_path, 'r', encoding='utf-8') as f:
            raw = f.read()
        if "[textRed" in raw:
            print(f"[TXT修复] {txt_filename} (无JSON源)")
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(clean_text_with_red(raw))
        return

    # 如果文件名里有范围 1-8
    if match_range:
        start_sec = int(match_range.group(1))
        end_sec = int(match_range.group(2))
        
        # 筛选符合范围的 JSON
        for jf in json_candidates:
            # 提取 JSON 的 Section 号 (101102-1.json -> 1)
            # 注意：也可能是 511901-1.json
            m_sec = re.search(r'[-_](\d+)(?:_|\.)', jf)
            if m_sec:
                sec = int(m_sec.group(1))
                # 还有一种情况：文件名 ID 不同 (511901...511909)
                # 需要判断这个 JSON 是否属于这个 TXT 的 ID 范围
                # 简单起见：如果 JSON 的文件名包含在 TXT 定义的 ID 序列里
                # 这里使用一种通用策略：如果 JSON 的 Section 在范围内，且 ID 前缀匹配
                
                # 严格匹配 ID：
                # 如果 TXT 是 101102_...，那么 JSON 必须是 101102-...
                if jf.startswith(base_id):
                     if start_sec <= sec <= end_sec:
                        target_jsons.append(jf)
                # 如果 TXT 是合并 ID (511901-09)，逻辑比较复杂，暂略，假设文件名 ID 一致
    else:
        # 没有范围，假设包含所有同 ID 的 JSON
        target_jsons = [f for f in json_candidates if f.startswith(base_id)]

    if not target_jsons:
        return

    # 重建内容
    print(f"[重建] {txt_filename} <== {len(target_jsons)} 个 JSON")
    new_content = ""
    for jf in target_jsons:
        new_content += extract_from_json(os.path.join(root, jf))
    
    if new_content:
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(new_content)

def main():
    base_dir = os.getcwd()
    for rel in TARGET_DIRS:
        abs_root = os.path.join(base_dir, rel)
        if not os.path.exists(abs_root): continue
        
        print(f"正在扫描: {rel}")
        for root, dirs, files in os.walk(abs_root):
            for f in files:
                if f.endswith(".txt") and not f.startswith("readme"):
                    process_txt_file(root, f)

    print("\n所有 TXT 已强制根据 JSON 重建（红字已修复）。")
    print("请记得运行 generate_index 脚本更新网站数据。")

if __name__ == "__main__":
    main()