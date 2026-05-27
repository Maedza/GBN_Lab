"""
Go-Back-N ARQ Protocol — Simulation Engine.

Combines the channel model, discrete-event engine, and Go-Back-N
protocol logic into a single cohesive module for clarity.

Conceptually, Go-Back-N works as follows:

    SENDER                                     RECEIVER
    ┌─────────────────┐                        ┌──────────────┐
    │ Window N=4      │  ═══ PACKET 0 ═══►     │ expected: 0  │
    │ [0][1][2][3]    │  ═══ PACKET 1 ═══►     │              │
    │  ▲               │  ◄═══ ACK 0  ════      │              │
    │ base            │  ═══ PACKET 2 ═══►     │              │
    │                 │  (PACKET 3 LOST)        │              │
    │                 │  ... TIMEOUT ...        │              │
    │ [2][3][4][5]    │  ═══ PACKET 2 ═══►     │ discards 4,5 │
    │  ▲               │  ═══ PACKET 3 ═══►     │              │
    │ base            │  ═══ PACKET 4 ═══►     │              │
    └─────────────────┘                        └──────────────┘

Key rules:
  • Sender transmits up to N packets without waiting for ACKs.
  • Receiver ONLY accepts packets in order; out-of-order packets are discarded.
  • Cumulative ACK: ACK(N) acknowledges all packets up to and including N.
  • On timeout, sender retransmits ALL unacknowledged packets in the window.
"""

from __future__ import annotations

import heapq
import math
import queue
import random
import threading
import time as _time
from dataclasses import dataclass, field
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════════════
# Event Types & Data Classes
# ═══════════════════════════════════════════════════════════════════════════════

class EventType:
    PACKET_SENT = "PACKET_SENT"
    PACKET_RECEIVED = "PACKET_RECEIVED"
    PACKET_CORRUPTED = "PACKET_CORRUPTED"
    PACKET_LOST = "PACKET_LOST"
    ACK_SENT = "ACK_SENT"
    ACK_RECEIVED = "ACK_RECEIVED"
    ACK_CORRUPTED = "ACK_CORRUPTED"
    ACK_LOST = "ACK_LOST"
    TIMEOUT = "TIMEOUT"


@dataclass(order=True)
class SimEvent:
    """A discrete event in the simulation timeline, ordered by time."""
    time: float
    priority: int = 50
    type: str = EventType.PACKET_SENT
    packet_id: int = -1
    ack_id: int = -1
    meta: dict = field(default_factory=dict, compare=False)


# ═══════════════════════════════════════════════════════════════════════════════
# Channel Model
# ═══════════════════════════════════════════════════════════════════════════════

class Channel:
    """Simulates a noisy communication channel with BER and packet loss."""

    def __init__(self, ber: float = 0.0, packet_loss: float = 0.0,
                 propagation_delay_ms: float = 10.0, data_rate_kbps: float = 100.0):
        self.ber = max(0.0, min(1.0, ber))
        self.packet_loss = max(0.0, min(1.0, packet_loss))
        self.propagation_delay_ms = propagation_delay_ms
        self.data_rate_kbps = data_rate_kbps

        # Statistics
        self.packets_through = 0
        self.corrupted = 0
        self.lost = 0

    def transmit(self, size_bits: int) -> tuple[bool, bool, float]:
        """Simulate transmission through the channel.

        Returns:
            (corrupted: bool, lost: bool, tx_time_ms: float)
        """
        self.packets_through += 1

        # Packet loss check
        if random.random() < self.packet_loss:
            self.lost += 1
            tx_time = size_bits / max(self.data_rate_kbps, 0.001)
            return False, True, tx_time

        # Bit error check: P(at least one error) = 1 - (1 - BER)^n
        corrupted = False
        if self.ber > 0:
            success_prob = (1.0 - self.ber) ** size_bits
            if random.random() > success_prob:
                corrupted = True
                self.corrupted += 1

        tx_time = size_bits / max(self.data_rate_kbps, 0.001)
        return corrupted, False, tx_time

    def one_way_ms(self, size_bits: int = 0) -> float:
        return (size_bits / max(self.data_rate_kbps, 0.001)) + self.propagation_delay_ms

    def reset(self) -> None:
        self.packets_through = 0
        self.corrupted = 0
        self.lost = 0


# ═══════════════════════════════════════════════════════════════════════════════
# Go-Back-N Protocol State
# ═══════════════════════════════════════════════════════════════════════════════

class GBNState:
    """Snapshot of the Go-Back-N sender and receiver at a given moment."""
    def __init__(self):
        # Sender
        self.base: int = 0               # oldest unacknowledged sequence number
        self.next_seq: int = 0           # next sequence number to send
        self.sent: set = set()           # packet IDs sent but not yet ACKed
        self.timed_out: set = set()      # packet IDs that triggered timeout

        # Receiver
        self.expected: int = 0           # next expected in-order packet
        self.received: set = set()       # correctly received packet IDs
        self.corrupted: set = set()      # corrupted packet IDs

        # Flying visualisation hints
        self.flying_packets: list[dict] = []   # {pkt_id, dir, label}
        self.last_event: str = "Idle"

        # Resend visual — which window range is currently being retransmitted
        self.retransmitting_window: tuple | None = None
        self.retransmit_frame: int = 0

        # Landing tracker — per-packet receiver-slot mapping for GUI logging
        self.packet_landings: list[dict] = []  # {pkt, receiver_slot, time, result}

        # Duplicate-ACK suppression: once the receiver has sent a
        # cumulative ACK for a given sequence number, it skips
        # re-sending the same ACK on subsequent out-of-order arrivals.
        # Resets when a new in-order packet is accepted.
        self._last_dup_ack_sent: int | None = None


# ═══════════════════════════════════════════════════════════════════════════════
# Go-Back-N Simulation Engine
# ═══════════════════════════════════════════════════════════════════════════════

class GBNSimulation:
    """Complete Go-Back-N simulation: channel + protocol + event engine.

    Runs in a background thread; call poll() periodically from the GUI thread
    to receive events and state snapshots.

    Usage:
        sim = GBNSimulation(window_size=4, ber=0.0001, num_packets=40)
        sim.start()
        while sim.running:
            for msg in sim.poll():
                if msg["type"] == "event":
                    ...  # handle event
                elif msg["type"] == "done":
                    ...  # simulation complete
                elif msg["type"] == "tick":
                    ...  # state snapshot
        metrics = sim.metrics
    """

    def __init__(self, *, window_size: int = 4, ber: float = 0.0001,
                 packet_loss: float = 0.0, num_packets: int = 40,
                 timeout_ms: float = 300.0, packet_size_bits: int = 1000,
                 data_rate_kbps: float = 100.0, propagation_delay_ms: float = 10.0,
                 sim_speed: float = 1.0):
        # Parameters
        self.window_size = window_size
        self.num_packets = num_packets
        self.packet_size_bits = packet_size_bits
        self.timeout_ms = timeout_ms
        self.data_rate_kbps = data_rate_kbps
        self.propagation_delay_ms = propagation_delay_ms
        self.sim_speed = max(0.1, min(50.0, sim_speed))  # throttle simulation speed

        self.channel = Channel(ber=ber, packet_loss=packet_loss,
                               propagation_delay_ms=propagation_delay_ms,
                               data_rate_kbps=data_rate_kbps)

        # Protocol state
        self.state = GBNState()
        self.delivered = 0
        self.total_sent = 0
        self.retransmissions = 0
        self.acks_sent = 0
        self.timeouts = 0
        self.errors = 0
        self.start_time = 0.0
        self.end_time = 0.0
        self.total_delay = 0.0

        # Engine internals
        self._event_heap: list[SimEvent] = []
        self._msg_queue: queue.Queue = queue.Queue(maxsize=300)  # bounded to prevent RAM explosion
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._sim_time: float = 0.0
        self._running = False
        self._event_count: int = 0  # for throttling emits

        # Timer tracking — GBN uses ONE timer for the oldest unACKed packet
        self._timeout_pending: bool = False

    # ── Public API ───────────────────────────────────────────────────────────

    @property
    def running(self) -> bool:
        return self._running

    @property
    def metrics(self) -> dict:
        """Return final performance metrics (valid after completion)."""
        duration = self.end_time - self.start_time
        if duration <= 0:
            return {"throughput_bps": 0, "efficiency": 0, "retransmissions": 0,
                    "timeouts": 0, "errors": 0, "avg_delay_ms": 0,
                    "delivered": self.delivered, "total_sent": self.total_sent}

        bits_delivered = self.delivered * self.packet_size_bits
        throughput = bits_delivered / (duration / 1000.0)
        efficiency = self.delivered / max(self.total_sent, 1)
        avg_delay = self.total_delay / max(self.delivered, 1)

        return {
            "throughput_bps": throughput,
            "efficiency": efficiency,
            "retransmissions": self.retransmissions,
            "timeouts": self.timeouts,
            "errors": self.errors,
            "avg_delay_ms": avg_delay,
            "delivered": self.delivered,
            "total_sent": self.total_sent,
            "duration_ms": duration,
        }

    def start(self) -> None:
        """Launch the simulation in a background thread."""
        if self._running:
            return
        self._stop.clear()
        self._running = True
        self._sim_time = 0.0

        # Initialise the global send-slot counter so all send events are
        # strictly serialised (1 slot = 1 tx_time on the wire).
        self._next_send_slot = 1.0

        # Seed: send up to N initial packets
        initial_count = min(self.window_size, self.num_packets)
        for i in range(initial_count):
            self._push(self._make_send_event(i))
            self.state.sent.add(i)
        # CRITICAL: next_seq must reflect ALL scheduled packets immediately,
        # otherwise early ACKs will re-send packets still in the future heap
        self.state.next_seq = initial_count

        self._state_to_queue()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the simulation."""
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._running = False

    def poll(self, max_msgs: int = 15) -> list[dict]:
        """Drain up to max_msgs from the queue. Call from GUI thread periodically."""
        msgs: list[dict] = []
        for _ in range(max_msgs):
            try:
                msgs.append(self._msg_queue.get_nowait())
            except queue.Empty:
                break
        return msgs

    # ── Internal: Event Loop ─────────────────────────────────────────────────

    def _run(self) -> None:
        """Main event loop, runs in background thread with rate-limiting.

        Events are emitted one at a time to the GUI, with a sleep between
        each so the event log and animation are human-readable.
        """
        while not self._stop.is_set() and self._event_heap:
            # Completion check
            if self.delivered >= self.num_packets:
                self.end_time = self._sim_time
                # Drain remaining ACK events so the GUI doesn't show stale
                # "ACK in the air" after all packets are delivered.
                self._drain_ack_events()
                self._emit({"type": "done", "metrics": self.metrics})
                self._running = False
                return

            event = heapq.heappop(self._event_heap)
            self._sim_time = event.time
            self._event_count += 1

            # Dispatch
            new = self._step(event)
            for evt in new:
                if evt.time < self._sim_time:
                    evt.time = self._sim_time + 0.001
                heapq.heappush(self._event_heap, evt)

            self.state.last_event = self._describe(event)

            # Emit EVERY event so the log reads step by step
            self._emit({"type": "event", "event": event, "state_snapshot": self._make_snapshot()})

            # Pace: at sim_speed=1.0 → 80ms/event, at 0.2 → 400ms/event
            _time.sleep(0.08 / self.sim_speed)

        # Natural completion
        if self.delivered >= self.num_packets:
            self.end_time = self._sim_time
            self._emit({"type": "done", "metrics": self.metrics})
        self._running = False

    def _drain_ack_events(self) -> None:
        """Silently process all remaining ACK events in the heap.

        After all data packets are delivered, the receiver's final ACK
        may still be in the heap (ACK_SENT at receiver → ACK_RECEIVED at
        sender).  Without draining, the GUI shows a stale "ACK still
        flying" dot after the simulation says DONE.
        """
        ack_types = {EventType.ACK_SENT, EventType.ACK_RECEIVED,
                     EventType.ACK_LOST, EventType.ACK_CORRUPTED}
        drained = 0
        limit = len(self._event_heap)
        while drained < limit and self._event_heap:
            # Only drain ACK-type events; leave anything else untouched
            event = self._event_heap[0]
            if event.type not in ack_types:
                break
            heapq.heappop(self._event_heap)
            drained += 1
            self._sim_time = event.time
            new = self._step(event)
            for evt in new:
                if evt.time < self._sim_time:
                    evt.time = self._sim_time + 0.001
                heapq.heappush(self._event_heap, evt)

    def _step(self, event: SimEvent) -> list[SimEvent]:
        """Route an event to the appropriate handler."""
        et = event.type
        if et == EventType.PACKET_SENT:
            return self._on_packet_sent(event)
        elif et == EventType.PACKET_RECEIVED:
            return self._on_packet_received(event)
        elif et in (EventType.PACKET_CORRUPTED, EventType.PACKET_LOST):
            return self._on_packet_dropped(event)
        elif et == EventType.ACK_SENT:
            return self._on_ack_sent(event)
        elif et == EventType.ACK_RECEIVED:
            return self._on_ack_received(event)
        elif et in (EventType.ACK_CORRUPTED, EventType.ACK_LOST):
            return []  # sender will timeout
        elif et == EventType.TIMEOUT:
            return self._on_timeout(event)
        return []

    # ── Event Handlers ───────────────────────────────────────────────────────

    def _on_packet_sent(self, event: SimEvent) -> list[SimEvent]:
        out = []
        pid = event.packet_id

        if self.total_sent == 0:
            self.start_time = event.time
        self.total_sent += 1

        # Update flying state
        self.state.sent.add(pid)

        corrupted, lost, tx_time = self.channel.transmit(self.packet_size_bits)
        arrival = event.time + tx_time + self.channel.propagation_delay_ms

        if lost:
            self.errors += 1
            self.state.corrupted.add(pid)
            out.append(SimEvent(arrival, type=EventType.PACKET_LOST, packet_id=pid))
            self.state.flying_packets.append(
                {"pkt": pid, "dir": "send", "result": "lost"})
        elif corrupted:
            self.errors += 1
            self.state.corrupted.add(pid)
            out.append(SimEvent(arrival, type=EventType.PACKET_CORRUPTED, packet_id=pid))
            self.state.flying_packets.append(
                {"pkt": pid, "dir": "send", "result": "corrupt"})
        else:
            out.append(SimEvent(arrival, type=EventType.PACKET_RECEIVED, packet_id=pid))
            self.state.flying_packets.append(
                {"pkt": pid, "dir": "send", "result": "ok"})

        # GBN: only ONE timer tracks the oldest unACKed packet (base)
        if not self._timeout_pending and pid == self.state.base:
            self._timeout_pending = True
            out.append(SimEvent(event.time + self.timeout_ms,
                                type=EventType.TIMEOUT, packet_id=pid))

        # Calculate next_seq if needed
        self.state.next_seq = max(self.state.next_seq, pid + 1)

        return out

    def _on_packet_received(self, event: SimEvent) -> list[SimEvent]:
        out = []
        pid = event.packet_id
        s = self.state

        if pid == s.expected:
            # Accept in-order
            self.delivered += 1
            delay = event.time - max(self.start_time, 0)
            self.total_delay += delay
            s.received.add(pid)
            s.expected += 1
            s.corrupted.discard(pid)

            # Reset duplicate-ACK suppression — a new expected slot
            # means the next stuck-state gets its *one* signal again.
            s._last_dup_ack_sent = None

            # Tag event so GUI knows this was accepted
            event.meta["accepted"] = True

            # Log this landing for GUI verification
            s.packet_landings.append({
                "pkt": pid, "receiver_slot": pid, "time": round(event.time, 1),
                "result": "accepted", "expected_before": pid,
            })

            # Send cumulative ACK
            ack = s.expected - 1
            ack_time = event.time + self.channel.propagation_delay_ms
            out.append(SimEvent(ack_time, type=EventType.ACK_SENT,
                                ack_id=ack, packet_id=pid,
                                meta={"from_accept": True}))
            self.acks_sent += 1
            self.state.flying_packets.append(
                {"pkt": pid, "dir": "ack", "result": "ok"})
        else:
            # Out of order — discard, re-ACK last in-order (once only)
            event.meta["accepted"] = False
            event.meta["expected"] = s.expected

            # CRITICAL: when expected=0, nothing has been received yet.
            # There is no meaningful cumulative ACK to send — sending ACK #0
            # would falsely tell the sender "packet 0 was delivered", sliding
            # the window forward and permanently stranding the receiver.
            # Instead, silently discard; the sender will timeout on packet 0.
            if s.expected > 0:
                ack = s.expected - 1
                if ack != s._last_dup_ack_sent:
                    s._last_dup_ack_sent = ack
                    out.append(SimEvent(event.time + self.channel.propagation_delay_ms,
                                        type=EventType.ACK_SENT, ack_id=ack, packet_id=pid,
                                        meta={"from_accept": False}))
                    self.acks_sent += 1
                    self.state.flying_packets.append(
                        {"pkt": pid, "dir": "ack", "result": "dup"})

            # Log rejected landing
            s.packet_landings.append({
                "pkt": pid, "receiver_slot": pid, "time": round(event.time, 1),
                "result": "rejected", "expected": s.expected,
            })

        # Trim old records
        if len(s.flying_packets) > 20:
            s.flying_packets = s.flying_packets[-16:]
        if len(s.packet_landings) > 40:
            s.packet_landings = s.packet_landings[-30:]

        return out

    def _on_packet_dropped(self, event: SimEvent) -> list[SimEvent]:
        """Packet was corrupted or lost at the receiver.

        Send ONE duplicate cumulative ACK for the last in-order packet
        to signal the sender faster than waiting for timeout.  The
        duplicate-ACK suppression in _on_packet_received ensures this
        is not repeated for subsequent out-of-order arrivals.
        """
        out = []
        s = self.state
        if s.expected > 0 and s._last_dup_ack_sent != s.expected - 1:
            ack = s.expected - 1
            s._last_dup_ack_sent = ack
            out.append(SimEvent(event.time + self.channel.propagation_delay_ms,
                                type=EventType.ACK_SENT, ack_id=ack,
                                packet_id=event.packet_id,
                                meta={"from_accept": False}))
            self.acks_sent += 1
            self.state.flying_packets.append(
                {"pkt": event.packet_id, "dir": "ack", "result": "dup"})
        return out

    def _on_ack_sent(self, event: SimEvent) -> list[SimEvent]:
        """ACK sent from receiver — transmit back through channel."""
        out = []
        corrupted, lost, _ = self.channel.transmit(40)  # ACKs are ~40 bits
        arrival = event.time + self.channel.propagation_delay_ms

        if lost:
            self.errors += 1
            out.append(SimEvent(arrival, type=EventType.ACK_LOST, ack_id=event.ack_id))
        elif corrupted:
            self.errors += 1
            out.append(SimEvent(arrival, type=EventType.ACK_CORRUPTED, ack_id=event.ack_id))
        else:
            out.append(SimEvent(arrival, type=EventType.ACK_RECEIVED, ack_id=event.ack_id))
        return out

    def _on_ack_received(self, event: SimEvent) -> list[SimEvent]:
        """Sender receives a cumulative ACK — slide the window."""
        out = []
        ack = event.ack_id
        old_base = self.state.base

        if ack >= self.state.base:
            # Cumulative ACK: all packets up to ack are confirmed
            self.state.base = ack + 1
            self.state.next_seq = max(self.state.next_seq, self.state.base)

            # Clear timeout tracking — restart timer for new base if needed
            self._timeout_pending = False
            if self.state.base > old_base:
                # Remove stale timeout events from heap (window has advanced)
                self._event_heap = [e for e in self._event_heap
                                    if e.type != EventType.TIMEOUT]
                heapq.heapify(self._event_heap)

            # Clear confirmed from sent set
            self.state.sent = {p for p in self.state.sent if p > ack}
            self.state.timed_out = {t for t in self.state.timed_out if t > ack}

            # Clear retransmit highlight once the window has slid past it
            rw = self.state.retransmitting_window
            if rw and self.state.base > rw[1]:
                self.state.retransmitting_window = None

            # Send new packets within window (slot counter auto-staggers)
            while self.state.next_seq < self.state.base + self.window_size \
                  and self.state.next_seq < self.num_packets:
                out.append(self._make_send_event(self.state.next_seq))
                self.state.sent.add(self.state.next_seq)
                self.state.next_seq += 1

            # GBN: restart timer for new base if unACKed packets remain
            if self.state.base < self.state.next_seq and not self._timeout_pending:
                self._timeout_pending = True
                out.append(SimEvent(self._sim_time + self.timeout_ms,
                                    type=EventType.TIMEOUT,
                                    packet_id=self.state.base))
        else:
            # Duplicate ACK — ignored by Go-Back-N; mark for GUI display
            event.meta["is_duplicate"] = True

        return out

    def _on_timeout(self, event: SimEvent) -> list[SimEvent]:
        """Timeout — Go-Back-N retransmits the ENTIRE window from base.

        Real GBN uses a single timer; after firing, remove all stale
        timeout events from the heap so only one retransmission occurs.

        Also purges all stale packet-receive and ACK events from the
        pre-timeout transmission round.  Without this, old
        PACKET_RECEIVED / CORRUPTED / LOST events still in the heap
        spur the receiver into sending duplicate cumulative ACKs,
        creating an "ACK storm" that makes the simulation appear stuck
        and can even advance the delivered count on ghost packets.
        """
        out = []

        # Guard: ignore a stale timeout if base has already advanced past this packet
        if event.packet_id < self.state.base:
            return out

        self.timeouts += 1
        self._timeout_pending = False  # timer fired — will re-schedule on retransmit
        self.state.timed_out.add(event.packet_id)

        win_start = self.state.base
        win_end = min(self.state.next_seq - 1, self.num_packets - 1)

        # ── Purge ALL stale events tied to the window we are about to re-send ──
        # 1. Old TIMEOUT events           (one-timer GBN rule)
        # 2. Old PACKET_RECEIVED / CORRUPTED / LOST events for window packets
        #    (these would trigger spurious duplicate ACKs at the receiver)
        # 3. Old ACK_SENT / ACK_RECEIVED events whose ack_id is below
        #    receiver.expected — generated by out-of-order discards before
        #    the timeout; harmless duplicates, but they clutter the event log
        stale_packet_types = {
            EventType.PACKET_RECEIVED,
            EventType.PACKET_CORRUPTED,
            EventType.PACKET_LOST,
        }
        stale_ack_types = {EventType.ACK_SENT, EventType.ACK_RECEIVED}
        recv_expected = self.state.expected

        keep = []
        for e in self._event_heap:
            if e.type == EventType.TIMEOUT:
                continue
            if e.type in stale_packet_types and win_start <= e.packet_id <= win_end:
                continue
            if e.type in stale_ack_types and e.ack_id < recv_expected:
                continue
            keep.append(e)
        self._event_heap = keep
        heapq.heapify(self._event_heap)

        # Attach window range to the event so the GUI can display it
        event.meta = {
            "window_start": win_start,
            "window_end": win_end,
            "window_size": self.window_size,
        }

        # Mark the visual retransmission window for canvas highlighting
        self.state.retransmitting_window = (win_start, win_end)
        self.state.retransmit_frame += 1

        # Retransmit all unACKed from base to next_seq-1
        # 5 ms penalty for timeout + slot-counter for serialisation
        self._next_send_slot = max(self._next_send_slot, self._sim_time + 5.0)
        for pid in range(win_start, win_end + 1):
            if pid < self.num_packets:
                self.retransmissions += 1
                self.state.sent.add(pid)
                self.state.flying_packets.append(
                    {"pkt": pid, "dir": "resend", "result": "timeout"})
                out.append(self._make_send_event(pid))

        return out

    # ── Helpers ──────────────────────────────────────────────────────────────

    @property
    def _tx_time_ms(self) -> float:
        """Transmission time for one packet in milliseconds."""
        return self.packet_size_bits / self.data_rate_kbps

    def _make_send_event(self, pkt_id: int) -> SimEvent:
        """Create a PACKET_SENT event with a globally-serialised send time.

        Every send event consumes one tx_time slot.  The slot counter ensures
        packets are always transmitted in the order they are scheduled, no
        matter which code path creates them (initial burst, window slide,
        or timeout retransmit).
        """
        # Never schedule before "right now" + 1 ms processing floor
        floor = self._sim_time + 1.0
        if self._next_send_slot < floor:
            self._next_send_slot = floor
        t = self._next_send_slot
        self._next_send_slot += self._tx_time_ms
        return SimEvent(t, type=EventType.PACKET_SENT, packet_id=pkt_id)

    def _describe(self, event: SimEvent) -> str:
        et = event.type
        pid = event.packet_id
        if et == EventType.PACKET_SENT:
            return f"Sent packet #{pid}"
        elif et == EventType.PACKET_RECEIVED:
            return f"Received packet #{pid}"
        elif et == EventType.PACKET_CORRUPTED:
            return f"Packet #{pid} CORRUPTED"
        elif et == EventType.PACKET_LOST:
            return f"Packet #{pid} LOST"
        elif et == EventType.ACK_SENT:
            return f"ACK #{event.ack_id} sent"
        elif et == EventType.ACK_RECEIVED:
            if event.meta.get("is_duplicate"):
                return f"ACK #{event.ack_id} received (duplicate)"
            return f"ACK #{event.ack_id} received → window slide"
        elif et == EventType.ACK_CORRUPTED:
            return f"ACK #{event.ack_id} CORRUPTED"
        elif et == EventType.ACK_LOST:
            return f"ACK #{event.ack_id} LOST"
        elif et == EventType.TIMEOUT:
            return f"TIMEOUT on #{pid} → retransmit window"
        return f"{et}"

    def _make_snapshot(self) -> dict:
        s = self.state
        win_end = min(s.base + self.window_size, self.num_packets)
        rw = s.retransmitting_window
        return {
            "sim_time": self._sim_time,
            "sender": {
                "base": s.base,
                "next_seq": s.next_seq,
                "window_size": self.window_size,
                "window": list(range(s.base, win_end)),
                "sent": sorted(s.sent),
                "timed_out": sorted(s.timed_out),
                "retransmitting_window": list(rw) if rw else None,
                "retransmit_frame": s.retransmit_frame,
            },
            "receiver": {
                "expected": s.expected,
                "received": sorted(s.received),
                "corrupted": sorted(s.corrupted),
            },
            "num_packets": self.num_packets,
            "delivered": self.delivered,
            "last_event": s.last_event,
            "flying": list(s.flying_packets[-16:]),
            "landings": list(s.packet_landings[-10:]),
        }

    # ── Queue Helpers ────────────────────────────────────────────────────────

    def _push(self, event: SimEvent) -> None:
        if event.time < self._sim_time:
            event.time = self._sim_time + 0.001
        heapq.heappush(self._event_heap, event)

    def _emit(self, msg: dict) -> None:
        try:
            self._msg_queue.put(msg, timeout=0.5)
        except queue.Full:
            pass  # GUI can't keep up, drop this message

    def _state_to_queue(self) -> None:
        self._emit({"type": "tick", "state_snapshot": self._make_snapshot()})
