import os
import re
import json
import natsort

# === 目录配置 ===
TARGET_DIRS = [
    "magireco-source-master/Scenarios_full",
    "magireco-translate-data-master/Scenarios_full"
]

def clean_text_safe(text):
    if not isinstance(text, str): return ""
    
    # 1. 预处理：处理换行符
    text = text.replace('@', '\n').replace('[br]', '\n')

    # 2. 转换颜色标签（去除方括号，转为 XML 风格）
    # 使用 DOTALL 模式确保匹配跨行内容
    text = re.sub(r'\[textRed:(.*?)\]', r'<red>\1</red>', text, flags=re.DOTALL)
    text = re.sub(r'\[textBlue:(.*?)\]', r'<blue>\1</blue>', text, flags=re.DOTALL)

    # 3. 【核心保护机制】使用占位符保护 textBlack
    # 将 [textBlack:内容] 替换为 {{TB_START}}内容{{TB_END}}
    # 这样接下来的清理步骤就不会误删它
    def protect_black(match):
        content = match.group(1)
        return f"{{{{TB_START}}}}{content}{{{{TB_END}}}}"
    
    text = re.sub(r'\[textBlack:(.*?)\]', protect_black, text, flags=re.DOTALL)

    # 4. 清理垃圾控制符
    # 现在剩下的 [...] 都是 [se:], [bg:], [chara:] 等不需要的内容
    # 我们放心大胆地全部删掉
    text = re.sub(r'\[.*?\]', '', text, flags=re.DOTALL)

    # 5. 还原 textBlack
    text = text.replace('{{TB_START}}', '[textBlack:')
    text = text.replace('{{TB_END}}', ']')

    return text.strip()

def extract_from_json(json_path):
    try:
        with open(json_path, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
        
        fname = os.path.basename(json_path)
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
                    cleaned = clean_text_safe(str(text))
                    if cleaned:
                        lines.append(f"{speaker or '旁白'}: {cleaned}\n")
        return "".join(lines)
    except Exception as e:
        print(f"Error parsing {json_path}: {e}")
        return ""

def process_txt_file(root, txt_filename):
    txt_path = os.path.join(root, txt_filename)
    match_id = re.match(r'^(\d+)', txt_filename)
    if not match_id: return
    base_id = match_id.group(1)
    match_range = re.search(r'_(\d+)-(\d+)\.txt$', txt_filename)
    
    all_files = os.listdir(root)
    json_candidates = natsort.natsorted([f for f in all_files if f.endswith(".json") and f.startswith(base_id[:4])])
    target_jsons = []

    if match_range:
        start_sec, end_sec = int(match_range.group(1)), int(match_range.group(2))
        for jf in json_candidates:
            if not jf.startswith(base_id): continue
            m_sec = re.search(r'[-_](\d+)(?:_|\.)', jf)
            if m_sec and start_sec <= int(m_sec.group(1)) <= end_sec:
                target_jsons.append(jf)
    else:
        target_jsons = [f for f in json_candidates if f.startswith(base_id)]

    if not target_jsons: return

    print(f"正在安全重建: {txt_filename} ...")
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
        print(f"扫描目录: {rel}")
        for root, dirs, files in os.walk(abs_root):
            for f in files:
                if f.endswith(".txt") and not f.startswith("readme"):
                    process_txt_file(root, f)
    print("\n✅ 安全重建完成！textBlack 已被保护。")

if __name__ == "__main__":
    main()