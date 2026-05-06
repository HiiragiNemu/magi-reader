import os
import re
import json
import natsort
import shutil
from collections import defaultdict

# === 目录配置 ===
TARGET_DIRS =[
    "magireco-source-master/Scenarios_full",
    "magireco-translate-data-master/Scenarios_full"
]

GLOBAL_ID_MAP = {}
BRANCH_REPORT = defaultdict(list)


def clean_and_format_content(text):
    """清理 JSON 文本内容，转换格式标记"""
    if not isinstance(text, str):
        return ""
    
    text = text.replace('@', '\\n').replace('[br]', '\\n')
    text = text.replace('「textBlack:', '[textBlack:').replace('『textBlack:', '[textBlack:')
    text = re.sub(r'\[textRed:(.*?)\]', r'<red>\1</red>', text, flags=re.DOTALL)
    text = re.sub(r'\[textBlue:(.*?)\]', r'<blue>\1</blue>', text, flags=re.DOTALL)
    text = re.sub(r'\[textYellow:(.*?)\]', r'<yellow>\1</yellow>', text, flags=re.DOTALL)
    text = re.sub(r'\[textBlack:(.*?)\]', r'<black>\1</black>', text, flags=re.DOTALL)
    text = re.sub(r'\[.*?\]', '', text)
    
    return text.strip()


def extract_branch_info(data, json_filename):
    """提取分支信息用于报告"""
    story = data.get('story', {})
    if not isinstance(story, dict): return None
    groups =[k for k in story.keys() if k.startswith('group_')]
    if len(groups) <= 1: return None
    selects =[]
    for gname, group in story.items():
        if not isinstance(group, list): continue
        for item in group:
            if isinstance(item, dict) and 'select' in item:
                for opt in item['select']:
                    selects.append({
                        'from_group': gname, 'to_group': opt.get('group', '?'),
                        'text': opt.get('textSelect', '?'), 'alt_id': opt.get('alternativeId', '?')
                    })
    skip_list = data.get('skipTransitionList',[])
    return {
        'file': json_filename, 'groups': sorted(groups), 'group_count': len(groups),
        'selects': selects, 'skip_transitions': skip_list
    }


INTERVIEW_MARKERS =['取材記録', '采访记录', '取材记录', '取材録']

def is_interview_marker(text):
    if not text: return False
    return any(m in text for m in INTERVIEW_MARKERS)


def extract_interview_name(cleaned_text):
    parts = cleaned_text.split('\\n')
    names =[]
    for part in parts:
        part_clean = re.sub(r'\[textBlack:(.*?)\]', r'\1', part).strip()
        if part_clean and '记录' not in part_clean and '記録' not in part_clean and '―' not in part_clean:
            names.append(part_clean)
    return names


def build_txt_from_json(json_path):
    """从单个 JSON 文件构建 TXT 文本 (高保真版)"""
    try:
        with open(json_path, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)

        fname = os.path.basename(json_path)
        sec_match = re.search(r'[-_](\d+)(?:_|\.)', fname)
        sec_num = sec_match.group(1) if sec_match else "?"

        story = data.get('story', {})
        if not isinstance(story, dict): return ""

        branch_info = extract_branch_info(data, fname)
        if branch_info:
            folder = os.path.dirname(json_path)
            BRANCH_REPORT[folder].append(branch_info)

        all_groups = sorted([k for k in story.keys() if k.startswith('group_')])
        res_lines =[]

        for group_name in all_groups:
            group = story[group_name]
            if not isinstance(group, list): continue

            group_lines =[]
            pos_to_id = {'Left': None, 'Right': None, 'Center': None}
            explicit_name_for_pos = {'Left': None, 'Right': None, 'Center': None}
            sticky_narration_name = "旁白"

            for item in group:
                if not isinstance(item, dict): continue

                # 1. 更新角色位置
                if 'chara' in item:
                    for c in item['chara']:
                        c_id = c.get('id')
                        if c_id and 'pos' in c:
                            p_key = 'Left' if c['pos'] == 0 else 'Center' if c['pos'] == 1 else 'Right'
                            old_id = pos_to_id[p_key]
                            pos_to_id[p_key] = str(c_id)
                            if old_id and old_id != str(c_id):
                                explicit_name_for_pos[p_key] = None

                # 2. 显式名字更新
                for pos in['Left', 'Right', 'Center']:
                    n_key = f'name{pos}'
                    if n_key in item:
                        explicit_name_for_pos[pos] = item[n_key]
                        if pos_to_id[pos]:
                            GLOBAL_ID_MAP[pos_to_id[pos]] = item[n_key]

                target_speaker = None
                raw_text = None

                # 3a. 选项
                if 'select' in item:
                    for opt in item['select']:
                        sel_text = opt.get('textSelect', '')
                        if sel_text:
                            group_lines.append(f"选项: 【{sel_text}】→ {opt.get('group', '')}\n")
                    continue

                # 3b. 取材记录
                if 'narration' in item and is_interview_marker(str(item['narration'])):
                    cleaned = clean_and_format_content(str(item['narration']))
                    if cleaned:
                        group_lines.append(f"\n―― 取材记录 ――\n")
                        for name in extract_interview_name(cleaned):
                            group_lines.append(f"旁白: {name}\n")
                    sticky_narration_name = "旁白"
                    continue

                # 3c. 旁白独白
                if 'narration' in item or 'progressNarration' in item:
                    raw_text = item.get('narration') or item.get('progressNarration')
                    if 'nameNarration' in item:
                        sticky_narration_name = item['nameNarration'] if item['nameNarration'] else "旁白"
                    target_speaker = sticky_narration_name

                # 3d. 普通对话
                elif not raw_text:
                    for pos in ['Left', 'Right', 'Center']:
                        if f'text{pos}' in item or f'textAv{pos}' in item:
                            raw_text = item.get(f'text{pos}') or item.get(f'textAv{pos}')
                            speaker_name = item.get(f'name{pos}') or explicit_name_for_pos[pos]
                            if not speaker_name and pos_to_id[pos]:
                                speaker_name = GLOBAL_ID_MAP.get(pos_to_id[pos])
                            target_speaker = speaker_name or "旁白"
                            sticky_narration_name = "旁白"
                            break

                # 4. 输出
                if raw_text:
                    cleaned = clean_and_format_content(str(raw_text))
                    if cleaned: group_lines.append(f"{target_speaker}: {cleaned}\n")

            if not group_lines: continue

            # 生成头部
            branch_label = group_name.replace('group_', 'Branch ')
            head = f"\n---[Section {sec_num}] (Source: {fname}) ---\n" if group_name == 'group_1' else f"\n--- [Section {sec_num} - {branch_label}] (Source: {fname}) ---\n"
            res_lines.append(head)
            res_lines.extend(group_lines)

        return "".join(res_lines)
    except Exception as e:
        print(f"  ❌ Error in {json_path}: {e}")
        return ""


def print_branch_report():
    if not BRANCH_REPORT: return
    print(f"\n{'='*70}\n🌿 多分支剧情报告\n{'='*70}")
    for folder, infos in sorted(BRANCH_REPORT.items()):
        print(f"\n📁 {os.path.basename(folder)} (含 {len(infos)} 个分支文件)")
    print("=" * 70)


def main():
    print("🚀 启动【JSON逆向驱动 + 全局重建版】...")
    rebuilt_count = 0
    skipped_count = 0
    obsolete_count = 0

    for rel_dir in TARGET_DIRS:
        abs_root = os.path.join(os.getcwd(), rel_dir)
        if not os.path.exists(abs_root): continue
        print(f"\n📂 处理: {rel_dir}")

        for root, dirs, files in os.walk(abs_root):
            # 1. 获取所有的 JSON 文件
            json_files = [f for f in files if f.endswith('.json')]
            if not json_files: continue

            # 2. 按照 ID 分组 (兼容 v11 的合并逻辑)
            groups = defaultdict(list)
            for jf in json_files:
                match = re.match(r'^(\d+)', jf)
                if not match:
                    continue
                fid = match.group(1)

                # 处理 7 位数字的文件（如 5170100-30_pVeLS.json）
                if fid.startswith('51701') and len(fid) >= 7:
                    # 提取后面的数字（如 5170100 中的 '00'）
                    suffix = fid[5:]  # 取第6位开始：'00', '01', '02'...
                    if suffix:
                        # 按十位数分组：00-09 一组，10-19 一组，20-29 一组...
                        group_num = int(suffix) // 10
                        group_key = f"51701_{group_num}"
                    else:
                        group_key = fid[:5]

                # 活动剧情 (5开头且>=6位) 激进合并
                elif len(fid) >= 6 and fid.startswith('5'):
                    group_key = fid[:5]
                else:
                    group_key = fid

                groups[group_key].append(jf)

            # 3. 处理每一组
            for g_key, g_files in groups.items():
                g_files = natsort.natsorted(g_files)
                
                # 提取首尾信息用于计算最终的 TXT 文件名
                m_first = re.match(r'^(\d+)[-_](\d+)', g_files[0])
                m_last = re.match(r'^(\d+)[-_](\d+)', g_files[-1])
                
                id_first = m_first.group(1) if m_first else g_key
                id_last = m_last.group(1) if m_last else g_key
                sec_first = m_first.group(2) if m_first else "1"
                sec_last = m_last.group(2) if m_last else str(len(g_files))

                # 确定目标文件名
                if id_first != id_last:
                    target_name = f"{id_first}-{id_last[-2:]}_{sec_first}-{sec_last}.txt"
                else:
                    if sec_first == sec_last:
                        target_name = f"{id_first}_{sec_first}.txt"
                    else:
                        target_name = f"{id_first}_{sec_first}-{sec_last}.txt"

                target_path = os.path.join(root, target_name)

                # 4. 组装全部内容
                full_content = "".join([build_txt_from_json(os.path.join(root, j)) for j in g_files])
                if not full_content: continue

                # 5. 【核心修复】作废旧的“半翻译”文件
                # 比如我们要生成 103001_1-10.txt，就要把 103001_1-9.txt 删掉/备份
                for f in files:
                    if f.endswith('.txt') and not f.startswith('readme'):
                        if f.startswith(f"{id_first}_") and f != target_name:
                            old_path = os.path.join(root, f)
                            if not os.path.exists(old_path + '.bak'):
                                os.rename(old_path, old_path + '.bak')
                                print(f"  🗑️ 废弃旧版(半翻译): {f} -> .bak")
                                obsolete_count += 1

                # 6. 检查内容是否无变化
                is_identical = False
                if os.path.exists(target_path):
                    with open(target_path, 'r', encoding='utf-8') as existing_file:
                        if existing_file.read() == full_content:
                            is_identical = True

                if is_identical:
                    # print(f"  ⏭️ 无变化: {target_name}")
                    skipped_count += 1
                    continue

                # 7. 写入最新文件
                if os.path.exists(target_path) and not os.path.exists(target_path + '.bak'):
                    shutil.copy2(target_path, target_path + '.bak')

                with open(target_path, 'w', encoding='utf-8') as out:
                    out.write(full_content)
                
                print(f"  ✅ 成功生成全翻译: {target_name} (包含 {len(g_files)} 个 JSON)")
                rebuilt_count += 1

    print_branch_report()
    print(f"\n✨ 全部完成！\n  - 新建/更新文件: {rebuilt_count} 个\n  - 跳过(内容一致): {skipped_count} 个\n  - 自动清理半翻译旧文件: {obsolete_count} 个\n  - 识别角色: {len(GLOBAL_ID_MAP)} 名")

if __name__ == "__main__":
    main()