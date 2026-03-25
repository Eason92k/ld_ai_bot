import cv2
import numpy as np
import os
import sys

# 將上一級目錄加入路徑以便匯入 ld_controller
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from advanced_player import AdvancedActionPlayer

def test_find_image():
    print("=== 開始測試影像辨識邏輯 ===")
    
    # 建立一個與隨機雜訊混合的螢幕截圖
    screen = np.random.randint(0, 100, (600, 800, 3), dtype=np.uint8)
    
    # 在 (300, 200) 畫一個顯眼的藍色方塊作為目標
    target_color = (255, 0, 0) # BGR
    cv2.rectangle(screen, (300, 200), (350, 250), (255, 255, 255), -1) # 先畫白底
    cv2.rectangle(screen, (310, 210), (340, 240), target_color, -1)   # 再畫藍核心
    
    # 建立樣板
    template = screen[200:250, 300:350].copy()
    
    # 使用 OpenCV 執行 matchTemplate
    result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
    
    print(f"最大信心度: {max_val:.4f}")
    print(f"匹配位置 (Top-Left): {max_loc}")
    
    h, w = template.shape[:2]
    center_x = max_loc[0] + w // 2
    center_y = max_loc[1] + h // 2
    print(f"計算出中心座標: ({center_x}, {center_y})")

    if max_val > 0.95:
        if center_x == 325 and center_y == 225:
            print("✓ 驗證成功：成功在噪音環境中穩定定位目標！")
        else:
            print(f"× 座標偏移：預期 (325, 225)，實際 ({center_x}, {center_y})")
    else:
        print("× 辨識失敗：信心度不足 0.95")

    # 清理
    if os.path.exists("test_screen.png"): os.remove("test_screen.png")
    if os.path.exists("test_template.png"): os.remove("test_template.png")

if __name__ == "__main__":
    test_find_image()
