"""
battle_detector.py
------------------
偵測遊戲是否已進入「戰鬥中」或「準備進入戰鬥」狀態。

判斷依據（兩種模式）：
  1. 右上角計時器  — 戰鬥中，右上角出現 "HH:MM:SS" 白色數字計時框
  2. 底部提示文字  — 戰鬥前，畫面底部出現橘黃色 "タップ" 等提示文字

偵測策略（不依賴 OCR，純顏色與亮度分析）：
  - 計時器區域（右上角 ROI）：該區域存在白色像素群落，且佈局緊湊 → 計時器存在
  - 底部提示區域（底部 ROI）：該區域橘黃色像素比例超過閾值 → 提示文字存在
"""

import cv2
import numpy as np
from ld_controller import get_window_screenshot


# ─── 可調整的超參數 ──────────────────────────────────────────────
# 計時器偵測：右上角 ROI (擴大左界包覆完整 ⏱ 02:07 / 04:30 計時器條)
TIMER_ROI_LEFT   = 0.67   # 向左擴大至 67%，完全包覆計時圖示與時間
TIMER_ROI_RIGHT  = 0.98   # 右邊界切除非計時器背景

# --- 一般戰鬥位置 (藍框) ---
TIMER_NORMAL_ROI_TOP    = 0.115  # 精準對齊橫條 upper boundary
TIMER_NORMAL_ROI_BOTTOM = 0.145   # 精準對齊橫條 lower boundary

# --- 稀有怪位置 (綠框) ---
TIMER_RARE_ROI_TOP      = 0.150  # 稀有怪橫幅下的計時器位置
TIMER_RARE_ROI_BOTTOM   = 0.180

# 底部提示文字偵測：底部 ROI
TEXT_ROI_LEFT   = 0.06
TEXT_ROI_TOP    = 0.83
TEXT_ROI_RIGHT  = 0.78
TEXT_ROI_BOTTOM = 0.88

# --- 判定閥值 ---
# 無色彩純度門檻 (黑白灰佔比)：20% (過濾鮮艷背景)
TIMER_PURITY_THRESHOLD = 0.20
# 深色底色佔比：10% (容許半透明黑底 gradient 與黑框)
TIMER_BLACK_RATIO_MIN  = 0.10
# 白色數字佔比：放寬至 2% ~ 30% (捕捉細數字與圖示)
TIMER_WHITE_RATIO_MIN  = 0.02
TIMER_WHITE_RATIO_MAX  = 0.30

# 橘黃色 HSV 範圍（"タップで戦"黃色文字）
TEXT_HSV_LOWER = np.array([15,  120, 120], dtype=np.uint8)
TEXT_HSV_UPPER = np.array([40,  255, 255], dtype=np.uint8)

# 底部提示：橘黃色像素比例閾值
TEXT_YELLOW_RATIO_THRESHOLD = 0.03  # 3%
# ─────────────────────────────────────────────────────────────────


def _crop_roi(img_bgr, left_r, top_r, right_r, bottom_r):
    """根據比例裁切 BGR 圖片的 ROI"""
    h, w = img_bgr.shape[:2]
    x1, y1 = int(w * left_r),  int(h * top_r)
    x2, y2 = int(w * right_r), int(h * bottom_r)
    return img_bgr[y1:y2, x1:x2]


def safe_log(msg, log_fn=print):
    """安全輸出 Log，防止 Windows CP950 終端機編碼報錯"""
    import sys
    try:
        log_fn(msg)
    except Exception:
        try:
            enc = sys.stdout.encoding or 'cp950'
            clean_msg = msg.encode(enc, errors='replace').decode(enc)
            log_fn(clean_msg)
        except Exception:
            print(str(msg).encode('ascii', 'replace').decode('ascii'))


def _is_pure_timer_roi(roi, log_prefix="", log_fn=None) -> bool:
    """
    核心判定：高純度無色彩與高對心對比。
    邏輯：計時器區域應為無色彩（黑白灰），且包含深色底與淺色字。
    """
    if roi is None or roi.size == 0: return False
    
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    
    # 1. 偵測「無色彩 (Achromatic)」像素：彩度 (S) 低於 70 視為黑白灰
    monochrome_mask = cv2.inRange(hsv, np.array([0, 0, 0]), np.array([180, 70, 255]))
    monochrome_count = np.count_nonzero(monochrome_mask)
    roi_size = monochrome_mask.size
    purity = monochrome_count / roi_size
    
    # 2. 在無色彩區域中偵測「黑色底」與「白色字」
    # 黑底：亮度 V < 100 且彩度低
    black_mask = cv2.inRange(hsv, np.array([0, 0, 0]), np.array([180, 70, 100]))
    black_ratio = np.count_nonzero(black_mask) / roi_size
    
    # 白字：亮度 V > 185
    _, white_mask = cv2.threshold(gray, 185, 255, cv2.THRESH_BINARY)
    white_ratio = np.count_nonzero(white_mask) / roi_size
    
    # 3. 偵測「高彩度鮮豔彩色」像素（避開 Buff 圖示與彩色背景）
    # 鮮豔色彩：彩度 S >= 120 且 亮度 V >= 120
    vivid_mask = cv2.inRange(hsv, np.array([0, 120, 120]), np.array([180, 255, 255]))
    vivid_ratio = np.count_nonzero(vivid_mask) / roi_size
    
    # 綜合判定
    is_pure = purity >= TIMER_PURITY_THRESHOLD
    has_black = black_ratio >= TIMER_BLACK_RATIO_MIN
    has_white = TIMER_WHITE_RATIO_MIN <= white_ratio <= TIMER_WHITE_RATIO_MAX
    is_not_vivid = vivid_ratio < 0.08  # 鮮豔色彩比例需小於 8%
    
    is_detected = is_pure and has_black and has_white and is_not_vivid
    
    if log_fn:
        res_tag = "[V] 成功" if is_detected else "[X] 失敗"
        reasons = []
        if not is_pure: reasons.append(f"純度不足({purity:.1%}<{TIMER_PURITY_THRESHOLD:.0%})")
        if not has_black: reasons.append(f"黑底不足({black_ratio:.1%}<{TIMER_BLACK_RATIO_MIN:.0%})")
        if not has_white: reasons.append(f"白字異常({white_ratio:.1%},門檻:{TIMER_WHITE_RATIO_MIN:.1%}-{TIMER_WHITE_RATIO_MAX:.1%})")
        if not is_not_vivid: reasons.append(f"鮮豔色彩過多({vivid_ratio:.1%}>=8.0%)")
        
        detail_str = f"純度:{purity:.1%}, 黑底:{black_ratio:.1%}, 白字:{white_ratio:.1%}, 鮮豔色:{vivid_ratio:.1%}"
        if reasons:
            detail_str += f" | 原因: {', '.join(reasons)}"
        safe_log(f"  [{log_prefix}] {res_tag} | {detail_str}", log_fn)
        
    return is_detected


def detect_timer(hwnd, log_fn=None, roi_top=TIMER_NORMAL_ROI_TOP, roi_bottom=TIMER_NORMAL_ROI_BOTTOM) -> bool:
    """診斷專用：偵測單一計時器位置"""
    im = get_window_screenshot(hwnd)
    if im is None: return False
    img_bgr = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
    roi = _crop_roi(img_bgr, TIMER_ROI_LEFT, roi_top, TIMER_ROI_RIGHT, roi_bottom)
    return _is_pure_timer_roi(roi, log_prefix=f"區域 {roi_top:.3f}-{roi_bottom:.3f}", log_fn=log_fn)


def detect_prebattle_text(hwnd) -> bool:
    """
    偵測底部是否出現橘黃色戰前提示文字。
    回傳 True 表示提示文字存在（即將進入戰鬥）。
    """
    im = get_window_screenshot(hwnd)
    if im is None:
        return False

    img_bgr = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
    roi = _crop_roi(img_bgr, TEXT_ROI_LEFT, TEXT_ROI_TOP,
                    TEXT_ROI_RIGHT, TEXT_ROI_BOTTOM)

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    yellow_mask = cv2.inRange(hsv, TEXT_HSV_LOWER, TEXT_HSV_UPPER)
    yellow_ratio = np.count_nonzero(yellow_mask) / yellow_mask.size

    return yellow_ratio >= TEXT_YELLOW_RATIO_THRESHOLD


def is_in_battle(hwnd, duration=2.0, log_fn=None, roi_top=TIMER_NORMAL_ROI_TOP, roi_bottom=TIMER_NORMAL_ROI_BOTTOM) -> bool:
    """
    通用戰鬥判定：結合 ROI 圖標比對與顏色算法。
    """
    import time
    check_start = time.time()
    
    while time.time() - check_start <= float(duration):
        im = get_window_screenshot(hwnd)
        if im is not None:
            img_bgr = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
            roi = _crop_roi(img_bgr, TIMER_ROI_LEFT, roi_top, TIMER_ROI_RIGHT, roi_bottom)
            if _is_pure_timer_roi(roi, log_prefix="計時器判定", log_fn=log_fn):
                return True
        
        if duration <= 0: break # 只檢查一次
        time.sleep(0.3)
        
    return False


def is_in_battle_normal(hwnd, duration=1.0) -> bool:
    """檢查一般戰鬥位置"""
    return is_in_battle(hwnd, duration=duration, roi_top=TIMER_NORMAL_ROI_TOP, roi_bottom=TIMER_NORMAL_ROI_BOTTOM)

def is_in_battle_rare(hwnd, duration=1.0) -> bool:
    """檢查稀有戰鬥位置"""
    return is_in_battle(hwnd, duration=duration, roi_top=TIMER_RARE_ROI_TOP, roi_bottom=TIMER_RARE_ROI_BOTTOM)


def is_in_any_battle(hwnd, duration=1.0) -> bool:
    """
    同時偵測一般與稀有戰鬥位置。只要任一位置出現計時器即回傳 True。
    """
    import time
    check_start = time.time()
    
    while True:
        im = get_window_screenshot(hwnd)
        if im:
            img_bgr = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
            
            roi_normal = _crop_roi(img_bgr, TIMER_ROI_LEFT, TIMER_NORMAL_ROI_TOP, TIMER_ROI_RIGHT, TIMER_NORMAL_ROI_BOTTOM)
            roi_rare   = _crop_roi(img_bgr, TIMER_ROI_LEFT, TIMER_RARE_ROI_TOP, TIMER_ROI_RIGHT, TIMER_RARE_ROI_BOTTOM)
            
            if _is_pure_timer_roi(roi_normal) or _is_pure_timer_roi(roi_rare):
                return True
                
        if time.time() - check_start >= float(duration): break
        time.sleep(0.3)
        
    return False


def is_prebattle(hwnd) -> bool:
    """
    綜合判斷：(暫時關閉) 底部提示文字不參與判定。
    """
    return False


def get_battle_state(hwnd, im=None) -> str:
    """
    回傳目前戰鬥狀態字串：
      'in_battle_normal' — 計時器在上方 (一般戰鬥)
      'in_battle_rare'   — 計時器在下方 (稀有戰鬥)
      'pre_battle'       — 底部文字存在，準備進入戰鬥
      'none'             — 非戰鬥狀態
    """
    if im is None:
        im = get_window_screenshot(hwnd)
    if im is None:
        return "none"
        
    img_bgr = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
    
    # 優先檢查一般戰鬥位置 (藍框)
    roi_normal = _crop_roi(img_bgr, TIMER_ROI_LEFT, TIMER_NORMAL_ROI_TOP, TIMER_ROI_RIGHT, TIMER_NORMAL_ROI_BOTTOM)
    if _is_pure_timer_roi(roi_normal):
        return "in_battle_normal"
        
    # 再檢查稀有戰鬥位置 (綠框)
    roi_rare = _crop_roi(img_bgr, TIMER_ROI_LEFT, TIMER_RARE_ROI_TOP, TIMER_ROI_RIGHT, TIMER_RARE_ROI_BOTTOM)
    if _is_pure_timer_roi(roi_rare):
        return "in_battle_rare"
    
    if is_prebattle(hwnd):
        return "pre_battle"
    return "none"


def wait_for_battle_start(hwnd, timeout=60.0, poll_interval=0.5, log_fn=None, required_consecutive=2, cancel_check=None) -> bool:
    """
    等待直到進入戰鬥（計時器出現）或超時。
    使用連續防誤判機制（預設連續 2 次偵測成功才確定進入戰鬥）。
    :param cancel_check: 可選的回呼函式，回傳 True 表示外部已要求中止
    """
    import time
    elapsed = 0.0
    last_state = None
    last_log_time = 0.0
    consecutive_count = 0
    
    while elapsed < timeout:
        # 檢查外部是否要求中止
        if cancel_check and cancel_check():
            if log_fn:
                safe_log("  [中止] 外部要求停止，中斷等待戰鬥開始", log_fn)
            return False

        im = get_window_screenshot(hwnd)
        state = get_battle_state(hwnd, im=im)
        
        current_time = time.time()
        if log_fn and (state != last_state or current_time - last_log_time >= 5.0):
            safe_log(f"  [戰鬥偵測] 狀態: {state} ({elapsed:.1f}s)", log_fn)
            last_state = state
            last_log_time = current_time
            
        if state in ["in_battle_normal", "in_battle_rare"]:
            consecutive_count += 1
            if consecutive_count >= required_consecutive:
                if log_fn:
                    safe_log(f"  [戰鬥] 確認進入戰鬥！({state})", log_fn)
                return True
        else:
            consecutive_count = 0
            if state == "pre_battle" and state != last_state:
                if log_fn:
                    safe_log("  [戰鬥] 偵測到戰前提示，等待計時器出現...", log_fn)
        
        time.sleep(poll_interval)
        elapsed += poll_interval

    if log_fn:
        safe_log(f"  [警告] 等待戰鬥開始超時 ({timeout}s)", log_fn)
    return False


def wait_for_battle_end(hwnd, timeout=300.0, poll_interval=1.0, log_fn=None, required_consecutive=3, cancel_check=None) -> bool:
    """
    等待直到計時器消失（戰鬥結束）或超時。
    使用連續防誤判機制（必須連續 3 次未偵測到計時器，約 2-3 秒，才判定為戰鬥結束）。
    :param cancel_check: 可選的回呼函式，回傳 True 表示外部已要求中止
    """
    import time
    elapsed = 0.0
    consecutive_no_battle = 0
    last_log_time = 0.0

    while elapsed < timeout:
        # 檢查外部是否要求中止
        if cancel_check and cancel_check():
            if log_fn:
                safe_log("  [中止] 外部要求停止，中斷等待戰鬥結束", log_fn)
            return False

        im = get_window_screenshot(hwnd)
        state = get_battle_state(hwnd, im=im)
        
        current_time = time.time()
        if state == "none":
            consecutive_no_battle += 1
            if log_fn and (current_time - last_log_time >= 5.0):
                safe_log(f"  [戰鬥] 等待戰鬥結束中 (無計時器 {consecutive_no_battle}/{required_consecutive}, {elapsed:.1f}s)", log_fn)
                last_log_time = current_time

            if consecutive_no_battle >= required_consecutive:
                if log_fn:
                    safe_log(f"  [戰鬥] 戰鬥結束偵測成功 ({elapsed:.1f}s)", log_fn)
                return True
        else:
            if consecutive_no_battle > 0 and log_fn:
                safe_log(f"  [戰鬥] 仍偵測到戰鬥中 ({state})，重設結束計數", log_fn)
            consecutive_no_battle = 0

        time.sleep(poll_interval)
        elapsed += poll_interval

    if log_fn:
        safe_log(f"  [警告] 等待戰鬥結束超時 ({timeout}s)", log_fn)
    return False


def debug_snapshot(hwnd, save_dir="scripts/advanced/assets", skill_positions=None):
    """
    除錯用：截圖並標記計時器 ROI、文字 ROI 以及技能點位，儲存到磁碟。
    """
    import os, time as _time
    im = get_window_screenshot(hwnd)
    if im is None:
        print("截圖失敗")
        return None

    img_bgr = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
    h, w = img_bgr.shape[:2]

    # 1. 畫計時器 ROI - 一般（藍色）
    cv2.rectangle(img_bgr,
                  (int(w * TIMER_ROI_LEFT),  int(h * TIMER_NORMAL_ROI_TOP)),
                  (int(w * TIMER_ROI_RIGHT),  int(h * TIMER_NORMAL_ROI_BOTTOM)),
                  (255, 0, 0), 2)
    cv2.putText(img_bgr, "Timer (Normal)", (int(w * TIMER_ROI_LEFT), int(h * TIMER_NORMAL_ROI_TOP) - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)

    # 2. 畫計時器 ROI - 稀有（綠色）
    cv2.rectangle(img_bgr,
                  (int(w * TIMER_ROI_LEFT),  int(h * TIMER_RARE_ROI_TOP)),
                  (int(w * TIMER_ROI_RIGHT),  int(h * TIMER_RARE_ROI_BOTTOM)),
                  (0, 255, 0), 2)
    cv2.putText(img_bgr, "Timer (Rare)", (int(w * TIMER_ROI_LEFT), int(h * TIMER_RARE_ROI_TOP) - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

    # 3. 畫文字 ROI（橘色）
    cv2.rectangle(img_bgr,
                  (int(w * TEXT_ROI_LEFT),   int(h * TEXT_ROI_TOP)),
                  (int(w * TEXT_ROI_RIGHT),   int(h * TEXT_ROI_BOTTOM)),
                  (0, 128, 255), 2)
    cv2.putText(img_bgr, "Pre-battle Text", (int(w * TEXT_ROI_LEFT), int(h * TEXT_ROI_TOP) - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 128, 255), 1)

    # 4. 畫技能點位（紫色圓圈）
    if skill_positions:
        for sid, pos in skill_positions.items():
            if isinstance(pos, list) and len(pos) == 2 and isinstance(pos[0], int):
                cv2.circle(img_bgr, (pos[0], pos[1]), 5, (255, 0, 255), -1)
                cv2.putText(img_bgr, str(sid), (pos[0] + 7, pos[1] + 7),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2)

    os.makedirs(save_dir, exist_ok=True)
    path = os.path.join(save_dir, f"debug_{hwnd}_{int(_time.time())}.png")
    cv2.imwrite(path, img_bgr)
    return path


def run_diagnostic_mode(log_fn=print):
    """
    戰鬥偵測診斷模式：分析目前所有 LDPlayer 視窗並輸出結果。
    """
    from ld_controller import list_all_ldplayer_windows
    import time
    
    safe_log("========================================", log_fn)
    safe_log("[診斷模式] 開始進行戰鬥偵測診斷...", log_fn)
    safe_log("========================================", log_fn)
    
    windows = list_all_ldplayer_windows()
    if not windows:
        safe_log("[X] 未找到任何開啟中的雷電模擬器 (LDPlayer) 視窗。", log_fn)
        return
        
    for title, hwnd in windows:
        safe_log(f"\n[視窗] [{title}] (HWND: {hwnd})", log_fn)
        path = debug_snapshot(hwnd)
        if path:
            safe_log(f"  [快照] 標記圖片已存檔: {path}", log_fn)
            
        im = get_window_screenshot(hwnd)
        if im is None:
            safe_log("  [X] 截圖失敗，無法讀取畫面", log_fn)
            continue
            
        img_bgr = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
        
        safe_log("  --- 一般計時器區域 (藍框) ---", log_fn)
        roi_normal = _crop_roi(img_bgr, TIMER_ROI_LEFT, TIMER_NORMAL_ROI_TOP, TIMER_ROI_RIGHT, TIMER_NORMAL_ROI_BOTTOM)
        _is_pure_timer_roi(roi_normal, log_prefix="一般位置", log_fn=log_fn)
        
        safe_log("  --- 稀有計時器區域 (綠框) ---", log_fn)
        roi_rare = _crop_roi(img_bgr, TIMER_ROI_LEFT, TIMER_RARE_ROI_TOP, TIMER_ROI_RIGHT, TIMER_RARE_ROI_BOTTOM)
        _is_pure_timer_roi(roi_rare, log_prefix="稀有位置", log_fn=log_fn)
        
        state = get_battle_state(hwnd, im=im)
        state_map = {
            "in_battle_normal": "[戰鬥] 一般戰鬥中 (Normal)",
            "in_battle_rare":   "[戰鬥] 稀有戰鬥中 (Rare)",
            "pre_battle":       "[等待] 準備進入戰鬥 (Pre-Battle)",
            "none":             "[停止] 非戰鬥狀態 (None)"
        }
        safe_log(f"  [狀態] 綜合判定: {state_map.get(state, state)}", log_fn)
    safe_log("\n========================================\n", log_fn)


if __name__ == "__main__":
    import sys
    run_diagnostic_mode(log_fn=print)
    print("\n提示：若要開啟即時動態監控診斷，請按 Enter 鍵 (或 Ctrl+C 結束)...")
    try:
        input()
        print("開始即時動態監控 (每 1 秒更新一次，Ctrl+C 中止)...")
        import time
        while True:
            run_diagnostic_mode(log_fn=print)
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n診斷結束。")


