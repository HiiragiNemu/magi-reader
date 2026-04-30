import os
import re

def scan_directory(root_path):
    """
    扫描目录，查找所有txt文件，并尝试提取一个标准化的 ID 用于对比
    """
    folders = set()
    files = set()
    
    if not os.path.exists(root_path):
        return folders, files

    base_len = len(root_path) + 1
    
    for root, dirs, filenames in os.walk(root_path):
        rel_folder = root[base_len:]
        if rel_folder:
            folders.add(rel_folder)
            
        for f in filenames:
            # 排除 readme 和非 txt 文件
            if f.endswith(".txt") and not f.lower().startswith("readme"):
                # 标准化文件名对比：
                # 去掉 _jp.txt, _cn.txt, _combined.txt 以及末尾的 _cn, _jp
                clean_name = f.replace(".txt", "")
                clean_name = re.sub(r'_(jp|cn|combined)$', '', clean_name)
                
                rel_file = os.path.join(rel_folder, clean_name)
                files.add(rel_file)
                
    return folders, files

def main():
    base_dir = os.getcwd()
    # 尝试匹配可能的路径名（处理大小写或微小差异）
    dir_source = os.path.join(base_dir, "magireco-source-master", "Scenarios_full")
    dir_trans = os.path.join(base_dir, "magireco-translate-data-master", "Scenarios_full")
    
    print(f"检查路径 1: {dir_source}")
    print(f"检查路径 2: {dir_trans}")

    src_folders, src_files = scan_directory(dir_source)
    print(f"--- 扫描日文源 (JP) ---")
    print(f"找到文件夹: {len(src_folders)}")
    print(f"找到 TXT 文件: {len(src_files)}")

    trans_folders, trans_files = scan_directory(dir_trans)
    print(f"\n--- 扫描汉化源 (CN) ---")
    print(f"找到文件夹: {len(trans_folders)}")
    print(f"找到 TXT 文件: {len(trans_files)}")

    if len(src_files) == 0:
        print("\n❌ 错误: 日文源目录中没有找到任何 .txt 文件！")
        print("提示: 请先运行 reconstruction.py 来将 JSON 转换为 TXT。")
        return

    # 计算差值
    missing_files = sorted(list(src_files - trans_files))
    
    # 计算进度
    progress = (len(trans_files) / len(src_files)) * 100

    # 生成报告
    report_name = "translation_progress_report.txt"
    with open(report_name, "w", encoding="utf-8") as f:
        f.write("=== Magia Record Translation Progress Report ===\n\n")
        f.write(f"Overall Progress: {progress:.2f}%\n")
        f.write(f"  - Files: {len(trans_files)} / {len(src_files)}\n")
        f.write(f"  - Folders: {len(trans_folders)} / {len(src_folders)}\n\n")
        f.write(f"缺失文件详情请查看 missing_files_list.txt\n")

    with open("missing_files_list.txt", "w", encoding="utf-8") as f:
        for item in missing_files:
            f.write(f"{item}\n")

    print(f"\n✅ 分析完成!")
    print(f"当前总进度: {progress:.2f}%")
    print(f"详细报告已生成。")

if __name__ == "__main__":
    main()