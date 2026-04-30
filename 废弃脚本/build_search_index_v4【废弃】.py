# build_search_index_v5.py
import os
import json
import re

TARGET_PUBLIC_DIR = "website/public"
OUTPUT_FILE = os.path.join(TARGET_PUBLIC_DIR, "search_content.json")
DATA_DIR = os.path.join(TARGET_PUBLIC_DIR, "data")

def main():
    print("正在构建双语搜索索引 (V5) —— 已修复 ID 一致性 + 红字标签...")
    search_index = []

    for root, _, files in os.walk(DATA_DIR):
        for file in files:
            if not file.endswith(".txt"): continue
            lang = "cn" if "_cn.txt" in file else "jp" if "_jp.txt" in file else None
            if not lang: continue

            # ←←← 关键修复：和 generate_index_v10.py 保持完全一致的 ID 生成规则
            raw_id = file.replace("_cn.txt", "").replace("_jp.txt", "").split("_")[0]

            path = os.path.join(root, file)
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            # 清理
            content = re.sub(r'---.*?---', "", content)           # 去掉 Section
            content = re.sub(r"<red>(.*?)</red>", r"\1", content) # 去掉红字标签（搜索用纯文本）
            content = re.sub(r"\s+", " ", content).strip()

            if content:
                search_index.append({"id": raw_id, "c": content, "l": lang})

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(search_index, f, ensure_ascii=False)

    print(f"搜索索引构建完成！共 {len(search_index)} 条，文件大小 {os.path.getsize(OUTPUT_FILE)/1024/1024:.2f} MB")

if __name__ == "__main__":
    main()