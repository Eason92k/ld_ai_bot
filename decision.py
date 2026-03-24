def decide(state):
    if state == "VICTORY":
        return "NEXT_STAGE"

    elif state == "BOSS":
        return "USE_SKILL"

    elif state == "SKILL_READY":
        return "USE_SKILL"

    elif state == "FIGHTING":
        return "AUTO_ATTACK"

    return "IDLE"