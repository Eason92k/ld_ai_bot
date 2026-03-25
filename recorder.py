import json
import time
import pyautogui
import win32gui
import win32api
from pynput import mouse, keyboard
from ld_controller import get_ldplayer_window

class ActionRecorder:
    def __init__(self, filename="actions_record.json"):
        self.filename = filename
        self.target_windows = []  # 格式: [(title, hwnd), ...]
        self.actions = []
        self.recording = False
        self.start_time = None
        self.log_callback = None
        self.mouse_down_pos = None
        self.mouse_down_time = None
        self.recording_mode = "sync"  # "sync" (錄一跑多) 或 "independent" (獨立錄製)

    def log(self, message):
        if self.log_callback:
            try:
                self.log_callback(message)
            except Exception:
                pass
        else:
            print(message)
        
    def get_window_at(self, x, y):
        """獲取座標所在的視窗控制代碼，並檢查是否在目標清單中"""
        hwnd = win32gui.WindowFromPoint((int(x), int(y)))
        # WindowFromPoint 可能點到子視窗，需要往上找父視窗直到找到在清單中的或到頂
        curr = hwnd
        while curr:
            for title, target_hwnd in self.target_windows:
                if curr == target_hwnd:
                    return title, target_hwnd
            curr = win32gui.GetParent(curr)
        return None, None

    def on_move(self, x, y):
        if not self.recording: return
        # 滑鼠移動通常不記錄，除非是滑動的一部分，暫不處理
        pass
    
    def on_click(self, x, y, button, pressed):
        if self.recording:
            elapsed = time.time() - self.start_time
            
            # 判斷這個點擊在哪個視窗
            title, hwnd = self.get_window_at(x, y)
            
            # 如果是「錄一跑多」模式，只記錄主視窗（第一個選中的）
            # 如果是「獨立錄製」模式，記錄所有選中的視窗
            if not hwnd:
                return

            if self.recording_mode == "sync":
                # 只記錄第一個選定的視窗作為 Master
                master_title, master_hwnd = self.target_windows[0]
                if hwnd != master_hwnd:
                    return
                win_rect = win32gui.GetWindowRect(hwnd)
            else:
                # 獨立錄製，記錄當前所屬視窗
                win_rect = win32gui.GetWindowRect(hwnd)

            if pressed:
                self.mouse_down_pos = (x, y)
                self.mouse_down_time = elapsed
            else:
                if self.mouse_down_pos:
                    start_x, start_y = self.mouse_down_pos
                    end_x, end_y = x, y
                    
                    distance = ((end_x - start_x)**2 + (end_y - start_y)**2)**0.5
                    
                    # 使用 ScreenToClient 獲取精確的相對於視窗客戶區的座標
                    # 注意：pynput 的 x, y 可能是邏輯座標，win32gui 需要物理座標
                    # 我們直接抓取當前的 win32 游標位置更保險
                    try:
                        # 再次確認當前位置
                        cur_x, cur_y = win32gui.GetCursorPos()
                        rel_x, rel_y = win32gui.ScreenToClient(hwnd, (cur_x, cur_y))
                        
                        # 同理處理起點（這裡簡化，假設點擊釋放時位置即為終點）
                        # 如果是滑動，起點座標需要根據之前的 mouse_down_pos 轉換
                        # 但邏輯坐標轉物理坐標較麻煩，我們先統一用當前 hwnd 轉換
                        rel_start_x, rel_start_y = win32gui.ScreenToClient(hwnd, (int(start_x), int(start_y)))
                        rel_end_x, rel_end_y = rel_x, rel_y
                    except Exception as e:
                        # 備用方案
                        rel_start_x = start_x - win_rect[0]
                        rel_start_y = start_y - win_rect[1]
                        rel_end_x = end_x - win_rect[0]
                        rel_end_y = end_y - win_rect[1]
                    
                    action_data = {
                        "time": self.mouse_down_time,
                        "window_title": title if self.recording_mode == "independent" else None
                    }

                    if distance > 15:
                        duration = elapsed - self.mouse_down_time
                        action_data.update({
                            "type": "swipe",
                            "start_x": rel_start_x,
                            "start_y": rel_start_y,
                            "end_x": rel_end_x,
                            "end_y": rel_end_y,
                            "duration": round(max(0.1, duration), 2)
                        })
                    else:
                        action_data.update({
                            "type": "click",
                            "x": rel_end_x,
                            "y": rel_end_y
                        })
                    
                    self.actions.append(action_data)

                
                self.mouse_down_pos = None
                self.mouse_down_time = None
    
    def on_press(self, key):
        if self.recording:
            elapsed = time.time() - self.start_time
            try:
                key_name = key.char
            except AttributeError:
                key_name = str(key)
            
            if "esc" in str(key).lower() or "f12" in str(key).lower():
                self.stop()
                return False
            
            # 獲取當前焦點視窗，看是否在錄製範圍
            focus_hwnd = win32gui.GetForegroundWindow()
            title = None
            for t, h in self.target_windows:
                if focus_hwnd == h:
                    title = t
                    break
            
            if self.recording_mode == "sync":
                # 同步模式下，只記錄在 Master 視窗的按鍵
                if focus_hwnd != self.target_windows[0][1]:
                    return
                title = None # 不標註視窗
            elif not title:
                # 獨立模式下，不在選定範圍則不記錄
                return

            self.actions.append({
                "type": "key",
                "key": key_name,
                "time": elapsed,
                "window_title": title
            })
    
    def start(self, target_windows, mode="sync"):
        """
        target_windows: [(title, hwnd), ...]
        mode: "sync" 或 "independent"
        """
        if not target_windows:
            self.log("✗ 錯誤: 未指定錄製目標視窗")
            return

        self.target_windows = target_windows
        self.recording_mode = mode
        self.actions = []
        self.recording = True
        self.start_time = time.time()

        self.log(f"=== 開始錄製 ({'錄一跑多' if mode=='sync' else '獨立錄製'}) ===")
        for title, hwnd in target_windows:
            self.log(f"✓ 監聽視窗: {title}")
        self.log("停止錄製: 按 ESC 或 F12 鍵")
        self.log("-" * 50)
        
        # 監聽滑鼠和鍵盤
        mouse_listener = mouse.Listener(on_click=self.on_click)
        keyboard_listener = keyboard.Listener(on_press=self.on_press)
        
        mouse_listener.start()
        keyboard_listener.start()
        
        try:
            keyboard_listener.join()
        except KeyboardInterrupt:
            self.stop()
    
    def stop(self):
        if self.recording:
            self.recording = False
            self.log("\n=== 錄製已停止 ===")
            self.save()
    
    def save(self):
        # 存檔時包含元數據
        output = {
            "mode": self.recording_mode,
            "actions": self.actions
        }
        with open(self.filename, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        self.log(f"✓ 操作已保存到: {self.filename}")
        self.log(f"✓ 總共記錄: {len(self.actions)} 個操作")


if __name__ == "__main__":
    recorder = ActionRecorder()
    recorder.start()
