import json
import time
import win32api
import win32con
import cv2
import numpy as np
import os
from PIL import Image
from ld_controller import list_all_ldplayer_windows, send_click, send_key, send_swipe, get_window_screenshot

from pynput import keyboard
import threading

class ActionPlayer:
    def __init__(self, filename=""):
        self.filename = filename
        self.actions = []
        self.mode = "sync"
        self.smart_mode = False
        self.assets_dir = None
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
            if not self.filename:
                return False
            with open(self.filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict) and "actions" in data:
                    self.actions = data["actions"]
                    self.mode = data.get("mode", "sync")
                    self.smart_mode = data.get("smart_mode", False)
                else:
                    self.actions = data
                    self.mode = "sync"
                    self.smart_mode = False
            
            if self.smart_mode:
                self.assets_dir = self.filename.replace(".json", "_assets")
                if not os.path.exists(self.assets_dir):
                    self.log("⚠️ 警告: 找不到視覺樣板資料夾，將忽略視覺檢查")
                    self.smart_mode = False

            self.log(f"✓ 已加載 {len(self.actions)} 個操作 (模式: {self.mode}, Smart: {self.smart_mode})")
            return True
        except Exception as e:
            self.log(f"✗ 載入失敗: {e}")
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
        window_map = {title: hwnd for title, hwnd in target_windows}

        for action in self.actions:
            if not self.playing: return
            
            current_time = action['time']
            wait_time = current_time - prev_time
            if wait_time > 0:
                time.sleep(wait_time)
            
            if self.mode == "sync":
                target_hwnds = [hwnd for _, hwnd in target_windows]
            else:
                target_title = action.get("window_title")
                if target_title in window_map:
                    target_hwnds = [window_map[target_title]]
                else:
                    target_hwnds = []

            threads = []
            for hwnd in target_hwnds:
                t = threading.Thread(target=self.execute_single_action, args=(hwnd, action))
                t.start()
                threads.append(t)
            
            for t in threads:
                t.join()

            prev_time = current_time

    def execute_single_action(self, hwnd, action):
        """在特定視窗執行單個動作"""
        try:
            # 視覺檢查邏輯
            if self.smart_mode and action.get("asset") and action['type'] == 'click':
                asset_path = os.path.join(self.assets_dir, action["asset"])
                if os.path.exists(asset_path):
                    if not self.wait_for_asset(hwnd, asset_path):
                        self.log(f"  ⚠️ 視覺檢查超時，視窗 {hwnd} 可能處於錯誤狀態")
                else:
                    self.log(f"  ⚠️ 找不到樣板檔案: {asset_path}")

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

    def wait_for_asset(self, hwnd, asset_path, timeout=8):
        """等待視窗中出現樣板圖片 (支援中文路徑)"""
        try:
            # 使用 numpy 讀取以支援中文路徑
            template = cv2.imdecode(np.fromfile(asset_path, dtype=np.uint8), cv2.IMREAD_COLOR)
        except Exception as e:
            self.log(f"  ⚠️ 讀取樣板失敗: {e}")
            return False
        
        if template is None: return False
        
        start_wait = time.time()
        while time.time() - start_wait < timeout:
            if not self.playing: return False
            
            im = get_window_screenshot(hwnd)
            if im:
                screen_cv = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
                result = cv2.matchTemplate(screen_cv, template, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(result)
                
                if max_val > 0.6: # 信心度門檻 (從 0.8 調低以提高相容性)
                    return True
            
            time.sleep(0.5)
        return False

if __name__ == "__main__":
    print("請執行 python main.py 來啟動控制面板")
