import os
import re
import shutil

def main():
    # 定义目录路径
    src_dir = r"A:\scenario"
    target_dir = r"A:\magi-reader\magireco-translate-data-master\Scenarios_full"
    
    # 正则表达式：匹配 _v1 以及 _v1 (1)、_v1(1)、_v1 (2) 等等，并保留 .json 扩展名
    pattern = re.compile(r'_v1(?:\s*\(\d+\))?(\.json)$', re.IGNORECASE)
    
    print(f"正在读取源目录: {src_dir} ...")
    if not os.path.exists(src_dir):
        print("错误: 源目录不存在！")
        return
    if not os.path.exists(target_dir):
        print("错误: 目标目录不存在！")
        return

    # 1. 获取源目录下的所有 json 文件
    src_files =[f for f in os.listdir(src_dir) if f.lower().endswith('.json')]
    total_src_count = len(src_files)
    
    # 2. 去除后缀，并检查 A:\scenario 内部是否有重复文件
    stripped_to_original = {}
    for f in src_files:
        # 剥离 _v1 和 _v1 (x)
        stripped = pattern.sub(r'\1', f)
        if stripped not in stripped_to_original:
            stripped_to_original[stripped] = []
        stripped_to_original[stripped].append(f)
        
    print("\n" + "="*40)
    print("【步骤1】内部重复文件检查 (A:\\scenario)")
    print("="*40)
    has_internal_dupes = False
    for stripped, originals in stripped_to_original.items():
        if len(originals) > 1:
            has_internal_dupes = True
            print(f"[警告] 发现内部重复！处理后的文件名 '{stripped}' 对应了多个原始文件:")
            for orig in originals:
                print(f"       - {orig}")
                
    if not has_internal_dupes:
        print("未发现去除后缀名后产生冲突的内部重复文件，状态良好。")

    # 3. 遍历目标目录（包含大量嵌套子目录），建立目标文件映射库
    print("\n正在扫描目标嵌套目录寻找匹配文件...")
    target_files_map = {}
    for root, dirs, files in os.walk(target_dir):
        for f in files:
            if f.lower().endswith('.json'):
                if f not in target_files_map:
                    target_files_map[f] = []
                target_files_map[f].append(os.path.join(root, f))

    # 4. 进行匹配比对
    matched_files = []
    unmatched_files =[]
    
    for stripped, originals in stripped_to_original.items():
        for orig in originals:
            if stripped in target_files_map:
                # 考虑到目标目录哪怕重名也可能在多个不同子目录有一模一样的文件
                for t_path in target_files_map[stripped]:
                    matched_files.append({
                        'original': orig,
                        'stripped': stripped,
                        'src_path': os.path.join(src_dir, orig),
                        'target_path': t_path
                    })
            else:
                unmatched_files.append(orig)

    # 5. 打印替换前的匹配综述
    print("\n" + "="*40)
    print("【步骤2】匹配信息综述")
    print("="*40)
    print(f"总计读取 A:\\scenario 原始文件数量 : {total_src_count} 个")
    print(f"共匹配到可替换的目标文件数量       : {len(matched_files)} 个")
    print(f"存在于 A:\\scenario 但没有找到匹配 : {len(unmatched_files)} 个")
    
    if unmatched_files:
        print("\n--- 以下是没有在目标目录中找到匹配的文件 ---")
        for uf in unmatched_files:
            print(f"  - [未匹配] {uf} (试图寻找: {pattern.sub(r'\\1', uf)})")

    # 6. 用户确认
    print("\n" + "="*40)
    user_input = input("请确认无误。是否开始进行全面替换？(输入 y 确认，其他取消): ")
    
    if user_input.strip().lower() != 'y':
        print("操作已取消。没有文件被修改。")
        return

    # 7. 开始替换并打印动作
    print("\n" + "="*40)
    print("【步骤3】开始执行替换...")
    print("="*40)
    
    replaced_count = 0
    for item in matched_files:
        try:
            # 使用 copy2 覆盖目标文件，保留了文件元数据(为了安全不直接用move删除源文件)
            shutil.copy2(item['src_path'], item['target_path'])
            print(f"[替换成功] {item['original']}  -->  {item['target_path']}")
            replaced_count += 1
        except Exception as e:
            print(f"[替换失败] {item['original']}  -->  {item['target_path']} | 错误原因: {e}")

    # 8. 最终核对
    print("\n" + "="*40)
    print("【步骤4】最终替换结果核对")
    print("="*40)
    print(f"A:\\scenario 原始总文件数量 : {total_src_count}")
    print(f"实际成功发生替换的动作次数  : {replaced_count}")
    
    # 因为存在未匹配的情况，或者1个源文件覆盖了子目录下2个同名文件，都会导致数量差异
    if replaced_count == total_src_count:
        print("\n>>> 核对通过: 全部替换文件综述与 A:\\scenario 原始文件数量 **完全一致**！")
    else:
        print("\n>>> 核对提示: 替换成功数与 A:\\scenario 原始文件数量 **不一致**！")
        if len(unmatched_files) > 0:
            print(f"    原因1: 有 {len(unmatched_files)} 个源文件在目标文件夹中根本不存在。")
        if has_internal_dupes:
            print("    原因2: A:\\scenario 内部有重复文件覆盖了同一个目标文件。")
        if replaced_count > total_src_count and len(unmatched_files) == 0:
            print("    原因3: 目标资源子目录中，有同一个文件出现在了不同的文件夹，全部被同步替换。")

if __name__ == "__main__":
    main()