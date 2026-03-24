import pygetwindow as gw

def get_ldplayer_window():
    windows = gw.getWindowsWithTitle("Test")

    if not windows:
        raise Exception("找不到雷電模擬器，請確認已開啟")

    return windows[0]