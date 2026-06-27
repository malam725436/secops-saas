from datetime import date

from blueprints.payroll import _calculate_shift_pay
from models import Shift


def test_overtime_hours_are_paid_at_time_and_a_half():
    shift = Shift(shift_date=date(2026, 6, 1), total_hours=45)

    _, amount, multiplier, premium_reason = _calculate_shift_pay(shift, 15.0, weekly_hours_before_shift=0.0)

    assert amount == 712.5
    assert multiplier == 1.5
    assert premium_reason == "overtime"


def test_holiday_shift_uses_standard_premium_rate():
    shift = Shift(shift_date=date(2026, 12, 25), total_hours=8)

    _, amount, multiplier, premium_reason = _calculate_shift_pay(shift, 15.0, weekly_hours_before_shift=0.0)

    assert amount == 150.0
    assert multiplier == 1.25
    assert premium_reason == "holiday"
