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

    def start_record():
        filename = filename_var.get().strip()
        selected_windows = [t for t, v in window_vars.items() if v.get()]
        
        if not selected_windows:
            messagebox.showwarning("警告", "請先勾選一個欲錄製的模擬器視窗")
            return
            
        window_title = selected_windows[0]
        if len(selected_windows) > 1:
            append_log(f"⚠️ 注意：偵測到多個勾選，將使用第一個：{window_title}")

        if filename:
            recorder.filename = filename
        
        recorder.window_title = window_title
        recorder.recording = True
        status_var.set("錄製中...")
        start_record_btn.config(state="disabled")
        stop_record_btn.config(state="normal")
        record_thread = threading.Thread(target=recorder.start, daemon=True)
        record_thread.start()

    def stop_record():
        recorder.stop()
        status_var.set("錄製已停止")
        stop_record_btn.config(state="disabled")
        start_record_btn.config(state="normal")

    def start_play():
        filename = filename_var.get().strip()
        selected_windows = [t for t, v in window_vars.items() if v.get()]
        
        if not selected_windows:
            messagebox.showwarning("警告", "請先勾選至少一個模擬器視窗")
            return
            
        if not filename:
            messagebox.showwarning("警告", "請先選擇動作檔案")
            return

        try:
            repeat = int(repeat_var.get())
            if repeat < 1:
                raise ValueError
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
        repeat_entry.config(state="disabled")

        def run_play():
            player.play(repeat=repeat, window_titles=selected_windows)
            if player.playing:
                status_var.set("已完成")
            play_btn.config(state="normal")
            stop_play_btn.config(state="disabled")
            repeat_entry.config(state="normal")

        threading.Thread(target=run_play, daemon=True).start()

    def stop_play():
        if player.playing:
            player.playing = False
            status_var.set("已停止")
            stop_play_btn.config(state="disabled")
            play_btn.config(state="normal")
            repeat_entry.config(state="normal")

    root = tk.Tk()
    root.title("LD AI Bot 綜合控制面板")
    root.geometry("700x650")

    filename_var = tk.StringVar(value=player.filename)
    repeat_var = tk.StringVar(value="1")
    manual_window_var = tk.StringVar()
    status_var = tk.StringVar(value="等待中")
    
    window_vars = {}
    
    def refresh_windows():
        found_windows = list_all_ldplayer_windows()
        for widget in scrollable_frame.winfo_children():
            widget.destroy()
            
        current_titles = list(window_vars.keys())
        all_titles = sorted(list(set(found_windows + current_titles)))
        
        new_window_vars = {}
        for title in all_titles:
            var = window_vars.get(title, tk.BooleanVar(value=False))
            new_window_vars[title] = var
            cb = tk.Checkbutton(scrollable_frame, text=title, variable=var, anchor="w")
            cb.pack(fill="x", padx=5)
            
        window_vars.clear()
        window_vars.update(new_window_vars)
        append_log(f"已掃描視窗列表，共有 {len(all_titles)} 個選項")

    def add_manual_window():
        title = manual_window_var.get().strip()
        if not title: return
        if title not in window_vars:
            var = tk.BooleanVar(value=True)
            window_vars[title] = var
            cb = tk.Checkbutton(scrollable_frame, text=title, variable=var, anchor="w")
            cb.pack(fill="x", padx=5)
            append_log(f"已手動新增視窗: {title}")
            manual_window_var.set("")
        else:
            window_vars[title].set(True)
            append_log(f"視窗 {title} 已在清單中")

    frame_top = tk.Frame(root)
    frame_top.pack(fill="x", padx=12, pady=10)

    tk.Label(frame_top, text="動作記錄檔:", width=14, anchor="e").grid(row=0, column=0, padx=5, pady=5)
    tk.Entry(frame_top, textvariable=filename_var, width=48).grid(row=0, column=1, padx=5, pady=5)
    tk.Button(frame_top, text="選擇", command=select_file, width=10).grid(row=0, column=2, padx=5, pady=5)

    tk.Label(frame_top, text="重複次數:", width=14, anchor="e").grid(row=1, column=0, padx=5, pady=5)
    repeat_entry = tk.Entry(frame_top, textvariable=repeat_var, width=10)
    repeat_entry.grid(row=1, column=1, sticky="w", padx=5, pady=5)

    tk.Label(frame_top, text="狀態:", width=14, anchor="e").grid(row=2, column=0, padx=5, pady=5)
    tk.Label(frame_top, textvariable=status_var, width=48, anchor="w").grid(row=2, column=1, padx=5, pady=5)

    frame_mid = tk.LabelFrame(root, text="模擬器選擇 (可多選進行同步播放)")
    frame_mid.pack(fill="both", expand=False, padx=12, pady=5)
    
    frame_manual = tk.Frame(frame_mid)
    frame_manual.pack(fill="x", padx=5, pady=2)
    tk.Label(frame_manual, text="手動新增名稱:").pack(side="left")
    tk.Entry(frame_manual, textvariable=manual_window_var, width=30).pack(side="left", padx=5)
    tk.Button(frame_manual, text="新增至列表", command=add_manual_window).pack(side="left")
    tk.Button(frame_manual, text="重新整理所有", command=refresh_windows).pack(side="right")

    list_container = tk.Frame(frame_mid)
    list_container.pack(fill="both", expand=True, padx=5, pady=5)
    
    canvas = tk.Canvas(list_container, height=100)
    scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=canvas.yview)
    scrollable_frame = tk.Frame(canvas)

    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )

    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    
    root.after(100, refresh_windows)

    frame_btn = tk.Frame(root)
    frame_btn.pack(fill="x", padx=12, pady=6)

    start_record_btn = tk.Button(frame_btn, text="開始錄製", command=start_record, width=12, bg="#008CBA", fg="white")
    start_record_btn.grid(row=0, column=0, padx=5, pady=5)

    stop_record_btn = tk.Button(frame_btn, text="停止錄製", command=stop_record, width=12, bg="#FF9800", fg="white", state="disabled")
    stop_record_btn.grid(row=0, column=1, padx=5, pady=5)

    play_btn = tk.Button(frame_btn, text="開始播放", command=start_play, width=12, bg="#4CAF50", fg="white")
    play_btn.grid(row=0, column=2, padx=5, pady=5)

    stop_play_btn = tk.Button(frame_btn, text="停止播放", command=stop_play, width=12, bg="#F44336", fg="white", state="disabled")
    stop_play_btn.grid(row=0, column=3, padx=5, pady=5)

    tk.Label(root, text="執行日誌: (可滾動)", anchor="w").pack(anchor="w", padx=12)
    log_text = ScrolledText(root, height=18, wrap="word", state="disabled")
    log_text.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    root.mainloop()

if __name__ == "__main__":
    main()