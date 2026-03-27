import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
import time
import threading
import os
import json
import win32gui
import win32api
from pynput import mouse
from player import ActionPlayer
from recorder import ActionRecorder
from advanced_player import AdvancedActionPlayer
from ld_controller import list_all_ldplayer_windows, get_window_screenshot
from skill_preset import (
    SkillPresetParser, SkillCooldownDetector, SkillPresetPlayer,
    save_preset, load_preset, list_presets, PRESET_DIR, ensure_preset_dir
)

def main():
    player = ActionPlayer(filename="") 
    recorder = ActionRecorder()
    skill_player = SkillPresetPlayer()
    adv_player = AdvancedActionPlayer(skill_player=skill_player)

    # --- 多開管理數據結構 ---
    instance_players = {}   # {hwnd: player_obj}
    instance_threads = {}   # {hwnd: thread_obj}
    instance_row_vars = {}  # {hwnd: {'status': StringVar, 'script': StringVar, 'check': BooleanVar, 'btn': Button}}

    def append_log(message):
        timestamp = time.strftime("%H:%M:%S")
        def update_log():
            log_text.config(state="normal")
            log_text.insert("end", f"[{timestamp}] {message}\n")
            
            # --- 效能優化：限制日誌顯示行數（預設 500 行） ---
            # 取得目前的總行數，如果超過 500 行則刪除最舊的內容
            line_count = float(log_text.index("end-1c"))
            if line_count > 500:
                log_text.delete("1.0", "2.0") # 刪除第一行
                
            log_text.see("end")
            log_text.config(state="disabled")
        root.after(0, update_log)

    player.log_callback = append_log
    recorder.log_callback = append_log
    adv_player.log_callback = append_log
    skill_player.log_callback = append_log

    def update_script_list(auto_select=True):
        scripts_dir = "scripts"
        if not os.path.exists(scripts_dir):
            os.makedirs(scripts_dir)
        files = sorted([f for f in os.listdir(scripts_dir) if f.endswith(".json")], reverse=True)
        script_combo['values'] = files

    def on_script_select(event):
        selected = script_combo.get()
        if selected:
            full_path = os.path.join("scripts", selected)
            filename_var.set(full_path)

    def select_file():
        path = filedialog.askopenfilename(title="選擇動作記錄檔", filetypes=[("JSON 檔案", "*.json"), ("全部檔案", "*.*")])
        if path: filename_var.set(path)

    def get_selected_window_info():
        selected = []
        for title, info in window_vars.items():
            if info['var'].get():
                selected.append((title, info['hwnd']))
        return selected

    # Recorder/Player Functions
    def start_record():
        filename = filename_var.get().strip()
        selected_info = get_selected_window_info()
        mode = "sync" if mode_var.get() == 0 else "independent"
        if not selected_info:
            messagebox.showwarning("警告", "請先勾選至少一個模擬器視窗")
            return
        if filename: recorder.filename = filename
        else: recorder.filename = None
        status_var.set("錄製中...")
        start_record_btn.config(state="disabled")
        stop_record_btn.config(state="normal")
        smart_mode = smart_var.get()
        threading.Thread(target=recorder.start, args=(selected_info, mode, smart_mode), daemon=True).start()

    def stop_record():
        recorder.stop()
        status_var.set("錄製已停止")
        stop_record_btn.config(state="disabled")
        start_record_btn.config(state="normal")
        update_script_list(auto_select=False)

    def start_play():
        filename = filename_var.get().strip()
        selected_info = get_selected_window_info()
        if not selected_info or not filename:
            messagebox.showwarning("警告", "請選擇模擬器與腳本檔案")
            return
        try:
            repeat = int(repeat_var.get())
        except: repeat = 1
        # 嘗試讀取並判斷類型
        import json
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
            is_advanced = isinstance(data, dict) and data.get("type") == "advanced"
        except:
            is_advanced = False

        if is_advanced:
            # 執行進階腳本播放
            adv_player.steps = data.get("steps", [])
            status_var.set("進階播放中...")
            play_btn.config(state="disabled")
            stop_play_btn.config(state="normal")
            def run_adv_play():
                adv_player.play(target_windows=selected_info, repeat=repeat)
                status_var.set("已完成" if adv_player.playing else "已停止")
                play_btn.config(state="normal")
                stop_play_btn.config(state="disabled")
            threading.Thread(target=run_adv_play, daemon=True).start()
        else:
            # 傳統播放
            player.filename = filename
            if not player.load(): return
            status_var.set("播放中...")
            play_btn.config(state="disabled")
            stop_play_btn.config(state="normal")
            def run_play():
                player.play(repeat=repeat, target_windows=selected_info)
                status_var.set("已完成" if player.playing else "已停止")
                play_btn.config(state="normal")
                stop_play_btn.config(state="disabled")
            threading.Thread(target=run_play, daemon=True).start()

    def stop_play():
        if player.playing:
            player.playing = False
            status_var.set("已停止")
        if adv_player.playing:
            adv_player.playing = False
            status_var.set("已停止")

    # Advanced Functions
    def save_adv_script():
        if not adv_player.steps:
            messagebox.showwarning("警告", "目前的腳本清單是空的")
            return
        filename = adv_player.save_script()
        update_script_list(auto_select=False)
        # 自動切換到基本分頁並選中該腳本 (選選方式)
        nb.select(0)
        script_combo.set(filename)
        filename_var.set(os.path.join("scripts", filename))
        append_log(f"✓ 已產出腳本並切換至基本功能: {filename}")
    def get_adv_step_from_ui():
        action = adv_action_var.get()
        type_rev_map = {
            "點擊 (Click)": "click",
            "滑動 (Swipe)": "swipe",
            "等候 (Wait)": "wait",
            "找圖點擊 (Find&Click)": "find_click",
            "找圖跳轉 (Find&Jump)": "find_jump",
            "偵測戰鬥 (Detect Battle)": "detect_battle",
            "等待進入戰鬥 (Wait Battle Start)": "wait_battle_start",
            "等待戰鬥結束 (Wait Battle End)": "wait_battle_end",
            "戰鬥技能 (Combat Skill)": "combat_skill"
        }
        if action not in type_rev_map: return None, None
        
        stype = type_rev_map[action]
        params = {}
        try:
            if stype == "click":
                params = {"x": int(adv_x_var.get()), "y": int(adv_y_var.get())}
            elif stype == "swipe":
                params = {"s_x": int(adv_x_var.get()), "s_y": int(adv_y_var.get()), 
                          "e_x": int(adv_ex_var.get()), "e_y": int(adv_ey_var.get())}
            elif stype == "wait":
                params = {"seconds": float(adv_x_var.get())}
            elif stype == "find_click":
                params = {"template": adv_img_path.get(), "threshold": float(adv_ex_var.get() or "0.7")}
            elif stype == "find_jump":
                params = {
                    "template": adv_img_path.get(), 
                    "threshold": float(adv_x_var.get() or "0.7"),
                    "jump_value": int(adv_y_var.get() or "0"),
                    "mode": 'absolute' if adv_ex_var.get().upper() == 'A' else 'relative',
                    "condition": 'if_not_found' if adv_ey_var.get().upper() == 'N' else 'if_found'
                }
            elif stype == "detect_battle":
                params = {
                    "duration": float(adv_x_var.get() or "2.0"),
                    "jump_value": int(adv_y_var.get() or "0"),
                    "mode": 'absolute' if adv_ex_var.get().upper() == 'A' else 'relative'
                }
            elif stype in ("wait_battle_start", "wait_battle_end"):
                params = {
                    "timeout": float(adv_x_var.get() or "60"),
                    "poll_interval": 1.0,
                    "on_timeout_jump": adv_ex_var.get().upper() == 'Y',
                    "jump_value": int(adv_y_var.get() or "0")
                }
            elif stype == "combat_skill":
                params = {"preset_file": adv_x_var.get().strip(), "set_name": adv_y_var.get().strip()}
            return stype, params
        except Exception as e:
            append_log(f"⚠️ 參數格式錯誤: {e}")
            return None, None

    def add_adv_step():
        stype, params = get_adv_step_from_ui()
        if stype:
            adv_player.add_step(stype, params)
            update_adv_list()
            if stype == "wait": append_log(f"加入等候：{params['seconds']} 秒")
            elif stype == "combat_skill": append_log(f"加入戰鬥技能：檔={params['preset_file']}, 套組={params['set_name']}")
            elif stype == "detect_battle": append_log(f"加入戰鬥跳轉：若 {params['duration']}s 內無計時器則跳轉 {params['jump_value']} 步")
            elif stype == "wait_battle_start": append_log(f"加入等待進入戰鬥：timeout={params['timeout']}s, 超時跳={params['on_timeout_jump']}")
            elif stype == "wait_battle_end": append_log(f"加入等待戰鬥結束：timeout={params['timeout']}s, 超時跳={params['on_timeout_jump']}")

    def update_adv_step():
        selected = adv_tree.selection()
        if not selected:
            messagebox.showwarning("提示", "請先從清單選中一個要更新的步驟")
            return
        index = adv_tree.index(selected[0])
        stype, params = get_adv_step_from_ui()
        if stype:
            adv_player.steps[index] = {"type": stype, "params": params}
            update_adv_list()
            append_log(f"✓ 已更新第 {index+1} 步 ({stype})")

    def import_adv_script():
        path = filedialog.askopenfilename(
            title="選擇進階腳本檔案", 
            initialdir="scripts",
            filetypes=[("JSON 檔案", "*.json"), ("全部檔案", "*.*")]
        )
        if not path: return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict) and "steps" in data:
                adv_player.steps = data["steps"]
            elif isinstance(data, list):
                adv_player.steps = data
            else:
                messagebox.showerror("錯誤", "不支援的腳本格式")
                return
            update_adv_list()
            append_log(f"✓ 已匯入進階腳本: {os.path.basename(path)} ({len(adv_player.steps)} 步)")
        except Exception as e:
            messagebox.showerror("錯誤", f"匯入失敗: {e}")

    def load_step_to_edit_ui():
        selected = adv_tree.selection()
        if not selected: return
        index = adv_tree.index(selected[0])
        step = adv_player.steps[index]
        stype = step['type']
        params = step['params']
        
        type_map = {
            "click": "點擊 (Click)",
            "swipe": "滑動 (Swipe)",
            "wait": "等候 (Wait)",
            "find_click": "找圖點擊 (Find&Click)",
            "find_jump": "找圖跳轉 (Find&Jump)",
            "detect_battle": "偵測戰鬥 (Detect Battle)",
            "wait_battle_start": "等待進入戰鬥 (Wait Battle Start)",
            "wait_battle_end": "等待戰鬥結束 (Wait Battle End)",
            "combat_skill": "戰鬥技能 (Combat Skill)"
        }
        
        if stype in type_map:
            adv_action_var.set(type_map[stype])
            adv_x_var.delete(0, tk.END); adv_y_var.delete(0, tk.END)
            adv_ex_var.delete(0, tk.END); adv_ey_var.delete(0, tk.END)
            adv_img_path.set("")
            
            if stype == "click":
                adv_x_var.insert(0, str(params.get('x', '')))
                adv_y_var.insert(0, str(params.get('y', '')))
            elif stype == "swipe":
                adv_x_var.insert(0, str(params.get('s_x', '')))
                adv_y_var.insert(0, str(params.get('s_y', '')))
                adv_ex_var.insert(0, str(params.get('e_x', '')))
                adv_ey_var.insert(0, str(params.get('e_y', '')))
            elif stype == "wait":
                adv_x_var.insert(0, str(params.get('seconds', '')))
            elif stype == "find_click":
                adv_img_path.set(params.get('template', ''))
                adv_ex_var.insert(0, str(params.get('threshold', '0.7')))
            elif stype == "find_jump":
                adv_img_path.set(params.get('template', ''))
                adv_x_var.insert(0, str(params.get('threshold', '0.7')))
                adv_y_var.insert(0, str(params.get('jump_value', '0')))
                adv_ex_var.insert(0, 'A' if params.get('mode') == 'absolute' else 'R')
                adv_ey_var.insert(0, 'N' if params.get('condition') == 'if_not_found' else 'F')
            elif stype == "detect_battle":
                adv_x_var.insert(0, str(params.get('duration', '2.0')))
                adv_y_var.insert(0, str(params.get('jump_value', '0')))
                adv_ex_var.insert(0, 'A' if params.get('mode') == 'absolute' else 'R')
            elif stype in ("wait_battle_start", "wait_battle_end"):
                adv_x_var.insert(0, str(params.get('timeout', '')))
                adv_y_var.insert(0, str(params.get('jump_value', '0')))
                adv_ex_var.insert(0, 'Y' if params.get('on_timeout_jump') else 'N')
            elif stype == "combat_skill":
                adv_x_var.insert(0, params.get('preset_file', ''))
                adv_y_var.insert(0, params.get('set_name', ''))
            
            append_log(f"已回填步驟 {index + 1} 參數")

    def update_adv_list():
        adv_tree.delete(*adv_tree.get_children())
        for i, step in enumerate(adv_player.steps):
            adv_tree.insert("", "end", values=(i+1, step['type'], str(step['params'])))

    def delete_selected_step():
        selected = adv_tree.selection()
        if not selected: return
        index = adv_tree.index(selected[0])
        if adv_player.delete_step(index):
            update_adv_list()

    def move_step_up():
        selected = adv_tree.selection()
        if not selected: return
        index = adv_tree.index(selected[0])
        if adv_player.move_step(index, -1):
            update_adv_list()
            # 保持選中
            new_selection = adv_tree.get_children()[index - 1]
            adv_tree.selection_set(new_selection)

    def move_step_down():
        selected = adv_tree.selection()
        if not selected: return
        index = adv_tree.index(selected[0])
        if adv_player.move_step(index, 1):
            update_adv_list()
            new_selection = adv_tree.get_children()[index + 1]
            adv_tree.selection_set(new_selection)

    def clear_adv_steps():
        adv_player.steps = []
        update_adv_list()

    def select_adv_image():
        path = filedialog.askopenfilename(title="選擇樣板圖片", filetypes=[("圖片檔案", "*.png *.jpg *.bmp"), ("全部檔案", "*.*")])
        if path: adv_img_path.set(path)

    def start_adv_play():
        selected_info = get_selected_window_info()
        if not selected_info:
            messagebox.showwarning("警告", "請先勾選模擬器視窗")
            return
        try: repeat = int(repeat_var.get())
        except: repeat = 1
        status_var.set("進階播放中...")
        threading.Thread(target=adv_player.play, args=(selected_info, repeat), daemon=True).start()

    def stop_adv_play():
        adv_player.playing = False
        status_var.set("進階停止")

    def pick_coordinate():
        append_log("📢 請點擊模擬器視窗以拾取座標...")
        def on_click(x, y, button, pressed):
            if not pressed:
                hwnd = win32gui.WindowFromPoint((int(x), int(y)))
                curr = hwnd
                found_hwnd = None
                while curr:
                    for title, info in window_vars.items():
                        if curr == info['hwnd']:
                            found_hwnd = curr
                            break
                    if found_hwnd: break
                    curr = win32gui.GetParent(curr)
                if found_hwnd:
                    cur_x, cur_y = win32gui.GetCursorPos()
                    rel_x, rel_y = win32gui.ScreenToClient(found_hwnd, (cur_x, cur_y))
                    adv_x_var.delete(0, tk.END); adv_x_var.insert(0, str(rel_x))
                    adv_y_var.delete(0, tk.END); adv_y_var.insert(0, str(rel_y))
                    append_log(f"✓ 已獲取座標: ({rel_x}, {rel_y})")
                else: append_log("× 未能識別模擬器視窗")
                return False 
        mouse.Listener(on_click=on_click).start()

    def pick_image():
        append_log("📢 請點擊目標按鈕中心以擷取樣板...")
        def on_click(x, y, button, pressed):
            if not pressed:
                hwnd = win32gui.WindowFromPoint((int(x), int(y)))
                curr = hwnd
                found_hwnd = None
                while curr:
                    for title, info in window_vars.items():
                        if curr == info['hwnd']:
                            found_hwnd = curr
                            break
                    if found_hwnd: break
                    curr = win32gui.GetParent(curr)
                if found_hwnd:
                    cur_x, cur_y = win32gui.GetCursorPos()
                    rel_x, rel_y = win32gui.ScreenToClient(found_hwnd, (cur_x, cur_y))
                    im = get_window_screenshot(found_hwnd)
                    if im:
                        size = 30
                        crop = im.crop((max(0, rel_x-size), max(0, rel_y-size), min(im.size[0], rel_x+size), min(im.size[1], rel_y+size)))
                        folder = "scripts/advanced/assets"
                        if not os.path.exists(folder): os.makedirs(folder)
                        path = os.path.join(folder, f"template_{int(time.time())}.png")
                        crop.save(path)
                        adv_img_path.set(path); append_log(f"✓ 已擷取樣板圖: {os.path.basename(path)}")
                    else: append_log("× 截圖失敗")
                else: append_log("× 未能識別模擬器視窗")
                return False
        mouse.Listener(on_click=on_click).start()

    def select_combat_skill_dialog():
        """彈出視窗讓用戶選擇已儲存的預設檔與套組"""
        top = tk.Toplevel(root)
        top.title("選擇戰鬥技能組")
        top.geometry("300x200")
        top.transient(root)
        top.grab_set()

        tk.Label(top, text="選擇預設檔案:").pack(pady=5)
        files = list_presets()
        file_var = tk.StringVar()
        cb_file = ttk.Combobox(top, textvariable=file_var, values=files, state="readonly", width=30)
        cb_file.pack(pady=5)

        tk.Label(top, text="選擇套組 (@名稱):").pack(pady=5)
        set_var = tk.StringVar()
        cb_set = ttk.Combobox(top, textvariable=set_var, state="readonly", width=30)
        cb_set.pack(pady=5)

        def on_file_change(event):
            fn = file_var.get()
            data = load_preset(fn)
            if data:
                ps = SkillPresetParser.parse(data.get("skill_text", ""))
                names = [p['name'] for p in ps]
                cb_set['values'] = names
                if names: cb_set.set(names[0])
        
        cb_file.bind("<<ComboboxSelected>>", on_file_change)
        if files:
            cb_file.set(files[0])
            on_file_change(None)

        def confirm():
            if file_var.get() and set_var.get():
                adv_x_var.delete(0, tk.END); adv_x_var.insert(0, file_var.get())
                adv_y_var.delete(0, tk.END); adv_y_var.insert(0, set_var.get())
                top.destroy()
        
        tk.Button(top, text="確定選擇", command=confirm, bg="#4CAF50", fg="white", width=15).pack(pady=15)

    def update_adv_ui_labels(*args):
        action = adv_action_var.get()
        if action == "點擊 (Click)":
            adv_l1.config(text="X 座標:"); adv_l2.config(text="Y 座標:")
            adv_l3.config(text="─"); adv_l4.config(text="─")
        elif action == "滑動 (Swipe)":
            adv_l1.config(text="起點 X:"); adv_l2.config(text="起點 Y:")
            adv_l3.config(text="終點 X:"); adv_l4.config(text="終點 Y:")
        elif action == "等候 (Wait)":
            adv_l1.config(text="等候秒數:"); adv_l2.config(text="─")
            adv_l3.config(text="─"); adv_l4.config(text="─")
        elif action == "找圖點擊 (Find&Click)":
            adv_l1.config(text="中心 X (選):"); adv_l2.config(text="中心 Y (選):")
            adv_l3.config(text="精準度 (0.7):"); adv_l4.config(text="─")
        elif action == "找圖跳轉 (Find&Jump)":
            adv_l1.config(text="精準度 (0.7):"); adv_l2.config(text="步數(正前負後):")
            adv_l3.config(text="模式 (R相對/A絕對):"); adv_l4.config(text="條件 (F有跳/N無跳):")
        elif action == "偵測戰鬥 (Detect Battle)":
            adv_l1.config(text="判定時長(秒):"); adv_l2.config(text="跳轉步數:")
            adv_l3.config(text="模式 (R相對/A絕對):"); adv_l4.config(text="─")
        elif action in ("等待進入戰鬥 (Wait Battle Start)", "等待戰鬥結束 (Wait Battle End)"):
            adv_l1.config(text="逾時秒數:"); adv_l2.config(text="超時跳轉步數:")
            adv_l3.config(text="超時是否跳 (Y/N):"); adv_l4.config(text="─")
        elif action == "戰鬥技能 (Combat Skill)":
            adv_l1.config(text="預設檔名(JSON):"); adv_l2.config(text="套組名稱(@名稱):")
            adv_l3.config(text="─"); adv_l4.config(text="─")
            btn_pick.config(text="選取技能", command=select_combat_skill_dialog, bg="#9C27B0")
        else:
            btn_pick.config(text="拾取點", command=pick_coordinate, bg="#E91E63")

    root = tk.Tk()
    root.title("LD AI Bot - 進階自動化版")
    root.geometry("800x850")

    filename_var = tk.StringVar()
    repeat_var = tk.StringVar(value="1")
    status_var = tk.StringVar(value="等待中")
    mode_var = tk.IntVar(value=0)
    smart_var = tk.BooleanVar(value=False)
    window_vars = {}

    nb = ttk.Notebook(root)
    nb.pack(fill="both", expand=True, padx=10, pady=5)

    tab1 = tk.Frame(nb); nb.add(tab1, text=" 基本功能 (錄製/播放) ")
    f_basic = tk.LabelFrame(tab1, text="腳本錄製與播放"); f_basic.pack(fill="x", padx=10, pady=5)
    tk.Label(f_basic, text="腳本清單:").grid(row=0, column=0, padx=5, pady=5)
    script_combo = ttk.Combobox(f_basic, width=40, state="readonly"); script_combo.grid(row=0, column=1, padx=5, pady=5)
    script_combo.bind("<<ComboboxSelected>>", on_script_select)
    tk.Button(f_basic, text="整理", command=update_script_list).grid(row=0, column=2, padx=5, pady=5)
    tk.Label(f_basic, text="檔案路徑:").grid(row=1, column=0, padx=5, pady=5)
    tk.Entry(f_basic, textvariable=filename_var, width=43).grid(row=1, column=1, padx=5, pady=5)
    tk.Button(f_basic, text="自選", command=select_file).grid(row=1, column=2, padx=5, pady=5)

    f_mode = tk.LabelFrame(tab1, text="運作模式"); f_mode.pack(fill="x", padx=10, pady=5)
    tk.Radiobutton(f_mode, text="錄一跑多 (同步)", variable=mode_var, value=0).pack(side="left", padx=10)
    tk.Radiobutton(f_mode, text="多窗獨立 (各自)", variable=mode_var, value=1).pack(side="left", padx=10)
    tk.Checkbutton(f_mode, text="視覺檢查 (Smart Mode)", variable=smart_var, fg="purple").pack(side="left", padx=10)

    f_ctrl = tk.Frame(tab1); f_ctrl.pack(fill="x", padx=10, pady=10)
    start_record_btn = tk.Button(f_ctrl, text="開始錄製", command=start_record, bg="#008CBA", fg="white", width=12); start_record_btn.grid(row=0, column=0, padx=5)
    stop_record_btn = tk.Button(f_ctrl, text="停止錄製", command=stop_record, bg="#FF9800", fg="white", width=12, state="disabled"); stop_record_btn.grid(row=0, column=1, padx=5)
    play_btn = tk.Button(f_ctrl, text="開始播放", command=start_play, bg="#4CAF50", fg="white", width=12); play_btn.grid(row=0, column=2, padx=5)
    stop_play_btn = tk.Button(f_ctrl, text="停止播放", command=stop_play, bg="#F44336", fg="white", width=12, state="disabled"); stop_play_btn.grid(row=0, column=3, padx=5)

    tab2 = tk.Frame(nb); nb.add(tab2, text=" 進階設定 (手動配置) ")
    f_adv_edit = tk.LabelFrame(tab2, text="新增動作步驟"); f_adv_edit.pack(fill="x", padx=10, pady=5)
    adv_action_var = tk.StringVar(value="點擊 (Click)")
    cb_act = ttk.Combobox(f_adv_edit, textvariable=adv_action_var, values=[
        "點擊 (Click)", "滑動 (Swipe)", "等候 (Wait)",
        "找圖點擊 (Find&Click)", "找圖跳轉 (Find&Jump)",
        "偵測戰鬥 (Detect Battle)",
        "等待進入戰鬥 (Wait Battle Start)",
        "等待戰鬥結束 (Wait Battle End)",
        "戰鬥技能 (Combat Skill)",
    ], state="readonly", width=24)
    cb_act.grid(row=0, column=0, padx=5, pady=5); adv_action_var.trace("w", update_adv_ui_labels)

    adv_l1 = tk.Label(f_adv_edit, text="X 座標:"); adv_l1.grid(row=0, column=1)
    adv_x_var = tk.Entry(f_adv_edit, width=10); adv_x_var.grid(row=0, column=2, padx=2)
    adv_l2 = tk.Label(f_adv_edit, text="Y 座標:"); adv_l2.grid(row=0, column=3)
    adv_y_var = tk.Entry(f_adv_edit, width=10); adv_y_var.grid(row=0, column=4, padx=2)
    btn_pick = tk.Button(f_adv_edit, text="拾取點", command=pick_coordinate, bg="#E91E63", fg="white")
    btn_pick.grid(row=0, column=5, padx=5)

    adv_l3 = tk.Label(f_adv_edit, text="─"); adv_l3.grid(row=1, column=1)
    adv_ex_var = tk.Entry(f_adv_edit, width=10); adv_ex_var.grid(row=1, column=2, padx=2)
    adv_l4 = tk.Label(f_adv_edit, text="─"); adv_l4.grid(row=1, column=3)
    adv_ey_var = tk.Entry(f_adv_edit, width=10); adv_ey_var.grid(row=1, column=4, padx=2)

    tk.Label(f_adv_edit, text="圖片路徑:").grid(row=2, column=0)
    adv_img_path = tk.StringVar()
    tk.Entry(f_adv_edit, textvariable=adv_img_path, width=40).grid(row=2, column=1, columnspan=3, padx=5)
    tk.Button(f_adv_edit, text="截取圖", command=pick_image, bg="#673AB7", fg="white").grid(row=2, column=4, padx=5)
    tk.Button(f_adv_edit, text="自選圖", command=select_adv_image).grid(row=2, column=5, padx=5)

    tk.Button(f_adv_edit, text="加入步驟", command=add_adv_step, bg="#2196F3", fg="white", width=12).grid(row=0, column=6, padx=10)
    tk.Button(f_adv_edit, text="更新選中", command=update_adv_step, bg="#FF9800", fg="white", width=12).grid(row=1, column=6, padx=10)
    tk.Button(f_adv_edit, text="清空清單", command=clear_adv_steps, width=12).grid(row=2, column=6, padx=10)

    f_adv_list = tk.LabelFrame(tab2, text="目前腳本步驟"); f_adv_list.pack(fill="both", expand=True, padx=10, pady=5)
    
    tree_container = tk.Frame(f_adv_list)
    tree_container.pack(fill="both", expand=True, padx=5, pady=5)

    adv_tree = ttk.Treeview(tree_container, columns=("ID", "Type", "Params"), show="headings", height=8)
    adv_tree.heading("ID", text="編號"); adv_tree.column("ID", width=50)
    adv_tree.heading("Type", text="類型"); adv_tree.column("Type", width=100)
    adv_tree.heading("Params", text="參數"); adv_tree.column("Params", width=400)
    adv_tree.pack(side="left", fill="both", expand=True)

    side_btns = tk.Frame(tree_container)
    side_btns.pack(side="right", fill="y", padx=5)
    tk.Button(side_btns, text="▲ 移上", command=move_step_up, width=8).pack(pady=2)
    tk.Button(side_btns, text="▼ 移下", command=move_step_down, width=8).pack(pady=2)
    tk.Button(side_btns, text="載入編輯", command=load_step_to_edit_ui, bg="#607D8B", fg="white", width=8).pack(pady=2)
    tk.Button(side_btns, text="刪除步驟", command=delete_selected_step, bg="#F44336", fg="white", width=8).pack(pady=10)

    f_adv_ctrl = tk.Frame(tab2); f_adv_ctrl.pack(fill="x", padx=10, pady=5)
    tk.Button(f_adv_ctrl, text="儲存為腳本 (產出)", command=save_adv_script, bg="#673AB7", fg="white", height=2, width=18).pack(side="left", padx=5)
    tk.Button(f_adv_ctrl, text="匯入腳本 (載入)", command=import_adv_script, bg="#008CBA", fg="white", height=2, width=18).pack(side="left", padx=5)
    tk.Button(f_adv_ctrl, text="開始測試執行", command=start_adv_play, bg="#4CAF50", fg="white", height=2, width=18).pack(side="left", padx=5)
    tk.Button(f_adv_ctrl, text="停止執行", command=stop_adv_play, bg="#F44336", fg="white", height=2, width=18).pack(side="left", padx=5)

    # ═══════════════════════════════════════════════════════
    # Tab 3: 預設技能
    # ═══════════════════════════════════════════════════════
    tab3 = tk.Frame(nb); nb.add(tab3, text=" 預設技能 (戰鬥施放) ")

    # --- 技能座標 (記憶用) ---
    skill_positions = {}  # {"1": [x, y], ...}
    calibration_labels = {}  # UI 標籤
    calibrating_state = {"active": False, "queue": [], "current": None}
    parsed_presets = []  # 解析後的套組

    # --- 座標與預設資料管理 ---
    def load_all_skill_data(filename=None):
        """載入指定檔案的技能相關資料（含座標與指令）"""
        data = load_preset(filename) 
        if data:
            if data.get("positions"):
                skill_positions.update(data["positions"])
            if data.get("skill_text"):
                skill_text.delete("1.0", "end")
                skill_text.insert("1.0", data["skill_text"])
            if "cast_interval" in data:
                skill_interval_var.set(str(data["cast_interval"]))
            if "battle_only" in data:
                skill_battle_var.set(data["battle_only"])
            
            update_coord_labels()
            parse_skill_text()
            return True
        return False

    def save_coords():
        """僅儲存目前的座標（保留其他設定）"""
        raw = skill_text.get("1.0", "end").strip()
        filename = preset_combo.get() or "技能預設.json"
        try:
            interval = float(skill_interval_var.get())
        except:
            interval = 0.3
        save_preset(raw, skill_positions, skill_battle_var.get(), interval, filename=filename)

    # ── 技能指令輸入區 ──
    f_skill_input = tk.LabelFrame(tab3, text="技能指令 (語法: @ 分套  : 分組  - 等待秒數  1-6 武器技能  a-f 角色技能)")
    f_skill_input.pack(fill="x", padx=10, pady=5)

    skill_text = tk.Text(f_skill_input, height=5, width=70, font=("Consolas", 11))
    skill_text.pack(fill="x", padx=5, pady=5)
    skill_text.insert("1.0", "# 範例:\n# 剣姬123a45:4:4:4b\n# @狂怒-20:1a:12345-30:ef")

    f_skill_btns = tk.Frame(f_skill_input)
    f_skill_btns.pack(fill="x", padx=5, pady=2)

    skill_set_var = tk.StringVar(value="")
    tk.Label(f_skill_btns, text="套組選擇:").pack(side="left", padx=3)
    skill_set_combo = ttk.Combobox(f_skill_btns, textvariable=skill_set_var, state="readonly", width=15)
    skill_set_combo.pack(side="left", padx=3)

    def parse_skill_text():
        nonlocal parsed_presets
        raw = skill_text.get("1.0", "end").strip()
        # 移除註解行
        lines = [l for l in raw.splitlines() if l.strip() and not l.strip().startswith('#')]
        clean = "\n".join(lines)
        parsed_presets = SkillPresetParser.parse(clean)
        if not parsed_presets:
            messagebox.showinfo("提示", "無法解析技能指令，請檢查語法")
            return
        # 更新套組下拉
        names = [p['name'] for p in parsed_presets]
        skill_set_combo['values'] = names
        if names:
            skill_set_combo.set(names[0])
        # 更新預覽
        update_skill_preview()
        append_log(f"✓ 已解析 {len(parsed_presets)} 個技能套組: {', '.join(names)}")

    tk.Button(f_skill_btns, text="解析預覽", command=parse_skill_text, bg="#2196F3", fg="white", width=10).pack(side="left", padx=5)

    def on_skill_set_select(event):
        update_skill_preview()
    skill_set_combo.bind("<<ComboboxSelected>>", on_skill_set_select)

    # ── 解析結果預覽 ──
    f_skill_preview = tk.LabelFrame(tab3, text="解析結果預覽")
    f_skill_preview.pack(fill="both", expand=True, padx=10, pady=3)

    skill_preview_tree = ttk.Treeview(f_skill_preview, columns=("ID", "Group", "Skills", "Wait"), show="headings", height=6)
    skill_preview_tree.heading("ID", text="#"); skill_preview_tree.column("ID", width=30)
    skill_preview_tree.heading("Group", text="組別"); skill_preview_tree.column("Group", width=50)
    skill_preview_tree.heading("Skills", text="技能序列"); skill_preview_tree.column("Skills", width=250)
    skill_preview_tree.heading("Wait", text="等待"); skill_preview_tree.column("Wait", width=60)
    skill_preview_tree.pack(fill="both", expand=True, padx=5, pady=3)

    def update_skill_preview():
        skill_preview_tree.delete(*skill_preview_tree.get_children())
        selected_name = skill_set_var.get()
        preset = None
        for p in parsed_presets:
            if p['name'] == selected_name:
                preset = p
                break
        if not preset:
            return
        for i, group in enumerate(preset['groups']):
            skills_str = " → ".join(group['skills']) if group['skills'] else "(空)"
            wait_str = f"{group['wait']}s" if group['wait'] > 0 else "-"
            skill_preview_tree.insert("", "end", values=(i+1, f"組{i+1}", skills_str, wait_str))
        skill_preview_tree.insert("", "end", values=("", "自動", "循環按亮起技能 (1→2→...→6→a→...→f)", "∞"))

    # ── 座標校準區 ──
    f_calibrate = tk.LabelFrame(tab3, text="技能座標校準")
    f_calibrate.pack(fill="x", padx=10, pady=3)

    # 顯示座標表格
    f_coord_grid = tk.Frame(f_calibrate)
    f_coord_grid.pack(fill="x", padx=5, pady=3)

    tk.Label(f_coord_grid, text="武器技能:", font=("Arial", 9, "bold")).grid(row=0, column=0, sticky="w", padx=3)
    for idx, sid in enumerate("123456"):
        col = idx + 1
        pos = skill_positions.get(sid, ["?", "?"])
        lbl = tk.Label(f_coord_grid, text=f"{sid}:({pos[0]},{pos[1]})", fg="#333", font=("Consolas", 9))
        lbl.grid(row=0, column=col, padx=4)
        calibration_labels[sid] = lbl

    tk.Label(f_coord_grid, text="角色技能:", font=("Arial", 9, "bold")).grid(row=1, column=0, sticky="w", padx=3)
    for idx, sid in enumerate("abcdef"):
        col = idx + 1
        pos = skill_positions.get(sid, ["?", "?"])
        lbl = tk.Label(f_coord_grid, text=f"{sid}:({pos[0]},{pos[1]})", fg="#333", font=("Consolas", 9))
        lbl.grid(row=1, column=col, padx=4)
        calibration_labels[sid] = lbl

    def update_coord_labels():
        for sid, lbl in calibration_labels.items():
            pos = skill_positions.get(sid, ["?", "?"])
            lbl.config(text=f"{sid}:({pos[0]},{pos[1]})")

    f_cal_btns = tk.Frame(f_calibrate)
    f_cal_btns.pack(fill="x", padx=5, pady=3)

    cal_status_var = tk.StringVar(value="")
    tk.Label(f_cal_btns, textvariable=cal_status_var, fg="#E91E63", font=("Arial", 10, "bold")).pack(side="left", padx=5)

    def start_calibration_all():
        """一鍵校準：依序點擊 1-6, a-f"""
        queue = list("123456abcdef")
        calibrating_state["active"] = True
        calibrating_state["queue"] = queue
        calibrating_state["current"] = queue.pop(0)
        cal_status_var.set(f"📌 請點擊技能 [{calibrating_state['current']}] 的位置")
        append_log(f"🎯 校準模式：請依序點擊各技能位置 (共 12 個)")

        def on_click(x, y, button, pressed):
            if not pressed:
                # 找到模擬器視窗
                hwnd = win32gui.WindowFromPoint((int(x), int(y)))
                curr = hwnd
                found_hwnd = None
                while curr:
                    for title, info in window_vars.items():
                        if curr == info['hwnd']:
                            found_hwnd = curr
                            break
                    if found_hwnd: break
                    curr = win32gui.GetParent(curr)
                if found_hwnd:
                    cur_x, cur_y = win32gui.GetCursorPos()
                    rel_x, rel_y = win32gui.ScreenToClient(found_hwnd, (cur_x, cur_y))
                    sid = calibrating_state["current"]
                    skill_positions[sid] = [rel_x, rel_y]
                    append_log(f"  ✓ 技能 {sid} 座標: ({rel_x}, {rel_y})")
                    root.after(0, update_coord_labels)

                    if calibrating_state["queue"]:
                        calibrating_state["current"] = calibrating_state["queue"].pop(0)
                        root.after(0, lambda: cal_status_var.set(
                            f"📌 請點擊技能 [{calibrating_state['current']}] 的位置"
                        ))
                        return  # 繼續監聽
                    else:
                        calibrating_state["active"] = False
                        save_coords()
                        root.after(0, lambda: cal_status_var.set("✅ 校準完成！座標已儲存"))
                        append_log("✅ 所有技能座標校準完成！")
                        return False  # 停止監聽
                else:
                    append_log("  × 未識別到模擬器視窗，請點擊模擬器內的技能")
                    return  # 繼續監聽
        mouse.Listener(on_click=on_click).start()

    def start_calibration_single():
        """單一點校準：只校準一個技能"""
        sid = cal_single_var.get().strip()
        if sid not in "123456abcdef" or len(sid) != 1:
            messagebox.showwarning("警告", "請輸入有效的技能 ID (1-6 或 a-f)")
            return
        cal_status_var.set(f"📌 請點擊技能 [{sid}] 的位置")
        def on_click(x, y, button, pressed):
            if not pressed:
                hwnd = win32gui.WindowFromPoint((int(x), int(y)))
                curr = hwnd
                found_hwnd = None
                while curr:
                    for title, info in window_vars.items():
                        if curr == info['hwnd']:
                            found_hwnd = curr
                            break
                    if found_hwnd: break
                    curr = win32gui.GetParent(curr)
                if found_hwnd:
                    cur_x, cur_y = win32gui.GetCursorPos()
                    rel_x, rel_y = win32gui.ScreenToClient(found_hwnd, (cur_x, cur_y))
                    skill_positions[sid] = [rel_x, rel_y]
                    save_coords()
                    root.after(0, update_coord_labels)
                    root.after(0, lambda: cal_status_var.set(f"✅ 技能 {sid}: ({rel_x}, {rel_y})"))
                    append_log(f"  ✓ 技能 {sid} 座標已更新: ({rel_x}, {rel_y})")
                else:
                    append_log("  × 未識別到模擬器視窗")
                return False
        mouse.Listener(on_click=on_click).start()

    tk.Button(f_cal_btns, text="一鍵校準 (12個)", command=start_calibration_all, bg="#E91E63", fg="white", width=14).pack(side="right", padx=3)
    cal_single_var = tk.StringVar(value="1")
    tk.Entry(f_cal_btns, textvariable=cal_single_var, width=3, font=("Consolas", 10)).pack(side="right", padx=2)
    tk.Label(f_cal_btns, text="單一校準:").pack(side="right")
    tk.Button(f_cal_btns, text="校準", command=start_calibration_single, bg="#FF9800", fg="white", width=5).pack(side="right", padx=3)

    # ── 執行設定 ──
    f_skill_settings = tk.LabelFrame(tab3, text="執行設定")
    f_skill_settings.pack(fill="x", padx=10, pady=3)

    skill_interval_var = tk.StringVar(value="0.3")
    skill_battle_var = tk.BooleanVar(value=True)

    tk.Label(f_skill_settings, text="施放間隔(秒):").pack(side="left", padx=5)
    tk.Entry(f_skill_settings, textvariable=skill_interval_var, width=5).pack(side="left", padx=3)
    tk.Checkbutton(f_skill_settings, text="僅戰鬥中施放", variable=skill_battle_var).pack(side="left", padx=10)

    # ── 亮度除錯 ──
    def debug_brightness():
        selected_info = get_selected_window_info()
        if not selected_info:
            messagebox.showwarning("警告", "請先勾選模擬器視窗")
            return
        hwnd = selected_info[0][1]
        detector = SkillCooldownDetector(skill_positions)
        ids_to_check = [s for s in "123456abcdef" if s in skill_positions]
        if not ids_to_check:
            append_log("⚠️ 請先校準座標")
            return
        append_log("🔍 技能亮度偵測:")
        detector.debug_brightness(hwnd, ids_to_check, log_fn=append_log)

    tk.Button(f_skill_settings, text="亮度測試", command=debug_brightness, bg="#607D8B", fg="white", width=8).pack(side="left", padx=5)

    # ── 儲存/載入/執行控制 ──
    f_skill_ctrl = tk.Frame(tab3)
    f_skill_ctrl.pack(fill="x", padx=10, pady=5)

    def start_skill_play():
        selected_info = get_selected_window_info()
        if not selected_info:
            messagebox.showwarning("警告", "請先勾選模擬器視窗")
            return
        if not parsed_presets:
            parse_skill_text()
            if not parsed_presets:
                return
        # 找到選中的套組
        selected_name = skill_set_var.get()
        preset = None
        for p in parsed_presets:
            if p['name'] == selected_name:
                preset = p
                break
        if not preset:
            messagebox.showwarning("警告", "請選擇一個套組")
            return
        # 檢查座標
        all_ids = SkillPresetParser.get_all_skill_ids(preset)
        missing = [s for s in all_ids if s not in skill_positions]
        if missing:
            messagebox.showwarning("警告", f"以下技能尚未校準座標: {', '.join(missing)}\n請先完成校準")
            return
        # 設定參數
        try:
            skill_player.cast_interval = float(skill_interval_var.get())
        except:
            skill_player.cast_interval = 0.3
        skill_player.battle_only = skill_battle_var.get()
        skill_player.set_positions(skill_positions)
        status_var.set(f"技能施放中：{preset['name']}")
        threading.Thread(target=skill_player.play, args=(selected_info, preset), daemon=True).start()

    def stop_skill_play():
        skill_player.stop()
        status_var.set("技能已停止")

    def save_skill_preset():
        raw = skill_text.get("1.0", "end").strip()
        if not raw:
            messagebox.showwarning("警告", "請先輸入技能指令")
            return
        
        # 取得選定的檔名或提示輸入
        sel = preset_combo.get().strip()
        if not sel:
            from tkinter import simpledialog
            sel = simpledialog.askstring("儲存預設", "請輸入預設檔名:", initialvalue="技能預設.json")
            if not sel: return

        try:
            interval = float(skill_interval_var.get())
        except:
            interval = 0.3
        
        fn = save_preset(raw, skill_positions, skill_battle_var.get(), interval, filename=sel)
        append_log(f"✓ 技能預設已儲存至 {fn}")
        update_preset_list()
        preset_combo.set(fn)

    def load_skill_preset():
        sel = preset_combo.get()
        if not sel:
            messagebox.showwarning("警告", "請先選擇一個預設檔案")
            return
        if load_all_skill_data(sel):
            append_log(f"✓ 已載入 {sel}")
        else:
            append_log(f"⚠️ 載入失敗: {sel}")

    def update_preset_list():
        files = list_presets()
        preset_combo['values'] = files

    tk.Button(f_skill_ctrl, text="▶ 開始施放", command=start_skill_play, bg="#4CAF50", fg="white", height=2, width=14).pack(side="left", padx=5)
    tk.Button(f_skill_ctrl, text="■ 停止施放", command=stop_skill_play, bg="#F44336", fg="white", height=2, width=14).pack(side="left", padx=5)
    tk.Button(f_skill_ctrl, text="儲存預設", command=save_skill_preset, bg="#673AB7", fg="white", height=2, width=10).pack(side="left", padx=5)
    preset_combo = ttk.Combobox(f_skill_ctrl, state="readonly", width=15)
    preset_combo.pack(side="left", padx=3)
    tk.Button(f_skill_ctrl, text="載入預設", command=load_skill_preset, bg="#FF9800", fg="white", height=2, width=10).pack(side="left", padx=3)

    # 啟動時自動載入或優先選取「技能預設.json」
    def init_load():
        update_preset_list()
        files = list_presets()
        if files:
            target = "技能預設.json"
            if target in files:
                preset_combo.set(target)
                load_all_skill_data(target)
            else:
                preset_combo.set(files[0])
                load_all_skill_data(files[0])
    
    root.after(300, init_load)

    # ═══════════════════════════════════════════════════════
    # Tab 4: 多開管理 (獨立控制)
    # ═══════════════════════════════════════════════════════
    tab4 = tk.Frame(nb); nb.add(tab4, text=" 多開管理 (獨立執行) ")

    f_multi_ctrl = tk.Frame(tab4); f_multi_ctrl.pack(fill="x", padx=10, pady=5)
    
    def refresh_multi_list():
        # 清空舊的 UI
        for widget in multi_list_frame.winfo_children():
            widget.destroy()
        instance_row_vars.clear()
        
        found = list_all_ldplayer_windows()
        scripts = sorted([f for f in os.listdir("scripts") if f.endswith(".json")], reverse=True)
        
        # 標題列
        header_bg = "#e0e0e0"
        tk.Label(multi_list_frame, text="選取", bg=header_bg, width=5).grid(row=0, column=0, sticky="nsew", padx=1, pady=1)
        tk.Label(multi_list_frame, text="模擬器視窗標題 (HWND)", bg=header_bg, width=35).grid(row=0, column=1, sticky="nsew", padx=1, pady=1)
        tk.Label(multi_list_frame, text="指定執行腳本", bg=header_bg, width=30).grid(row=0, column=2, sticky="nsew", padx=1, pady=1)
        tk.Label(multi_list_frame, text="目前狀態", bg=header_bg, width=12).grid(row=0, column=3, sticky="nsew", padx=1, pady=1)
        tk.Label(multi_list_frame, text="操作", bg=header_bg, width=10).grid(row=0, column=4, sticky="nsew", padx=1, pady=1)

        for i, (title, hwnd) in enumerate(found):
            row = i + 1
            check_var = tk.BooleanVar(value=False)
            script_var = tk.StringVar()
            status_var_inst = tk.StringVar(value="停止")
            
            # 若已有正在執行的狀態，繼承它 (這裡簡單處理，刷新後預設停止，除非我們要追蹤全域狀態)
            if hwnd in instance_threads and instance_threads[hwnd].is_alive():
                status_var_inst.set("運行中")

            # 選取框
            cb = tk.Checkbutton(multi_list_frame, variable=check_var)
            cb.grid(row=row, column=0, padx=1, pady=1)
            
            # 標題
            tk.Label(multi_list_frame, text=f"{title} ({hwnd})", anchor="w").grid(row=row, column=1, sticky="w", padx=5, pady=1)
            
            # 腳本下拉
            cmb = ttk.Combobox(multi_list_frame, textvariable=script_var, values=scripts, state="readonly", width=28)
            cmb.grid(row=row, column=2, padx=5, pady=1)
            if scripts: cmb.set(scripts[0])
            
            # 狀態標籤
            lbl_status = tk.Label(multi_list_frame, textvariable=status_var_inst, fg="gray")
            lbl_status.grid(row=row, column=3, padx=1, pady=1)
            
            # 開始/停止按鈕
            btn_text = "停止" if status_var_inst.get() == "運行中" else "開始"
            btn_bg = "#F44336" if btn_text == "停止" else "#4CAF50"
            btn = tk.Button(multi_list_frame, text=btn_text, bg=btn_bg, fg="white", width=8)
            btn.config(command=lambda h=hwnd, s=script_var, v=status_var_inst, b=btn: toggle_instance_play(h, s, v, b))
            btn.grid(row=row, column=4, padx=5, pady=2)
            
            instance_row_vars[hwnd] = {
                'check': check_var,
                'script': script_var,
                'status': status_var_inst,
                'btn': btn,
                'title': title
            }

    tk.Button(f_multi_ctrl, text="🔄 刷新模擬器列表", command=refresh_multi_list, bg="#008CBA", fg="white").pack(side="left", padx=5)
    
    def batch_action(action_type):
        """action_type: 'start' or 'stop'"""
        for hwnd, info in instance_row_vars.items():
            if info['check'].get():
                curr_status = info['status'].get()
                if action_type == 'start' and curr_status != "運行中":
                    toggle_instance_play(hwnd, info['script'], info['status'], info['btn'])
                elif action_type == 'stop' and curr_status == "運行中":
                    toggle_instance_play(hwnd, info['script'], info['status'], info['btn'])

    tk.Button(f_multi_ctrl, text="▶ 啟動選中項", command=lambda: batch_action('start'), bg="#4CAF50", fg="white").pack(side="left", padx=5)
    tk.Button(f_multi_ctrl, text="■ 停止選中項", command=lambda: batch_action('stop'), bg="#F44336", fg="white").pack(side="left", padx=5)

    def select_all_instances():
        for info in instance_row_vars.values():
            info['check'].set(True)
    tk.Button(f_multi_ctrl, text="全選", command=select_all_instances).pack(side="left", padx=5)

    # 列表區域 (可捲動)
    multi_list_container = tk.Frame(tab4)
    multi_list_container.pack(fill="both", expand=True, padx=10, pady=5)
    
    multi_canvas = tk.Canvas(multi_list_container)
    multi_v_scroll = ttk.Scrollbar(multi_list_container, orient="vertical", command=multi_canvas.yview)
    multi_h_scroll = ttk.Scrollbar(multi_list_container, orient="horizontal", command=multi_canvas.xview)
    multi_list_frame = tk.Frame(multi_canvas)
    
    multi_list_frame.bind("<Configure>", lambda e: multi_canvas.configure(scrollregion=multi_canvas.bbox("all")))
    multi_canvas.create_window((0, 0), window=multi_list_frame, anchor="nw")
    multi_canvas.configure(yscrollcommand=multi_v_scroll.set, xscrollcommand=multi_h_scroll.set)
    
    multi_canvas.pack(side="top", fill="both", expand=True)
    multi_v_scroll.pack(side="right", fill="y", before=multi_canvas) # 修正 pack 順序
    multi_v_scroll.pack_forget(); multi_v_scroll.pack(side="right", fill="y")
    multi_h_scroll.pack(side="bottom", fill="x")

    def toggle_instance_play(hwnd, script_var, status_var_inst, btn):
        if status_var_inst.get() == "運行中":
            # 停止
            if hwnd in instance_players:
                instance_players[hwnd].playing = False
                append_log(f"🛑 已發送停止信號至 [{hwnd}]")
        else:
            # 開始
            script_name = script_var.get()
            if not script_name:
                messagebox.showwarning("警告", "請先選擇腳本")
                return
            
            script_path = os.path.join("scripts", script_name)
            if not os.path.exists(script_path):
                messagebox.showerror("錯誤", f"找不到腳本檔案: {script_name}")
                return

            status_var_inst.set("運行中")
            btn.config(text="停止", bg="#F44336")
            
            t = threading.Thread(target=run_single_instance_task, args=(hwnd, script_path, status_var_inst, btn), daemon=True)
            instance_threads[hwnd] = t
            t.start()

    def run_single_instance_task(hwnd, script_path, status_var_inst, btn):
        title = ""
        for h, info in instance_row_vars.items():
            if h == hwnd:
                title = info['title']
                break
        
        append_log(f"🚀 啟動模擬器 [{title}] 執行腳本: {os.path.basename(script_path)}")
        
        try:
            # 辨識腳本類型
            with open(script_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            is_advanced = isinstance(data, dict) and data.get("type") == "advanced"
            
            # 獲取或建立 Player 實例
            if is_advanced:
                inst_player = AdvancedActionPlayer(skill_player=SkillPresetPlayer())
                inst_player.steps = data.get("steps", [])
            else:
                inst_player = ActionPlayer(filename=script_path)
                inst_player.load()
            
            inst_player.log_callback = lambda msg: append_log(f"[{title}] {msg}")
            instance_players[hwnd] = inst_player
            
            # 獲取全域重複次數
            try: repeat = int(repeat_var.get())
            except: repeat = 1
            
            # 開始執行 (這會阻塞直到播放完成或停止)
            target = [(title, hwnd)]
            if is_advanced:
                inst_player.play(target, repeat=repeat)
            else:
                inst_player.play(repeat=repeat, target_windows=target)
                
        except Exception as e:
            append_log(f"❌ 模擬器 [{title}] 執行發生異常: {e}")
        finally:
            status_var_inst.set("停止")
            btn.config(text="開始", bg="#4CAF50")
            if hwnd in instance_players:
                del instance_players[hwnd]
            append_log(f"🏁 模擬器 [{title}] 腳本執行結束")

    # ═══════════════════════════════════════════════════════
    # 共用底部區域
    # ═══════════════════════════════════════════════════════
    f_shared = tk.Frame(root); f_shared.pack(fill="x", padx=15, pady=5)
    tk.Label(f_shared, text="重複次數:").pack(side="left")
    tk.Entry(f_shared, textvariable=repeat_var, width=5).pack(side="left", padx=5)
    
    f_win = tk.LabelFrame(root, text="模擬器選取 (全域)"); f_win.pack(fill="x", padx=10, pady=5)
    tk.Button(f_win, text="重新整理視窗列表", command=lambda: refresh_windows()).pack(side="left", padx=10, pady=2)
    win_container = tk.Frame(f_win); win_container.pack(fill="both", expand=True, padx=5, pady=5)
    win_canvas = tk.Canvas(win_container, height=80)
    win_scroll = ttk.Scrollbar(win_container, orient="vertical", command=win_canvas.yview)
    win_frame = tk.Frame(win_canvas)
    win_frame.bind("<Configure>", lambda e: win_canvas.configure(scrollregion=win_canvas.bbox("all")))
    win_canvas.create_window((0, 0), window=win_frame, anchor="nw")
    win_canvas.configure(yscrollcommand=win_scroll.set); win_canvas.pack(side="left", fill="both", expand=True); win_scroll.pack(side="right", fill="y")

    def refresh_windows():
        found = list_all_ldplayer_windows()
        for widget in win_frame.winfo_children(): widget.destroy()
        window_vars.clear()
        for title, hwnd in found:
            var = tk.BooleanVar(value=False); window_vars[title] = {'var': var, 'hwnd': hwnd}
            tk.Checkbutton(win_frame, text=f"{title} (ID: {hwnd})", variable=var, anchor="w").pack(fill="x", padx=5)
        append_log(f"已整理視窗，共發現 {len(found)} 個模擬器")

    tk.Label(root, text="狀態:").pack(anchor="w", padx=15)
    tk.Label(root, textvariable=status_var, fg="blue", font=("Arial", 10, "bold")).pack(anchor="w", padx=25)
    tk.Label(root, text="操作日誌:").pack(anchor="w", padx=15)
    log_text = ScrolledText(root, height=10, state="disabled"); log_text.pack(fill="both", expand=True, padx=15, pady=5)

    root.after(100, refresh_windows)
    root.after(150, refresh_multi_list)
    root.after(200, lambda: update_script_list(auto_select=False))
    root.mainloop()

if __name__ == "__main__":
    main()