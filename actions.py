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