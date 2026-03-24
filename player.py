import json
import time
import pyautogui
from ld_controller import get_ldplayer_window
from pynput import keyboard
import threading

class ActionPlayer:
    def __init__(self, filename="actions_record.json"):
        self.filename = filename
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
    
    def play(self, repeat=1):
        if not self.actions:
            self.log("✗ 沒有操作可以播放")
            return
        
        self.log(f"=== 準備播放操作 ===")
        self.log(f"✓ 將重複: {repeat} 次")
        self.log("✓ 停止播放: 按 ESC 或 F12 鍵")
        self.log("⏳ 5 秒後開始播放...\n")
        time.sleep(5)
        
        # 確保遊戲窗口在前面
        try:
            window = get_ldplayer_window()
            window.activate()
        except Exception as e:
            self.log(f"✗ 警告: 無法激活遊戲窗口 - {e}")
        
        # 啟動鍵盤監聽線程
        self.playing = True
        keyboard_listener = keyboard.Listener(on_press=self.on_key_press)
        keyboard_listener.start()
        
        for cycle in range(repeat):
            if not self.playing:
                self.log("✗ 播放已被中止")
                break
            
            self.log(f"\n--- 循環 {cycle + 1}/{repeat} ---")
            self.play_once()
        
        self.playing = False
        keyboard_listener.stop()
        self.log("\n=== 播放完成 ===")
    
    def play_once(self):
        if not self.actions:
            return
        
        # 獲取模擬器窗口位置
        try:
            window = get_ldplayer_window()
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
    import tkinter as tk
    from tkinter import filedialog, messagebox
    from tkinter.scrolledtext import ScrolledText
    from recorder import ActionRecorder

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
        if filename:
            recorder.filename = filename
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
            player.play(repeat=repeat)
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
    root.title("ActionPlayer 綜合控制面板")
    root.geometry("700x520")

    filename_var = tk.StringVar(value=player.filename)
    repeat_var = tk.StringVar(value="1")
    status_var = tk.StringVar(value="等待中")

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
