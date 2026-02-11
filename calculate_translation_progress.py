# ==============================================================================
# Magia Record Translation Progress Calculator
#
# 目标：
# 1. 对比 Source (日文源) 与 Translate (汉化源)。
# 2. 计算目录缺失情况和文件缺失情况。
# 3. 生成详细的进度报告。
# ==============================================================================

import os

def scan_directory(root_path):
    """
    扫描目录，返回两个集合：
    1. folders: 相对路径集合 (e.g., 'event_story/5010 - Christmas')
    2. files:   相对路径集合 (e.g., 'event_story/.../501001_combined.txt')
    """
    folders = set()
    files = set()
    
    base_len = len(root_path) + 1
    
    for root, dirs, filenames in os.walk(root_path):
        # 记录相对文件夹路径
        rel_folder = root[base_len:]
        if rel_folder:
            folders.add(rel_folder)
            
        for f in filenames:
            if f.endswith(".txt") and "_combined" in f:
                rel_file = os.path.join(rel_folder, f)
                files.add(rel_file)
                
    return folders, files

def main():
    base_dir = os.getcwd()
    dir_source = os.path.join(base_dir, "magireco-source-master", "Scenarios_full")
    dir_trans = os.path.join(base_dir, "magireco-translate-data-master", "Scenarios_full")
    
    if not os.path.exists(dir_source) or not os.path.exists(dir_trans):
        print("Error: Source or Translate directories not found.")
        return

    print("--- Scanning JP Source (Total Content) ---")
    src_folders, src_files = scan_directory(dir_source)
    print(f"Total Folders: {len(src_folders)}")
    print(f"Total Files:   {len(src_files)}")

    print("\n--- Scanning CN Translate (Current Progress) ---")
    trans_folders, trans_files = scan_directory(dir_trans)
    print(f"Total Folders: {len(trans_folders)}")
    print(f"Total Files:   {len(trans_files)}")

    # 计算差值
    missing_folders = sorted(list(src_folders - trans_folders))
    missing_files = sorted(list(src_files - trans_files))
    
    # 过滤掉子文件夹，只看一级分类目录差异（为了报告简洁）
    # 例如：如果 'event_story/Event_5058' 缺失，就不需要报告它里面的子目录了
    missing_root_folders = []
    for f in missing_folders:
        # 只报告类似 'category/folder_name' 这一级的缺失
        parts = f.split(os.sep)
        if len(parts) == 2: 
            missing_root_folders.append(f)

    # 计算进度
    if len(src_files) > 0:
        progress = (len(trans_files) / len(src_files)) * 100
    else:
        progress = 0

    # 生成报告
    report_name = "translation_progress_report.txt"
    with open(report_name, "w", encoding="utf-8") as f:
        f.write("=== Magia Record Translation Progress Report ===\n\n")
        f.write(f"Overall Progress: {progress:.2f}%\n")
        f.write(f"  - Files: {len(trans_files)} / {len(src_files)}\n")
        f.write(f"  - Folders: {len(trans_folders)} / {len(src_folders)}\n\n")
        
        f.write("=== MISSING DIRECTORIES (Totally Untranslated Arcs/Events) ===\n")
        f.write(f"Count: {len(missing_root_folders)}\n\n")
        
        # 按类别分组打印
        categories = {}
        for folder in missing_root_folders:
            cat = folder.split(os.sep)[0]
            if cat not in categories: categories[cat] = []
            categories[cat].append(folder)
            
        for cat in sorted(categories.keys()):
            f.write(f"--- {cat} ---\n")
            for item in sorted(categories[cat]):
                f.write(f"  [ ] {item}\n")
            f.write("\n")
            
        f.write("\n=== MISSING FILES (Partial Translations or Missing Chapters) ===\n")
        f.write(f"Count: {len(missing_files)}\n")
        f.write("(See file 'missing_files_list.txt' for the full list if this is too long)\n")

    # 另外生成一个详细的文件丢失列表
    with open("missing_files_list.txt", "w", encoding="utf-8") as f:
        for item in missing_files:
            f.write(f"{item}\n")

    print(f"\nAnalysis Complete!")
    print(f"Overall Progress: {progress:.2f}%")
    print(f"Detailed report saved to: {report_name}")
    print(f"Full missing file list saved to: missing_files_list.txt")

if __name__ == "__main__":
    main()