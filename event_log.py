"""Live event handling: log lines, flight tracking, and completion handling."""

import time as _time

from config import (
    COLOR_ERROR,
    COLOR_WARNING,
    COLOR_ACCENT,
    MAX_LOG_TEXT_LINES,
    STATUS_COMPLETE,
)
from simulation import EventType


class EventLogMixin:
    """Consumes simulation events and renders them to the event log."""

    def _on_event(self, event) -> None:
        pid = event.packet_id
        ack = event.ack_id

        if self._sim:
            self._update_progress(self._sim.delivered, self._sim.num_packets)

        if event.type == EventType.PACKET_SENT:
            self._log("ok", f"Sent packet #{pid}     @ {event.time:.1f}ms")
            self._track_flight(pid, "send", "ok")
        elif event.type == EventType.PACKET_RECEIVED:
            meta = getattr(event, "meta", {}) or {}
            accepted = meta.get("accepted", True)
            if accepted:
                self._log(
                    "ok", f"Recv packet #{pid} → slot #{pid} @ {event.time:.1f}ms")
            else:
                exp = meta.get("expected", "?")
                self._log(
                    "warn", f"DISCARD #{pid} (out-of-order, expected #{exp}) @ {event.time:.1f}ms")
            self._active_flights.pop(pid, None)
        elif event.type == EventType.PACKET_CORRUPTED:
            self._log(
                "err", f"Packet #{pid} CORRUPTED (target slot #{pid}) @ {event.time:.1f}ms")
            if pid in self._active_flights:
                self._active_flights[pid]["result"] = "corrupt"
                self._active_flights[pid]["failed_at"] = self._anim_frame
        elif event.type == EventType.PACKET_LOST:
            self._log(
                "err", f"Packet #{pid} LOST     (target slot #{pid}) @ {event.time:.1f}ms")
            if pid in self._active_flights:
                self._active_flights[pid]["result"] = "lost"
                self._active_flights[pid]["failed_at"] = self._anim_frame
        elif event.type == EventType.ACK_SENT:
            meta = getattr(event, "meta", {}) or {}
            triggered_by_accept = meta.get("from_accept", True)
            if triggered_by_accept:
                self._log(
                    "ok", f"ACK #{ack} ← recv (cumulative 0..{ack}) @ {event.time:.1f}ms")
            else:
                sn = self._last_snapshot
                exp = sn.get("receiver", {}).get("expected", "?")
                self._log(
                    "info", f"ACK #{ack} ← recv (repeat 0..{ack}, still waiting #{exp}) @ {event.time:.1f}ms")
            self._track_flight(-ack - 1, "ack", "ok")
        elif event.type == EventType.ACK_RECEIVED:
            meta = getattr(event, "meta", {}) or {}
            sn = self._last_snapshot
            new_base = sn.get("sender", {}).get("base", "?")
            if meta.get("is_duplicate"):
                self._log(
                    "info", f"ACK #{ack} recv (dup — base already {new_base} > {ack}) @ {event.time:.1f}ms")
            else:
                self._log(
                    "ok", f"ACK #{ack} recv → window slides to base={new_base} @ {event.time:.1f}ms")
                self._slide_delay = 2
            ack_fid = -ack - 1
            if ack_fid in self._active_flights:
                self._active_flights[ack_fid]["start_frame"] = \
                    self._anim_frame - self._FLIGHT_FRAMES
                self._active_flights[ack_fid]["landing_frames"] = 2
        elif event.type == EventType.ACK_CORRUPTED:
            self._log("err", f"ACK #{ack} CORRUPTED  @ {event.time:.1f}ms")
            ack_id = -ack - 1
            if ack_id in self._active_flights:
                self._active_flights[ack_id]["result"] = "corrupt"
                self._active_flights[ack_id]["failed_at"] = self._anim_frame
        elif event.type == EventType.ACK_LOST:
            self._log("err", f"ACK #{ack} LOST       @ {event.time:.1f}ms")
            ack_id = -ack - 1
            if ack_id in self._active_flights:
                self._active_flights[ack_id]["result"] = "lost"
                self._active_flights[ack_id]["failed_at"] = self._anim_frame
        elif event.type == EventType.TIMEOUT:
            meta = getattr(event, "meta", {}) or {}
            ws = meta.get("window_start", "?")
            we = meta.get("window_end", "?")
            n = meta.get("window_size", "?")
            self._log("warn", f"TIMEOUT #{pid} → RESEND WINDOW [{ws}..{we}] N={n} "
                      f"@ {event.time:.1f}ms")
            self._active_flights.pop(pid, None)

    def _track_flight(self, pkt_id: int, direction: str, result: str) -> None:
        self._active_flights[pkt_id] = {
            "start_frame": self._anim_frame,
            "direction": direction,
            "result": result,
        }

    def _on_done(self, metrics: dict) -> None:
        self._completed = True
        self._stop_polling()
        self._stop_animation()
        self._replay_capturing = False
        self._update_progress(metrics.get("delivered", 0),
                              metrics.get("delivered", 0))

        self._active_flights.clear()

        ch_lost = ch_corrupt = 0
        if self._sim:
            ch_lost = self._sim.channel.lost
            ch_corrupt = self._sim.channel.corrupted
            self._sim.stop()
            self._sim = None

        self._set_status(STATUS_COMPLETE)
        self._start_btn.configure(text="Start Simulation", fg_color="#166534",
                                  state="normal")

        eff = metrics.get("efficiency", 0) * 100
        tp = metrics.get("throughput_bps", 0) / 1000
        self._cards["throughput"].set(f"{tp:.1f}")
        self._cards["efficiency"].set(f"{eff:.1f}")
        self._cards["retransmissions"].set(
            str(metrics.get("retransmissions", 0)))
        self._cards["timeouts"].set(str(metrics.get("timeouts", 0)))
        self._cards["delay"].set(f"{metrics.get('avg_delay_ms', 0):.1f}")

        self._chan_label.configure(
            text=f"Lost: {ch_lost}  Corrupted: {ch_corrupt}")

        n = metrics.get("delivered", 0)
        if n == 0:
            n = self._last_snapshot.get("num_packets", 0)
        self._last_snapshot = {
            "num_packets": n,
            "delivered": n,
            "sender": {
                "base": n,
                "next_seq": n,
                "window_size": self._last_snapshot.get("sender", {}).get("window_size", 4),
                "window": [],
                "sent": [],
                "timed_out": [],
                "retransmitting_window": None,
                "retransmit_frame": 0,
            },
            "receiver": {
                "expected": n,
                "received": list(range(n)),
                "corrupted": [],
            },
        }

        if self._replay_frames:
            base = self._replay_frames[-1]["anim_frame"]
            for i in range(1, 6):
                self._replay_frames.append({
                    "anim_frame": base + i,
                    "snapshot": dict(self._last_snapshot),
                    "flights": {},
                })
            done_anim = self._replay_frames[-1]["anim_frame"]
        else:
            done_anim = self._anim_frame

        last_time = metrics.get("duration_ms", 0)
        self._replay_events.append({
            "event_type": "DONE",
            "event_time": last_time,
            "event_packet_id": -1,
            "event_ack_id": -1,
            "event_meta": {
                "delivered": metrics.get("delivered", 0),
                "total_sent": metrics.get("total_sent", 0),
                "efficiency": eff,
                "throughput": tp,
                "retransmissions": metrics.get("retransmissions", 0),
                "timeouts": metrics.get("timeouts", 0),
                "avg_delay_ms": metrics.get("avg_delay_ms", 0),
                "n": n,
            },
            "anim_frame": done_anim,
        })

        self._redraw_canvas()

        self._log("info", f"COMPLETE — {metrics.get('delivered', 0)}/{n} delivered "
                  f"({metrics.get('total_sent', 0)} sent incl. retransmissions), "
                  f"efficiency={eff:.1f}%, throughput={tp:.1f} kbps")

        self._log(
            "info", "Replay mode active — drag the seek bar or use ▶/◀ to step through events")
        self._show_replay_controls()

    def _log(self, tag: str, text: str) -> None:
        self._log_text.configure(state="normal")
        ts = _time.strftime("%H:%M:%S")
        self._log_text.insert("end", f"[{ts}] ", "ts")
        self._log_text.insert("end", text + "\n", tag)
        self._log_text.see("end")
        line_count = int(self._log_text.index("end-1c").split(".")[0])
        if line_count > MAX_LOG_TEXT_LINES:
            excess = line_count - MAX_LOG_TEXT_LINES
            self._log_text.delete("1.0", f"{excess + 1}.0")
        self._log_text.configure(state="disabled")
