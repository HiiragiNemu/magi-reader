import os
import re
import shutil


def main():
    # 目录路径（按需修改）
    src_dir = r"A:\magi-reader\magireco-translate-data-master\Scenarios_full"
    target_dir = r"A:\magireco-cn-patch\madomagi\resource"

    # 匹配 _v1 / _v1(1) / _v1 (2) 等后缀，保留 .json
    pattern = re.compile(r"_v1(?:\s*\(\d+\))?(\.json)$", re.IGNORECASE)

    print(f"正在读取源目录(递归): {src_dir} ...")
    if not os.path.exists(src_dir):
        print("错误: 源目录不存在！")
        return
    if not os.path.exists(target_dir):
        print("错误: 目标目录不存在！")
        return

    # 1) 递归扫描源目录所有 json 文件
    src_files_info = []
    for root, _, files in os.walk(src_dir):
        for filename in files:
            if filename.lower().endswith(".json"):
                full_path = os.path.join(root, filename)
                rel_path = os.path.relpath(full_path, src_dir)
                src_files_info.append(
                    {
                        "filename": filename,   # 纯文件名（用于匹配）
                        "full_path": full_path, # 源文件绝对路径
                        "rel_path": rel_path,   # 相对路径（用于打印）
                    }
                )

    total_src_count = len(src_files_info)

    # 2) 去后缀并检查源目录内部重复（按去后缀后的文件名）
    stripped_to_sources = {}
    for item in src_files_info:
        stripped_name = pattern.sub(r"\1", item["filename"])
        stripped_to_sources.setdefault(stripped_name, []).append(item)

    print("\n" + "=" * 40)
    print("【步骤1】内部重复文件检查 (源目录递归)")
    print("=" * 40)
    has_internal_dupes = False
    for stripped_name, sources in stripped_to_sources.items():
        if len(sources) > 1:
            has_internal_dupes = True
            print(f"[警告] 发现内部重复！处理后文件名 '{stripped_name}' 对应多个源文件:")
            for s in sources:
                print(f"       - {s['rel_path']}")
    if not has_internal_dupes:
        print("未发现去除后缀后产生冲突的内部重复文件，状态良好。")

    # 3) 递归扫描目标目录所有 json 文件，建立文件名 -> 路径列表 映射
    print("\n正在扫描目标嵌套目录寻找匹配文件...")
    target_files_map = {}
    for root, _, files in os.walk(target_dir):
        for filename in files:
            if filename.lower().endswith(".json"):
                target_files_map.setdefault(filename, []).append(os.path.join(root, filename))

    # 4) 匹配
    matched_files = []
    unmatched_files = []

    for stripped_name, sources in stripped_to_sources.items():
        if stripped_name in target_files_map:
            for src_item in sources:
                for t_path in target_files_map[stripped_name]:
                    matched_files.append(
                        {
                            "source_rel": src_item["rel_path"],
                            "src_path": src_item["full_path"],
                            "target_path": t_path,
                        }
                    )
        else:
            for src_item in sources:
                unmatched_files.append(
                    {
                        "source_rel": src_item["rel_path"],
                        "expected_name": stripped_name,
                    }
                )

    # 5) 匹配综述
    print("\n" + "=" * 40)
    print("【步骤2】匹配信息综述")
    print("=" * 40)
    print(f"总计读取源目录原始文件数量(含子目录): {total_src_count} 个")
    print(f"共匹配到可替换的目标文件数量      : {len(matched_files)} 个")
    print(f"存在于源目录但没有找到匹配        : {len(unmatched_files)} 个")

    if unmatched_files:
        print("\n--- 以下是没有在目标目录中找到匹配的文件 ---")
        for uf in unmatched_files:
            print(f"  - [未匹配] {uf['source_rel']} (试图寻找: {uf['expected_name']})")

    # 6) 用户确认
    print("\n" + "=" * 40)
    user_input = input("请确认无误。是否开始进行全面替换？(输入 y 确认，其他取消): ")
    if user_input.strip().lower() != "y":
        print("操作已取消。没有文件被修改。")
        return

    # 7) 执行替换
    print("\n" + "=" * 40)
    print("【步骤3】开始执行替换...")
    print("=" * 40)

    replaced_count = 0
    for item in matched_files:
        try:
            # copy2 覆盖并尽量保留元数据
            shutil.copy2(item["src_path"], item["target_path"])
            print(f"[替换成功] {item['source_rel']}  -->  {item['target_path']}")
            replaced_count += 1
        except Exception as e:
            print(f"[替换失败] {item['source_rel']}  -->  {item['target_path']} | 错误原因: {e}")

    # 8) 最终核对
    print("\n" + "=" * 40)
    print("【步骤4】最终替换结果核对")
    print("=" * 40)
    print(f"源目录原始总文件数量(含子目录): {total_src_count}")
    print(f"实际成功发生替换的动作次数    : {replaced_count}")

    if replaced_count == total_src_count:
        print("\n>>> 核对通过: 替换动作数与源文件总数一致。")
    else:
        print("\n>>> 核对提示: 替换成功数与源文件总数不一致。")

        if unmatched_files:
            print(f"    原因1: 有 {len(unmatched_files)} 个源文件在目标目录中不存在。")

            print("\n--- 未匹配文件清单（完整）---")
            for i, uf in enumerate(unmatched_files, 1):
                print(f"{i:04d}. {uf['source_rel']}  (查找目标名: {uf['expected_name']})")

            report_path = os.path.join(os.getcwd(), "unmatched_files.txt")
            with open(report_path, "w", encoding="utf-8") as f:
                f.write("未匹配文件清单\n")
                f.write("=" * 40 + "\n")
                for i, uf in enumerate(unmatched_files, 1):
                    f.write(f"{i:04d}. {uf['source_rel']}  (查找目标名: {uf['expected_name']})\n")

            print(f"\n未匹配清单已保存到: {report_path}")

        if has_internal_dupes:
            print("    原因2: 源目录内部有重复文件名(去后缀后)导致多对一覆盖。")

        if replaced_count > total_src_count and not unmatched_files:
            print("    原因3: 目标目录多个子目录存在同名文件，全部被同步替换。")


if __name__ == "__main__":
    main()