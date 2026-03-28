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
# 計時器偵測：右上角 ROI (依據最新截圖微調)
TIMER_ROI_LEFT   = 0.77   # 調回 0.77，確保時鐘圖標不被切掉
TIMER_ROI_RIGHT  = 0.98

# --- 一般戰鬥位置 (藍框) ---
TIMER_NORMAL_ROI_TOP    = 0.10   
TIMER_NORMAL_ROI_BOTTOM = 0.16   

# --- 稀有怪位置 (綠框) ---
TIMER_RARE_ROI_TOP      = 0.16
TIMER_RARE_ROI_BOTTOM   = 0.22

# 計時器：白色像素比例閾值（超過才算有計時器）
TIMER_WHITE_RATIO_THRESHOLD  = 0.04  # 提高到 4%

# 底部提示文字偵測：底部 ROI
TEXT_ROI_LEFT   = 0.10
TEXT_ROI_TOP    = 0.85
TEXT_ROI_RIGHT  = 0.90
TEXT_ROI_BOTTOM = 0.95

# 橘黃色 HSV 範圍（"タップで戦"黃色文字）
TEXT_HSV_LOWER = np.array([15,  120, 120], dtype=np.uint8)
TEXT_HSV_UPPER = np.array([40,  255, 255], dtype=np.uint8)

# 底部提示：橘黃色像素比例閾值
TEXT_YELLOW_RATIO_THRESHOLD = 0.03  # 提高到 3%
# ─────────────────────────────────────────────────────────────────


def _crop_roi(img_bgr, left_r, top_r, right_r, bottom_r):
    """根據比例裁切 BGR 圖片的 ROI"""
    h, w = img_bgr.shape[:2]
    x1, y1 = int(w * left_r),  int(h * top_r)
    x2, y2 = int(w * right_r), int(h * bottom_r)
    return img_bgr[y1:y2, x1:x2]


def detect_timer(hwnd, log_fn=None, roi_top=TIMER_NORMAL_ROI_TOP, roi_bottom=TIMER_NORMAL_ROI_BOTTOM) -> bool:
    """
    偵測計時器：黑底白字雙重判讀。
    可以傳入自定義的 roi_top 與 roi_bottom 來偵測不同位置。
    """
    im = get_window_screenshot(hwnd)
    if im is None: return False

    img_bgr = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
    roi = _crop_roi(img_bgr, TIMER_ROI_LEFT, roi_top, TIMER_ROI_RIGHT, roi_bottom)

    # 1. 偵測「黑底」(梯形背景)
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    lower_black = np.array([0, 0, 0])
    upper_black = np.array([180, 255, 80]) # 亮度低於 80 視為黑色背景
    black_mask = cv2.inRange(hsv, lower_black, upper_black)
    black_ratio = np.count_nonzero(black_mask) / black_mask.size

    # 2. 偵測「白字」(數字與時鐘)
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    _, white_mask = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
    white_ratio = np.count_nonzero(white_mask) / white_mask.size
    
    # 判定條件：黑底需佔一定比例，且白字比例也需達標
    has_black = black_ratio >= 0.15 # 黑底至少 15%
    has_white = white_ratio >= 0.01 # 白字至少 1%
    is_detected = has_black and has_white
    
    if log_fn:
        res_str = "✓ 偵測成功" if is_detected else "× 未偵測到"
        log_fn(f"  [診斷] {res_str} (黑底:{black_ratio:.1%}, 白字:{white_ratio:.1%}, 區域:T{roi_top:.2f}-B{roi_bottom:.2f})")
        
    return is_detected


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


def _find_image_in_roi(roi_bgr, template_path, threshold=0.7, log_fn=None):
    """在截取的 ROI 中精確尋找圖片"""
    import cv2
    import numpy as np
    try:
        if not os.path.exists(template_path): return False
        template = cv2.imdecode(np.fromfile(template_path, dtype=np.uint8), cv2.IMREAD_COLOR)
        if template is None: return False
        
        result = cv2.matchTemplate(roi_bgr, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(result)
        
        if log_fn:
            log_fn(f"  [診斷] 區域圖標比對: 分數={max_val:.3f}, 閾值={threshold:.2f}")
        return max_val >= threshold
    except:
        return False

def is_in_battle(hwnd, duration=2.0, log_fn=None, roi_top=TIMER_NORMAL_ROI_TOP, roi_bottom=TIMER_NORMAL_ROI_BOTTOM) -> bool:
    """
    通用戰鬥判定：結合 ROI 圖標比對與顏色算法。
    預設為一般位置。
    """
    import os
    import time
    
    timer_path = "scripts/advanced/assets/timer.png"
    check_start = time.time()
    
    # 為了效能，如果只是單次檢查，duration 設短一點
    while time.time() - check_start <= float(duration):
        im = get_window_screenshot(hwnd)
        if im:
            img_bgr = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
            roi = _crop_roi(img_bgr, TIMER_ROI_LEFT, roi_top, TIMER_ROI_RIGHT, roi_bottom)
            
            # --- 1. 優先：區域圖標比對 (最準確) ---
            if os.path.exists(timer_path):
                if _find_image_in_roi(roi, timer_path, threshold=0.70, log_fn=log_fn):
                    return True
            
            # --- 2. 備案：強化版顏色判斷 ---
            hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
            black_mask = cv2.inRange(hsv, np.array([0, 0, 0]), np.array([180, 255, 60]))
            black_ratio = np.count_nonzero(black_mask) / black_mask.size
            
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            _, white_mask = cv2.threshold(gray, 220, 255, cv2.THRESH_BINARY)
            white_ratio = np.count_nonzero(white_mask) / white_mask.size
            
            is_color_match = (black_ratio >= 0.22) and (0.015 <= white_ratio <= 0.10)
            
            if is_color_match:
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
        # 這裡不呼叫 is_in_battle_normal/rare 以避免重複截圖，直接在同一個迴圈處理
        im = get_window_screenshot(hwnd)
        if im:
            img_bgr = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
            
            # 檢查 一般位置
            roi_normal = _crop_roi(img_bgr, TIMER_ROI_LEFT, TIMER_NORMAL_ROI_TOP, TIMER_ROI_RIGHT, TIMER_NORMAL_ROI_BOTTOM)
            # 檢查 稀有位置
            roi_rare = _crop_roi(img_bgr, TIMER_ROI_LEFT, TIMER_RARE_ROI_TOP, TIMER_ROI_RIGHT, TIMER_RARE_ROI_BOTTOM)
            
            # 簡單的顏色判定邏輯提取 (為了效率)
            def _check_timer_roi(roi):
                hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
                black_mask = cv2.inRange(hsv, np.array([0, 0, 0]), np.array([180, 255, 60]))
                black_ratio = np.count_nonzero(black_mask) / black_mask.size
                gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
                _, white_mask = cv2.threshold(gray, 220, 255, cv2.THRESH_BINARY)
                white_ratio = np.count_nonzero(white_mask) / white_mask.size
                return (black_ratio >= 0.22) and (0.015 <= white_ratio <= 0.10)

            if _check_timer_roi(roi_normal) or _check_timer_roi(roi_rare):
                return True
                
        if time.time() - check_start >= float(duration): break
        time.sleep(0.3)
        
    return False


def is_prebattle(hwnd) -> bool:
    """
    綜合判斷：底部提示文字出現，戰鬥即將開始（等待點擊）
    """
    return detect_prebattle_text(hwnd)


def get_battle_state(hwnd) -> str:
    """
    回傳目前戰鬥狀態字串：
      'in_battle_normal' — 計時器在上方 (一般戰鬥)
      'in_battle_rare'   — 計時器在下方 (稀有戰鬥)
      'pre_battle'       — 底部文字存在，準備進入戰鬥
      'none'             — 非戰鬥狀態
    """
    # 優先檢查計時器位置
    if is_in_battle_normal(hwnd, duration=0):
        return "in_battle_normal"
    if is_in_battle_rare(hwnd, duration=0):
        return "in_battle_rare"
    
    if is_prebattle(hwnd):
        return "pre_battle"
    return "none"


def wait_for_battle_start(hwnd, timeout=60.0, poll_interval=0.5, log_fn=None) -> bool:
    """
    等待直到進入戰鬥（計時器出現）或超時。
    """
    import time
    elapsed = 0.0
    last_state = None
    last_log_time = 0.0
    
    while elapsed < timeout:
        state = get_battle_state(hwnd)
        
        # 效能優化：僅在狀態改變或每 5 秒輸出一次日誌，避免刷屏
        current_time = time.time()
        if log_fn and (state != last_state or current_time - last_log_time >= 5.0):
            log_fn(f"  🔍 戰鬥偵測: {state} ({elapsed:.1f}s)")
            last_state = state
            last_log_time = current_time
            
        if state in ["in_battle_normal", "in_battle_rare"]:
            return True
        if state == "pre_battle" and state != last_state:
            if log_fn:
                log_fn("  ⚔️ 偵測到戰前提示，等待計時器出現...")
        
        time.sleep(poll_interval)
        elapsed += poll_interval
    if log_fn:
        log_fn(f"  ⚠️ 等待戰鬥開始超時 ({timeout}s)")
    return False


def wait_for_battle_end(hwnd, timeout=300.0, poll_interval=1.0, log_fn=None) -> bool:
    """
    等待直到計時器消失（戰鬥結束）或超時。
    :return: True 表示戰鬥已結束；False 表示超時
    """
    import time
    elapsed = 0.0
    while elapsed < timeout:
        # 如果兩處都沒有計時器，視為戰鬥結束
        if not is_in_battle_normal(hwnd, duration=0) and not is_in_battle_rare(hwnd, duration=0):
            if log_fn:
                log_fn(f"  ✅ 戰鬥結束偵測成功 ({elapsed:.1f}s)")
            return True
        time.sleep(poll_interval)
        elapsed += poll_interval
    if log_fn:
        log_fn(f"  ⚠️ 等待戰鬥結束超時 ({timeout}s)")
    return False


def debug_snapshot(hwnd, save_dir="scripts/advanced/assets"):
    """
    除錯用：截圖並標記計時器 ROI 與文字 ROI，儲存到磁碟。
    """
    import os, time as _time
    im = get_window_screenshot(hwnd)
    if im is None:
        print("截圖失敗")
        return

    img_bgr = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
    h, w = img_bgr.shape[:2]

    # 畫計時器 ROI - 一般（藍色）
    cv2.rectangle(img_bgr,
                  (int(w * TIMER_ROI_LEFT),  int(h * TIMER_NORMAL_ROI_TOP)),
                  (int(w * TIMER_ROI_RIGHT),  int(h * TIMER_NORMAL_ROI_BOTTOM)),
                  (255, 0, 0), 2)

    # 畫計時器 ROI - 稀有（綠色）
    cv2.rectangle(img_bgr,
                  (int(w * TIMER_ROI_LEFT),  int(h * TIMER_RARE_ROI_TOP)),
                  (int(w * TIMER_ROI_RIGHT),  int(h * TIMER_RARE_ROI_BOTTOM)),
                  (0, 255, 0), 2)

    # 畫文字 ROI（橘色）
    cv2.rectangle(img_bgr,
                  (int(w * TEXT_ROI_LEFT),   int(h * TEXT_ROI_TOP)),
                  (int(w * TEXT_ROI_RIGHT),   int(h * TEXT_ROI_BOTTOM)),
                  (0, 128, 255), 2)

    os.makedirs(save_dir, exist_ok=True)
    path = os.path.join(save_dir, f"battle_debug_{int(_time.time())}.png")
    cv2.imwrite(path, img_bgr)
    print(f"除錯截圖已儲存: {path}")
    return path
