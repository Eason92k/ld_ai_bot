import json
import time
import os
import threading
import cv2
import numpy as np
from ld_controller import send_click, send_swipe, get_window_screenshot

class AdvancedActionPlayer:
    def __init__(self):
        self.steps = []
        self.playing = False
        self.log_callback = None
        self.scripts_dir = "scripts/advanced"
        if not os.path.exists(self.scripts_dir):
            os.makedirs(self.scripts_dir)

    def log(self, message):
        if self.log_callback:
            try:
                self.log_callback(message)
            except Exception:
                pass
        else:
            print(message)

    def add_step(self, action_type, params):
        """
        action_type: 'click', 'swipe', 'wait', 'find_click'
        params: dict of parameters
        """
        self.steps.append({
            "type": action_type,
            "params": params
        })

    def delete_step(self, index):
        if 0 <= index < len(self.steps):
            removed = self.steps.pop(index)
            self.log(f"✓ 已刪除步驟 {index + 1}: {removed['type']}")
            return True
        return False

    def move_step(self, index, direction):
        """direction: -1 for up, 1 for down"""
        new_index = index + direction
        if 0 <= index < len(self.steps) and 0 <= new_index < len(self.steps):
            self.steps[index], self.steps[new_index] = self.steps[new_index], self.steps[index]
            return True
        return False

    def play(self, target_windows, repeat=1):
        """
        target_windows: [(title, hwnd), ...]
        """
        if not self.steps:
            self.log("✗ 沒有進階動作可以執行")
            return

        self.playing = True
        self.log(f"=== 開始執行進階腳本 (次數: {repeat}) ===")
        
        for cycle in range(repeat):
            if not self.playing: break
            self.log(f"\n--- 進階循環 {cycle + 1}/{repeat} ---")
            for step in self.steps:
                if not self.playing: break
                self.execute_step(target_windows, step)
        
        self.playing = False
        self.log("\n=== 進階腳本執行完成 ===")

    def execute_step(self, target_windows, step):
        action_type = step["type"]
        params = step["params"]
        
        # 目前進階模式暫定為同步模式 (Sync)
        target_hwnds = [hwnd for _, hwnd in target_windows]

        if action_type == "click":
            self.log(f"  ➜ 點擊 ({params['x']}, {params['y']})")
            for hwnd in target_hwnds:
                send_click(hwnd, params['x'], params['y'])
                
        elif action_type == "swipe":
            self.log(f"  ➜ 滑動 ({params['s_x']}, {params['s_y']}) -> ({params['e_x']}, {params['e_y']})")
            for hwnd in target_hwnds:
                send_swipe(hwnd, params['s_x'], params['s_y'], params['e_x'], params['e_y'], params.get('duration', 0.5))
                
        elif action_type == "wait":
            self.log(f"  ➜ 等待 {params['seconds']} 秒")
            time.sleep(params['seconds'])
            
        elif action_type == "find_click":
            template_path = params['template']
            threshold = params.get('threshold', 0.7)
            self.log(f"  ➜ 搜尋圖片: {os.path.basename(template_path)}")
            
            for hwnd in target_hwnds:
                found_pos = self.find_image(hwnd, template_path, threshold)
                if found_pos:
                    self.log(f"    ✓ 找到目標，執行點擊: {found_pos}")
                    send_click(hwnd, found_pos[0], found_pos[1])
                else:
                    self.log(f"    × 未找到目標")

    def find_image(self, hwnd, template_path, threshold=0.7):
        """在指定視窗中尋找圖片，傳回中心座標或 None"""
        try:
            template = cv2.imdecode(np.fromfile(template_path, dtype=np.uint8), cv2.IMREAD_COLOR)
            if template is None: return None
            
            im = get_window_screenshot(hwnd)
            if not im: return None
            
            screen_cv = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
            result = cv2.matchTemplate(screen_cv, template, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            
            if max_val >= threshold:
                h, w = template.shape[:2]
                center_x = max_loc[0] + w // 2
                center_y = max_loc[1] + h // 2
                return (center_x, center_y)
        except Exception as e:
            self.log(f"  ⚠️ 圖片辨識發生錯誤: {e}")
        return None

    def save_script(self, filename):
        if not filename.endswith(".json"):
            filename += ".json"
        path = os.path.join(self.scripts_dir, filename)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.steps, f, indent=2, ensure_ascii=False)
        self.log(f"✓ 進階腳本已儲存: {filename}")

    def load_script(self, filename):
        path = os.path.join(self.scripts_dir, filename)
        if not os.path.exists(path):
            self.log(f"✗ 找不到腳本: {filename}")
            return False
        with open(path, 'r', encoding='utf-8') as f:
            self.steps = json.load(f)
        self.log(f"✓ 已載入進階腳本: {filename} ({len(self.steps)} 個步驟)")
        return True
