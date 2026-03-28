"""
skill_preset.py
---------------
預設技能系統：解析文字指令語法，自動施放技能。

語法規則：
  @ 分套（獨立選擇）
  : 分組（同組技能連續施放）
  - 等待時間（該組施放後等待秒數）
  1-6 底部武器技能槽
  a-f 頂部角色/同伴技能

範例：
  剣姬123a45:4:4:4b
  @狂怒-20:1a:12345-30:ef
  @坦123a-10:2:2:2:245
"""

import json
import time
import os
import re
import cv2
import numpy as np
from ld_controller import send_click, get_window_screenshot
from battle_detector import is_in_any_battle


# ─── 所有合法的技能 ID ────────────────────────────────
VALID_SKILL_IDS = set("123456abcdef")


# ═══════════════════════════════════════════════════════
# 1. 語法解析器
# ═══════════════════════════════════════════════════════
class SkillPresetParser:
    """解析技能文字指令語法"""

    @staticmethod
    def parse(text: str) -> list:
        """
        解析完整文字，回傳多個套組。
        
        回傳格式:
        [
            {
                "name": "剣姬",
                "groups": [
                    {"skills": ["1","2","3","a","4","5"], "wait": 0},
                    {"skills": ["4"], "wait": 0},
                    ...
                ]
            },
            ...
        ]
        """
        if not text or not text.strip():
            return []

        # 將換行合併，以 @ 分割套組
        lines = text.strip().splitlines()
        # 合併成一個字串，保留 @ 作為分隔符
        merged = ""
        for line in lines:
            line = line.strip()
            if not line:
                continue
            merged += line

        # 以 @ 分割
        # 第一段不需要 @, 後續段以 @ 開頭
        parts = re.split(r'@', merged)
        
        presets = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            preset = SkillPresetParser.parse_single_set(part)
            if preset:
                presets.append(preset)

        return presets

    @staticmethod
    def parse_single_set(text: str) -> dict:
        """
        解析單一套組文字。
        
        範例: "剣姬123a45:4:4:4b"
        → { "name": "剣姬", "groups": [...] }
        """
        text = text.strip()
        if not text:
            return None

        # 分離名稱和技能指令
        # 名稱 = 開頭的非技能字元（非 1-6, a-f, :, -,  數字）
        name = ""
        skill_part = text
        
        # 找到第一個技能字元或特殊符號的位置
        for i, ch in enumerate(text):
            if ch in VALID_SKILL_IDS or ch == ':' or ch == '-':
                name = text[:i].strip()
                skill_part = text[i:]
                break
        else:
            # 整段都是名稱，沒有技能
            name = text
            skill_part = ""

        if not name:
            name = "未命名"

        # 解析技能部分：以 : 分組
        groups = []
        if skill_part:
            raw_groups = skill_part.split(':')
            for raw_group in raw_groups:
                raw_group = raw_group.strip()
                if not raw_group:
                    continue
                group = SkillPresetParser._parse_group(raw_group)
                groups.append(group)

        return {"name": name, "groups": groups}

    @staticmethod
    def _parse_group(raw: str) -> dict:
        """
        解析單一組別。
        
        範例: "123a45" → {"skills": ["1","2","3","a","4","5"], "wait": 0}
        範例: "12345-30" → {"skills": ["1","2","3","4","5"], "wait": 30}
        範例: "-20" → {"skills": [], "wait": 20}
        """
        skills = []
        wait = 0

        # 尋找等待時間 (-數字)
        wait_match = re.search(r'-(\d+(?:\.\d+)?)', raw)
        if wait_match:
            wait = float(wait_match.group(1))
            # 移除等待部分，剩下的是技能字元
            raw = raw[:wait_match.start()]

        # 提取技能 ID
        for ch in raw:
            if ch in VALID_SKILL_IDS:
                skills.append(ch)

        return {"skills": skills, "wait": wait}

    @staticmethod
    def get_all_skill_ids(preset: dict) -> list:
        """取得一個套組中所有用到的技能 ID（去重，保持順序）"""
        seen = set()
        result = []
        for group in preset.get("groups", []):
            for skill_id in group.get("skills", []):
                if skill_id not in seen:
                    seen.add(skill_id)
                    result.append(skill_id)
        return result

    @staticmethod
    def format_preview(preset: dict) -> str:
        """產生人類可讀的預覽文字"""
        lines = [f"套組：{preset['name']}"]
        for i, group in enumerate(preset["groups"]):
            skills_str = "→".join(group["skills"]) if group["skills"] else "(空)"
            wait_str = f"  等待 {group['wait']}s" if group["wait"] > 0 else ""
            lines.append(f"  組{i+1}: {skills_str}{wait_str}")
        lines.append(f"  自動: 循環按亮起技能")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════
# 2. CD 偵測器（亮度檢測）
# ═══════════════════════════════════════════════════════
class SkillCooldownDetector:
    """透過截圖亮度偵測技能是否 CD 完畢"""

    # 亮度閾值：超過此值視為「技能亮起」（可施放）
    BRIGHTNESS_THRESHOLD = 120
    # 裁切大小（技能圖標周圍的像素範圍）
    CROP_SIZE = 25

    # 「NEXT / 數字」佇列標記偵測 (更精確的 HSV 橘色核心)
    # 修正：收窄寬度 (左右各 25)，調整高度，改進色域以避免鄰近干擾
    QUEUE_HSV_LOWER = np.array([12, 180, 180], dtype=np.uint8) 
    QUEUE_HSV_UPPER = np.array([25, 255, 255], dtype=np.uint8)
    QUEUE_ROI_OFFSET = (0, -20, 25, 20) 
    QUEUE_PIXEL_THRESHOLD = 50 
    QUEUE_TOLERANCE = 50       # 基準寬容度

    def __init__(self, positions: dict = None):
        """
        positions: {"1": [x, y], "2": [x, y], ...}
        """
        self.positions = positions or {}
        self.base_queued = {}  # 儲存背景橘色像素基準值 {"id": px_count}

    def calibrate_base_queued(self, hwnd, skill_ids: list):
        """在施放前校準背景的橘色像素量，避免特效誤判"""
        im = get_window_screenshot(hwnd)
        if im is None: return
        
        img_bgr = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
        hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
        h, w = img_bgr.shape[:2]
        ox, oy, ow, oh = self.QUEUE_ROI_OFFSET

        self.base_queued = {}
        for sid in skill_ids:
            if sid not in self.positions: continue
            x, y = self.positions[sid]
            rx1, ry1 = max(0, x + ox - ow), max(0, y + oy - oh)
            rx2, ry2 = min(w, x + ox + ow), min(h, y + oy + oh)
            if rx1 >= rx2 or ry1 >= ry2: continue
            
            roi_hsv = hsv[ry1:ry2, rx1:rx2]
            mask = cv2.inRange(roi_hsv, self.QUEUE_HSV_LOWER, self.QUEUE_HSV_UPPER)
            self.base_queued[sid] = np.count_nonzero(mask)

    def is_skill_ready(self, hwnd, skill_id: str) -> bool:
        """偵測指定技能是否亮起（CD 完畢，可施放）"""
        if skill_id not in self.positions:
            return True  # 沒有座標，預設可用

        x, y = self.positions[skill_id]
        im = get_window_screenshot(hwnd)
        if im is None:
            return False

        img = np.array(im)
        h, w = img.shape[:2]
        size = self.CROP_SIZE

        # 裁切技能槽區域
        x1 = max(0, x - size)
        y1 = max(0, y - size)
        x2 = min(w, x + size)
        y2 = min(h, y + size)

        roi = img[y1:y2, x1:x2]
        if roi.size == 0:
            return False

        # 轉灰階計算平均亮度
        gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
        avg_brightness = np.mean(gray)

        return avg_brightness >= self.BRIGHTNESS_THRESHOLD

    def get_ready_skills(self, hwnd, skill_ids: list) -> list:
        """
        一次截圖，批量檢測所有技能，回傳所有 CD 完畢的技能 ID。
        （比逐一截圖效率更高）
        """
        im = get_window_screenshot(hwnd)
        if im is None:
            return []

        img = np.array(im)
        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        size = self.CROP_SIZE
        ready = []

        for skill_id in skill_ids:
            if skill_id not in self.positions:
                continue
            x, y = self.positions[skill_id]
            x1 = max(0, x - size)
            y1 = max(0, y - size)
            x2 = min(w, x + size)
            y2 = min(h, y + size)

            roi = gray[y1:y2, x1:x2]
            if roi.size == 0:
                continue

            avg_brightness = np.mean(roi)
            if avg_brightness >= self.BRIGHTNESS_THRESHOLD:
                ready.append(skill_id)

        return ready

    def debug_brightness(self, hwnd, skill_ids: list, log_fn=None):
        """除錯用：列出所有技能的亮度值"""
        im = get_window_screenshot(hwnd)
        if im is None:
            if log_fn:
                log_fn("  ⚠️ 截圖失敗")
            return

        img = np.array(im)
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        size = self.CROP_SIZE

        for skill_id in skill_ids:
            if skill_id not in self.positions:
                continue
            x, y = self.positions[skill_id]
            x1 = max(0, x - size)
            y1 = max(0, y - size)
            x2 = min(img.shape[1], x + size)
            y2 = min(img.shape[0], y + size)

            roi = gray[y1:y2, x1:x2]
            avg = np.mean(roi) if roi.size > 0 else 0
            status = "✓ 亮" if avg >= self.BRIGHTNESS_THRESHOLD else "× 暗"
            if log_fn:
                log_fn(f"  技能 {skill_id}: 亮度={avg:.1f} {status}")

    def get_queued_skills_info(self, hwnd, skill_ids: list) -> dict:
        """回傳目前畫面上哪些技能處於「佇列中」及其增量像素數量"""
        im = get_window_screenshot(hwnd)
        if im is None: return {}

        img_bgr = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
        hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
        h, w = img_bgr.shape[:2]
        ox, oy_global, ow, oh = self.QUEUE_ROI_OFFSET
        result = {}

        for sid in skill_ids:
            if sid not in self.positions: continue
            
            # 智慧型偏移：針對不同排數給予不同 y 偏移
            # a-f 是上排角色技能，標籤在圖示中間偏下；1-6 是底排技能，標籤在圖示上方
            oy = 15 if sid in ['a','b','c','d','e','f'] else -20
            
            x, y = self.positions[sid]
            rx1, ry1 = max(0, int(x + ox - ow)), max(0, int(y + oy - oh))
            rx2, ry2 = min(w, int(x + ox + ow)), min(h, int(y + oy + oh))
            if rx1 >= rx2 or ry1 >= ry2: continue

            roi_hsv = hsv[ry1:ry2, rx1:rx2]
            mask = cv2.inRange(roi_hsv, self.QUEUE_HSV_LOWER, self.QUEUE_HSV_UPPER)
            count = np.count_nonzero(mask)
            
            # 使用增量判斷
            base_px = self.base_queued.get(sid, 0)
            if count > base_px + self.QUEUE_TOLERANCE and count >= self.QUEUE_PIXEL_THRESHOLD:
                result[sid] = count - base_px
                
        return result


# ═══════════════════════════════════════════════════════
# 3. 技能施放引擎
# ═══════════════════════════════════════════════════════
class SkillPresetPlayer:
    """
    技能施放引擎
    
    Phase 1: 依序執行各組技能（按照語法定義的順序）
    Phase 2: 自動循環模式（偵測亮度，按 CD 好的技能）
    """

    def __init__(self):
        self.playing = False
        self.log_callback = None
        self.cd_detector = SkillCooldownDetector()
        self.cast_interval = 0.3  # 每次施放之間的間隔
        self.battle_only = True   # 僅戰鬥中施放

    def log(self, message):
        if self.log_callback:
            try:
                self.log_callback(message)
            except Exception:
                pass
        else:
            print(message)

    def set_positions(self, positions: dict):
        """設定技能座標"""
        self.cd_detector.positions = positions

    def play(self, target_windows, preset_data: dict):
        """
        主執行迴圈。
        
        target_windows: [(title, hwnd), ...]
        preset_data: 解析後的單一套組 {"name": ..., "groups": [...]}
        """
        if not target_windows:
            self.log("✗ 無目標視窗")
            return
        if not preset_data or not preset_data.get("groups"):
            self.log("✗ 無技能資料")
            return

        self.playing = True
        main_hwnd = target_windows[0][1]  # 使用第一個視窗
        all_hwnds = [hwnd for _, hwnd in target_windows]
        
        name = preset_data.get("name", "未命名")
        groups = preset_data["groups"]
        all_skill_ids = SkillPresetParser.get_all_skill_ids(preset_data)

        self.log(f"=== 開始技能預設：{name} ===")

        # ── 等待戰鬥開始 ──
        if self.battle_only:
            self.log("⏳ 等待進入戰鬥...")
            wait_start = time.time()
            wait_timeout = 15.0  # 加入 15 秒超時預防機制，避免戰鬥瞬間結束導致卡死
            
            while self.playing:
                if is_in_any_battle(main_hwnd, duration=1.0):
                    self.log("⚔️ 偵測到戰鬥！開始施放技能")
                    break
                
                # 檢查是否超時
                if time.time() - wait_start > wait_timeout:
                    self.log(f"  ⚠️ 超時 {wait_timeout}s 未偵測到戰鬥，判定已脫離，跳過施放")
                    self.playing = False
                    return
                
                time.sleep(0.5)

        if not self.playing:
            return

        # ── Phase 1: 依序執行組別 ──
        self.log("── Phase 1: 依序施放 ──")
        for i, group in enumerate(groups):
            if not self.playing:
                break
            
            # 戰鬥中檢測 (增加時長至 1.0s 以提高穩定性)
            if self.battle_only and not is_in_any_battle(main_hwnd, duration=1.0):
                self.log("  ⚠️ 戰鬥結束，停止施放")
                self.playing = False
                return

            skills = group.get("skills", [])
            wait_time = group.get("wait", 0)

            if skills:
                # ── 施放前校準背景 ──
                self.cd_detector.calibrate_base_queued(main_hwnd, skills)
                
                skills_str = "→".join(skills)
                self.log(f"  組{i + 1}: {skills_str}")
                for skill_id in skills:
                    if not self.playing: break
                    if self.battle_only and not is_in_any_battle(main_hwnd, duration=0.5):
                        self.playing = False
                        return
                    # 修改：傳入完整的 target_windows (包含標題)
                    self._cast_skill(target_windows, skill_id)
                    time.sleep(self.cast_interval)

            if not self.playing: break

            # ── 智慧混合等待 ──
            if skills:
                # 有技能：以標記歸零為主，設定時間為輔 (上限 80s)
                target_timeout = abs(wait_time) if wait_time != 0 else 80.0
                self.wait_for_queue_clear(main_hwnd, skills, timeout=target_timeout)
            else:
                # 沒技能 (純等待組，如 -20)：強制等滿，僅在戰鬥結束時中止
                if wait_time != 0:
                    target_wait = abs(wait_time)
                    self.log(f"  組{i+1}: 等待 {target_wait} s")
                    wait_start = time.time()
                    while self.playing and time.time() - wait_start < target_wait:
                        # 戰鬥中檢測 (確保沒怪了能縮短等待)
                        if self.battle_only and not is_in_any_battle(main_hwnd, duration=1.0):
                            break
                        time.sleep(0.5)

        if not self.playing:
            self.log("=== 技能預設已停止 ===")
            return

        # ── Phase 2: 自動循環 ──
        self.log("── Phase 2: 自動循環（按亮起技能） ──")
        # 按 1→2→3→4→5→6→a→b→c→d→e→f 的固定順序
        cycle_order = [s for s in "123456abcdef" if s in all_skill_ids]
        
        if not cycle_order:
            self.log("  ⚠️ 無技能可循環")
            self.playing = False
            return

        self.log(f"  循環技能: {', '.join(cycle_order)}")

        while self.playing:
            # 戰鬥中檢測 (循環模式建議維持較短偵測以利快速反應)
            if self.battle_only:
                if not is_in_any_battle(main_hwnd, duration=0.6):
                    self.log("  ⚠️ 戰鬥結束，停止施放")
                    break

            # 批量偵測哪些技能亮了
            ready_skills = self.cd_detector.get_ready_skills(main_hwnd, cycle_order)

            if ready_skills:
                for skill_id in cycle_order:
                    if not self.playing:
                        break
                    if skill_id in ready_skills:
                        # 修改：傳入完整的 target_windows (包含標題)
                        self._cast_skill(target_windows, skill_id)
                        time.sleep(self.cast_interval)
            else:
                time.sleep(0.3)  # 沒有技能亮，短暫等待

        self.playing = False
        self.log("=== 技能預設執行完畢 ===")

    def _cast_skill(self, target_windows, skill_id: str):
        """施放一個技能：對所有視窗發送點擊"""
        pos = self.cd_detector.positions.get(skill_id)
        if not pos:
            self.log(f"  ⚠️ 技能 {skill_id} 無座標")
            return
        x, y = pos
        for title, hwnd in target_windows:
            if not self.playing: break
            # 效能與穩定性優化：為每個視窗添加獨立日誌與微小延遲
            self.log(f"    ➜ [{title}] 施放技能 {skill_id}")
            send_click(hwnd, x, y)
            time.sleep(0.05) # 視窗間微小延遲，避免指令衝撞

    def wait_for_queue_clear(self, hwnd, skill_ids, timeout=60.0):
        """等待畫面上所有標記完全消失（數量歸零）"""
        if not self.playing:
            return
            
        # 緩衝延遲，等待標籤出現
        time.sleep(1.0)
        start_wait = time.time()
        
        while time.time() - start_wait < timeout and self.playing:
            # 戰鬥中檢測
            if self.battle_only and not is_in_any_battle(hwnd, duration=0.5):
                time.sleep(0.5)
                if not is_in_any_battle(hwnd, duration=0.5):
                    self.playing = False
                    return
                
            blocking_map = self.cd_detector.get_queued_skills_info(hwnd, skill_ids)
            if not blocking_map:
                # 再次確認
                time.sleep(0.3)
                blocking_map = self.cd_detector.get_queued_skills_info(hwnd, skill_ids)
                if not blocking_map:
                    return
            
            time.sleep(0.8)
            
        if time.time() - start_wait >= timeout:
            self.log("  ⚠️ 等待佇列超時，繼續執行")

    def stop(self):
        """停止施放"""
        self.playing = False


# ═══════════════════════════════════════════════════════
# 4. 預設檔案管理
# ═══════════════════════════════════════════════════════
PRESET_DIR = "scripts/skill_presets"
PRESET_FILE = os.path.join(PRESET_DIR, "技能預設.json")


def ensure_preset_dir():
    if not os.path.exists(PRESET_DIR):
        os.makedirs(PRESET_DIR)


def save_preset(skill_text: str, positions: dict, 
                battle_only: bool = True, cast_interval: float = 0.3,
                filename: str = None) -> str:
    """
    儲存預設為單一 JSON 檔案。
    """
    ensure_preset_dir()
    
    if not filename:
        filename = "技能預設.json"
    
    if not filename.endswith(".json"):
        filename += ".json"
        
    target_file = os.path.join(PRESET_DIR, filename)

    data = {
        "skill_text": skill_text,
        "positions": positions,
        "battle_only": battle_only,
        "cast_interval": cast_interval
    }

    with open(target_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return os.path.basename(target_file)


def load_preset(filename: str = None) -> dict:
    """載入預設 JSON。如果成功，回傳資料內容。"""
    ensure_preset_dir()
    
    # 優先嘗試 migration
    migrate_old_data()

    if not filename:
        filename = "技能預設.json"
        
    target_file = os.path.join(PRESET_DIR, filename)
    if not os.path.exists(target_file):
        return None
        
    try:
        with open(target_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return None


def list_presets() -> list:
    """列出預設目錄下的所有 .json 檔案"""
    ensure_preset_dir()
    return sorted([f for f in os.listdir(PRESET_DIR) if f.endswith(".json") and not f.endswith(".bak")])


def migrate_old_data():
    """遷移舊版的 coordinates.json 到 技能預設.json 中"""
    coord_file = os.path.join(PRESET_DIR, "coordinates.json")
    if not os.path.exists(coord_file):
        return

    # 如果主檔案不存在，建立一個基本的
    if not os.path.exists(PRESET_FILE):
        try:
            with open(coord_file, 'r', encoding='utf-8') as f:
                coords = json.load(f)
            
            data = {
                "skill_text": "",
                "positions": coords,
                "battle_only": True,
                "cast_interval": 0.3
            }
            with open(PRESET_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # 備份舊檔
            os.rename(coord_file, coord_file + ".bak")
        except:
            pass
    else:
        # 如果主檔案已存在但沒有座標，嘗試補入
        try:
            with open(PRESET_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if not data.get("positions"):
                with open(coord_file, 'r', encoding='utf-8') as f:
                    coords = json.load(f)
                data["positions"] = coords
                with open(PRESET_FILE, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                os.rename(coord_file, coord_file + ".bak")
        except:
            pass
