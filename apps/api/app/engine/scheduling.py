"""Killzone + session scheduling.

Defines trading sessions (killzones) and checks whether current time
falls within an active session. Used to gate analysis runs and alerts.

Sessions (all UTC):
    Sydney:  21:00 – 06:00
    Tokyo:   00:00 – 09:00
    London:  07:00 – 16:00
    New York: 12:00 – 21:00
    London/NY overlap: 12:00 – 16:00 (highest liquidity)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone


@dataclass
class Session:
    name: str
    start: time  # UTC
    end: time    # UTC
    wraps_midnight: bool = False


SESSIONS = [
    Session("sydney", time(21, 0), time(6, 0), wraps_midnight=True),
    Session("tokyo", time(0, 0), time(9, 0)),
    Session("london", time(7, 0), time(16, 0)),
    Session("new_york", time(12, 0), time(21, 0)),
]

# High-liquidity overlap windows
OVERLAPS = [
    Session("london_ny_overlap", time(12, 0), time(16, 0)),
    Session("tokyo_london_overlap", time(7, 0), time(9, 0)),
]


def _in_session(t: time, s: Session) -> bool:
    if s.wraps_midnight:
        return t >= s.start or t < s.end
    return s.start <= t < s.end


def active_sessions(now: datetime | None = None) -> list[str]:
    """Return names of all active sessions at the given time."""
    if now is None:
        now = datetime.now(timezone.utc)
    t = now.time()
    active = [s.name for s in SESSIONS if _in_session(t, s)]
    active += [s.name for s in OVERLAPS if _in_session(t, s)]
    return active


def is_killzone(now: datetime | None = None) -> bool:
    """True if any session is active."""
    return len(active_sessions(now)) > 0


def next_session_open(now: datetime | None = None) -> tuple[str, float]:
    """Return (session_name, minutes_until_open) for the next session to open."""
    if now is None:
        now = datetime.now(timezone.utc)
    t = now.time()
    now_minutes = t.hour * 60 + t.minute

    best_name = ""
    best_delta = float("inf")

    for s in SESSIONS:
        start_minutes = s.start.hour * 60 + s.start.minute
        if _in_session(t, s):
            continue  # already open
        delta = (start_minutes - now_minutes) % 1440
        if delta < best_delta:
            best_delta = delta
            best_name = s.name

    return best_name, round(best_delta, 1)


def session_status(now: datetime | None = None) -> dict:
    """Full status snapshot for API/UI consumption."""
    if now is None:
        now = datetime.now(timezone.utc)
    active = active_sessions(now)
    next_name, next_mins = next_session_open(now)
    return {
        "utc_time": now.strftime("%H:%M"),
        "active_sessions": active,
        "is_killzone": len(active) > 0,
        "next_session": next_name,
        "next_session_in_minutes": next_mins,
        "sessions": [
            {"name": s.name, "start": s.start.strftime("%H:%M"), "end": s.end.strftime("%H:%M")}
            for s in SESSIONS
        ],
        "overlaps": [
            {"name": s.name, "start": s.start.strftime("%H:%M"), "end": s.end.strftime("%H:%M")}
            for s in OVERLAPS
        ],
    }
