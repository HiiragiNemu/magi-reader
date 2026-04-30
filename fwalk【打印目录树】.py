import os

# 扫描当前目录及其子目录
for root, dirs, files in os.walk('.'):
    # 只输出目录路径（包括当前目录和所有子目录）
    print(root)