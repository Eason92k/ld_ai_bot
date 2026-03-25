import json
import time
import os
import shutil
import stat
import pyautogui
import win32gui
import win32api
from pynput import mouse, keyboard
from ld_controller import get_ldplayer_window, get_window_screenshot

class ActionRecorder:
    def __init__(self, filename=None):
        self.scripts_dir = "scripts"
        if not os.path.exists(self.scripts_dir):
            os.makedirs(self.scripts_dir)
            
        if filename:
            self.filename = filename
        else:
            # 預設不設定，save 時動態生成
            self.filename = None
        self.target_windows = []  # 格式: [(title, hwnd), ...]
        self.actions = []
        self.recording = False
        self.start_time = None
        self.log_callback = None
        self.mouse_down_pos = None
        self.mouse_down_time = None
        self.recording_mode = "sync"  # "sync" (錄一跑多) 或 "independent" (獨立錄製)
        self.smart_mode = False
        self.assets_dir = None

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
                        
                        # 如果是同步點擊，嘗試抓取視覺樣板
                        if self.smart_mode and action_data["type"] == "click":
                            asset = self.capture_click_asset(hwnd, self.mouse_down_pos[0], self.mouse_down_pos[1], len(self.actions))
                            if asset:
                                action_data["asset"] = asset
                    
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
    
    def capture_click_asset(self, hwnd, x, y, action_index):
        if not self.smart_mode or not self.assets_dir:
            return None
        
        try:
            im = get_window_screenshot(hwnd)
            if im:
                # 轉為客戶區座標 (目前 x, y 是屏幕座標)
                rel_x, rel_y = win32gui.ScreenToClient(hwnd, (int(x), int(y)))
                
                # 截取點擊點周圍 50x50
                size = 25
                left = max(0, rel_x - size)
                top = max(0, rel_y - size)
                right = min(im.size[0], rel_x + size)
                bottom = min(im.size[1], rel_y + size)
                
                crop = im.crop((left, top, right, bottom))
                asset_name = f"action_{action_index}.png"
                crop.save(os.path.join(self.assets_dir, asset_name))
                return asset_name
        except Exception as e:
            self.log(f"⚠️ 視覺樣板截取失敗: {e}")
        return None

    def start(self, target_windows, mode="sync", smart_mode=False):
        """
        target_windows: [(title, hwnd), ...]
        mode: "sync" 或 "independent"
        """
        if not target_windows:
            self.log("✗ 錯誤: 未指定錄製目標視窗")
            return

        self.target_windows = target_windows
        self.recording_mode = mode
        self.smart_mode = smart_mode
        self.actions = []
        self.recording = True
        self.start_time = time.time()

        # 準備資產目錄
        if self.smart_mode:
            # 我們在 save 時才會知道最終檔名，這裡先用臨時的或預設的
            # 實際上 save 時再移動可能更好，但為了當下能存，先建一個暫存區
            self.assets_dir = os.path.join(self.scripts_dir, "temp_assets")
            if not os.path.exists(self.assets_dir):
                os.makedirs(self.assets_dir)
            # 清空暫存區
            for f in os.listdir(self.assets_dir):
                os.remove(os.path.join(self.assets_dir, f))

        self.log(f"=== 開始錄製 ({'錄一跑多' if mode=='sync' else '獨立錄製'}) {'[Smart Mode]' if smart_mode else ''} ===")
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
        # 如果沒指定檔名，使用統一命名「錄製腳本」並處理重複
        if not self.filename:
            base_name = "錄製腳本"
            ext = ".json"
            target_path = os.path.join(self.scripts_dir, f"{base_name}{ext}")
            
            if os.path.exists(target_path):
                counter = 1
                while os.path.exists(os.path.join(self.scripts_dir, f"{base_name}{counter}{ext}")):
                    counter += 1
                target_path = os.path.join(self.scripts_dir, f"{base_name}{counter}{ext}")
            
            self.filename = target_path
        elif not os.path.isabs(self.filename) and not self.filename.startswith(self.scripts_dir):
            self.filename = os.path.join(self.scripts_dir, self.filename)

        # 確保目錄存在
        os.makedirs(os.path.dirname(self.filename), exist_ok=True)
        # 存檔時包含元數據
        output = {
            "mode": self.recording_mode,
            "smart_mode": self.smart_mode,
            "actions": self.actions
        }
        with open(self.filename, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        
        # 處理資產目錄：將 temp_assets 改名為 {filename}_assets
        if self.smart_mode and self.assets_dir and os.path.exists(self.assets_dir):
            final_assets_dir = self.filename.replace(".json", "_assets")
            
            # 定義一個處理唯讀檔案的 helper (Windows 常用)
            def remove_readonly(func, path, _):
                os.chmod(path, stat.S_IWRITE)
                func(path)

            try:
                # 確保我們不試圖移除正在使用的資料夾本身 (如果是 recording 的 tmp)
                if os.path.abspath(self.assets_dir) == os.path.abspath(final_assets_dir):
                    self.log(f"✓ 視覺樣板已在目標目錄: {final_assets_dir}")
                    return

                # 如果目標資料夾已存在，先嘗試刪除
                if os.path.exists(final_assets_dir):
                    # 增加延遲，讓系統釋放控制代碼
                    time.sleep(1.0) 
                    try:
                        shutil.rmtree(final_assets_dir, onerror=remove_readonly)
                    except Exception as e:
                        self.log(f"⚠️ 無法刪除舊的資產目錄 (可能被鎖定): {e}")
                        # 如果刪不掉，我們換個名字存，以免錄製內容丟失
                        final_assets_dir = final_assets_dir + "_" + time.strftime("%H%M%S")
                        self.log(f"   將嘗試保存至新目錄: {final_assets_dir}")
                
                # 重新命名暫存目錄
                # 再次確保 assets_dir 存在且未被重新命名
                if os.path.exists(self.assets_dir):
                    os.rename(self.assets_dir, final_assets_dir)
                    self.assets_dir = final_assets_dir
                    self.log(f"✓ 視覺樣板已保存到: {final_assets_dir}")
                else:
                    self.log(f"⚠️ 找不到暫存資產目錄，略過重新命名")

            except Exception as e:
                self.log(f"⚠️ 更新資產資料夾時發生錯誤: {e}")
                self.log(f"   暫存資料夾保留在: {self.assets_dir}")

        self.log(f"✓ 操作已保存到: {self.filename}")
        self.log(f"✓ 總共記錄: {len(self.actions)} 個操作")


if __name__ == "__main__":
    recorder = ActionRecorder()
    recorder.start()
