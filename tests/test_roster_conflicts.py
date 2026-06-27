from datetime import date, time

from models import Shift


def test_shift_conflict_is_detected_for_overlapping_time_window_on_same_day():
    existing = Shift(
        id=1,
        site_id=1,
        guard_id=7,
        shift_date=date(2026, 6, 27),
        start_time=time(9, 0),
        end_time=time(17, 0),
    )
    candidate = Shift(
        id=2,
        site_id=2,
        guard_id=7,
        shift_date=date(2026, 6, 27),
        start_time=time(14, 0),
        end_time=time(18, 0),
    )

    assert existing.has_conflict_with(candidate)


def test_shift_conflict_is_not_detected_for_non_overlapping_time_window():
    existing = Shift(
        id=1,
        site_id=1,
        guard_id=7,
        shift_date=date(2026, 6, 27),
        start_time=time(9, 0),
        end_time=time(17, 0),
    )
    candidate = Shift(
        id=2,
        site_id=2,
        guard_id=7,
        shift_date=date(2026, 6, 27),
        start_time=time(17, 0),
        end_time=time(18, 0),
    )

    assert not existing.has_conflict_with(candidate)
