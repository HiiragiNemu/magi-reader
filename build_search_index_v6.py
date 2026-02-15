# build_search_index_v6.py
import os
import json
import re

TARGET_PUBLIC_DIR = "website/public"
OUTPUT_FILE = os.path.join(TARGET_PUBLIC_DIR, "search_content.json")
DATA_DIR = os.path.join(TARGET_PUBLIC_DIR, "data")

def main():
    print("正在构建搜索索引 (V6) - 深度清理标签，保留内容...")
    search_index = []

    for root, _, files in os.walk(DATA_DIR):
        for file in files:
            if not file.endswith(".txt"): continue
            lang = "cn" if "_cn.txt" in file else "jp" if "_jp.txt" in file else None
            if not lang: continue

            raw_id = file.replace("_cn.txt", "").replace("_jp.txt", "").split("_")[0]
            path = os.path.join(root, file)
            
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            # 1. 去掉 Section 头
            content = re.sub(r'---.*?---', "", content)
            
            # 2. 【关键】去掉 XML 标签 (<red>text</red> -> text)
            content = re.sub(r"<(red|blue)>(.*?)</\1>", r"\2", content, flags=re.DOTALL)
            
            # 3. 【关键】去掉 textBlack 标签 ([textBlack:text] -> text)
            # 这样搜索文件里只存纯文本，体积最小，且能搜到内容
            content = re.sub(r"\[textBlack:(.*?)\]", r"\1", content, flags=re.DOTALL)
            
            # 4. 压缩空白
            content = re.sub(r"\s+", " ", content).strip()

            if content:
                search_index.append({"id": raw_id, "c": content, "l": lang})

    # 写入 JSON
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(search_index, f, ensure_ascii=False, separators=(',', ':')) # 使用 separators 进一步压缩体积

    size_mb = os.path.getsize(OUTPUT_FILE) / 1024 / 1024
    print(f"✅ 索引构建完成！")
    print(f"   条目数: {len(search_index)}")
    print(f"   文件大小: {size_mb:.2f} MB")
    
    if size_mb < 30:
        print("⚠️ 注意：文件大小如果远小于 40MB，请先确认 TXT 内容是否已通过 safe_fix_data.py 恢复完整。")
    else:
        print("🎉 大小正常 (接近 40MB)。")

if __name__ == "__main__":
    main()