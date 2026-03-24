import cv2
import numpy as np
from screen import get_screen

def match_template(screen, template_path, threshold=0.8):
    screen_np = np.array(screen)
    screen_gray = cv2.cvtColor(screen_np, cv2.COLOR_BGR2GRAY)

    template = cv2.imread(template_path, 0)

    result = cv2.matchTemplate(screen_gray, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)

    if max_val >= threshold:
        return True, max_loc
    return False, None


def get_state():
    screen = get_screen()

    found, _ = match_template(screen, "images/victory.png")
    if found:
        return "VICTORY"

    found, _ = match_template(screen, "images/boss.png")
    if found:
        return "BOSS"

    found, _ = match_template(screen, "images/skill_ready.png")
    if found:
        return "SKILL_READY"

    return "FIGHTING"