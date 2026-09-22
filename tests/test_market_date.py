"""A-share market-date timezone contracts."""

from __future__ import annotations

from datetime import date, datetime, timezone

from chstockdata import a_stock


class _FrozenDateTime(datetime):
    current: datetime

    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return cls.current.replace(tzinfo=None)
        return cls.current.astimezone(tz)


def test_a_stock_today_uses_shanghai_date_at_utc_day_boundary(monkeypatch):
    # 16:30 UTC is already 00:30 on the next calendar day in Shanghai.
    _FrozenDateTime.current = datetime(2026, 9, 21, 16, 30, tzinfo=timezone.utc)
    monkeypatch.setattr(a_stock, "datetime", _FrozenDateTime)

    assert a_stock._today() == date(2026, 9, 22)
