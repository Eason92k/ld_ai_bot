import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
import time
import threading
import os
import win32gui
import win32api
from pynput import mouse
from player import ActionPlayer
from recorder import ActionRecorder
from advanced_player import AdvancedActionPlayer
from ld_controller import list_all_ldplayer_windows, get_window_screenshot

def main():
    player = ActionPlayer(filename="") 
    recorder = ActionRecorder()
    adv_player = AdvancedActionPlayer()

    def append_log(message):
        timestamp = time.strftime("%H:%M:%S")
        def update_log():
            log_text.config(state="normal")
            log_text.insert("end", f"[{timestamp}] {message}\n")
            log_text.see("end")
            log_text.config(state="disabled")
        root.after(0, update_log)

    player.log_callback = append_log
    recorder.log_callback = append_log
    adv_player.log_callback = append_log

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

    # Advanced Functions
    def add_adv_step():
        action = adv_action_var.get()
        if action == "點擊 (Click)":
            try:
                x, y = int(adv_x_var.get()), int(adv_y_var.get())
                adv_player.add_step("click", {"x": x, "y": y})
            except: return
        elif action == "滑動 (Swipe)":
            try:
                sx, sy = int(adv_x_var.get()), int(adv_y_var.get())
                ex, ey = int(adv_ex_var.get()), int(adv_ey_var.get())
                adv_player.add_step("swipe", {"s_x": sx, "s_y": sy, "e_x": ex, "e_y": ey})
            except: return
        elif action == "等候 (Wait)":
            try:
                sec = float(adv_x_var.get())
                adv_player.add_step("wait", {"seconds": sec})
                append_log(f"加入等候：{sec} 秒")
            except: return
        elif action == "找圖點擊 (Find&Click)":
            path = adv_img_path.get()
            if not path: return
            try:
                thr = float(adv_ex_var.get() if adv_ex_var.get() else "0.7")
            except: thr = 0.7
            adv_player.add_step("find_click", {"template": path, "threshold": thr})
        
        update_adv_list()

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

    tab2 = tk.Frame(nb); nb.add(tab2, text=" 進階功能 (手動配置) ")
    f_adv_edit = tk.LabelFrame(tab2, text="新增動作步驟"); f_adv_edit.pack(fill="x", padx=10, pady=5)
    adv_action_var = tk.StringVar(value="點擊 (Click)")
    cb_act = ttk.Combobox(f_adv_edit, textvariable=adv_action_var, values=["點擊 (Click)", "滑動 (Swipe)", "等候 (Wait)", "找圖點擊 (Find&Click)"], state="readonly", width=18)
    cb_act.grid(row=0, column=0, padx=5, pady=5); adv_action_var.trace("w", update_adv_ui_labels)

    adv_l1 = tk.Label(f_adv_edit, text="X 座標:"); adv_l1.grid(row=0, column=1)
    adv_x_var = tk.Entry(f_adv_edit, width=10); adv_x_var.grid(row=0, column=2, padx=2)
    adv_l2 = tk.Label(f_adv_edit, text="Y 座標:"); adv_l2.grid(row=0, column=3)
    adv_y_var = tk.Entry(f_adv_edit, width=10); adv_y_var.grid(row=0, column=4, padx=2)
    tk.Button(f_adv_edit, text="拾取點", command=pick_coordinate, bg="#E91E63", fg="white").grid(row=0, column=5, padx=5)

    adv_l3 = tk.Label(f_adv_edit, text="─"); adv_l3.grid(row=1, column=1)
    adv_ex_var = tk.Entry(f_adv_edit, width=10); adv_ex_var.grid(row=1, column=2, padx=2)
    adv_l4 = tk.Label(f_adv_edit, text="─"); adv_l4.grid(row=1, column=3)
    adv_ey_var = tk.Entry(f_adv_edit, width=10); adv_ey_var.grid(row=1, column=4, padx=2)

    tk.Label(f_adv_edit, text="圖片路徑:").grid(row=2, column=0)
    adv_img_path = tk.StringVar()
    tk.Entry(f_adv_edit, textvariable=adv_img_path, width=40).grid(row=2, column=1, columnspan=3, padx=5)
    tk.Button(f_adv_edit, text="截取圖", command=pick_image, bg="#673AB7", fg="white").grid(row=2, column=4, padx=5)
    tk.Button(f_adv_edit, text="自選圖", command=select_adv_image).grid(row=2, column=5, padx=5)

    tk.Button(f_adv_edit, text="加入步驟", command=add_adv_step, bg="#2196F3", fg="white", width=12).grid(row=0, column=6, rowspan=2, padx=10)
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
    tk.Button(side_btns, text="刪除步驟", command=delete_selected_step, bg="#F44336", fg="white", width=8).pack(pady=10)

    f_adv_ctrl = tk.Frame(tab2); f_adv_ctrl.pack(fill="x", padx=10, pady=5)
    tk.Button(f_adv_ctrl, text="開始執行進階腳本", command=start_adv_play, bg="#4CAF50", fg="white", height=2, width=20).pack(side="left", padx=5)
    tk.Button(f_adv_ctrl, text="停止執行", command=stop_adv_play, bg="#F44336", fg="white", height=2, width=20).pack(side="left", padx=5)

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

    root.after(100, refresh_windows); root.after(200, lambda: update_script_list(auto_select=False))
    root.mainloop()

if __name__ == "__main__":
    main()