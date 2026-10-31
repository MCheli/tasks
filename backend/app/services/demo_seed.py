"""Demo seed: Claudius Banks's task lists, rebuilt nightly for tasks-demo.markcheli.com.

One simulation, not random rows. Cycles are laid out backwards from the moment the seed runs
(Personal: about a week, planned on Sunday evenings; Professional: two-week sprints planned on
Monday mornings). Every task is a story: it is created in some cycle and then, cycle by cycle,
forwarded, checked off, completed or canceled at the transition, or left open, exactly as the
real app would have recorded it (see `cycle_service.transition_cycle`). Chores repeat every
cycle; seasonal and dated items (gutters, snow tires, open enrollment, RSU vests, taxes) follow
the calendar, so a reseed in any month looks current. Deterministic for a given moment.

Claudius Banks is made up (the same person as in the Tallied demo): 30, software engineer at
Microsoft, $145K plus RSUs vesting quarterly, a house in Springfield, MA bought in 2021, a 2019
RAV4 and a 2015 Civic, a Fidelity 401(k), retiring around 55, reads Tallied's Monday recap.

Run by the container entrypoint in demo mode:  python -m app.services.demo_seed --reset
"""

from __future__ import annotations

import argparse
import asyncio
import calendar
import logging
import random
import secrets
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.api_key import ApiKey
from app.models.cycle import Cycle
from app.models.task import DisplayIdSequence, Task
from app.models.user import User

logger = logging.getLogger("tasks.demo_seed")

PERSONA_NAME = "Claudius Banks"
PERSONAL_PAST_CYCLES = 10
SPRINTS_PAST = 5
SPRINT_EPOCH = datetime(2026, 1, 5, 14, 0, tzinfo=UTC)  # a sprint-planning Monday, 9am Eastern
MIN = timedelta(minutes=1)
HOUR = timedelta(hours=1)
DAY = timedelta(days=1)


# ---------------------------------------------------------------------------
# Time
# ---------------------------------------------------------------------------


def _eastern_offset(dt: datetime) -> timedelta:
    """Springfield, MA. Close enough for picking believable hours: EDT Mar 15-Nov 5."""
    edt = (dt.month, dt.day) >= (3, 15) and (dt.month, dt.day) < (11, 5)
    return timedelta(hours=-4 if edt else -5)


def _plausible(dt: datetime, category: str, rng: random.Random) -> datetime:
    """Move `dt` to an hour Claudius would actually be doing this, on (about) the same day."""
    off = _eastern_offset(dt)
    local = dt + off
    if category == "professional":
        while local.weekday() >= 5:
            local -= DAY
        hour = rng.choice([9, 10, 10, 11, 13, 14, 15, 16, 16, 17])
    elif local.weekday() < 5:
        hour = rng.choice([7, 18, 19, 19, 20, 20, 21, 21, 22])
    else:
        hour = rng.choice([9, 10, 10, 11, 13, 14, 15, 16, 17, 19])
    return local.replace(hour=hour, minute=rng.randrange(60), second=0, microsecond=0) - off


def _on(d: date, category: str, rng: random.Random) -> datetime:
    return _plausible(datetime(d.year, d.month, d.day, 12, tzinfo=UTC), category, rng)


@dataclass
class Span:
    """One cycle as the seed lays it out."""

    category: str
    start: datetime
    end: datetime | None  # None = the current cycle
    nominal: timedelta
    id: UUID = field(default_factory=uuid4)

    def at(self, frac: float) -> datetime:
        return self.start + (self.end - self.start if self.end else self.nominal) * frac


def personal_cycles(now: datetime, rng: random.Random) -> list[Span]:
    """Planned on Sunday evenings (Monday 00:30 UTC); the current one is 2-9 days old."""
    d = now - 2 * DAY
    start = (d - d.weekday() * DAY).replace(hour=0, minute=30, second=0, microsecond=0)
    if start > d:
        start -= 7 * DAY
    starts = [start]
    for k in range(1, PERSONAL_PAST_CYCLES + 1):
        jitter = rng.choice([0, 0, 0, 0, 0, 1.5, 19, -21, 23])  # a late or early planning night
        starts.append(start - 7 * k * DAY + jitter * HOUR)
    starts.reverse()
    return [
        Span("personal", s, starts[i + 1] if i + 1 < len(starts) else None, 7 * DAY)
        for i, s in enumerate(starts)
    ]


def sprints(now: datetime, rng: random.Random) -> list[Span]:
    """Two-week sprints planned Monday 9am Eastern; the current one is 3-17 days old."""
    d = now - 3 * DAY
    start = SPRINT_EPOCH + ((d - SPRINT_EPOCH).days // 14) * 14 * DAY
    if start > d:
        start -= 14 * DAY
    starts = [start]
    for k in range(1, SPRINTS_PAST + 1):
        starts.append(start - 14 * k * DAY + rng.choice([0, 0, 0, 24]) * HOUR)
    starts.reverse()
    return [
        Span("professional", s, starts[i + 1] if i + 1 < len(starts) else None, 14 * DAY)
        for i, s in enumerate(starts)
    ]


def _index_at(cycles: list[Span], dt: datetime) -> int:
    for i, c in enumerate(cycles):
        if c.start <= dt and (c.end is None or dt < c.end):
            return i
    return 0 if dt < cycles[0].start else len(cycles) - 1


# ---------------------------------------------------------------------------
# Stories
# ---------------------------------------------------------------------------


@dataclass
class Story:
    """A task lineage. `path` has one letter per cycle starting at cycle index `start`
    (0 = current, -1 = the previous cycle):

    F  forwarded at the transition (the next cycle has the next row)
    C  checked off during the cycle, at `done`
    T  marked complete at the transition
    X  canceled at the transition
    x  canceled during the cycle, at `done`
    O  still open (current cycle only)

    `created`/`done` are fractions of the first/last cycle, or absolute times. A C in the current
    cycle whose time hasn't come yet is still open: the simulation stops at `now`.
    """

    category: str
    title: str
    start: int
    path: str
    notes: str | None = None
    created: float | datetime = 0.0
    done: float | datetime = 0.6
    deleted: bool = False


def _dated(
    category: str,
    title: str,
    created: date,
    done: date | None,
    cycles: list[Span],
    now: datetime,
    rng: random.Random,
    notes: str | None = None,
) -> Story | None:
    """A story pinned to the calendar: created on one day, done on another (or still open)."""
    c_at = _on(created, category, rng)
    d_at = _on(done, category, rng) if done else None
    if c_at > now - HOUR:
        return None
    if d_at and d_at < cycles[0].start + DAY:
        return None  # resolved before Claudius started using the app
    c_at = max(c_at, cycles[0].start + 2 * HOUR)
    if d_at and d_at <= c_at:
        d_at = c_at + 3 * HOUR
    last = len(cycles) - 1
    i0 = _index_at(cycles, c_at)
    if d_at and d_at <= now - HOUR:
        path = "F" * (_index_at(cycles, d_at) - i0) + "C"
    else:
        path = "F" * (last - i0) + "O"
    return Story(category, title, i0 - last, path, notes, created=c_at, done=d_at or 0.6)


def _annual(month: int, day: int, now: datetime) -> list[date]:
    return [date(y, month, day) for y in (now.year - 1, now.year, now.year + 1)]


def _quarterly(months: tuple[int, ...], day: int, now: datetime) -> list[date]:
    return [date(y, m, day) for y in (now.year - 1, now.year, now.year + 1) for m in months]


def _month_starts(now: datetime) -> list[date]:
    out, y, m = [], now.year - 1, now.month
    for _ in range(14):
        out.append(date(y, m, 1))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _fmt(d: date) -> str:
    return f"{calendar.month_abbr[d.month]} {d.day}"


def personal_stories(now: datetime, cycles: list[Span], rng: random.Random) -> list[Story]:
    p = "personal"
    s: list[Story] = []
    last = len(cycles) - 1

    # Every week: chores that come back each cycle.
    for k in range(-last, 1):
        missed_gym = k in (-8, -5, -2)
        s.append(
            Story(p, "Gym 3× this week", k, "C" if not missed_gym or k == 0 else "X", done=0.86)
        )
        s.append(Story(p, "Groceries + meal prep", k, "C", done=0.8, created=0.0))
        s.append(
            Story(
                p,
                "Read Monday's Tallied recap",
                k,
                "C" if k != -6 else "X",
                done=0.1,
                notes=(
                    "Spending vs. last week, the plan's odds, anything that needs a look."
                    if k == 0
                    else None
                ),
            )
        )
    # Every other week from spring to fall.
    for k in range(-last, 1, 2):
        if 4 <= cycles[last + k].start.month <= 10:
            s.append(Story(p, "Mow the lawn", k, "C", done=0.8))
    # One duplicate entry he deleted right away (soft-deleted rows leave display-id gaps).
    s.append(Story(p, "Groceries + meal prep", -6, "O", created=0.01, deleted=True))

    # Things that don't depend on the season.
    s += [
        Story(p, "Hang the hallway shelf", -10, "C", created=0.0, done=0.75),
        Story(p, "Schedule an annual physical", -10, "FC", created=0.3, done=0.2),
        Story(p, "Replace the porch light", -9, "C", created=0.4, done=0.8),
        Story(p, "Cancel the streaming service I never watch", -8, "C", created=0.2, done=0.25),
        Story(p, "Pick up dry cleaning", -8, "C", created=0.5, done=0.7),
        Story(p, "Wash + vacuum the RAV4", -7, "C", created=0.0, done=0.85),
        Story(p, "Pay the water bill", -7, "C", created=0.4, done=0.5),
        Story(
            p,
            "Fix the squeaky stair",
            -10,
            "FFC",
            created=0.2,
            done=0.7,
            notes="Shims + finishing screws from the stair kit in the basement.",
        ),
        Story(
            p,
            "Renew passport",
            -9,
            "FFC",
            created=0.1,
            done=0.4,
            notes="Form DS-82 by mail. Photos at the pharmacy. Expires next spring.",
        ),
        Story(
            p,
            "Update emergency fund target in Tallied",
            -8,
            "C",
            created=0.3,
            done=0.5,
            notes="Six months of expenses, mortgage included.",
        ),
        Story(
            p,
            "Clean out the garage",
            -7,
            "FFX",
            created=0.0,
            notes="Too big for one weekend. Split it up instead.",
        ),
        Story(
            p,
            "Sign up for a pottery class",
            -6,
            "FFX",
            created=0.4,
            notes="Thursday-night session filled up. Maybe in the spring.",
        ),
        Story(p, "Back up phone photos", -5, "FFC", created=0.2, done=0.6),
        Story(
            p,
            "RAV4 oil change",
            -6,
            "C",
            created=0.1,
            done=0.75,
            notes="Due at 45,000 mi; it's at 44,600. Ask them to rotate the tires too.",
        ),
        Story(
            p,
            "Get a quote to bundle home + auto insurance",
            -5,
            "C",
            created=0.3,
            done=0.8,
            notes="Current renewal is up 9%. Compare at least two quotes.",
        ),
        Story(p, "Garage: donate the old bike and bins", -4, "C", created=0.0, done=0.85),
        Story(
            p,
            "Fix the leaky bathroom faucet",
            -4,
            "FFFFO",
            created=0.35,
            notes="Drips from the hot side. Probably the cartridge; check the brand under the "
            "handle before buying a replacement.",
        ),
        Story(p, "Order new running shoes", -3, "C", created=0.2, done=0.4),
        Story(p, "Call the dentist to book a cleaning", -3, "C", created=0.1, done=0.4),
        Story(
            p,
            "RSVP to Jordan & Alex's wedding",
            -3,
            "C",
            created=0.3,
            done=0.85,
            notes="Plus-one: yes. Meal: salmon. Hotel block closes two weeks before.",
        ),
        Story(p, "Return library books", -2, "C", created=0.0, done=0.7),
        Story(
            p,
            "Rebalance 401(k) back to 80/20",
            -2,
            "FFO",
            created=0.3,
            notes="Fidelity: drifted to about 86% stocks after the run-up. Do it inside the "
            "401(k) so there's no tax hit.",
        ),
        Story(p, "Buy a gift from Jordan & Alex's registry", -1, "FO", created=0.6),
        Story(p, "Haircut", -1, "C", created=0.0, done=0.75),
        Story(p, "Order contact lenses", -1, "C", created=0.2, done=0.3),
        Story(p, "Drop off the donation bags", -1, "C", created=0.0, done=0.85),
    ]
    dentist = (now + 2 * DAY).date()  # booked three cycles ago, coming up this week
    s.append(
        Story(
            p,
            f"Dentist cleaning, {_fmt(dentist)} 8:30am",
            0,
            "O",
            created=0.0,
            notes="Bring the new insurance card.",
        )
    )

    # The calendar: (created, done) by month/day; each year's instance appears when in range.
    def dated(title, created, done, notes=None):
        st = _dated(p, title, created, done, cycles, now, rng, notes)
        if st:
            s.append(st)

    for d in _annual(10, 15, now):
        dated(
            "Clean the gutters before winter",
            d,
            d + timedelta(days=36),
            "Ladder's in the garage. The downspout by the back door clogs first.",
        )
    for d in _annual(4, 5, now):
        dated("Clean the gutters (spring)", d, d + timedelta(days=21))
    for d in _annual(9, 22, now):
        dated("Book the furnace service", d, d + timedelta(days=6))
        dated(
            "Furnace tune-up visit: be home 8–noon",
            d + timedelta(days=7),
            d + timedelta(days=22),
            "Ask about the humidifier pad.",
        )
    for d in _annual(10, 10, now):
        dated(
            "Plant garlic + tulip bulbs for the spring garden",
            d,
            d + timedelta(days=8),
            "Raised bed by the fence. Mulch after the first frost.",
        )
    for d in _annual(3, 8, now):
        dated("Plan the spring garden beds", d, d + timedelta(days=14))
        dated("Start tomato + pepper seeds indoors", d + timedelta(days=14), d + timedelta(days=25))
        dated("Plant the spring garden", d + timedelta(days=62), d + timedelta(days=76))
    for d in _annual(10, 9, now):
        dated(
            "Civic: Massachusetts inspection sticker",
            d,
            d + timedelta(days=18),
            "Sticker expires at the end of October. Any inspection station works.",
        )
    for d in _annual(10, 27, now):
        dated(
            "Book the snow-tire swap for the RAV4",
            d,
            d + timedelta(days=7),
            "Tires are in the garage. The shop wants a week's notice in November.",
        )
        dated(
            "Snow tires on the RAV4 (drop off 8am)", d + timedelta(days=7), d + timedelta(days=24)
        )
    for d in _annual(4, 1, now):
        dated("Swap the RAV4 back to all-seasons", d, d + timedelta(days=17))
    for d in _annual(10, 26, now):
        dated(
            f"Open enrollment: pick {d.year + 1} benefits",
            d,
            d + timedelta(days=17),
            "Closes Nov 13. Compare the HSA plan vs. the PPO again; dental is unchanged.",
        )
    for d in _annual(11, 10, now):
        dated(
            f"Start a folder for {d.year} tax documents",
            d,
            d + timedelta(days=14),
            "W-2, 1099-B for the RSU sales, 1098 mortgage interest, 401(k) statement.",
        )
    for d in _annual(1, 18, now):
        dated("Gather tax documents (W-2, 1099-B, 1098)", d, d + timedelta(days=27))
        dated(f"File {d.year - 1} taxes", d + timedelta(days=42), d + timedelta(days=70))
    for d in _annual(8, 20, now):
        dated("Harvest + freeze the last tomatoes", d, d + timedelta(days=9))
    for d in _annual(9, 6, now):
        dated("Book a cabin for the Berkshires hiking weekend", d, d + timedelta(days=6))
        dated(
            "Hike Mount Greylock: layers + headlamp",
            d + timedelta(days=15),
            d + timedelta(days=21),
            "Bellows Pipe trail up, Cheshire Harbor down.",
        )
    for d in _annual(6, 7, now):
        dated("Plan a Berkshires hiking weekend", d, d + timedelta(days=12))
    for d in _annual(1, 10, now):
        dated("Plan a snowshoe weekend in the Berkshires", d, d + timedelta(days=20))
    for d in _annual(10, 12, now):
        dated("Book flights home for Thanksgiving", d, d + timedelta(days=5))
    for d in _annual(11, 24, now):
        dated("Holiday gift list", d, d + timedelta(days=24))
    for d in _annual(10, 29, now):
        dated("Smoke detector batteries (clocks fall back)", d, d + timedelta(days=5))
    for d in _annual(3, 6, now):
        dated("Smoke detector batteries (clocks spring forward)", d, d + timedelta(days=4))
    for due in _quarterly((2, 5, 8, 11), 1, now):
        quarter = {2: 3, 5: 4, 8: 1, 11: 2}[due.month]
        dated(
            f"Pay Q{quarter} property tax (due {_fmt(due)})",
            due - timedelta(days=6),
            due - timedelta(days=3),
        )
    for vest in _quarterly((2, 5, 8, 11), 15, now):
        dated(
            f"RSU vest {_fmt(vest)}: sell-to-cover, decide on the rest",
            vest - timedelta(days=16),
            vest + timedelta(days=2),
            "Quarterly vest. Check the withholding, then follow the sell-half plan in Tallied.",
        )
    for first in _month_starts(now):
        prev = first - timedelta(days=1)
        lag = 4 if first.month % 3 else 10  # quarter-end months take longer
        dated(
            f"Review {calendar.month_name[prev.month]} spending in Tallied",
            first,
            first + timedelta(days=lag),
        )
    return s


def professional_stories(now: datetime, cycles: list[Span], rng: random.Random) -> list[Story]:
    w = "professional"
    s: list[Story] = []
    last = len(cycles) - 1
    cur = cycles[-1]

    for k in range(-last, 1):
        s.append(Story(w, "Sprint planning: size the carry-over tickets", k, "C", done=0.01))
        s.append(Story(w, "Clear the code review queue", k, "T" if k == -3 else "C", done=0.55))
        s.append(Story(w, "Mentor Sam: weekly 1:1s", k, "C", done=0.75))
        s.append(Story(w, "Prep the sprint review demo", k, "C", done=0.88))

    on_call_prev = cycles[1].at(0.55)
    next_monday = (now + (7 - now.weekday()) * DAY).date()
    review_due = (cur.start + 24 * DAY).date()
    s += [
        Story(w, "Rotate the service's test certificates", -5, "FC", created=0.3, done=0.2),
        Story(w, "Onboarding prep for Sam's first week", -5, "C", created=0.1, done=0.4),
        Story(w, "Fix the broken staging deploy alert", -5, "C", created=0.5, done=0.6),
        Story(w, "Write up the sprint retro notes", -4, "C", created=0.0, done=0.05),
        Story(
            w,
            "Write on-call handoff notes",
            -4,
            "C",
            created=on_call_prev,
            done=0.62,
            notes="Two pages, one false alarm. Proposed raising the disk alert to 85%.",
        ),
        Story(
            w,
            "Fix flaky integration test (token refresh)",
            -4,
            "FX",
            created=0.4,
            notes="Identity team took it; it's in their backlog.",
        ),
        Story(
            w,
            "Investigate p95 latency regression in sync API",
            -3,
            "FC",
            created=0.2,
            done=0.3,
            notes="Started after the Tuesday deploy. It was the new JSON serializer "
            "allocating per field; fixed with a pooled buffer.",
        ),
        Story(w, "Update alert thresholds on the sync dashboard", -3, "C", created=0.5, done=0.7),
        Story(w, "Interview loop: backend candidate", -3, "C", created=0.1, done=0.3),
        Story(w, "Write interview feedback", -3, "C", created=0.3, done=0.32),
        Story(w, "Start a wins doc for the performance review", -3, "C", created=0.6, done=0.65),
        Story(
            w, "Review PR: telemetry batching in the upload client", -2, "C", created=0.2, done=0.25
        ),
        Story(w, "Mentor Sam: pair on first production PR", -2, "FC", created=0.1, done=0.4),
        Story(
            w,
            "Submit expense report: team offsite dinner",
            -2,
            "FFC",
            created=0.3,
            done=0.2,
            notes="Receipt photo is in the email from the restaurant.",
        ),
        Story(w, "Read the Q4 planning doc and comment", -1, "C", created=0.1, done=0.3),
        Story(
            w,
            "Write design doc: retry queue for the sync service",
            -1,
            "FO",
            created=0.45,
            notes="Due this sprint. Left: rollout plan, metrics, open questions. Review with "
            "the team on Thursday.",
        ),
        Story(
            w,
            "Update onboarding doc with Sam's feedback",
            -1,
            "FO",
            created=0.7,
            notes="Local setup section is out of date; add the VPN step.",
        ),
        Story(w, "Book the design review with the team", 0, "C", created=0.05, done=0.12),
        Story(w, "Mentor Sam: walk through the deploy pipeline", 0, "C", created=0.1, done=0.3),
        Story(
            w,
            f"On-call week starts {_fmt(next_monday)}: read the runbook changes",
            0,
            "O",
            created=0.2,
        ),
        Story(
            w,
            f"Performance review self-assessment (due {_fmt(review_due)})",
            0,
            "O",
            created=0.25,
            notes="Pull highlights from the wins doc: latency fix, design doc, " "mentoring Sam.",
        ),
    ]
    for first in _month_starts(now):
        prev = first - timedelta(days=1)
        st = _dated(
            w,
            f"Submit {calendar.month_name[prev.month]} expenses",
            first + DAY,
            first + timedelta(days=5 if first.month % 2 else 12),
            cycles,
            now,
            rng,
        )
        if st:
            s.append(st)
    return s


# ---------------------------------------------------------------------------
# Rows
# ---------------------------------------------------------------------------


def _rows(story: Story, cycles: list[Span], now: datetime, rng: random.Random) -> list[dict]:
    last = len(cycles) - 1
    i0 = last + story.start
    assert 0 <= i0 and i0 + len(story.path) - 1 <= last, story.title
    first = cycles[i0]
    if isinstance(story.created, datetime):
        created = story.created
    elif story.created == 0:
        created = first.start + rng.randrange(3, 40) * MIN  # written down while planning
    else:
        created = max(_plausible(first.at(story.created), story.category, rng), first.start + MIN)
    created = min(created, now - HOUR)

    rows = []
    for j, letter in enumerate(story.path):
        c = cycles[i0 + j]
        is_last = j == len(story.path) - 1
        assert letter in "FCTXxO", story.title
        assert letter not in "FTX" or c.end is not None, story.title
        assert letter != "F" or not is_last, story.title
        assert letter != "O" or c.end is None or story.deleted, story.title
        row_created = created if j == 0 else c.start
        row = {"cycle": c, "created_at": row_created, "status": "open", "updated_at": row_created}
        if letter == "T":
            row.update(status="completed", completed_at=c.end, updated_at=c.end)
        elif letter == "X":
            row.update(status="canceled", canceled_at=c.end, updated_at=c.end)
        elif letter in "Cx":
            if isinstance(story.done, datetime):
                t = story.done
            else:
                t = _plausible(c.at(story.done), story.category, rng)
            t = max(t, row_created + 20 * MIN)
            if c.end is not None:
                t = min(t, c.end - 5 * MIN)
            if c.end is not None or t <= now - 5 * MIN:  # in the current cycle, only the past
                key = "completed_at" if letter == "C" else "canceled_at"
                row.update(status="completed" if letter == "C" else "canceled", updated_at=t)
                row[key] = t
        rows.append(row)
    return rows


async def seed_demo(db: AsyncSession, now: datetime | None = None) -> dict[str, int]:
    """Create the persona and everything he has. Flushes; the caller commits."""
    now = now or datetime.now(UTC)
    rng = random.Random(1996)

    user = User(email=settings.DEMO_USER_EMAIL, display_name=PERSONA_NAME, created_at=now)
    db.add(user)
    await db.flush()

    lineages: list[tuple[Story, list[dict]]] = []
    for cycles, stories in (
        (c := personal_cycles(now, rng), personal_stories(now, c, rng)),
        (c := sprints(now, rng), professional_stories(now, c, rng)),
    ):
        for span in cycles:
            db.add(
                Cycle(
                    id=span.id,
                    user_id=user.id,
                    category=span.category,
                    started_at=span.start,
                    ended_at=span.end,
                    created_at=span.start,
                )
            )
        await db.flush()
        for prev, nxt in zip(cycles, cycles[1:], strict=False):
            (await db.get(Cycle, prev.id)).next_cycle_id = nxt.id
        lineages += [(st, _rows(st, cycles, now, rng)) for st in stories]

    # Display ids and positions follow creation order, as the app assigns them.
    lineages.sort(key=lambda sr: sr[1][0]["created_at"])
    tasks: list[list[Task]] = []
    for display_id, (story, rows) in enumerate(lineages, start=1):
        pid = uuid4()
        lineage = []
        for row in rows:
            lineage.append(
                Task(
                    id=uuid4(),
                    previous_task_id=lineage[-1].id if lineage else None,
                    persistent_task_id=pid,
                    display_id=display_id,
                    user_id=user.id,
                    cycle_id=row["cycle"].id,
                    title=story.title,
                    notes=story.notes,
                    status=row["status"],
                    position=display_id,
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    completed_at=row.get("completed_at"),
                    canceled_at=row.get("canceled_at"),
                    deleted_at=row["created_at"] + 2 * MIN if story.deleted else None,
                )
            )
        tasks.append(lineage)
    # Oldest first, so every previous_task_id already exists (and nothing is UPDATEd, which
    # would stamp updated_at with the real clock).
    db.add_all(sorted((t for lineage in tasks for t in lineage), key=lambda t: t.created_at))
    await db.flush()
    db.add(DisplayIdSequence(user_id=user.id, next_value=len(lineages) + 1))

    # Settings shows keys he made for his own scripts. The raw keys were never kept anywhere.
    for name, made, used, active in (
        ("raycast-extension", 41, 0.6, True),
        ("weekly-review-script", 19, 5.2, True),
        ("old-laptop", 66, 48.0, False),
    ):
        raw = f"{ApiKey.KEY_PREFIX}{secrets.token_urlsafe(32)}"
        db.add(
            ApiKey(
                user_id=user.id,
                name=name,
                key_prefix=raw[:12],
                key_hash=ApiKey.hash_key(raw),
                is_active=active,
                created_at=now - made * DAY,
                last_used_at=now - timedelta(days=used),
            )
        )
    await db.flush()
    return {"lineages": len(lineages), "rows": sum(len(t) for t in tasks)}


async def reset_and_seed() -> dict[str, int]:
    from app.db.session import AsyncSessionLocal
    from app.demo import DEMO_EMAIL_DOMAIN, check_demo_database

    if not settings.DEMO_MODE:
        raise SystemExit("Refusing to seed: TASKS_DEMO_MODE is not set.")
    async with AsyncSessionLocal() as db:
        await check_demo_database(db)  # never wipe a database with real users in it
        await db.execute(delete(User).where(User.email.endswith(DEMO_EMAIL_DOMAIN)))
        counts = await seed_demo(db)
        await db.commit()
        counts["users"] = await db.scalar(select(func.count(User.id)))
    return counts


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s :: %(message)s"
    )
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--reset",
        action="store_true",
        required=True,
        help="delete the persona and rebuild (the only mode)",
    )
    parser.parse_args()
    counts = asyncio.run(reset_and_seed())
    logger.info("Seeded %s: %s", PERSONA_NAME, counts)


if __name__ == "__main__":
    main()
