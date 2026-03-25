import json
import time
import pyautogui
from pynput import mouse, keyboard
from ld_controller import get_ldplayer_window

class ActionRecorder:
    def __init__(self, filename="actions_record.json", window_title=None):
        self.filename = filename
        self.window_title = window_title
        self.actions = []
        self.recording = False
        self.start_time = None
        self.window = None
        self.log_callback = None

    def log(self, message):
        if self.log_callback:
            try:
                self.log_callback(message)
            except Exception:
                pass
        else:
            print(message)
        
    def on_move(self, x, y):
        if self.recording and self.window:
            elapsed = time.time() - self.start_time
            # 轉換為相對於窗口的虛擬坐標
            rel_x = x - self.window.left
            rel_y = y - self.window.top
            self.actions.append({
                "type": "move",
                "x": rel_x,
                "y": rel_y,
                "time": elapsed
            })
    
    def on_click(self, x, y, button, pressed):
        if self.recording and self.window:
            elapsed = time.time() - self.start_time
            if pressed:
                # 轉換為相對於窗口的虛擬坐標
                rel_x = x - self.window.left
                rel_y = y - self.window.top
                self.actions.append({
                    "type": "click",
                    "x": rel_x,
                    "y": rel_y,
                    "button": str(button),
                    "time": elapsed
                })
    
    def on_press(self, key):
        if self.recording:
            elapsed = time.time() - self.start_time
            try:
                key_name = key.char
            except AttributeError:
                key_name = str(key)
            
            # 檢查是否按下 Escape 或 F12 鍵停止錄製
            if "esc" in str(key).lower() or "f12" in str(key).lower():
                print("\n[停止錄製按鍵檢測到]")
                self.stop()
                return False
            
            self.actions.append({
                "type": "key",
                "key": key_name,
                "time": elapsed
            })
    
    def start(self):
        self.log("=== 開始錄製操作 ===")
        self.log("進行您的遊戲操作")
        self.log("停止錄製: 按 ESC 或 F12 鍵")
        self.log("-" * 50)
        
        # 獲取模擬器窗口
        try:
            self.window = get_ldplayer_window(self.window_title)
            self.window.activate()  # 激活窗口
            print(f"✓ 已鎖定窗口: {self.window.title}")
            print(f"✓ 窗口位置: ({self.window.left}, {self.window.top})")
            print(f"✓ 窗口大小: {self.window.width} x {self.window.height}")
            print(f"⚠️  舊的操作記錄將被覆蓋")
            print("-" * 50)
            print("開始錄製...\n")
        except Exception as e:
            self.log(f"✗ 錯誤: {e}")
            return
        
        self.actions = []
        self.recording = True
        self.start_time = time.time()
        
        # 監聽滑鼠和鍵盤
        mouse_listener = mouse.Listener(
            on_move=self.on_move,
            on_click=self.on_click
        )
        keyboard_listener = keyboard.Listener(
            on_press=self.on_press
        )
        
        mouse_listener.start()
        keyboard_listener.start()
        
        # 等待錄製停止
        try:
            keyboard_listener.join()
        except KeyboardInterrupt:
            self.stop()
    
    def stop(self):
        self.recording = False
        self.log("\n=== 錄製已停止 ===")
        self.save()
    
    def save(self):
        with open(self.filename, 'w', encoding='utf-8') as f:
            json.dump(self.actions, f, indent=2, ensure_ascii=False)
        self.log(f"✓ 操作已保存到: {self.filename}")
        self.log(f"✓ 總共記錄: {len(self.actions)} 個操作")

if __name__ == "__main__":
    recorder = ActionRecorder()
    recorder.start()
