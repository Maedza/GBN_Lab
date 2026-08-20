"""Replay controls: seek, step, playback, and replay event logging."""

from config import COLOR_WARNING, COLOR_ACCENT


class ReplayControlMixin:
    """Seek/playback through captured replay events and frames."""

    def _show_replay_controls(self) -> None:
        self._replay_mode = True
        self._sim_progress_frame.pack_forget()
        n_events = max(len(self._replay_events), 1)
        self._replay_slider.configure(
            to=n_events - 1, number_of_steps=n_events)
        last = n_events - 1
        self._replay_slider_var.set(last)
        self._replay_pos_label.configure(text=f"  {last}/{last}")
        self._replay_frame.pack(fill="x", expand=True)
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.configure(state="disabled")
        self._anim_frame = 0
        self._seek_to_event(last)

    def _event_to_frame_idx(self, event_idx: int) -> int:
        events = self._replay_events
        frames = self._replay_frames
        if not events or not frames:
            return 0
        target = events[max(0, min(event_idx, len(events) - 1))]["anim_frame"]
        best = 0
        for i, f in enumerate(frames):
            if f.get("anim_frame", i) <= target:
                best = i
            else:
                break
        return best

    def _frame_to_event_idx(self, frame_idx: int) -> int:
        """Find the event whose anim_frame is closest to this animation frame."""
        events = self._replay_events
        frames = self._replay_frames
        if not events or not frames:
            return 0
        if frame_idx >= len(frames):
            frame_idx = len(frames) - 1
        current = frames[frame_idx].get("anim_frame", frame_idx)
        best = 0
        for i, ev in enumerate(events):
            if ev["anim_frame"] <= current:
                best = i
            else:
                break
        return best

    def _seek_to_event(self, event_idx: int) -> None:
        n_events = len(self._replay_events)
        if n_events == 0:
            return
        event_idx = max(0, min(event_idx, n_events - 1))
        self._replay_event_idx = event_idx
        self._replay_slider_var.set(event_idx)

        frame_idx = self._event_to_frame_idx(event_idx)
        self._replay_frame_idx = frame_idx

        if self._replay_frames:
            f = self._replay_frames[min(
                frame_idx, len(self._replay_frames) - 1)]
            self._last_snapshot = f["snapshot"]
            self._active_flights.clear()
            for fid, fdata in f["flights"].items():
                self._active_flights[fid] = dict(fdata)
            frame_anim = f.get("anim_frame", frame_idx)
            for flight in self._active_flights.values():
                flight["start_frame"] = self._anim_frame - \
                    (frame_anim - flight.get("start_frame", 0))

        self._redraw_canvas()

        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        for i in range(event_idx + 1):
            self._log_replay_event(self._replay_events[i])
        self._log_text.see("end")
        self._log_text.configure(state="disabled")

        ev = self._replay_events[event_idx]
        desc = self._describe_replay_event(
            ev["event_type"], ev.get("event_packet_id", -1),
            ev.get("event_ack_id", -1), ev.get("event_time", 0))
        self._replay_pos_label.configure(
            text=f"  {event_idx}/{n_events - 1}  {desc}")

    def _on_replay_seek(self, value: float) -> None:
        if self._replay_playing:
            self._stop_replay_auto()
        self._seek_to_event(int(round(float(value))))

    def _on_replay_step_back(self) -> None:
        if self._replay_playing:
            self._stop_replay_auto()
        if self._replay_event_idx > 0:
            self._seek_to_event(self._replay_event_idx - 1)

    def _on_replay_step_fwd(self) -> None:
        if self._replay_playing:
            self._stop_replay_auto()
        n = len(self._replay_events)
        if n > 0 and self._replay_event_idx < n - 1:
            self._seek_to_event(self._replay_event_idx + 1)

    def _on_replay_play(self) -> None:
        if self._replay_playing:
            self._stop_replay_auto()
        else:
            self._start_replay_auto()

    def _start_replay_auto(self) -> None:
        self._replay_playing = True
        self._replay_play_btn.configure(text="⏸", fg_color=COLOR_WARNING,
                                        hover_color="#ca8a04")
        self._start_animation()

    def _stop_replay_auto(self) -> None:
        self._replay_playing = False
        self._stop_animation()
        self._replay_play_btn.configure(text="▶", fg_color=COLOR_ACCENT,
                                        hover_color="#4f46e5")

    def _playback_animation_frame(self) -> None:
        frames = self._replay_frames
        if not frames:
            return

        if self._replay_playing:
            if self._replay_frame_idx < len(frames) - 1:
                self._replay_frame_idx += 1
            else:
                self._stop_replay_auto()
                return

        idx = min(self._replay_frame_idx, len(frames) - 1)
        f = frames[idx]
        self._last_snapshot = f["snapshot"]

        recorded_anim = f["anim_frame"]
        self._active_flights.clear()
        for fid, fdata in f["flights"].items():
            fc = dict(fdata)
            original_start = fc.get("start_frame", recorded_anim)
            fc["start_frame"] = self._anim_frame - \
                (recorded_anim - original_start)
            self._active_flights[fid] = fc

        self._redraw_canvas()

        ev_idx = self._frame_to_event_idx(idx)
        if ev_idx != self._replay_event_idx:
            self._replay_event_idx = ev_idx
            self._replay_slider_var.set(ev_idx)
            self._log_text.configure(state="normal")
            self._log_text.delete("1.0", "end")
            for i in range(ev_idx + 1):
                self._log_replay_event(self._replay_events[i])
            self._log_text.see("end")
            self._log_text.configure(state="disabled")
            ev = self._replay_events[ev_idx]
            desc = self._describe_replay_event(
                ev["event_type"], ev.get("event_packet_id", -1),
                ev.get("event_ack_id", -1), ev.get("event_time", 0))
            n_events = len(self._replay_events)
            self._replay_pos_label.configure(
                text=f"  {ev_idx}/{n_events - 1}  {desc}")

    def _log_replay_event(self, event: dict) -> None:
        """Log a replay event to the event log mirroring live-sim format."""
        etype = event["event_type"]
        pid = event.get("event_packet_id", -1)
        ack = event.get("event_ack_id", -1)
        t = event.get("event_time", 0)
        meta = event.get("event_meta", {})

        if etype == "PACKET_SENT":
            self._log("ok", f"Sent packet #{pid}     @ {t:.1f}ms")
        elif etype == "PACKET_RECEIVED":
            accepted = meta.get("accepted", True)
            if accepted:
                self._log(
                    "ok", f"Recv packet #{pid} → slot #{pid} @ {t:.1f}ms")
            else:
                exp = meta.get("expected", "?")
                self._log(
                    "warn", f"DISCARD #{pid} (out-of-order, expected #{exp}) @ {t:.1f}ms")
        elif etype == "PACKET_CORRUPTED":
            self._log(
                "err", f"Packet #{pid} CORRUPTED (target slot #{pid}) @ {t:.1f}ms")
        elif etype == "PACKET_LOST":
            self._log(
                "err", f"Packet #{pid} LOST     (target slot #{pid}) @ {t:.1f}ms")
        elif etype == "ACK_SENT":
            triggered_by_accept = meta.get("from_accept", True)
            if triggered_by_accept:
                self._log(
                    "ok", f"ACK #{ack} ← recv (cumulative 0..{ack}) @ {t:.1f}ms")
            else:
                self._log(
                    "info", f"ACK #{ack} ← recv (repeat, out-of-order) @ {t:.1f}ms")
        elif etype == "ACK_RECEIVED":
            if meta.get("is_duplicate"):
                self._log("info", f"ACK #{ack} recv (duplicate) @ {t:.1f}ms")
            else:
                self._log("ok", f"ACK #{ack} recv → window slides @ {t:.1f}ms")
        elif etype == "ACK_CORRUPTED":
            self._log("err", f"ACK #{ack} CORRUPTED  @ {t:.1f}ms")
        elif etype == "ACK_LOST":
            self._log("err", f"ACK #{ack} LOST       @ {t:.1f}ms")
        elif etype == "TIMEOUT":
            ws = meta.get("window_start", "?")
            we = meta.get("window_end", "?")
            n_val = meta.get("window_size", "?")
            self._log("warn", f"TIMEOUT #{pid} → RESEND WINDOW [{ws}..{we}] N={n_val} "
                      f"@ {t:.1f}ms")
        elif etype == "DONE":
            d = meta.get("delivered", "?")
            ts = meta.get("total_sent", "?")
            eff_val = meta.get("efficiency", 0)
            tp_val = meta.get("throughput", 0)
            self._log("info", "▼ SIMULATION COMPLETE ▼")
            self._log("info", f"COMPLETE — {d}/{meta.get('n', '?')} delivered "
                      f"({ts} sent incl. retransmissions), "
                      f"efficiency={eff_val:.1f}%, throughput={tp_val:.1f} kbps")
        else:
            self._log("info", f"{etype} @ {t:.1f}ms")

    @staticmethod
    def _describe_replay_event(etype: str, pid: int, ack: int, time: float) -> str:
        if etype == "PACKET_SENT":
            return f"Sent packet #{pid}     @ {time:.1f}ms"
        elif etype == "PACKET_RECEIVED":
            return f"Recv packet #{pid} → slot #{pid} @ {time:.1f}ms"
        elif etype == "PACKET_CORRUPTED":
            return f"Packet #{pid} CORRUPTED @ {time:.1f}ms"
        elif etype == "PACKET_LOST":
            return f"Packet #{pid} LOST       @ {time:.1f}ms"
        elif etype == "ACK_SENT":
            return f"ACK #{ack} ← recv @ {time:.1f}ms"
        elif etype == "ACK_RECEIVED":
            return f"ACK #{ack} recv → window slides @ {time:.1f}ms"
        elif etype == "ACK_CORRUPTED":
            return f"ACK #{ack} CORRUPTED  @ {time:.1f}ms"
        elif etype == "ACK_LOST":
            return f"ACK #{ack} LOST       @ {time:.1f}ms"
        elif etype == "TIMEOUT":
            return f"TIMEOUT on #{pid} → retransmit window @ {time:.1f}ms"
        elif etype == "DONE":
            return "▼ SIMULATION COMPLETE ▼"
        return f"{etype} @ {time:.1f}ms"
