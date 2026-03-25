import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
import time
import threading
from player import ActionPlayer
from recorder import ActionRecorder
from ld_controller import list_all_ldplayer_windows

def main():
    player = ActionPlayer()
    recorder = ActionRecorder(filename=player.filename)

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

    def select_file():
        path = filedialog.askopenfilename(
            title="選擇動作記錄檔",
            filetypes=[("JSON 檔案", "*.json"), ("全部檔案", "*.*")]
        )
        if path:
            filename_var.set(path)

    def get_selected_window_info():
        # 回傳選中的 [(title, hwnd), ...]
        selected = []
        for title, info in window_vars.items():
            if info['var'].get():
                selected.append((title, info['hwnd']))
        return selected

    def start_record():
        filename = filename_var.get().strip()
        selected_info = get_selected_window_info()
        mode = "sync" if mode_var.get() == 0 else "independent"
        
        if not selected_info:
            messagebox.showwarning("警告", "請先勾選至少一個模擬器視窗")
            return
            
        if mode == "sync" and len(selected_info) > 1:
            append_log(f"⚠️ 注意：錄一跑多模式將使用第一個勾選視窗作為錄製源：{selected_info[0][0]}")

        if filename:
            recorder.filename = filename
        
        status_var.set("錄製中...")
        start_record_btn.config(state="disabled")
        stop_record_btn.config(state="normal")
        
        # 啟動錄製線程
        record_thread = threading.Thread(target=recorder.start, args=(selected_info, mode), daemon=True)
        record_thread.start()

    def stop_record():
        recorder.stop()
        status_var.set("錄製已停止")
        stop_record_btn.config(state="disabled")
        start_record_btn.config(state="normal")

    def start_play():
        filename = filename_var.get().strip()
        selected_info = get_selected_window_info()
        
        if not selected_info:
            messagebox.showwarning("警告", "請先勾選至少一個目標模擬器視窗")
            return
            
        if not filename:
            messagebox.showwarning("警告", "請先選擇動作檔案")
            return

        try:
            repeat = int(repeat_var.get())
            if repeat < 1: raise ValueError
        except ValueError:
            messagebox.showwarning("警告", "請輸入正整數的重複次數")
            return

        player.filename = filename
        if not player.load():
            status_var.set("載入失敗")
            return

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

    root = tk.Tk()
    root.title("LD AI Bot - 多開同步版")
    root.geometry("750x700")

    filename_var = tk.StringVar(value=player.filename)
    repeat_var = tk.StringVar(value="1")
    status_var = tk.StringVar(value="等待中")
    mode_var = tk.IntVar(value=0) # 0: Sync, 1: Independent
    
    window_vars = {} # {title: {'var': BooleanVar, 'hwnd': int}}
    
    def refresh_windows():
        found = list_all_ldplayer_windows() # [(title, hwnd), ...]
        for widget in scrollable_frame.winfo_children():
            widget.destroy()
            
        window_vars.clear()
        for title, hwnd in found:
            var = tk.BooleanVar(value=False)
            window_vars[title] = {'var': var, 'hwnd': hwnd}
            cb = tk.Checkbutton(scrollable_frame, text=f"{title} (ID: {hwnd})", variable=var, anchor="w")
            cb.pack(fill="x", padx=5)
            
        append_log(f"已整理視窗，共發現 {len(found)} 個模擬器")

    # Layout
    frame_top = tk.LabelFrame(root, text="基本設定")
    frame_top.pack(fill="x", padx=12, pady=5)

    tk.Label(frame_top, text="記錄檔:").grid(row=0, column=0, padx=5, pady=5)
    tk.Entry(frame_top, textvariable=filename_var, width=50).grid(row=0, column=1, padx=5, pady=5)
    tk.Button(frame_top, text="選擇", command=select_file).grid(row=0, column=2, padx=5, pady=5)

    tk.Label(frame_top, text="重複次數:").grid(row=1, column=0, padx=5, pady=5)
    tk.Entry(frame_top, textvariable=repeat_var, width=10).grid(row=1, column=1, sticky="w", padx=5, pady=5)

    frame_mode = tk.LabelFrame(root, text="運作模式")
    frame_mode.pack(fill="x", padx=12, pady=5)
    tk.Radiobutton(frame_mode, text="錄一跑多 (同步操作)", variable=mode_var, value=0).pack(side="left", padx=20)
    tk.Radiobutton(frame_mode, text="多窗獨立 (各自錄製)", variable=mode_var, value=1).pack(side="left", padx=20)

    frame_mid = tk.LabelFrame(root, text="模擬器選取")
    frame_mid.pack(fill="both", expand=False, padx=12, pady=5)
    tk.Button(frame_mid, text="重新整理視窗列表", command=refresh_windows).pack(pady=5)

    list_container = tk.Frame(frame_mid)
    list_container.pack(fill="both", expand=True, padx=5, pady=5)
    canvas = tk.Canvas(list_container, height=120)
    scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=canvas.yview)
    scrollable_frame = tk.Frame(canvas)
    scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    
    frame_btn = tk.Frame(root)
    frame_btn.pack(fill="x", padx=12, pady=10)
    start_record_btn = tk.Button(frame_btn, text="開始錄製", command=start_record, width=15, bg="#008CBA", fg="white")
    start_record_btn.grid(row=0, column=0, padx=5)
    stop_record_btn = tk.Button(frame_btn, text="停止錄製", command=stop_record, width=15, bg="#FF9800", fg="white", state="disabled")
    stop_record_btn.grid(row=0, column=1, padx=5)
    play_btn = tk.Button(frame_btn, text="開始播放", command=start_play, width=15, bg="#4CAF50", fg="white")
    play_btn.grid(row=0, column=2, padx=5)
    stop_play_btn = tk.Button(frame_btn, text="停止播放", command=stop_play, width=15, bg="#F44336", fg="white", state="disabled")
    stop_play_btn.grid(row=0, column=3, padx=5)

    tk.Label(root, text="狀態:").pack(anchor="w", padx=12)
    tk.Label(root, textvariable=status_var, fg="blue").pack(anchor="w", padx=20)

    tk.Label(root, text="日誌:").pack(anchor="w", padx=12)
    log_text = ScrolledText(root, height=15, state="disabled")
    log_text.pack(fill="both", expand=True, padx=12, pady=5)

    root.after(100, refresh_windows)
    root.mainloop()

if __name__ == "__main__":
    main()