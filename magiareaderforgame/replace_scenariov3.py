import os
import shutil

def main():
    # ---------------- 1. 核心目录配置 ----------------
    # 源文件所在的基础目录（需要在里面找出列表中的文件）
    src_dir = r"A:\magireco-cn-patch\madomagi\resource"
    # 仅扫描，不修改，用于获取目录结构的源库
    scan_dir = r"A:\magi-reader\magireco-source-master"
    # 构建目标目录，用于克隆目录结构并转移文件
    build_dir = r"A:\magi-reader\magireco-translate-data-master"

    # ---------------- 2. 指定的文件列表 ----------------
    # 将你提供的内容作为多行字符串放入，脚本会自动清洗和过滤
    raw_file_list = """
scenario_1
103301-10_5hsw3.json
103301-11_5hsw3.json
103301-12_5hsw3.json
103301-13_5hsw3.json
103301-14_5hsw3.json
103301-15_5hsw3.json
103301-16_5hsw3.json
103301-17_5hsw3.json
103301-18_5hsw3.json
103301-1_5hsw3.json
103301-2_5hsw3.json
103301-3_5hsw3.json
103301-4_5hsw3.json
103301-5_5hsw3.json
103301-6_5hsw3.json
103301-7_5hsw3.json
103301-8_5hsw3.json
103301-9_5hsw3.json
103302-10_5hsw3.json
103302-11_5hsw3.json
103302-12_5hsw3.json
103302-13_5hsw3.json
103302-14_5hsw3.json
103302-15_5hsw3.json
103302-16_5hsw3.json
103302-1_5hsw3.json
103302-2_5hsw3.json
103302-3_5hsw3.json
103302-4_5hsw3.json
103302-5_5hsw3.json
103302-6_5hsw3.json
103302-7_5hsw3.json
103302-8_5hsw3.json
103302-9_5hsw3.json
103303-10_5hsw3.json
103303-11_5hsw3.json
103303-12_5hsw3.json
103303-13_5hsw3.json
103303-14_5hsw3.json
103303-15_5hsw3.json
103303-16_5hsw3.json
103303-17_5hsw3.json
103303-18_5hsw3.json
103303-19_5hsw3.json
103303-1_5hsw3.json
103303-20_5hsw3.json
103303-21_5hsw3.json
103303-22_5hsw3.json
103303-23_5hsw3.json
103303-24_5hsw3.json
103303-2_5hsw3.json
103303-3_5hsw3.json
103303-4_5hsw3.json
103303-5_5hsw3.json
103303-6_5hsw3.json
103303-7_5hsw3.json
103303-8_5hsw3.json
103303-9_5hsw3.json
103304-10_eP5wU.json
103304-11_eP5wU.json
103304-1_eP5wU.json
103304-2_eP5wU.json
103304-3_eP5wU.json
103304-4_eP5wU.json
103304-5_eP5wU.json
103304-6_eP5wU.json
103304-7_eP5wU.json
103304-8_eP5wU.json
103304-9_eP5wU.json
103305-10_eP5wU.json
103305-11_eP5wU.json
103305-12_eP5wU.json
103305-13_eP5wU.json
103305-14_eP5wU.json
103305-15_eP5wU.json
103305-16_eP5wU.json
103305-17_eP5wU.json
103305-18_eP5wU.json
103305-19_eP5wU.json
103305-1_eP5wU.json
103305-2_eP5wU.json
103305-3_eP5wU.json
103305-4_eP5wU.json
103305-5_eP5wU.json
103305-6_eP5wU.json
103305-7_eP5wU.json
103305-8_eP5wU.json
103305-9_eP5wU.json
103306-1_k0jv8.json
103306-2_k0jv8.json
103306-3_k0jv8.json
103306-4_k0jv8.json
103306-5_k0jv8.json
103306-6_k0jv8.json
103306-7_k0jv8.json
scenario_5
520510-0.json
520510-10_bXUCP.json
520510-1_bXUCP.json
520510-2_bXUCP.json
520510-3_bXUCP.json
520510-4_bXUCP.json
520510-5_bXUCP.json
520510-6_bXUCP.json
520510-7_bXUCP.json
520510-8_bXUCP.json
520510-9_bXUCP.json
520520-10_LNbJr.json
520520-1_LNbJr.json
520520-2_LNbJr.json
520520-3_LNbJr.json
520520-4_LNbJr.json
520520-5_LNbJr.json
520520-6_LNbJr.json
520520-7_LNbJr.json
520520-8_LNbJr.json
520520-9_LNbJr.json
103305-6_eP5wU.json
103305-7_eP5wU.json
    """
    
    # 清洗数据：只要 .json 结尾的行，并使用 set 去重
    required_files = {line.strip() for line in raw_file_list.split('\n') if line.strip().lower().endswith('.json')}
    
    print(f"解析列表完毕，共需处理 {len(required_files)} 个独立的目标 JSON 文件。\n")
    
    # 检查基本目录是否存在
    for d in[src_dir, scan_dir]:
        if not os.path.exists(d):
            print(f"错误: 必需的目录不存在: {d}")
            return
            
    if not os.path.exists(build_dir):
        os.makedirs(build_dir)

    # ---------------- 3. 从 src_dir 中找出这些文件的物理路径 ----------------
    print(f"正在 {src_dir} 及其子目录中搜索目标文件...")
    found_in_src = {}
    for root, dirs, files in os.walk(src_dir):
        for f in files:
            if f in required_files:
                if f not in found_in_src:
                    found_in_src[f] =[]
                found_in_src[f].append(os.path.join(root, f))
                
    # 检查是否有没有找到的文件，或者有重复的源文件
    missing_in_src =[]
    for req in required_files:
        if req not in found_in_src:
            missing_in_src.append(req)
        elif len(found_in_src[req]) > 1:
            print(f"[警告] {req} 在 patch 目录中存在多份副本，脚本将默认提取找到的第一个: {found_in_src[req][0]}")

    # ---------------- 4. 扫描 scan_dir，学习需要转移的目录结构 ----------------
    print(f"正在扫描 {scan_dir} 记录这些文件的目录结构...")
    scan_files_map = {}
    for root, dirs, files in os.walk(scan_dir):
        for f in files:
            if f in required_files:
                rel_dir = os.path.relpath(root, scan_dir)
                if f not in scan_files_map:
                    scan_files_map[f] =[]
                scan_files_map[f].append(rel_dir)

    # ---------------- 5. 比对合并转移任务 ----------------
    matched_tasks = []
    missing_in_scan =[]
    
    for req in required_files:
        # 如果在 patch 文件夹找不到它，跳过
        if req not in found_in_src:
            continue
            
        # 如果在 source 文件夹找不到它的结构记录，跳过并记录
        if req not in scan_files_map:
            missing_in_scan.append(req)
            continue
            
        # 准备转移任务
        src_file_path = found_in_src[req][0]  # 取第一个找到的源文件物理路径
        for rel_dir in scan_files_map[req]:
            matched_tasks.append({
                'filename': req,
                'src_path': src_file_path,
                'rel_dir': rel_dir
            })

    # ---------------- 6. 打印综述 ----------------
    print("\n" + "="*50)
    print("【比对与检索结果综述】")
    print("="*50)
    print(f"需求列表文件总数     : {len(required_files)} 个")
    print(f"在 patch 目录中找到  : {len(required_files) - len(missing_in_src)} 个")
    print(f"在 source 库中匹配到 : {len(required_files) - len(missing_in_src) - len(missing_in_scan)} 个 (对应 {len(matched_tasks)} 次构建/转移操作)")
    
    if missing_in_src:
        print("\n[未找到源文件] 以下文件在 A:\\magireco-cn-patch\\madomagi\\resource 未找到:")
        for m in missing_in_src:
            print(f"  - {m}")
            
    if missing_in_scan:
        print("\n[无法定位结构] 以下文件有源文件，但在 source 库中找不到对应目录无法学习位置:")
        for m in missing_in_scan:
            print(f"  - {m}")

    if not matched_tasks:
        print("\n未生成任何可执行任务，请检查路径和列表。程序退出。")
        return

    # ---------------- 7. 用户确认与执行 ----------------
    print("\n" + "="*50)
    print(f"待构建与转移到的主目录为: {build_dir}")
    user_input = input("确认无误。是否开始在 translate-data 中构建嵌套目录并覆盖文件？(输入 y 确认): ")
    
    if user_input.strip().lower() != 'y':
        print("操作已取消。没有文件被修改。")
        return

    print("\n" + "="*50)
    print("【开始执行目录构建与文件转移】")
    print("="*50)
    
    success_count = 0
    for task in matched_tasks:
        try:
            # 构建绝对的目标文件夹路径并创建它
            target_dest_dir = os.path.join(build_dir, task['rel_dir'])
            if not os.path.exists(target_dest_dir):
                os.makedirs(target_dest_dir)
                
            # 目标文件的绝对路径
            target_file_path = os.path.join(target_dest_dir, task['filename'])
            
            # 复制覆盖
            shutil.copy2(task['src_path'], target_file_path)
            print(f"[成功转移] {task['filename']} --> {target_file_path}")
            success_count += 1
        except Exception as e:
            print(f"[转移失败] {task['filename']} | 错误原因: {e}")

    # ---------------- 8. 最终核对 ----------------
    print("\n" + "="*50)
    print("【任务执行完毕】")
    print("="*50)
    print(f"计划执行转移任务次数 : {len(matched_tasks)}")
    print(f"实际成功转移文件次数 : {success_count}")
    if success_count == len(matched_tasks):
        print(">>> 转移完美结束！")

if __name__ == "__main__":
    main()