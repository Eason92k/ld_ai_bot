import pyautogui
from ld_controller import get_ldplayer_window

def get_screen():
    win = get_ldplayer_window()

    region = (win.left, win.top, win.width, win.height)
    screenshot = pyautogui.screenshot(region=region)

    return screenshot