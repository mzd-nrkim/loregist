#!/usr/bin/env python3
# stashdex-memo.command
# 역할: Tkinter 멀티라인 textarea 창으로 메모를 입력받아 stashdex memo 명령으로 기록한다.
# 최종 배치 위치: ~/Applications/stashdex-memo.command (또는 Dock/Finder에서 실행)
# 수동 설치 방법:
#   1. 이 파일을 ~/Applications/ 에 복사한다.
#   2. chmod +x ~/Applications/stashdex-memo.command
#   3. PROJECT_KEY / LOREGIST_BIN 값을 환경에 맞게 수정하거나
#      install-nondev-kit.sh 의 sed 치환을 통해 자동 설정한다.

import tkinter as tk
from tkinter import messagebox
import subprocess
import sys

# sed 치환 마커용 상수 — install-nondev-kit.sh 가 이 값을 실제 환경 값으로 교체한다.
PROJECT_KEY = "personal-work"
LOREGIST_BIN = "/usr/local/bin/stashdex"


def submit(event=None):
    text = text_widget.get("1.0", tk.END).rstrip("\n")
    if not text:
        root.destroy()
        return
    subprocess.run([LOREGIST_BIN, "memo", text, "--project", PROJECT_KEY])
    messagebox.showinfo("완료", "메모가 기록되었습니다.")
    root.destroy()


def update_counter(event=None):
    content = text_widget.get("1.0", tk.END).rstrip("\n")
    counter_label.config(text=f"{len(content)}자")


def cancel(event=None):
    root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    root.title("메모 기록")

    # 상단 안내 레이블
    label = tk.Label(root, text="기록할 메모를 입력하세요:")
    label.pack(anchor="w", padx=10, pady=(10, 2))

    # 멀티라인 textarea
    text_widget = tk.Text(root, width=60, height=15, wrap=tk.WORD)
    text_widget.pack(padx=10, pady=(0, 4))
    text_widget.focus_set()

    # 실시간 글자 수 카운터
    counter_label = tk.Label(root, text="0자", anchor="e")
    counter_label.pack(fill="x", padx=10, pady=(0, 4))
    text_widget.bind("<KeyRelease>", update_counter)

    # 전송 버튼
    submit_btn = tk.Button(root, text="전송 (⌘Return)", command=submit)
    submit_btn.pack(pady=(0, 10))

    # 단축키 바인딩
    root.bind("<Command-Return>", submit)
    root.bind("<Escape>", cancel)

    root.mainloop()
