import subprocess
import sys
import os
import time

# 腳本配置列表 [模擬器索引, 腳本檔名]
# 你可以在這裡自由增加或修改
configs = [
    {"index": 0, "script": "活動後篇1(古代).json", "title": "古代千影-Bot"},
    {"index": 1, "script": "活動後篇1(亡命).json", "title": "亡命千影-Bot"},
    {"index": 2, "script": "活動後篇1(劍姬).json", "title": "劍姬千影-Bot"},
    {"index": 3, "script": "活動後篇1.json",        "title": "坦-Bot"},
    {"index": 4, "script": "活動後篇1.json",        "title": "補-Bot"},
]

def main():
    python_exe = sys.executable  # 使用目前正在執行的 Python 環境
    base_dir = os.path.dirname(os.path.abspath(__file__))
    main_py = os.path.join(base_dir, "main.py")

    print(f"==================================================")
    print(f"      LD Player 多開啟動器 (Python 版)")
    print(f"==================================================")
    print(f"使用環境: {python_exe}")
    print(f"專案路徑: {base_dir}")
    print(f"--------------------------------------------------")

    # 手動輸入啟動數量
    try:
        max_configs = len(configs)
        user_input = input(f"請問要啟動幾個視窗？ (1-{max_configs}，直接按 Enter 啟動全部): ").strip()
        if user_input == "":
            num_to_start = max_configs
        else:
            num_to_start = int(user_input)
            if num_to_start < 1: num_to_start = 1
            if num_to_start > max_configs: num_to_start = max_configs
    except ValueError:
        print("⚠️ 輸入無效，將預設啟動全部視窗。")
        num_to_start = len(configs)

    active_configs = configs[:num_to_start]
    print(f"正在啟動 {len(active_configs)} 個視窗...")

    processes = []
    for cfg in active_configs:
        cmd = [
            python_exe,
            main_py,
            "--index", str(cfg["index"]),
            "--script", cfg["script"]
        ]
        
        print(f"➜ 啟動中: {cfg['title']} (Index: {cfg['index']}, Script: {cfg['script']})")
        
        # 使用 subprocess.Popen 啟動背景進程
        # 在 Windows 上使用 creationflags=subprocess.CREATE_NEW_CONSOLE 可以彈出新視窗以便查看日誌
        try:
            p = subprocess.Popen(
                cmd, 
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                cwd=base_dir
            )
            processes.append(p)
            # 稍微延遲一下，避免同時讀取檔案可能發生的衝突
            time.sleep(1)
        except Exception as e:
            print(f"❌ 啟動失敗: {cfg['title']} - {e}")

    print(f"--------------------------------------------------")
    print(f"✅ 所有視窗已發出啟動指令。")
    print(f"您可以關閉此啟動器，分身視窗會保持運行。")
    print(f"==================================================")
    
    # 保持主腳本運行一下，讓用戶看清楚 Log
    time.sleep(5)

if __name__ == "__main__":
    main()
