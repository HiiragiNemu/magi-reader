import os
import subprocess
import time

def run_command(cmd, cwd=None):
    print(f">> 执行: {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=cwd)
    if result.returncode != 0:
        print(f"❌ 错误: 命令执行失败")
        exit(1)

def main():
    start_time = time.time()
    
    # 1. 生成基础索引 (计算汉化比 + 复制文件到 public/data)
    print("\n--- [Step 1] 生成 story_index.json ---")
    run_command("python generate_story_index.py")

    # 2. 生成全文搜索索引 (42MB 的那个)
    print("\n--- [Step 2] 生成 search_content.json ---")
    run_command("python build_search_index_v4.py")

    # 3. 上传大文件到 Cloudflare R2
    print("\n--- [Step 3] 上传搜索索引至 R2 存储桶 ---")
    # 假设你的桶名叫 magi-assets，请根据实际修改
    run_command("npx wrangler r2 object put magi-assets/search_content.json --file=website/public/search_content.json", cwd="website")

    # 4. Git 自动化推送
    print("\n--- [Step 4] 推送代码至 GitHub (排除大文件) ---")
    run_command("git add .")
    run_command('git commit -m "Auto-sync content: ' + time.strftime("%Y-%m-%d %H:%M:%S") + '"')
    run_command("git push origin main")

    print(f"\n✅ 全部任务同步完成！耗时: {time.time() - start_time:.2f}s")

if __name__ == "__main__":
    main()