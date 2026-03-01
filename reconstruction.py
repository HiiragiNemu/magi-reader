import os
import re
import json
import natsort
import shutil
from collections import defaultdict

# === 目录配置 ===
TARGET_DIRS = [
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
    if not isinstance(story, dict):
        return None
    groups = [k for k in story.keys() if k.startswith('group_')]
    if len(groups) <= 1:
        return None
    selects = []
    for gname, group in story.items():
        if not isinstance(group, list):
            continue
        for item in group:
            if isinstance(item, dict) and 'select' in item:
                for opt in item['select']:
                    selects.append({
                        'from_group': gname,
                        'to_group': opt.get('group', '?'),
                        'text': opt.get('textSelect', '?'),
                        'alt_id': opt.get('alternativeId', '?')
                    })
    skip_list = data.get('skipTransitionList', [])
    return {
        'file': json_filename,
        'groups': sorted(groups),
        'group_count': len(groups),
        'selects': selects,
        'skip_transitions': skip_list
    }


# ===== 取材记录/采访记录 检测关键词 =====
INTERVIEW_MARKERS = ['取材記録', '采访记录', '取材记录', '取材録']


def is_interview_marker(text):
    """判断文本是否包含取材记录/采访记录标记"""
    if not text:
        return False
    return any(m in text for m in INTERVIEW_MARKERS)


def extract_interview_name(cleaned_text):
    """
    从取材记录标题中提取被采访者姓名
    输入示例: "[textBlack:―取材記録―]\\n[textBlack:柊　ねむ]"
    输出示例: "柊　ねむ"
    """
    parts = cleaned_text.split('\\n')
    names = []
    for part in parts:
        # 去掉 [textBlack:...] 标签
        part_clean = re.sub(r'\[textBlack:(.*?)\]', r'\1', part).strip()
        # 排除包含"记录/記録"的行（那是标题行），保留人名行
        if part_clean and '记录' not in part_clean and '記録' not in part_clean and '―' not in part_clean:
            names.append(part_clean)
    return names


def build_txt_from_json(json_path):
    """
    从单个 JSON 文件构建 TXT 文本
    
    修复清单:
    1. progressFnarration → progressNarration（拼写修正）
    2. 取材記録/采访记录 作为独立预拦截，不依赖 nameNarration 是否为空
    3. 空字符串 nameNarration 正确处理，重置为"旁白"
    4. 取材记录输出格式：分隔线 + 清洗后人名，同时保留原始内容
    """
    try:
        with open(json_path, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)

        fname = os.path.basename(json_path)
        sec_match = re.search(r'[-_](\d+)(?:_|\.)', fname)
        sec_num = sec_match.group(1) if sec_match else "?"

        story = data.get('story', {})
        if not isinstance(story, dict):
            return ""

        branch_info = extract_branch_info(data, fname)
        if branch_info:
            folder = os.path.dirname(json_path)
            BRANCH_REPORT[folder].append(branch_info)

        all_groups = sorted([k for k in story.keys() if k.startswith('group_')])
        res_lines = []

        for group_name in all_groups:
            group = story[group_name]
            if not isinstance(group, list):
                continue

            group_lines = []
            pos_to_id = {'Left': None, 'Right': None, 'Center': None}
            explicit_name_for_pos = {'Left': None, 'Right': None, 'Center': None}
            sticky_narration_name = "旁白"

            for item in group:
                if not isinstance(item, dict):
                    continue

                # ────────────────────────────────────────
                # 1. 更新位置上的角色 ID（检测角色切换）
                # ────────────────────────────────────────
                if 'chara' in item:
                    for c in item['chara']:
                        c_id = c.get('id')
                        if c_id and 'pos' in c:
                            p_val = c['pos']
                            p_key = 'Left' if p_val == 0 else 'Center' if p_val == 1 else 'Right'
                            old_id = pos_to_id[p_key]
                            pos_to_id[p_key] = str(c_id)
                            # 如果角色 ID 变了，清除旧的显式名字
                            if old_id and old_id != str(c_id):
                                explicit_name_for_pos[p_key] = None

                # ────────────────────────────────────────
                # 2. 显式名字更新（nameLeft / nameRight / nameCenter）
                # ────────────────────────────────────────
                for pos in ['Left', 'Right', 'Center']:
                    n_key = f'name{pos}'
                    if n_key in item:
                        explicit_name_for_pos[pos] = item[n_key]
                        if pos_to_id[pos]:
                            GLOBAL_ID_MAP[pos_to_id[pos]] = item[n_key]

                # ────────────────────────────────────────
                # 3. 内容提取（选项 → 取材记录 → 旁白/独白 → 普通对话）
                # ────────────────────────────────────────
                target_speaker = None
                raw_text = None

                # === 3a. 选项处理 ===
                if 'select' in item:
                    for opt in item['select']:
                        sel_text = opt.get('textSelect', '')
                        sel_group = opt.get('group', '')
                        if sel_text:
                            group_lines.append(f"选项: 【{sel_text}】→ {sel_group}\n")
                    continue

                # === 3b. ★ 取材记录/采访记录 预拦截（独立于 nameNarration 判断）===
                # 无论 nameNarration 是空字符串、缺失还是有值，只要内容含标记就拦截
                if 'narration' in item:
                    narr_raw = str(item['narration'])
                    if is_interview_marker(narr_raw):
                        cleaned = clean_and_format_content(narr_raw)
                        if cleaned:
                            # 输出分隔线
                            group_lines.append(f"\n―― 取材记录 ――\n")
                            # 提取并输出被采访者姓名
                            interview_names = extract_interview_name(cleaned)
                            for name in interview_names:
                                group_lines.append(f"旁白: {name}\n")
                        # 重置 sticky，后续由 nameNarration 重新指定
                        sticky_narration_name = "旁白"
                        continue

                # === 3c. ★ 旁白 / 独白 / progressNarration（修正拼写）===
                if 'narration' in item or 'progressNarration' in item:
                    raw_text = item.get('narration') or item.get('progressNarration')

                    # 处理 nameNarration
                    if 'nameNarration' in item:
                        nn = item['nameNarration']
                        if nn:
                            # 非空名字：正常更新
                            sticky_narration_name = nn
                        else:
                            # 空字符串：强制重置为"旁白"（防止继承前一个角色名）
                            sticky_narration_name = "旁白"

                    target_speaker = sticky_narration_name

                # === 3d. 普通对话（textLeft / textRight / textCenter / textAvXxx）===
                elif not raw_text:
                    for pos in ['Left', 'Right', 'Center']:
                        t_key = f'text{pos}'
                        av_t_key = f'textAv{pos}'
                        if t_key in item or av_t_key in item:
                            raw_text = item.get(t_key) or item.get(av_t_key)

                            # 名字解析优先级：
                            # 1) 当前 item 显式指定
                            # 2) 该位置上次显式指定的名字
                            # 3) 全局 ID 缓存
                            # 4) "旁白"
                            speaker_name = item.get(f'name{pos}')
                            if not speaker_name:
                                speaker_name = explicit_name_for_pos[pos]
                            if not speaker_name and pos_to_id[pos]:
                                speaker_name = GLOBAL_ID_MAP.get(pos_to_id[pos])

                            target_speaker = speaker_name or "旁白"
                            # 进入普通对话后重置旁白名
                            sticky_narration_name = "旁白"
                            break

                # ────────────────────────────────────────
                # 4. 输出
                # ────────────────────────────────────────
                if raw_text:
                    cleaned = clean_and_format_content(str(raw_text))
                    if cleaned:
                        group_lines.append(f"{target_speaker}: {cleaned}\n")

            if not group_lines:
                continue

            # 生成 Section / Branch 头部
            if group_name == 'group_1':
                res_lines.append(f"\n--- [Section {sec_num}] (Source: {fname}) ---\n")
            else:
                branch_label = group_name.replace('group_', 'Branch ')
                res_lines.append(f"\n--- [Section {sec_num} - {branch_label}] (Source: {fname}) ---\n")

            res_lines.extend(group_lines)

        return "".join(res_lines)
    except Exception as e:
        print(f"  ❌ Error in {json_path}: {e}")
        return ""


def find_target_jsons(root, txt_filename):
    """
    根据 TXT 文件名匹配对应的 JSON 文件
    
    支持的命名模式:
    A. 范围模式: 513901-09_0-9.txt → story ID 513901~513909, section 0~9
    B. 节范围:   420221_1-4.txt   → story ID 420221, section 1~4
    C. 简单模式: 420221.txt       → 所有 420221*.json
    D. 兜底:     用文件名开头数字匹配
    """
    all_files = os.listdir(root)
    all_jsons = [f for f in all_files if f.endswith('.json')]

    if not all_jsons:
        return []

    # 模式 A: 513901-09_0-9.txt
    match_full_range = re.match(r'^(\d+)-(\d+)_(\d+)-(\d+)\.txt$', txt_filename)
    if match_full_range:
        id_start_str = match_full_range.group(1)
        id_end_suffix = match_full_range.group(2)
        sec_start = int(match_full_range.group(3))
        sec_end = int(match_full_range.group(4))

        prefix = id_start_str[:len(id_start_str) - len(id_end_suffix)]
        suffix_start = int(id_start_str[len(prefix):])
        suffix_end = int(id_end_suffix)

        valid_ids = set()
        suffix_width = len(id_end_suffix)
        for s in range(suffix_start, suffix_end + 1):
            valid_ids.add(f"{prefix}{s:0{suffix_width}d}")

        target = []
        for jf in all_jsons:
            jm = re.match(r'^(\d+)[-_](\d+)', jf)
            if jm:
                j_id = jm.group(1)
                j_sec = int(jm.group(2))
                if j_id in valid_ids and sec_start <= j_sec <= sec_end:
                    target.append(jf)

        return natsort.natsorted(target)

    # 模式 B: 420221_1-4.txt
    match_sec_range = re.search(r'^(\d+)_(\d+)-(\d+)\.txt$', txt_filename)
    if match_sec_range:
        base_id = match_sec_range.group(1)
        sec_start = int(match_sec_range.group(2))
        sec_end = int(match_sec_range.group(3))

        target = []
        for jf in all_jsons:
            if not jf.startswith(base_id):
                continue
            jm = re.search(r'[-_](\d+)(?:_|\.)', jf)
            if jm and sec_start <= int(jm.group(1)) <= sec_end:
                target.append(jf)

        return natsort.natsorted(target)

    # 模式 C: 420221.txt
    match_simple = re.match(r'^(\d+)\.txt$', txt_filename)
    if match_simple:
        base_id = match_simple.group(1)
        target = [j for j in all_jsons if j.startswith(base_id)]
        return natsort.natsorted(target)

    # 模式 D: 兜底
    match_id = re.match(r'^(\d+)', txt_filename)
    if match_id:
        base_id = match_id.group(1)
        target = [j for j in all_jsons if j.startswith(base_id)]
        return natsort.natsorted(target)

    return []


def print_branch_report():
    """打印多分支剧情检测报告"""
    if not BRANCH_REPORT:
        print("\n📋 未发现任何多分支剧情文件。")
        return

    total_files = sum(len(v) for v in BRANCH_REPORT.values())
    total_folders = len(BRANCH_REPORT)

    print("\n" + "=" * 70)
    print(f"🌿 多分支剧情报告：{total_folders} 个目录，{total_files} 个文件")
    print("=" * 70)

    for folder, infos in sorted(BRANCH_REPORT.items()):
        rel = folder
        for td in TARGET_DIRS:
            abs_td = os.path.join(os.getcwd(), td)
            if folder.startswith(abs_td):
                rel = os.path.relpath(folder, os.getcwd())
                break

        print(f"\n📁 {rel}")
        print(f"   包含 {len(infos)} 个分支文件:")

        for info in sorted(infos, key=lambda x: x['file']):
            groups_str = ', '.join(info['groups'])
            print(f"   ├─ 📄 {info['file']}")
            print(f"   │     Groups({info['group_count']}): [{groups_str}]")

            if info['selects']:
                for sel in info['selects']:
                    print(f"   │     🔀 [{sel['from_group']}] "
                          f"「{sel['text']}」→ {sel['to_group']} "
                          f"(alt:{sel['alt_id']})")

            if info['skip_transitions']:
                for skip in info['skip_transitions']:
                    skip_info = f"from={skip.get('from', '?')} → to={skip.get('to', '?')}"
                    can_skip = skip.get('canSkip', True)
                    if not can_skip:
                        skip_info += " [不可跳过]"
                    print(f"   │     ⏭️  {skip_info}")

        print(f"   └─ (共 {len(infos)} 个)")

    print("\n" + "=" * 70)
    print(f"📊 汇总: {total_files} 个分支文件 分布在 {total_folders} 个目录中")
    print("=" * 70)


def main():
    print("🚀 启动【全模式匹配 + 分支检测 + 取材记录修复版 + 跳过提速版】全量重建脚本...")

    rebuilt_count = 0
    skipped_count = 0

    for rel_dir in TARGET_DIRS:
        abs_root = os.path.join(os.getcwd(), rel_dir)
        if not os.path.exists(abs_root):
            print(f"  ⚠️ 目录不存在: {rel_dir}")
            continue

        print(f"\n📂 处理: {rel_dir}")

        for root, dirs, files in os.walk(abs_root):
            for f in files:
                if not f.endswith('.txt') or f.startswith('readme'):
                    continue

                txt_path = os.path.join(root, f)

                target_jsons = find_target_jsons(root, f)

                if not target_jsons:
                    continue

                full_content = "".join([
                    build_txt_from_json(os.path.join(root, j)) for j in target_jsons
                ])

                if full_content:
                    # 1. 检查文件是否已存在并且内容完全一致
                    is_identical = False
                    if os.path.exists(txt_path):
                        with open(txt_path, 'r', encoding='utf-8') as existing_file:
                            if existing_file.read() == full_content:
                                is_identical = True

                    # 2. 如果完全一致，则直接跳过，减少磁盘 I/O
                    if is_identical:
                        print(f"  ⏭️ 无变化，跳过: {f}")
                        skipped_count += 1
                        continue

                    # 3. 只有在内容不同（或新文件）时，才执行备份和写入
                    if os.path.exists(txt_path) and not os.path.exists(txt_path + '.bak'):
                        shutil.copy2(txt_path, txt_path + '.bak')

                    with open(txt_path, 'w', encoding='utf-8') as out:
                        out.write(full_content)
                    
                    rebuilt_count += 1

                    # 分支检测提示
                    folder_key = root
                    has_branch = False
                    if folder_key in BRANCH_REPORT:
                        branch_files = [b['file'] for b in BRANCH_REPORT[folder_key]]
                        has_branch = any(j in branch_files for j in target_jsons)

                    if re.match(r'^\d+-\d+_\d+-\d+\.txt$', f):
                        json_list = ', '.join(target_jsons[:3])
                        suffix = f"...+{len(target_jsons) - 3}" if len(target_jsons) > 3 else ""
                        branch_tag = "🌿" if has_branch else ""
                        print(f"  ✅{branch_tag} 范围更新: {f} → {len(target_jsons)} JSONs [{json_list}{suffix}]")
                    elif has_branch:
                        print(f"  ✅🌿 更新(含分支): {f}")
                    else:
                        print(f"  ✅ 更新完成: {f} ({len(target_jsons)} jsons)")

    print_branch_report()

    print(f"\n✨ 全部完成。更新了 {rebuilt_count} 个文件，跳过了 {skipped_count} 个无变化文件，"
          f"识别 {len(GLOBAL_ID_MAP)} 个角色 ID。")


if __name__ == "__main__":
    main()