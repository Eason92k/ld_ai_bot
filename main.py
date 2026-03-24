import time
from vision import get_state
from decision import decide
from actions import do_action

def main():
    print("AI 自動刷副本 啟動 (Ctrl+C 結束)")

    while True:
        try:
            state = get_state()
            action = decide(state)

            print(f"狀態: {state} → 動作: {action}")

            do_action(action)

            time.sleep(1)

        except KeyboardInterrupt:
            print("停止程式")
            break

        except Exception as e:
            print("錯誤:", e)
            time.sleep(2)

if __name__ == "__main__":
    main()