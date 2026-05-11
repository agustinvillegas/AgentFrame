from __future__ import annotations
import threading
import queue
import tkinter as tk
from core.overlay_theme import (
    BG_PRIMARY, BG_SECONDARY, BG_TERTIARY, BG_ACCENT,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_ACCENT,
    BTN_CONFIRM, BTN_CANCEL, BTN_HOVER, BTN_FG,
    CHAT_AGENT, CHAT_USER, CHAT_ACCENT,
    FONT_FAMILY, FONT_SIZE_SM, FONT_SIZE_MD, FONT_SIZE_LG,
    NOTIFY_W, NOTIFY_H, NOTIFY_MARGIN, NOTIFY_BOTTOM,
    STATUS_W, STATUS_H, CONFIRM_W, CONFIRM_H, CHAT_W, CHAT_H,
    ALPHA_NOTIFY, ALPHA_STATUS, ALPHA_OVERLAY, APP_NAME,
    SPACING_SM, SPACING_MD, SPACING_LG, ICON_STATUS,
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

            # Header frame
            header = tk.Frame(win, bg=BG_SECONDARY, height=8)
            header.pack(fill="x")

            # Message frame with padding
            msg_frame = tk.Frame(win, bg=BG_PRIMARY)
            msg_frame.pack(fill="both", expand=True, padx=SPACING_LG, pady=SPACING_LG)

            tk.Label(
                msg_frame, text=message, bg=BG_PRIMARY, fg=TEXT_PRIMARY,
                font=(FONT_FAMILY, FONT_SIZE_LG), wraplength=340, pady=SPACING_MD,
                justify="center"
            ).pack()

            # Button frame with improved styling
            btn_frame = tk.Frame(win, bg=BG_PRIMARY)
            btn_frame.pack(pady=SPACING_MD)

            def _yes():
                value[0] = True
                win.destroy()
                result.set()

            def _no():
                value[0] = False
                win.destroy()
                result.set()

            def _on_confirm_enter(e):
                e.widget.config(bg=BTN_HOVER)

            def _on_confirm_leave(e):
                e.widget.config(bg=BTN_CONFIRM)

            yes_btn = tk.Button(
                btn_frame, text="Confirmar", command=_yes,
                bg=BTN_CONFIRM, fg=BTN_FG,
                font=(FONT_FAMILY, FONT_SIZE_MD, "bold"),
                relief="flat", padx=SPACING_LG, pady=SPACING_SM, cursor="hand2",
                activebackground=BTN_HOVER, activeforeground=BTN_FG
            )
            yes_btn.pack(side="left", padx=SPACING_SM)
            yes_btn.bind("<Enter>", _on_confirm_enter)
            yes_btn.bind("<Leave>", _on_confirm_leave)

            cancel_btn = tk.Button(
                btn_frame, text="Cancelar", command=_no,
                bg=BTN_CANCEL, fg=BTN_FG,
                font=(FONT_FAMILY, FONT_SIZE_MD, "bold"),
                relief="flat", padx=SPACING_LG, pady=SPACING_SM, cursor="hand2",
                activebackground="#dc2626", activeforeground=BTN_FG
            )
            cancel_btn.pack(side="left", padx=SPACING_SM)

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

        # Main container with accent border left
        main_frame = tk.Frame(win, bg=BG_SECONDARY)
        main_frame.pack(fill="both", expand=True)

        # Left accent bar
        accent = tk.Frame(main_frame, bg=TEXT_ACCENT, width=3)
        accent.pack(side="left", fill="y")

        # Content frame
        content = tk.Frame(main_frame, bg=BG_SECONDARY)
        content.pack(side="left", fill="both", expand=True, padx=SPACING_MD, pady=SPACING_SM)

        tk.Label(
            content, text=message, bg=BG_SECONDARY, fg=TEXT_PRIMARY,
            font=(FONT_FAMILY, FONT_SIZE_MD), wraplength=270, justify="left"
        ).pack(anchor="w", pady=SPACING_SM)

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
        win.configure(bg=BG_SECONDARY)

        sw = win.winfo_screenwidth()
        win.geometry(f"{STATUS_W}x{STATUS_H}+{(sw - STATUS_W) // 2}+8")

        # Content with icon
        content_frame = tk.Frame(win, bg=BG_SECONDARY)
        content_frame.pack(fill="both", expand=True, padx=SPACING_MD, pady=SPACING_SM)

        tk.Label(
            content_frame, text=f"{ICON_STATUS} {message}", bg=BG_SECONDARY, fg=TEXT_ACCENT,
            font=(FONT_FAMILY, FONT_SIZE_MD, "bold"), padx=SPACING_SM
        ).pack(side="left", anchor="w")

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

        self._chat = win
        
        # Header with branding
        header = tk.Frame(win, bg=BG_SECONDARY, height=32)
        header.pack(fill="x")
        header.pack_propagate(False)
        
        tk.Label(
            header, text=f"💬 {APP_NAME}", bg=BG_SECONDARY, fg=TEXT_ACCENT,
            font=(FONT_FAMILY, FONT_SIZE_LG, "bold")
        ).pack(side="left", padx=SPACING_MD, pady=SPACING_SM)

        # Chat container
        self._chat_frame = tk.Frame(win, bg=BG_PRIMARY)
        self._chat_frame.pack(fill="both", expand=True, padx=SPACING_MD, pady=SPACING_MD)

        # Canvas for scrollable content
        self._chat_canvas = tk.Canvas(
            self._chat_frame, bg=BG_PRIMARY, highlightthickness=0, 
            highlightbackground=BG_ACCENT
        )
        self._chat_scrollbar = tk.Scrollbar(
            self._chat_frame, orient="vertical", 
            command=self._chat_canvas.yview,
            bg=BG_SECONDARY
        )
        self._chat_canvas.configure(yscrollcommand=self._chat_scrollbar.set)

        self._chat_scrollbar.pack(side="right", fill="y", padx=(SPACING_SM, 0))
        self._chat_canvas.pack(side="left", fill="both", expand=True)

        # Inner frame for messages
        self._chat_inner = tk.Frame(self._chat_canvas, bg=BG_PRIMARY)
        self._chat_canvas.create_window((0, 0), window=self._chat_inner, anchor="nw")
        self._chat_inner.bind("<Configure>", lambda e: self._chat_canvas.configure(
            scrollregion=self._chat_canvas.bbox("all")
        ))

    def _refresh_chat(self):
        for widget in self._chat_inner.winfo_children():
            widget.destroy()

        for msg in self._chat_messages:
            sender = msg["sender"]
            text   = msg["message"]
            is_user = sender == "user"

            # Choose colors based on sender
            bubble_bg = CHAT_USER if is_user else CHAT_AGENT
            text_color = TEXT_PRIMARY
            anchor = "e" if is_user else "w"
            padx = (40, SPACING_SM) if is_user else (SPACING_SM, 40)

            # Message frame
            frame = tk.Frame(self._chat_inner, bg=BG_PRIMARY)
            frame.pack(fill="x", pady=SPACING_SM)

            # Message bubble with styling
            bubble = tk.Frame(frame, bg=bubble_bg, relief="flat", bd=0)
            bubble.pack(anchor=anchor, padx=padx)

            tk.Label(
                bubble, text=text, bg=bubble_bg, fg=text_color,
                font=(FONT_FAMILY, FONT_SIZE_MD), wraplength=240,
                justify="left", padx=SPACING_MD, pady=SPACING_SM,
                relief="flat", bd=0
            ).pack(anchor="w")

        self._chat_canvas.update_idletasks()
        self._chat_canvas.yview_moveto(1.0)


overlay = OverlayManager()