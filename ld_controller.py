import pygetwindow as gw
import win32gui

def list_all_ldplayer_windows():
    """列出所有可能是雷電模擬器的窗口"""
    ld_windows = []
    
    def enum_cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            classname = win32gui.GetClassName(hwnd)
            # 優先使用類別名稱識別
            if classname == "LDPlayerMainFrame":
                ld_windows.append(title)
            # 備用：標題關鍵字
            elif any(k in title for k in ["LDPlayer", "雷電模擬器", "Test"]):
                ld_windows.append(title)
                
    win32gui.EnumWindows(enum_cb, None)
    return sorted(list(set(ld_windows)))

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