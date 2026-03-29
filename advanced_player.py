import json
import time
import os
import threading
import cv2
import numpy as np
from ld_controller import send_click, send_swipe, get_window_screenshot
from battle_detector import (
    is_in_battle, get_battle_state, wait_for_battle_start, wait_for_battle_end, debug_snapshot
)
from skill_preset import SkillPresetParser, load_preset

class AdvancedActionPlayer:
    def __init__(self, skill_player=None):
        self.steps = []
        self.playing = False
        self.log_callback = None
        self.skill_player = skill_player
        self.runtime_preset = None # {"preset_file": str, "set_name": str}
        self.scripts_dir = "scripts"
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
        action_type:
          'click'            — 點擊 (x, y)
          'swipe'            — 滑動 (s_x, s_y, e_x, e_y)
          'wait'             — 等待 seconds 秒
          'find_click'       — 找圖點擊
          'find_jump'        — 找圖跳轉
          'detect_battle'    — 偵測戰鬥狀態並依據結果跳轉
          'wait_battle_start'— 等待進入戰鬥（計時器出現）
          'wait_battle_end'  — 等待戰鬥結束（計時器消失）
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
            
            i = 0
            while i < len(self.steps):
                if not self.playing: break
                
                step = self.steps[i]
                jump_to = self.execute_step(target_windows, step, current_index=i)
                
                if jump_to is not None:
                    i = jump_to
                else:
                    i += 1
        
        self.playing = False
        self.log("\n=== 進階腳本執行完成 ===")

    def execute_step(self, target_windows, step, current_index=0):
        action_type = step["type"]
        params = step["params"]
        
        # 目前進階模式暫定為同步模式 (Sync)
        target_hwnds = [hwnd for _, hwnd in target_windows]

        if action_type == "click":
            for title, hwnd in target_windows:
                if not self.playing: break
                self.log(f"    ➜ [{title}] 執行點擊 ({params['x']}, {params['y']})")
                send_click(hwnd, params['x'], params['y'])
                time.sleep(0.05)
                
        elif action_type == "swipe":
            for title, hwnd in target_windows:
                if not self.playing: break
                self.log(f"    ➜ [{title}] 執行滑動 ({params['s_x']}, {params['s_y']}) -> ({params['e_x']}, {params['e_y']})")
                send_swipe(hwnd, params['s_x'], params['s_y'], params['e_x'], params['e_y'], params.get('duration', 0.5))
                time.sleep(0.05)
                
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
        
        elif action_type == "find_jump":
            template_path = params['template']
            threshold = params.get('threshold', 0.7)
            jump_val = params.get('jump_value', 0)
            mode = params.get('mode', 'relative') # 'relative' or 'absolute'
            condition = params.get('condition', 'if_found') # 'if_found' or 'if_not_found'
            
            self.log(f"  ➜ 判斷圖片跳轉: {os.path.basename(template_path)} (條件: {condition})")
            
            # 使用第一個視窗作為主要判定依據
            if target_hwnds:
                main_hwnd = target_hwnds[0]
                found_pos = self.find_image(main_hwnd, template_path, threshold)
                
                # 判定邏輯：(找到圖且條件為有圖就跳) 或 (沒找到圖且條件為沒圖就跳)
                should_jump = (found_pos is not None and condition == 'if_found') or \
                              (found_pos is None and condition == 'if_not_found')
                
                if should_jump:
                    if mode == 'relative':
                        target_idx = current_index + jump_val
                    else:
                        target_idx = jump_val - 1 # UI 顯示 1-indexed, 內部為 0-indexed
                    
                    # 邊界檢查
                    target_idx = max(0, min(target_idx, len(self.steps)))
                    self.log(f"    ✓ 達成條件！跳轉至步驟 {target_idx + 1}")
                    return target_idx
                else:
                    self.log(f"    × 未達成跳轉條件，繼續下一步")

        # ── 偵測戰鬥：判定是否有計時器，若無則執行跳轉 ───────────────
        elif action_type == "detect_battle":
            duration     = params.get('duration', 2.0)
            jump_val     = params.get('jump_value', 0)
            mode         = params.get('mode', 'relative')

            if target_hwnds:
                main_hwnd = target_hwnds[0]
                # 使用 get_battle_state 取得具體類別
                state = get_battle_state(main_hwnd)
                
                # 如果判定「不在戰鬥中」(包含 pre_battle 或 none)，就執行跳轉
                if state not in ["in_battle_normal", "in_battle_rare"]:
                    if mode == 'relative':
                         target_idx = current_index + jump_val
                    else:
                        target_idx = jump_val - 1
                    target_idx = max(0, min(target_idx, len(self.steps)))
                    
                    self.log(f"  ➜ 戰鬥判定：非戰鬥中 (狀態: {state}) -> 跳轉至步驟 {target_idx + 1}")
                    return target_idx
                else:
                    status_text = "一般" if state == "in_battle_normal" else "稀有"
                    self.log(f"    ✓ 戰鬥中({status_text})，繼續執行後續指令")

        # ── 等待進入戰鬥 ─────────────────────────────────────────────
        elif action_type == "wait_battle_start":
            # params 結構：
            #   timeout:       最長等候秒數（預設 60）
            #   poll_interval: 輪詢間隔（預設 0.5）
            #   on_timeout_jump: 超時是否跳轉（True/False，預設 False）
            #   jump_value:    超時時跳轉步數（相對）
            timeout       = params.get('timeout', 60)
            poll_interval = params.get('poll_interval', 0.5)
            on_timeout_jump = params.get('on_timeout_jump', False)
            jump_val      = params.get('jump_value', 0)

            if target_hwnds:
                self.log(f"  ➜ 等待進入戰鬥（最多 {timeout}s）...")
                success = wait_for_battle_start(
                    target_hwnds[0],
                    timeout=timeout,
                    poll_interval=poll_interval,
                    log_fn=self.log
                )
                if not success and on_timeout_jump and jump_val != 0:
                    target_idx = max(0, min(current_index + jump_val, len(self.steps)))
                    self.log(f"    ⏱ 超時跳轉至步驟 {target_idx + 1}")
                    return target_idx

        # ── 等待戰鬥結束 ─────────────────────────────────────────────
        elif action_type == "wait_battle_end":
            # params 結構：
            #   timeout:       最長等候秒數（預設 300）
            #   poll_interval: 輪詢間隔（預設 1.0）
            #   on_timeout_jump: 超時是否跳轉
            #   jump_value:    超時時跳轉步數（相對）
            timeout         = params.get('timeout', 300)
            poll_interval   = params.get('poll_interval', 1.0)
            on_timeout_jump = params.get('on_timeout_jump', False)
            jump_val        = params.get('jump_value', 0)

            if target_hwnds:
                self.log(f"  ➜ 等待戰鬥結束（最多 {timeout}s）...")
                success = wait_for_battle_end(
                    target_hwnds[0],
                    timeout=timeout,
                    poll_interval=poll_interval,
                    log_fn=self.log
                )
                if not success and on_timeout_jump and jump_val != 0:
                    target_idx = max(0, min(current_index + jump_val, len(self.steps)))
                    self.log(f"    ⏱ 超時跳轉至步驟 {target_idx + 1}")
                    return target_idx

        # ── 執行預設技能組 ──
        elif action_type == "combat_skill":
            preset_file = params.get('preset_file')
            set_name    = params.get('set_name')
            
            # 優先檢查是否為動態套用的特殊標記
            if preset_file == "__CURRENT__" and self.runtime_preset:
                preset_file = self.runtime_preset.get('preset_file')
                set_name = self.runtime_preset.get('set_name')
                self.log(f"  ➜ 執行全域/實例動態技能：檔案={preset_file}, 套組={set_name}")
            else:
                self.log(f"  ➜ 執行預設技能：檔案={preset_file}, 套組={set_name}")
            
            if self.skill_player and target_hwnds:
                # 載入預設
                data = load_preset(preset_file)
                if not data:
                    self.log(f"    × 找不到預設檔: {preset_file}")
                    return None
                
                # 解析套組
                presets = SkillPresetParser.parse(data.get("skill_text", ""))
                preset = next((p for p in presets if p['name'] == set_name), None)
                
                if not preset:
                    self.log(f"    × 預設檔中找不到套組: {set_name}")
                    return None
                
                # 執行技能 (skill_player.play 會在戰鬥結束後自動停止)
                # 這裡需要同步執行，所以直接呼叫
                # 先更新座標與設定
                self.skill_player.set_positions(data.get("positions", {}))
                self.skill_player.battle_only = True # 強制僅戰鬥中
                self.skill_player.cast_interval = data.get("cast_interval", 0.3)
                
                # 執行一輪直到戰鬥結束
                self.skill_player.play(target_windows, preset)
                self.log(f"    ✓ 預設技能執行完畢（戰鬥結束或手動停止）")

        return None

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

    def save_script(self, filename=None):
        if not filename:
            base_name = "進階腳本"
            ext = ".json"
            target_path = os.path.join(self.scripts_dir, f"{base_name}{ext}")
            
            if os.path.exists(target_path):
                counter = 1
                while os.path.exists(os.path.join(self.scripts_dir, f"{base_name}{counter}{ext}")):
                    counter += 1
                target_path = os.path.join(self.scripts_dir, f"{base_name}{counter}{ext}")
            
            filename = os.path.basename(target_path)
        
        if not filename.endswith(".json"):
            filename += ".json"
            
        path = os.path.join(self.scripts_dir, filename)
        
        # 儲存為統一包裝格式
        output = {
            "type": "advanced",
            "steps": self.steps
        }
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
            
        self.log(f"✓ 進階腳本已儲存: {filename}")
        return filename

    def load_script(self, filename):
        path = os.path.join(self.scripts_dir, filename)
        if not os.path.exists(path):
            self.log(f"✗ 找不到腳本: {filename}")
            return False
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, dict) and "steps" in data:
                self.steps = data["steps"]
            else:
                self.steps = data
        self.log(f"✓ 已載入進階腳本: {filename} ({len(self.steps)} 個步驟)")
        return True
