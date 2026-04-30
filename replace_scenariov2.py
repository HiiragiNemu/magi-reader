import os
import re
import shutil

def main():
    # 定义目录路径
    src_dir = r"A:\scenario"
    scan_dir = r"A:\magi-reader\magireco-source-master"        # 仅扫描，不修改，用于获取目录结构
    build_dir = r"A:\magi-reader\magireco-translate-data-master" # 构建目标目录，用于转移文件
    
    # 正则表达式：匹配 _v1 以及 _v1 (1) 等，并保留 .json 扩展名
    pattern = re.compile(r'_v1(?:\s*\(\d+\))?(\.json)$', re.IGNORECASE)
    
    print(f"正在读取需要处理的源目录: {src_dir} ...")
    if not os.path.exists(src_dir):
        print("错误: 源目录不存在！")
        return
    if not os.path.exists(scan_dir):
        print(f"错误: 用于扫描结构的目录不存在！({scan_dir})")
        return
    
    # 确保构建的基础目录存在，不存在则主动创建基础目录
    if not os.path.exists(build_dir):
        os.makedirs(build_dir)

    # 1. 获取源目录下的所有 json 文件
    src_files =[f for f in os.listdir(src_dir) if f.lower().endswith('.json')]
    total_src_count = len(src_files)
    
    # 2. 去除后缀，并检查 A:\scenario 内部是否有重复文件
    stripped_to_original = {}
    for f in src_files:
        stripped = pattern.sub(r'\1', f)
        if stripped not in stripped_to_original:
            stripped_to_original[stripped] =[]
        stripped_to_original[stripped].append(f)
        
    print("\n" + "="*45)
    print("【步骤1】内部重复文件检查 (A:\\scenario)")
    print("="*45)
    has_internal_dupes = False
    for stripped, originals in stripped_to_original.items():
        if len(originals) > 1:
            has_internal_dupes = True
            print(f"[警告] 发现内部重复！处理后的文件名 '{stripped}' 对应了多个原始文件:")
            for orig in originals:
                print(f"       - {orig}")
                
    if not has_internal_dupes:
        print("未发现去除后缀名后产生冲突的内部重复文件，状态良好。")

    # 3. 扫描源数据仓库（scan_dir），记录所有符合条件的 json 文件的相对目录树
    print(f"\n正在扫描目录 {scan_dir} 以记录结构...")
    scan_files_map = {}  # 结构: { 'stripped_name.json' :['相对路径1', '相对路径2', ...] }
    for root, dirs, files in os.walk(scan_dir):
        for f in files:
            if f.lower().endswith('.json'):
                if f not in scan_files_map:
                    scan_files_map[f] =[]
                # 获取该文件所在的相对目录路径 (比如 scenario\subfolder)
                rel_dir = os.path.relpath(root, scan_dir)
                scan_files_map[f].append(rel_dir)

    # 4. 进行匹配比对
    matched_files = []
    unmatched_files =[]
    
    for stripped, originals in stripped_to_original.items():
        for orig in originals:
            if stripped in scan_files_map:
                # 针对扫描记录中该文件存在的所有相对目录，生成待构建转移任务
                for rel_dir in scan_files_map[stripped]:
                    matched_files.append({
                        'original': orig,
                        'stripped': stripped,
                        'src_path': os.path.join(src_dir, orig),
                        'rel_dir': rel_dir
                    })
            else:
                unmatched_files.append(orig)

    # 5. 打印替换前的匹配综述
    print("\n" + "="*45)
    print("【步骤2】扫描匹配信息综述")
    print("="*45)
    print(f"总计读取 A:\\scenario 原始文件数量         : {total_src_count} 个")
    print(f"在 source 库中扫描出将要同步转移的目标数量 : {len(matched_files)} 个动作")
    print(f"存在于 A:\\scenario 但在 source 库中未找到 : {len(unmatched_files)} 个")
    
    if unmatched_files:
        print("\n--- 以下是没有在 source 目录中查找到对应结构的文件 ---")
        for uf in unmatched_files:
            print(f"  - [未匹配] {uf} (试图寻找: {pattern.sub(r'\\1', uf)})")

    # 6. 用户确认
    print("\n" + "="*45)
    print(f"待构建与转移到的主目录为: {build_dir}")
    user_input = input("请确认无误。是否开始在 translate-data 中构建嵌套目录并转移文件？(输入 y 确认): ")
    
    if user_input.strip().lower() != 'y':
        print("操作已取消。没有文件被复制或构建。")
        return

    # 7. 开始构建目录并转移文件
    print("\n" + "="*45)
    print("【步骤3】开始执行目录构建与文件转移...")
    print("="*45)
    
    transferred_count = 0
    for item in matched_files:
        try:
            # 计算将要克隆出来的完整目标目录路径
            target_dest_dir = os.path.join(build_dir, item['rel_dir'])
            
            # 如果该多级子目录不存在，则创建它 (相当于克隆了 source 库的该分支结构)
            if not os.path.exists(target_dest_dir):
                os.makedirs(target_dest_dir)
            
            # 完整的目标文件路径（这里转移过去后，使用去除后缀的标准名称）
            target_file_path = os.path.join(target_dest_dir, item['stripped'])
            
            # 复制并重命名文件
            shutil.copy2(item['src_path'], target_file_path)
            
            # 打印包含所有嵌套层次的绝对路径
            print(f"[转移成功] {item['original']}  -->  {target_file_path}")
            transferred_count += 1
        except Exception as e:
            print(f"[转移失败] {item['original']} | 错误原因: {e}")

    # 8. 最终核对
    print("\n" + "="*45)
    print("【步骤4】最终转移结果核对")
    print("="*45)
    print(f"A:\\scenario 原始总文件数量       : {total_src_count}")
    print(f"实际成功发生目录构建与转移的次数  : {transferred_count}")
    
    if transferred_count == total_src_count:
        print("\n>>> 核对通过: 全部转移文件综述与 A:\\scenario 原始文件数量 **完全一致**！")
    else:
        print("\n>>> 核对提示: 转移成功数与 A:\\scenario 原始文件数量 **不一致**！")
        if len(unmatched_files) > 0:
            print(f"    原因1: 有 {len(unmatched_files)} 个源文件在 source 扫描库中根本找不到对照。")
        if has_internal_dupes:
            print("    原因2: A:\\scenario 内部有重复文件覆盖了目标库的同一个位置。")
        if transferred_count > total_src_count and len(unmatched_files) == 0:
            print("    原因3: source 扫描库中，同一个文件存在于多个不同的子文件夹，现已全部对应构建并同步转移。")

if __name__ == "__main__":
    main()