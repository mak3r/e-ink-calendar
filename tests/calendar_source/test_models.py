"""Regression guard for #140: ``Event.occurs_on`` boundary behavior.

Google's all-day ``end.date`` is exclusive, but timed events' ``end`` is a
real instant. ``occurs_on`` is the single source of truth day_view, week_view,
and month_view all delegate to for "does this event show on this day" — these
tests assert its boundary directly so a regression can't slip back in through
any one of the three render call sites.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from eink_calendar.calendar_source.models import Event


def _all_day_event(start: date, end: date) -> Event:
    return Event(
        id="a",
        summary="All-day reminder",
        start=datetime(start.year, start.month, start.day, tzinfo=timezone.utc),
        end=datetime(end.year, end.month, end.day, tzinfo=timezone.utc),
        all_day=True,
        calendar_id="primary",
        color="blue",
    )


def _timed_event(start: datetime, end: datetime) -> Event:
    return Event(
        id="b",
        summary="Timed meeting",
        start=start,
        end=end,
        all_day=False,
        calendar_id="primary",
        color="red",
    )


def test_single_day_all_day_event_occurs_on_its_own_day():
    event = _all_day_event(date(2026, 9, 10), date(2026, 9, 11))
    assert event.occurs_on(date(2026, 9, 10))


def test_single_day_all_day_event_does_not_occur_the_day_after():
    event = _all_day_event(date(2026, 9, 10), date(2026, 9, 11))
    assert not event.occurs_on(date(2026, 9, 11))


def test_multi_day_all_day_event_occurs_across_its_exclusive_range():
    event = _all_day_event(date(2026, 9, 10), date(2026, 9, 13))
    assert not event.occurs_on(date(2026, 9, 9))
    assert event.occurs_on(date(2026, 9, 10))
    assert event.occurs_on(date(2026, 9, 11))
    assert event.occurs_on(date(2026, 9, 12))
    assert not event.occurs_on(date(2026, 9, 13))


def test_timed_event_keeps_inclusive_end_day_behavior():
    start = datetime(2026, 9, 10, 23, 0, tzinfo=timezone.utc)
    end = start + timedelta(hours=1, minutes=30)  # crosses into 2026-09-11
    event = _timed_event(start, end)
    assert event.occurs_on(date(2026, 9, 10))
    assert event.occurs_on(date(2026, 9, 11))
    assert not event.occurs_on(date(2026, 9, 12))
