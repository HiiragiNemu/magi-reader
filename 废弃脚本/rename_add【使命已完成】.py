# ==============================================================================
# Magia Record Folder Renamer (Update V3 - Mercury & AS Support)
#
# 目标：
# 1. 扫描 event_story, login_story, 和 main_story。
# 2. 根据最新的映射表更新文件夹名称。
# 3. 自动保留文件夹前的四位数字ID (例如: 2052 - 支线剧情...)。
# ==============================================================================

import os
import re

# --- 1. 活动剧情映射表 (集成水银文本) ---
NEW_EVENT_MAP = {
    # 水银提供的补充列表
    "5058": "三日月庄的Summer Vacation",
    "5059": "而后杜鹃花开",
    "5072": "CROSS CONNECTION～魔法少女铃音～",
    "5081": "初出茅庐女仆十七夜 阔达自在！",
    "5083": "起始和永远～The Lost Record～",
    "5096": "Magia Clash! ～魔法少女奈叶 Detonation～",
}

# --- 2. 登录剧情映射表 ---
NEW_LOGIN_MAP = {
    # 水银补充
    "6185": "新年抽签对话（2018-2022？）",
    "6348": "新年抽签（2023）",
    "6358": "少女史记维京篇实装预告",
    "6107": "无法变得坦率的14日",
}

# --- 3. 主线剧情 (Another Story) 映射表 ---
# 自动生成 2052-2060 和 2071-2081 的规则
NEW_MAIN_MAP = {}

# 第一部 AS (2052-2060: 第2章-第10章)
# 2052 -> 第2章, 2060 -> 第10章
for i in range(2052, 2061):
    chapter_num = i - 2050 # 52-50=2
    NEW_MAIN_MAP[str(i)] = f"支线剧情(AS) 第I部 第{chapter_num}章"

# 第二部 AS (2071-2081: 第1章-第11章)
# 2071 -> 第1章, 2081 -> 第11章
for i in range(2071, 2082):
    chapter_num = i - 2070 # 71-70=1
    NEW_MAIN_MAP[str(i)] = f"支线剧情(AS) 第II部 第{chapter_num}章"


def sanitize_foldername(name):
    # 移除不可见字符和非法符号
    name = re.sub(r'[\u200e\u200f]', '', name)
    return re.sub(r'[<>:"/\\|?*]', '', name).strip()

def rename_folders(base_path):
    print(f"\n[RENAMING] {os.path.basename(base_path)}...")
    scenarios_root = os.path.join(base_path, "Scenarios_full")
    
    # 定义处理任务：(文件夹名, 映射表)
    tasks = [
        ("event_story", NEW_EVENT_MAP),
        ("login_story", NEW_LOGIN_MAP),
        ("main_story", NEW_MAIN_MAP)
    ]
    
    renamed_count = 0
    
    for category, map_data in tasks:
        target_dir = os.path.join(scenarios_root, category)
        if not os.path.exists(target_dir): continue
        
        # 遍历目录下的文件夹
        for folder_name in os.listdir(target_dir):
            folder_path = os.path.join(target_dir, folder_name)
            if not os.path.isdir(folder_path): continue
            
            # 提取 ID (兼容 "Main_2052", "Event_5101", "5101 - OldName" 等格式)
            match = re.search(r'(\d{4,})', folder_name)
            if not match: continue
            
            story_id = match.group(1)
            
            # 如果ID在我们的映射表中
            if story_id in map_data:
                new_title = map_data[story_id]
                # 核心规则：保留4位ID + 新标题
                new_folder_name = f"{story_id} - {sanitize_foldername(new_title)}"
                new_folder_path = os.path.join(target_dir, new_folder_name)
                
                # 如果名字不同，执行重命名
                if folder_path != new_folder_path:
                    try:
                        os.rename(folder_path, new_folder_path)
                        # print(f"  Renamed: {folder_name} -> {new_folder_name}")
                        renamed_count += 1
                    except Exception as e:
                        print(f"  Error renaming {folder_name}: {e}")

    print(f"  -> Updated {renamed_count} folder names.")

if __name__ == "__main__":
    script_dir = os.getcwd()
    # 包含所有需要处理的根目录
    targets = [
        "magireco-source-master", 
        "magireco-translate-data-master", 
        "Magireco_Extracted/magireco-official-translate-data-master"
    ]
    
    for t in targets:
        full_path = os.path.join(script_dir, t)
        if os.path.exists(full_path):
            rename_folders(full_path)