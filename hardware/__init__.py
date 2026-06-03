# hardware/__init__.py
import sys
import os

print("📸 [硬體環境初始化] 正在動態校準硬體模擬套件之環境變數路徑...")

# 將專案根目錄自動加入系統路徑（免除在每個子檔案裡重複寫 sys.path.append 的麻煩）
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)