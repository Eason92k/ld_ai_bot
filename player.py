import json
import time
import pyautogui
from ld_controller import get_ldplayer_window
from pynput import keyboard
import threading

class ActionPlayer:
    def __init__(self, filename="actions_record.json", window_title=None):
        self.filename = filename
        self.window_title = window_title
        self.actions = []
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
                self.actions = json.load(f)
            self.log(f"✓ 已加載 {len(self.actions)} 個操作")
            return True
        except FileNotFoundError:
            self.log(f"✗ 找不到文件: {self.filename}")
            return False
    
    def on_key_press(self, key):
        """監聽按鍵停止播放"""
        if self.playing:
            try:
                # 檢查是否按下 ESC 或 F12 停止播放
                if "esc" in str(key).lower() or "f12" in str(key).lower():
                    print("\n[偵測到停止按鍵]")
                    self.playing = False
                    return False
            except:
                pass
    
    def play(self, repeat=1, window_titles=None):
        if not self.actions:
            self.log("✗ 沒有操作可以播放")
            return
        
        if not window_titles:
            self.log("✗ 未指定目標視窗")
            return

        self.log(f"=== 準備播放操作 ===")
        self.log(f"✓ 目標視窗: {', '.join(window_titles)}")
        self.log(f"✓ 將重複: {repeat} 次")
        self.log("✓ 停止播放: 按 ESC 或 F12 鍵")
        self.log("⏳ 3 秒後開始播放...\n")
        time.sleep(3)
        
        # 啟動鍵盤監聽線程
        self.playing = True
        keyboard_listener = keyboard.Listener(on_press=self.on_key_press)
        keyboard_listener.start()
        
        for cycle in range(repeat):
            if not self.playing:
                self.log("✗ 播放已被中止")
                break
            
            self.log(f"\n--- 循環 {cycle + 1}/{repeat} ---")
            
            # 對於每個視窗執行一次
            for title in window_titles:
                if not self.playing: break
                self.log(f"  ▶ 執行視窗: {title}")
                self.window_title = title
                self.play_once()
        
        self.playing = False
        keyboard_listener.stop()
        self.log("\n=== 播放完成 ===")
    
    def play_once(self):
        if not self.actions:
            return
        
        # 獲獲模擬器窗口位置
        try:
            window = get_ldplayer_window(self.window_title)
            window.activate()
        except Exception as e:
            self.log(f"✗ 警告: 無法獲取窗口 - {e}")
            return
        
        # 窗口邊界
        win_left = window.left
        win_top = window.top
        win_right = window.left + window.width
        win_bottom = window.top + window.height
        
        prev_time = 0
        for action in self.actions:
            if not self.playing:
                return
            
            current_time = action['time']
            wait_time = current_time - prev_time
            
            if wait_time > 0:
                time.sleep(wait_time)
            
            if action['type'] == 'click':
                # 虛擬坐標轉換為絕對屏幕坐標
                abs_x = int(win_left + action['x'])
                abs_y = int(win_top + action['y'])
                
                # 邊界檢查 - 確保點擊在窗口內
                if win_left <= abs_x <= win_right and win_top <= abs_y <= win_bottom:
                    self.log(f"  ✓ 點擊: ({action['x']}, {action['y']})")
                    # 直接點擊，不需要先移動
                    pyautogui.click(abs_x, abs_y)
                else:
                    self.log(f"  ✗ 跳過超範圍點擊: ({action['x']}, {action['y']}) - 絕對坐標: ({abs_x}, {abs_y})")
            
            elif action['type'] == 'key':
                key = action['key']
                self.log(f"  ⌨️ 按鍵: {key}")
                pyautogui.press(key)
            
            prev_time = current_time
        
        self.log("✓ 本循環播放完成")

if __name__ == "__main__":
    # 原有的 GUI 邏輯已移至 main.py
    # 執行 python main.py 即可開啟控制面板
    print("請執行 python main.py 來啟動控制面板")
