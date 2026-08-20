"""GBN Lab application shell — behaviour lives in the mixin modules."""

import sys
from collections import deque
from typing import Optional

import customtkinter as ctk

from config import (
    init_scale,
    DEFAULT_SIM_SPEED,
    MAX_LOG_EVENTS,
    COLOR_BG,
    DEFAULT_SCENARIO,
)
from simulation import GBNSimulation
from splash import SplashScreen
from ui_builder import UIBuilderMixin
from sim_control import SimControlMixin
from replay_control import ReplayControlMixin
from event_log import EventLogMixin
from canvas_render import CanvasRenderMixin

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class GBNLabApp(UIBuilderMixin, SimControlMixin, ReplayControlMixin,
                EventLogMixin, CanvasRenderMixin, ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("GBN Lab — E_force Software")

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self._s = init_scale(sw, sh)
        if sys.platform == "darwin":
            ctk.set_widget_scaling(1.0)

        w, h = int(sw * 0.9), int(sh * 0.9)
        x, y = (sw - w) // 2, (sh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.minsize(900, 580)
        self.configure(fg_color=COLOR_BG)

        self._sim: Optional[GBNSimulation] = None
        self._state: dict = {}
        self._last_snapshot: dict = {}
        self._events: deque = deque(maxlen=MAX_LOG_EVENTS)

        self._poll_id: Optional[str] = None
        self._anim_id: Optional[str] = None
        self._anim_frame: int = 0
        self._anim_active: bool = False
        self._completed = False

        self._replay_events: list[dict] = []
        self._replay_frames: list[dict] = []
        self._replay_capturing: bool = False
        self._replay_mode: bool = False
        self._replay_event_idx: int = 0
        self._replay_frame_idx: int = 0
        self._replay_playing: bool = False
        self._replay_id: Optional[str] = None

        self._active_flights: dict[int, dict] = {}
        self._FLIGHT_FRAMES = 20
        self._FAIL_POINT = 0.65
        self._FAIL_DISPLAY_FRAMES = 15

        self._pending_snapshot: Optional[dict] = None
        self._slide_delay: int = 0

        self._step_mode = False
        self._step_paused = False
        self._last_paused_anomaly = None
        self._canvas_size = (0, 0)
        self._sim_speed_replay = DEFAULT_SIM_SPEED

        self._build_ui()

        self._scenario_var.set(DEFAULT_SCENARIO)
        self._on_scenario_select(DEFAULT_SCENARIO)
        self.after(100, self._draw_placeholder)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind_all("<Command-q>", lambda e: self._force_quit())
        self.bind_all("<Control-q>", lambda e: self._force_quit())
        self.bind_all("<Command-w>", lambda e: self._on_close())

    def _on_close(self) -> None:
        self._stop_polling()
        self._stop_animation()
        if self._sim:
            self._sim.stop()
            self._sim = None
        try:
            self.destroy()
        except Exception:
            pass

    def _force_quit(self) -> None:
        import os
        try:
            self._stop_polling()
            self._stop_animation()
            if self._sim:
                self._sim.stop()
                self._sim = None
            self.destroy()
        except Exception:
            pass
        os._exit(0)


def main():
    app = GBNLabApp()

    def _show_app():
        app.attributes("-alpha", 1.0)
        app.deiconify()
        app.lift()
        app.focus_force()

    app.attributes("-alpha", 0.0)
    app.update_idletasks()
    splash = SplashScreen(app, on_done=_show_app)
    app.mainloop()


if __name__ == "__main__":
    main()
