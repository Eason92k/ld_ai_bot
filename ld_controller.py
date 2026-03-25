import pygetwindow as gw
import win32gui
import win32api
import win32con
import time

def list_all_ldplayer_windows():
    """列出所有可能是雷電模擬器的窗口 (傳回標題與句柄)"""
    ld_windows = []
    
    def enum_cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            classname = win32gui.GetClassName(hwnd)
            # 優先使用類別名稱識別
            if classname == "LDPlayerMainFrame":
                ld_windows.append((title, hwnd))
            # 備用：標題關鍵字
            elif any(k in title for k in ["LDPlayer", "雷電模擬器", "Test"]):
                ld_windows.append((title, hwnd))
                
    win32gui.EnumWindows(enum_cb, None)
    # 去重並排序
    unique_windows = []
    seen_hwnds = set()
    for title, hwnd in ld_windows:
        if hwnd not in seen_hwnds:
            unique_windows.append((title, hwnd))
            seen_hwnds.add(hwnd)
            
    return sorted(unique_windows, key=lambda x: x[0])

def get_ldplayer_window(title=None):
    if title:
        windows = gw.getWindowsWithTitle(title)
        if windows:
            return windows[0]
    
    # 嘗試找類別名稱為 LDPlayerMainFrame 的視窗
    ld_windows = []
    def enum_cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            if win32gui.GetClassName(hwnd) == "LDPlayerMainFrame":
                ld_windows.append(win32gui.GetWindowText(hwnd))
    win32gui.EnumWindows(enum_cb, None)
    
    if ld_windows:
        # 直接拿第一個找到的
        windows = gw.getWindowsWithTitle(ld_windows[0])
        if windows:
            return windows[0]

    # 如果沒指定或找不到指定的，嘗試原有的關鍵字
    keywords = ["LDPlayer", "雷電模擬器", "Test"]
    for k in keywords:
        windows = gw.getWindowsWithTitle(k)
        if windows:
            return windows[0]

    raise Exception("找不到指定的模擬器視窗，請確認已開啟")

def find_sub_window(hwnd):
    """找到雷電模擬器的實際渲染子窗口 (RenderWindow)，這通常是接收輸入的地方"""
    # LDPlayer 9 的結構通常是 MainFrame -> TheAeroWindow -> BindWindow -> RenderWindow
    # 我們需要找到最深層的那個子視窗
    render_hwnd = [None]
    
    def enum_child_cb(child_hwnd, _):
        classname = win32gui.GetClassName(child_hwnd)
        if "RenderWindow" in classname or "BindWindow" in classname:
            render_hwnd[0] = child_hwnd
            # 繼續往下找，因為我們要找最深層的
            return True
        return True

    win32gui.EnumChildWindows(hwnd, enum_child_cb, None)
    
    if render_hwnd[0]:
        return render_hwnd[0]
    return hwnd

def send_click(hwnd, x, y):
    """使用 PostMessage 發送背景點擊"""
    target_hwnd = find_sub_window(hwnd)
    
    # 將相對於 MainFrame 的座標轉為屏幕座標，再轉為相對於 TargetWindow 的座標
    try:
        # 1. 將 (x, y) 從 MainFrame 的客戶區座標轉為屏幕座標
        screen_pos = win32gui.ClientToScreen(hwnd, (int(x), int(y)))
        # 2. 將屏幕座標轉為 TargetWindow (渲染視窗) 的客戶區座標
        local_x, local_y = win32gui.ScreenToClient(target_hwnd, screen_pos)
    except:
        local_x, local_y = int(x), int(y)

    lparam = win32api.MAKELONG(local_x, local_y)
    
    # 模擬滑鼠序列
    win32gui.PostMessage(target_hwnd, win32con.WM_MOUSEMOVE, 0, lparam)
    time.sleep(0.01)
    win32gui.PostMessage(target_hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam)
    time.sleep(0.05)
    win32gui.PostMessage(target_hwnd, win32con.WM_LBUTTONUP, 0, lparam)


def send_swipe(hwnd, start_x, start_y, end_x, end_y, duration=0.3):
    """使用 PostMessage 模擬滑動"""
    target_hwnd = find_sub_window(hwnd)
    try:
        s_p = win32gui.ClientToScreen(hwnd, (int(start_x), int(start_y)))
        s_l = win32gui.ScreenToClient(target_hwnd, s_p)
        e_p = win32gui.ClientToScreen(hwnd, (int(end_x), int(end_y)))
        e_l = win32gui.ScreenToClient(target_hwnd, e_p)
    except:
        s_l = (int(start_x), int(start_y))
        e_l = (int(end_x), int(end_y))

    win32gui.PostMessage(target_hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, win32api.MAKELONG(s_l[0], s_l[1]))
    
    steps = 5
    for i in range(steps + 1):
        curr_x = int(s_l[0] + (e_l[0] - s_l[0]) * i / steps)
        curr_y = int(s_l[1] + (e_l[1] - s_l[1]) * i / steps)
        win32gui.PostMessage(target_hwnd, win32con.WM_MOUSEMOVE, win32con.MK_LBUTTON, win32api.MAKELONG(curr_x, curr_y))
        time.sleep(duration / (steps + 1))
        
    win32gui.PostMessage(target_hwnd, win32con.WM_LBUTTONUP, 0, win32api.MAKELONG(e_l[0], e_l[1]))

def send_key(hwnd, key_code):
    """使用 PostMessage 發送按鍵"""
    target_hwnd = find_sub_window(hwnd)
    win32gui.PostMessage(target_hwnd, win32con.WM_KEYDOWN, key_code, 0)
    time.sleep(0.01)
    win32gui.PostMessage(target_hwnd, win32con.WM_KEYUP, key_code, 0)

