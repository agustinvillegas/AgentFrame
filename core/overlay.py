from __future__ import annotations
import threading
import queue
import tkinter as tk
from core.overlay_theme import (
    BG_PRIMARY, BG_SECONDARY, BG_TERTIARY,
    TEXT_PRIMARY, TEXT_ACCENT,
    BTN_CONFIRM, BTN_CANCEL, BTN_FG,
    FONT_FAMILY, FONT_SIZE_SM, FONT_SIZE_MD, FONT_SIZE_LG,
    NOTIFY_W, NOTIFY_H, NOTIFY_MARGIN, NOTIFY_BOTTOM,
    STATUS_W, STATUS_H, CONFIRM_W, CONFIRM_H, CHAT_W, CHAT_H,
    ALPHA_NOTIFY, ALPHA_STATUS, APP_NAME,
)


class OverlayManager:

    def __init__(self):
        self._queue:  queue.Queue = queue.Queue()
        self._thread  = threading.Thread(target=self._run, daemon=True)
        self._root:   tk.Tk | None = None
        self._status: tk.Toplevel | None = None
        self._chat:   tk.Toplevel | None = None
        self._chat_messages: list[dict] = []
        self._thread.start()

    def send(self, command: str, **kwargs):
        self._queue.put({"command": command, **kwargs})

    def confirm(self, message: str) -> bool:
        result = threading.Event()
        value  = [False]

        def _ask():
            win = tk.Toplevel(self._root)
            win.title(APP_NAME)
            win.attributes("-topmost", True)
            win.resizable(False, False)
            win.configure(bg=BG_PRIMARY)

            sw = win.winfo_screenwidth()
            sh = win.winfo_screenheight()
            win.geometry(f"{CONFIRM_W}x{CONFIRM_H}+{(sw - CONFIRM_W) // 2}+{(sh - CONFIRM_H) // 2}")

            tk.Label(
                win, text=message, bg=BG_PRIMARY, fg=TEXT_PRIMARY,
                font=(FONT_FAMILY, FONT_SIZE_LG), wraplength=340, pady=16
            ).pack()

            btn_frame = tk.Frame(win, bg=BG_PRIMARY)
            btn_frame.pack()

            def _yes():
                value[0] = True
                win.destroy()
                result.set()

            def _no():
                value[0] = False
                win.destroy()
                result.set()

            tk.Button(
                btn_frame, text="Yes", command=_yes,
                bg=BTN_CONFIRM, fg=BTN_FG,
                font=(FONT_FAMILY, FONT_SIZE_MD, "bold"),
                relief="flat", padx=20, pady=6, cursor="hand2"
            ).pack(side="left", padx=8)

            tk.Button(
                btn_frame, text="No", command=_no,
                bg=BTN_CANCEL, fg=BTN_FG,
                font=(FONT_FAMILY, FONT_SIZE_MD, "bold"),
                relief="flat", padx=20, pady=6, cursor="hand2"
            ).pack(side="left", padx=8)

        self._queue.put({"command": "_confirm_dialog", "fn": _ask})
        result.wait(timeout=30)
        return value[0]

    def _run(self):
        self._root = tk.Tk()
        self._root.withdraw()
        self._root.after(100, self._poll)
        self._root.mainloop()

    def _poll(self):
        try:
            while True:
                item = self._queue.get_nowait()
                self._handle(item)
        except queue.Empty:
            pass
        self._root.after(100, self._poll)

    def _handle(self, item: dict):
        cmd = item.get("command")

        if cmd == "notify":
            self._show_notify(item.get("message", ""), item.get("duration", 3))
        elif cmd == "status":
            msg = item.get("message")
            if msg:
                self._show_status(msg)
            else:
                self._hide_status()
        elif cmd == "chat":
            msg   = item.get("message", "")
            sender = item.get("sender", "agent")
            clear  = item.get("clear", False)
            if clear:
                self._clear_chat()
            else:
                self._add_chat_message(msg, sender)
        elif cmd == "_confirm_dialog":
            item["fn"]()

    def _show_notify(self, message: str, duration: int):
        win = tk.Toplevel(self._root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-alpha", ALPHA_NOTIFY)
        win.configure(bg=BG_SECONDARY)

        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        win.geometry(f"{NOTIFY_W}x{NOTIFY_H}+{sw - NOTIFY_W - NOTIFY_MARGIN}+{sh - NOTIFY_H - NOTIFY_BOTTOM}")

        tk.Label(
            win, text=message, bg=BG_SECONDARY, fg=TEXT_PRIMARY,
            font=(FONT_FAMILY, FONT_SIZE_MD), wraplength=290, padx=16, pady=16
        ).pack()

        self._root.after(duration * 1000, win.destroy)

    def _show_status(self, message: str):
        if self._status:
            try:
                self._status.destroy()
            except Exception:
                pass

        win = tk.Toplevel(self._root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-alpha", ALPHA_STATUS)
        win.configure(bg=BG_PRIMARY)

        sw = win.winfo_screenwidth()
        win.geometry(f"{STATUS_W}x{STATUS_H}+{(sw - STATUS_W) // 2}+8")

        tk.Label(
            win, text=f"⚙ {message}", bg=BG_PRIMARY, fg=TEXT_ACCENT,
            font=(FONT_FAMILY, FONT_SIZE_SM), padx=12
        ).pack(side="left")

        self._status = win

    def _hide_status(self):
        if self._status:
            try:
                self._status.destroy()
            except Exception:
                pass
            self._status = None

    def _add_chat_message(self, message: str, sender: str):
        if not self._chat or not self._chat.winfo_exists():
            self._create_chat_window()
        self._chat_messages.append({"sender": sender, "message": message})
        self._refresh_chat()

    def _clear_chat(self):
        self._chat_messages = []
        if self._chat and self._chat.winfo_exists():
            self._refresh_chat()

    def _create_chat_window(self):
        win = tk.Toplevel(self._root)
        win.title(APP_NAME)
        win.attributes("-topmost", True)
        win.configure(bg=BG_PRIMARY)
        win.geometry(f"{CHAT_W}x{CHAT_H}+40+40")
        win.resizable(True, True)

        self._chat       = win
        self._chat_frame = tk.Frame(win, bg=BG_PRIMARY)
        self._chat_frame.pack(fill="both", expand=True, padx=8, pady=8)

        self._chat_canvas    = tk.Canvas(self._chat_frame, bg=BG_PRIMARY, highlightthickness=0)
        self._chat_scrollbar = tk.Scrollbar(self._chat_frame, orient="vertical", command=self._chat_canvas.yview)
        self._chat_canvas.configure(yscrollcommand=self._chat_scrollbar.set)

        self._chat_scrollbar.pack(side="right", fill="y")
        self._chat_canvas.pack(side="left", fill="both", expand=True)

        self._chat_inner = tk.Frame(self._chat_canvas, bg=BG_PRIMARY)
        self._chat_canvas.create_window((0, 0), window=self._chat_inner, anchor="nw")
        self._chat_inner.bind("<Configure>", lambda e: self._chat_canvas.configure(
            scrollregion=self._chat_canvas.bbox("all")
        ))

    def _refresh_chat(self):
        for widget in self._chat_inner.winfo_children():
            widget.destroy()

        for msg in self._chat_messages:
            sender  = msg["sender"]
            text    = msg["message"]
            is_user = sender == "user"

            bubble_bg = BG_TERTIARY if is_user else BG_SECONDARY
            anchor    = "e" if is_user else "w"
            padx      = (40, 8) if is_user else (8, 40)

            frame = tk.Frame(self._chat_inner, bg=BG_PRIMARY)
            frame.pack(fill="x", pady=3)

            tk.Label(
                frame, text=text, bg=bubble_bg, fg=TEXT_PRIMARY,
                font=(FONT_FAMILY, FONT_SIZE_MD), wraplength=260,
                justify="left", padx=10, pady=8, relief="flat"
            ).pack(anchor=anchor, padx=padx)

        self._chat_canvas.update_idletasks()
        self._chat_canvas.yview_moveto(1.0)


overlay = OverlayManager()