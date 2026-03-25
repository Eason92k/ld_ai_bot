import pyautogui
import random
from ld_controller import get_ldplayer_window

def click_relative(x, y):
    win = get_ldplayer_window()

    real_x = win.left + x + random.randint(-5, 5)
    real_y = win.top + y + random.randint(-5, 5)

    pyautogui.click(real_x, real_y)


def do_action(action):
    if action == "USE_SKILL":
        click_relative(600, 900)

    elif action == "NEXT_STAGE":
        click_relative(1000, 800)

    elif action == "AUTO_ATTACK":
        click_relative(800, 900)

    elif action == "IDLE":
        pass

def swipe_relative(x1, y1, x2, y2, duration=0.5):
    win = get_ldplayer_window()
    
    real_x1 = win.left + x1
    real_y1 = win.top + y1
    real_x2 = win.left + x2
    real_y2 = win.top + y2
    
    pyautogui.moveTo(real_x1, real_y1)
    pyautogui.dragTo(real_x2, real_y2, duration=duration, button='left')