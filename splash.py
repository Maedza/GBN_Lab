"""
E_force Software — Splash screen.
"""

from __future__ import annotations

import customtkinter as ctk
import tkinter as tk

import config as _cfg


class SplashScreen(ctk.CTkToplevel):
    """Branded loading screen shown at startup.

    Calls ``on_done`` after fade-out completes so the caller can
    show the main window at exactly the right moment.
    """

    def __init__(self, parent: ctk.CTk, *, on_done=None):
        super().__init__(parent)
        self._on_done = on_done
        self.overrideredirect(True)
        self.configure(fg_color="#0f172a")

        # Compact splash — scales with screen density
        s = _cfg.CANVAS_SCALE
        w, h = int(480 * s), int(320 * s)
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x, y = (sw - w) // 2, (sh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

        self._s = s

        # Prevent interaction with parent
        self.grab_set()
        self.attributes("-topmost", True)

        frame = ctk.CTkFrame(self, fg_color="#0f172a", corner_radius=int(16 * s),
                             border_width=2, border_color="#334155")
        frame.pack(fill="both", expand=True, padx=1, pady=1)

        # ── Brand ──
        ctk.CTkLabel(
            frame, text="E_force Software",
            font=ctk.CTkFont(size=max(16, int(28 * s)), weight="bold"),
            text_color="#6366f1",
        ).pack(pady=(int(40 * s), int(6 * s)))

        ctk.CTkLabel(
            frame, text="Presents",
            font=ctk.CTkFont(size=max(8, int(11 * s))),
            text_color="#94a3b8",
        ).pack()

        # Divider
        ctk.CTkFrame(frame, fg_color="#334155",
                     height=1, width=int(140 * s)).pack(pady=int(14 * s))

        # ── App name ──
        ctk.CTkLabel(
            frame, text="GBN Lab",
            font=ctk.CTkFont(size=max(14, int(22 * s)), weight="bold"),
            text_color="#38bdf8",
        ).pack()

        ctk.CTkLabel(
            frame, text="Go-Back-N ARQ Protocol Simulator",
            font=ctk.CTkFont(size=max(8, int(11 * s))),
            text_color="#64748b",
        ).pack(pady=(int(2 * s), int(28 * s)))

        # ── Progress bar ──
        self._bar = ctk.CTkProgressBar(
            frame, width=int(320 * s), height=int(6 * s),
            progress_color="#6366f1",
            fg_color="#1e293b",
            corner_radius=int(3 * s),
        )
        self._bar.pack(pady=(0, int(16 * s)))
        self._bar.set(0)

        self._status = ctk.CTkLabel(
            frame, text="Initialising...",
            font=ctk.CTkFont(size=max(8, int(10 * s))),
            text_color="#475569",
        )
        self._status.pack()

        # ── Slogan ──
        ctk.CTkLabel(
            frame, text="Engineering the future, one protocol at a time.",
            font=ctk.CTkFont(size=max(7, int(9 * s)), slant="italic"),
            text_color="#334155",
        ).pack(pady=(int(20 * s), 0))

        self.attributes("-alpha", 0.0)
        self._fade_in()

    def _fade_in(self) -> None:
        a = self.attributes("-alpha")
        if a < 1.0:
            self.attributes("-alpha", min(a + 0.1, 1.0))
            self.after(30, self._fade_in)
        else:
            self._start_progress()

    def _start_progress(self) -> None:
        self._tick = 0
        self._total_ticks = 24
        self._animate_progress()

    def _animate_progress(self) -> None:
        self._tick += 1
        progress = self._tick / self._total_ticks
        self._bar.set(progress)

        msgs = [
            "Loading modules...",
            "Initialising simulation engine...",
            "Setting up channel model...",
            "Preparing protocol state...",
            "Building user interface...",
            "Rendering animation canvas...",
            "Calibrating performance metrics...",
            "Connecting event pipeline...",
            "Almost ready...",
        ]
        idx = min(self._tick * len(msgs) // self._total_ticks, len(msgs) - 1)
        self._status.configure(text=msgs[idx])

        if self._tick < self._total_ticks:
            self.after(120, self._animate_progress)
        else:
            self._fade_out()

    def _fade_out(self) -> None:
        a = self.attributes("-alpha")
        if a > 0.05:
            self.attributes("-alpha", max(a - 0.1, 0.0))
            self.after(30, self._fade_out)
        else:
            self.grab_release()
            self.destroy()
            if self._on_done:
                self._on_done()
