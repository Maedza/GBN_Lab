"""
E_force Software — Splash / Loading Screen.

Displays a branded splash window while the main application
initialises, then fades out and hands off to the main window.
"""

from __future__ import annotations

import customtkinter as ctk
import tkinter as tk


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

        # Compact splash — like MATLAB, VS Code, etc.
        w, h = 480, 320
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x, y = (sw - w) // 2, (sh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

        # Prevent interaction with parent
        self.grab_set()
        self.attributes("-topmost", True)

        # Rounded-corner illusion with a frame
        frame = ctk.CTkFrame(self, fg_color="#0f172a", corner_radius=16,
                             border_width=2, border_color="#334155")
        frame.pack(fill="both", expand=True, padx=1, pady=1)

        # ── Brand ──
        ctk.CTkLabel(
            frame, text="E_force Software",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color="#6366f1",
        ).pack(pady=(40, 6))

        ctk.CTkLabel(
            frame, text="Presents",
            font=ctk.CTkFont(size=11),
            text_color="#94a3b8",
        ).pack()

        # Divider
        ctk.CTkFrame(frame, fg_color="#334155", height=1, width=140).pack(pady=14)

        # ── App name ──
        ctk.CTkLabel(
            frame, text="GBN Lab",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color="#38bdf8",
        ).pack()

        ctk.CTkLabel(
            frame, text="Go-Back-N ARQ Protocol Simulator",
            font=ctk.CTkFont(size=11),
            text_color="#64748b",
        ).pack(pady=(2, 28))

        # ── Progress bar ──
        self._bar = ctk.CTkProgressBar(
            frame, width=320, height=6,
            progress_color="#6366f1",
            fg_color="#1e293b",
            corner_radius=3,
        )
        self._bar.pack(pady=(0, 16))
        self._bar.set(0)

        self._status = ctk.CTkLabel(
            frame, text="Initialising...",
            font=ctk.CTkFont(size=10),
            text_color="#475569",
        )
        self._status.pack()

        # ── Slogan ──
        ctk.CTkLabel(
            frame, text="Engineering the future, one protocol at a time.",
            font=ctk.CTkFont(size=9, slant="italic"),
            text_color="#334155",
        ).pack(pady=(20, 0))

        # Animate in
        self.attributes("-alpha", 0.0)
        self._fade_in()

    # ── Timing ────────────────────────────────────────────────────────
    # Total splash duration ≈ 8 seconds:
    #   fade-in:    ~20 steps × 50 ms ≈ 1 000 ms
    #   progress:   40 ticks × 120 ms = 4 800 ms
    #   hold:       800 ms after bar fills
    #   fade-out:   ~20 steps × 50 ms ≈ 1 000 ms

    def _fade_in(self) -> None:
        a = self.attributes("-alpha")
        if a < 1.0:
            self.attributes("-alpha", min(a + 0.05, 1.0))
            self.after(50, self._fade_in)
        else:
            self._start_progress()

    def _start_progress(self) -> None:
        self._tick = 0
        self._total_ticks = 40
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
            self.attributes("-alpha", max(a - 0.05, 0.0))
            self.after(50, self._fade_out)
        else:
            self.grab_release()
            self.destroy()
            if self._on_done:
                self._on_done()
