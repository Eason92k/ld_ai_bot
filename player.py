import json
import time
import win32api
import win32con
from ld_controller import list_all_ldplayer_windows, send_click, send_key, send_swipe

from pynput import keyboard
import threading

class ActionPlayer:
    def __init__(self, filename="actions_record.json"):
        self.filename = filename
        self.actions = []
        self.mode = "sync"
        self.playing = False
        self.log_callback = None

    def log(self, message):
        if self.log_callback:
            try:
                self.log_callback(message)
            except Exception:
                pass
        else:
            print(message)

    def load(self):
        try:
            with open(self.filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict) and "actions" in data:
                    self.actions = data["actions"]
                    self.mode = data.get("mode", "sync")
                else:
                    self.actions = data
                    self.mode = "sync" # 舊格式默認為同步
            self.log(f"✓ 已加載 {len(self.actions)} 個操作 (模式: {self.mode})")
            return True
        except FileNotFoundError:
            self.log(f"✗ 找不到文件: {self.filename}")
            return False
    
    def on_key_press(self, key):
        if self.playing:
            try:
                if "esc" in str(key).lower() or "f12" in str(key).lower():
                    self.playing = False
                    return False
            except:
                pass
    
    def play(self, repeat=1, target_windows=None):
        """
        target_windows: [(title, hwnd), ...]
        """
        if not self.actions:
            self.log("✗ 沒有操作可以播放")
            return
        
        if not target_windows:
            self.log("✗ 未指定目標視窗")
            return

        self.log(f"=== 準備播放操作 ({'錄一跑多' if self.mode=='sync' else '獨立播放'}) ===")
        self.log(f"✓ 執行次數: {repeat}")
        self.log("✓ 停止播放: 按 ESC 或 F12 鍵")
        self.log("⏳ 3 秒後開始播放...\n")
        time.sleep(3)
        
        self.playing = True
        keyboard_listener = keyboard.Listener(on_press=self.on_key_press)
        keyboard_listener.start()
        
        for cycle in range(repeat):
            if not self.playing: break
            self.log(f"\n--- 循環 {cycle + 1}/{repeat} ---")
            self.run_actions(target_windows)
        
        self.playing = False
        keyboard_listener.stop()
        self.log("\n=== 播放完成 ===")
    
    def run_actions(self, target_windows):
        prev_time = 0
        
        # 建立 HWND 對應表以便獨立模式查找
        window_map = {title: hwnd for title, hwnd in target_windows}

        for action in self.actions:
            if not self.playing: return
            
            # 等待時間
            current_time = action['time']
            wait_time = current_time - prev_time
            if wait_time > 0:
                time.sleep(wait_time)
            
            # 獲取目標視窗列表
            if self.mode == "sync":
                # 同步模式：所有人都要做
                target_hwnds = [hwnd for _, hwnd in target_windows]
            else:
                # 獨立模式：根據標註執行
                target_title = action.get("window_title")
                if target_title in window_map:
                    target_hwnds = [window_map[target_title]]
                else:
                    # 如果找不到標註的視窗，跳過
                    target_hwnds = []

            # 執行動作 - 使用執行緒達成真正同步
            threads = []
            for hwnd in target_hwnds:
                t = threading.Thread(target=self.execute_single_action, args=(hwnd, action))
                t.start()
                threads.append(t)
            
            # 等待所有視窗完成此動作再繼續下一個時間點
            for t in threads:
                t.join()

            prev_time = current_time

    def execute_single_action(self, hwnd, action):
        """在特定視窗執行單個動作"""
        try:
            if action['type'] == 'click':
                send_click(hwnd, action['x'], action['y'])
            elif action['type'] == 'key':
                key_str = action['key']
                if len(key_str) == 1:
                    vk_code = win32api.VkKeyScan(key_str) & 0xFF
                    send_key(hwnd, vk_code)
            elif action['type'] == 'swipe':
                send_swipe(hwnd, action['start_x'], action['start_y'], action['end_x'], action['end_y'], action.get('duration', 0.3))
        except Exception as e:
            self.log(f"  ✗ 錯誤: 視窗 {hwnd} 執行失敗 - {e}")


if __name__ == "__main__":
    print("請執行 python main.py 來啟動控制面板")

