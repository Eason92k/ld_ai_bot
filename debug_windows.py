import pygetwindow as gw

print("當前打開的所有窗口：")
print("-" * 50)

for window in gw.getAllWindows():
    if window.title:  # 只顯示有標題的窗口
        print(f"標題: {window.title}")
        print(f"是否可見: {window.isActive}")
        print()

print("-" * 50)
print("查找包含 '雷' 或 '模擬' 的窗口：")
for window in gw.getAllWindows():
    if '雷' in window.title or '模擬' in window.title or 'ld' in window.title.lower():
        print(f"找到: {window.title}")
