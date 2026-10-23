"""Annual PIT Stock universe schedule tests (Task 2 scope, M1-L04).

At each year-end cutoff the schedule may only use facts knowable at that
cutoff: listing age, ST/identity, tradability, and the trailing-window
median amount. Ranking is deterministic (``-median_amount, InstrumentId``),
the real policy takes the top 50 and fails closed below 20 eligible names,
and each cohort is frozen for the following calendar year. Future records
must never change a prior-year cohort, and the schedule must not retain any
caller-owned mutable collection.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from systematic_investing.domain.identifiers import InstrumentId
from systematic_investing.domain.market import TradabilityStatusKind
from systematic_investing.research.universe import (
    AmbiguousFormationError,
    AnnualCohortFailedError,
    AnnualUniversePolicy,
    AnnualUniverseSchedule,
    InvalidAnnualPolicyError,
    InvalidFormationFactError,
    NoCohortFormedError,
    StockFormationFact,
    StockIdentityStatus,
    TrailingAmount,
    form_annual_schedule,
)

YE_2020 = date(2020, 12, 31)
YE_2021 = date(2021, 12, 31)
JUNE_2021 = date(2021, 6, 1)
JUNE_2022 = date(2022, 6, 1)

# Small explicit test policy exercising the same rules as the real one.
SMALL_POLICY = AnnualUniversePolicy(
    minimum_listing_sessions=10,
    trailing_amount_sessions=4,
    minimum_cohort_size=2,
    maximum_cohort_size=3,
)


def _instrument(symbol: str) -> InstrumentId:
    """Explicit typed instrument identifier; never guessed from strings."""
    return InstrumentId.parse(symbol)


def _trailing(amount: str, count: int, *, end: date) -> tuple:
    """``count`` weekday-dated amounts ending at ``end``."""
    session_dates = []
    cursor = end
    while len(session_dates) < count:
        if cursor.weekday() < 5:
            session_dates.append(cursor)
        cursor = cursor - timedelta(days=1)
    session_dates.reverse()
    return tuple(
        TrailingAmount(session_date, Decimal(amount))
        for session_date in session_dates
    )


def _fact(
    instrument_id: InstrumentId,
    formation_session: date,
    *,
    listed: int = 300,
    identity: StockIdentityStatus = StockIdentityStatus.NORMAL,
    tradability: TradabilityStatusKind = TradabilityStatusKind.TRADABLE,
    median: str = "4000000",
    window: int | None = None,
    amounts: tuple | None = None,
) -> StockFormationFact:
    return StockFormationFact(
        instrument_id=instrument_id,
        formation_session=formation_session,
        listed_sessions=listed,
        identity_status=identity,
        tradability=tradability,
        trailing_amounts=amounts
        if amounts is not None
        else _trailing(median, window if window is not None else 4, end=formation_session),
    )


def _base_records(formation_session: date) -> list[StockFormationFact]:
    return [
        _fact(_instrument("XSHG:600001"), formation_session, median="5000000"),
        _fact(_instrument("XSHG:600002"), formation_session, median="4500000"),
        _fact(_instrument("XSHG:600003"), formation_session, median="4000000"),
        _fact(_instrument("XSHG:600004"), formation_session, median="4000000"),
    ]


def test_standard_policy_uses_real_m1_thresholds() -> None:
    policy = AnnualUniversePolicy.standard()

    assert policy.minimum_listing_sessions == 250
    assert policy.trailing_amount_sessions == 60
    assert policy.minimum_cohort_size == 20
    assert policy.maximum_cohort_size == 50


def test_future_records_cannot_change_prior_year_cohort() -> None:
    records_through_2020 = _base_records(YE_2020)
    records_from_2021 = _base_records(YE_2021)
    NEW_STOCK = _instrument("XSHG:600099")
    records_from_2021.append(
        _fact(NEW_STOCK, YE_2021, median="6000000")
    )

    schedule_a = form_annual_schedule(records_through_2020, SMALL_POLICY)
    schedule_b = form_annual_schedule(
        records_through_2020 + records_from_2021, SMALL_POLICY
    )

    assert schedule_a.view_for(JUNE_2021) == schedule_b.view_for(JUNE_2021)
    assert schedule_a.view_for(JUNE_2021).instrument_ids == (
        _instrument("XSHG:600001"),
        _instrument("XSHG:600002"),
        _instrument("XSHG:600003"),
    )


def test_newly_eligible_stock_can_enter_next_year() -> None:
    NEW_STOCK = _instrument("XSHG:600099")
    records_through_2020 = _base_records(YE_2020)
    # The new stock only becomes eligible at the 2021 formation.
    records_through_2021 = [
        *records_through_2020,
        _fact(NEW_STOCK, YE_2021, median="6000000"),
        *_base_records(YE_2021),
    ]

    schedule = form_annual_schedule(records_through_2021, SMALL_POLICY)

    assert NEW_STOCK not in schedule.view_for(JUNE_2021).instrument_ids
    assert NEW_STOCK in schedule.view_for(JUNE_2022).instrument_ids


def test_cohort_is_frozen_for_the_whole_calendar_year() -> None:
    schedule = form_annual_schedule(_base_records(YE_2020), SMALL_POLICY)

    first = schedule.view_for(date(2021, 1, 4))
    last = schedule.view_for(date(2021, 12, 30))
    assert first == last


def test_ranking_uses_median_desc_with_instrument_id_tie_breaker() -> None:
    # 600003 and 600004 share the same median; the lower InstrumentId wins
    # the last slot under the small-policy cap of 3.
    records = [
        _fact(_instrument("XSHG:600001"), YE_2020, median="5000000"),
        _fact(_instrument("XSHG:600002"), YE_2020, median="4500000"),
        _fact(_instrument("XSHG:600004"), YE_2020, median="4000000"),
        _fact(_instrument("XSHG:600003"), YE_2020, median="4000000"),
    ]

    schedule = form_annual_schedule(records, SMALL_POLICY)

    assert schedule.view_for(JUNE_2021).instrument_ids == (
        _instrument("XSHG:600001"),
        _instrument("XSHG:600002"),
        _instrument("XSHG:600003"),
    )


def test_ranked_median_is_over_the_trailing_window() -> None:
    # A cohort view is a set in canonical InstrumentId order, so ranking is
    # only observable at the truncation boundary. With a cap of 3 the five
    # candidates below produce a *different top-3 membership* under every
    # wrong statistic, and the asserted membership is reachable only through
    # the true window median (even window: average of the two middle
    # values):
    #   600001 (1M, 4.5M, 5.5M, 5.5M): med 5.0M, mean 4.125M, max 5.5M, min 1M
    #   600002 flat 4.5M            : every statistic 4.5M
    #   600003 (4M, 4M, 4M, 6M)     : med 4.0M, mean 4.5M,  max 6.0M
    #   600004 (2M, 4M, 10M, 20M)   : med 7.0M, mean 9.0M,  max 20M, min 2M
    #   600005 (6M, 6M, 6M, 100M)   : med 6.0M, mean 29.5M, max 100M, min 6M
    # median -> {1, 4, 5}; mean -> {2, 4, 5}; max -> {3, 4, 5};
    # min -> {2, 3, 5}; last -> {1, 3, 5} - all distinct memberships.
    spikes = {
        _instrument("XSHG:600001"): (
            TrailingAmount(date(2020, 12, 28), Decimal("1000000")),
            TrailingAmount(date(2020, 12, 29), Decimal("4500000")),
            TrailingAmount(date(2020, 12, 30), Decimal("5500000")),
            TrailingAmount(YE_2020, Decimal("5500000")),
        ),
        _instrument("XSHG:600003"): (
            TrailingAmount(date(2020, 12, 28), Decimal("4000000")),
            TrailingAmount(date(2020, 12, 29), Decimal("4000000")),
            TrailingAmount(date(2020, 12, 30), Decimal("4000000")),
            TrailingAmount(YE_2020, Decimal("6000000")),
        ),
        _instrument("XSHG:600004"): (
            TrailingAmount(date(2020, 12, 28), Decimal("2000000")),
            TrailingAmount(date(2020, 12, 29), Decimal("4000000")),
            TrailingAmount(date(2020, 12, 30), Decimal("10000000")),
            TrailingAmount(YE_2020, Decimal("20000000")),
        ),
        _instrument("XSHG:600005"): (
            TrailingAmount(date(2020, 12, 28), Decimal("6000000")),
            TrailingAmount(date(2020, 12, 29), Decimal("6000000")),
            TrailingAmount(date(2020, 12, 30), Decimal("6000000")),
            TrailingAmount(YE_2020, Decimal("100000000")),
        ),
    }
    records = [
        _fact(_instrument("XSHG:600001"), YE_2020, amounts=spikes[_instrument("XSHG:600001")]),
        _fact(_instrument("XSHG:600002"), YE_2020, median="4500000"),
        _fact(_instrument("XSHG:600003"), YE_2020, amounts=spikes[_instrument("XSHG:600003")]),
        _fact(_instrument("XSHG:600004"), YE_2020, amounts=spikes[_instrument("XSHG:600004")]),
        _fact(_instrument("XSHG:600005"), YE_2020, amounts=spikes[_instrument("XSHG:600005")]),
    ]
    policy = AnnualUniversePolicy(
        minimum_listing_sessions=10,
        trailing_amount_sessions=4,
        minimum_cohort_size=1,
        maximum_cohort_size=3,
    )

    schedule = form_annual_schedule(records, policy)

    assert schedule.view_for(JUNE_2021).instrument_ids == (
        _instrument("XSHG:600001"),
        _instrument("XSHG:600004"),
        _instrument("XSHG:600005"),
    )


def test_input_order_does_not_change_schedule() -> None:
    records = _base_records(YE_2020) + _base_records(YE_2021)

    ordered = form_annual_schedule(records, SMALL_POLICY)
    shuffled = form_annual_schedule(list(reversed(records)), SMALL_POLICY)

    assert ordered == shuffled


def test_schedule_does_not_retain_caller_collections() -> None:
    records = _base_records(YE_2020)
    amounts = list(_trailing("5000000", 4, end=YE_2020))

    schedule = form_annual_schedule(records, SMALL_POLICY)
    view = schedule.view_for(JUNE_2021)

    records.clear()
    records.append(_fact(_instrument("XSHG:600099"), YE_2020, median="9999999"))
    amounts.append(TrailingAmount(date(2020, 12, 30), Decimal("7777777")))

    assert schedule.view_for(JUNE_2021) == view
    assert view.instrument_ids == (
        _instrument("XSHG:600001"),
        _instrument("XSHG:600002"),
        _instrument("XSHG:600003"),
    )


def test_identity_and_tradability_conditions_are_enforced() -> None:
    records = _base_records(YE_2020)
    records.extend(
        [
            _fact(
                _instrument("XSHG:600101"),
                YE_2020,
                median="9000000",
                identity=StockIdentityStatus.ST,
            ),
            _fact(
                _instrument("XSHG:600102"),
                YE_2020,
                median="9000000",
                identity=StockIdentityStatus.DELISTING_PROCESS,
            ),
            _fact(
                _instrument("XSHG:600103"),
                YE_2020,
                median="9000000",
                tradability=TradabilityStatusKind.SUSPENDED,
            ),
            _fact(
                _instrument("XSHG:600104"),
                YE_2020,
                median="9000000",
                tradability=TradabilityStatusKind.UNKNOWN,
            ),
            _fact(_instrument("XSHG:600105"), YE_2020, median="9000000", listed=9),
        ]
    )

    schedule = form_annual_schedule(records, SMALL_POLICY)

    view = schedule.view_for(JUNE_2021)
    for excluded in (
        "XSHG:600101",
        "XSHG:600102",
        "XSHG:600103",
        "XSHG:600104",
        "XSHG:600105",
    ):
        assert _instrument(excluded) not in view.instrument_ids


def test_incomplete_trailing_window_is_not_eligible() -> None:
    NEW_STOCK = _instrument("XSHG:600099")
    records = _base_records(YE_2020)
    records.append(
        _fact(
            NEW_STOCK,
            YE_2020,
            amounts=_trailing("9000000", 3, end=YE_2020),
        )
    )

    schedule = form_annual_schedule(records, SMALL_POLICY)

    assert NEW_STOCK not in schedule.view_for(JUNE_2021).instrument_ids


def test_future_dated_amounts_fail_closed() -> None:
    with pytest.raises(InvalidFormationFactError):
        _fact(
            _instrument("XSHG:600001"),
            YE_2020,
            amounts=(
                TrailingAmount(date(2021, 1, 4), Decimal("4000000")),
                *_trailing("4000000", 3, end=YE_2020),
            ),
        )


def test_duplicate_instrument_in_one_formation_year_fails() -> None:
    records = _base_records(YE_2020)
    records.append(_fact(_instrument("XSHG:600001"), YE_2020, median="9999999"))

    with pytest.raises(AmbiguousFormationError):
        form_annual_schedule(records, SMALL_POLICY)


def test_mixed_formation_sessions_in_one_year_fail() -> None:
    records = _base_records(YE_2020)
    records.append(
        _fact(_instrument("XSHG:600099"), date(2020, 12, 30), median="9999999")
    )

    with pytest.raises(AmbiguousFormationError):
        form_annual_schedule(records, SMALL_POLICY)


def test_view_for_year_without_formation_fails() -> None:
    schedule = form_annual_schedule(_base_records(YE_2020), SMALL_POLICY)

    with pytest.raises(NoCohortFormedError):
        schedule.view_for(JUNE_2022)
    with pytest.raises(NoCohortFormedError):
        schedule.view_for(date(2020, 6, 1))


def test_year_below_minimum_cohort_fails_closed() -> None:
    records = [
        _fact(_instrument(f"XSHG:6000{index:02d}"), YE_2020, median="4000000", window=60)
        for index in range(1, 20)
    ]

    schedule = form_annual_schedule(records, AnnualUniversePolicy.standard())

    with pytest.raises(AnnualCohortFailedError) as error:
        schedule.view_for(JUNE_2021)
    assert "19" in str(error.value)


def test_standard_policy_takes_the_real_top_fifty() -> None:
    records = [
        _fact(
            _instrument(f"XSHG:6{index:05d}"),
            YE_2020,
            median=str(4000000 + index),
            window=60,
        )
        for index in range(55)
    ]

    schedule = form_annual_schedule(records, AnnualUniversePolicy.standard())
    view = schedule.view_for(JUNE_2021)

    assert len(view.instrument_ids) == 50
    assert _instrument("XSHG:600054") in view.instrument_ids
    assert _instrument("XSHG:600005") in view.instrument_ids
    assert _instrument("XSHG:600004") not in view.instrument_ids


def test_top_fifty_boundary_tie_breaks_by_instrument_id() -> None:
    # 51 eligible names; the two lowest share the same median so the
    # canonical InstrumentId decides which one is excluded at rank 51.
    records = [
        _fact(
            _instrument(f"XSHG:6{index:05d}"),
            YE_2020,
            median=str(4000001 + index),
            window=60,
        )
        for index in range(49)
    ]
    records.append(
        _fact(_instrument("XSHG:699998"), YE_2020, median="4000000", window=60)
    )
    records.append(
        _fact(_instrument("XSHG:699999"), YE_2020, median="4000000", window=60)
    )

    schedule = form_annual_schedule(records, AnnualUniversePolicy.standard())
    view = schedule.view_for(JUNE_2021)

    assert len(view.instrument_ids) == 50
    assert _instrument("XSHG:699998") in view.instrument_ids
    assert _instrument("XSHG:699999") not in view.instrument_ids


def test_standard_policy_requires_minimum_listing_and_window() -> None:
    # 20 eligible names plus one that fails each real-threshold condition.
    records = [
        _fact(_instrument(f"XSHG:6{index:05d}"), YE_2020, median="4000000", window=60)
        for index in range(20)
    ]
    records.append(
        _fact(
            _instrument("XSHG:699998"),
            YE_2020,
            median="9000000",
            listed=249,
            window=60,
        )
    )
    records.append(
        _fact(
            _instrument("XSHG:699999"),
            YE_2020,
            median="9000000",
            amounts=_trailing("9000000", 59, end=YE_2020),
        )
    )

    schedule = form_annual_schedule(records, AnnualUniversePolicy.standard())

    view = schedule.view_for(JUNE_2021)
    assert len(view.instrument_ids) == 20
    assert _instrument("XSHG:699998") not in view.instrument_ids
    assert _instrument("XSHG:699999") not in view.instrument_ids


def test_invalid_policy_fails_closed() -> None:
    with pytest.raises(InvalidAnnualPolicyError):
        AnnualUniversePolicy(
            minimum_listing_sessions=250,
            trailing_amount_sessions=60,
            minimum_cohort_size=60,
            maximum_cohort_size=50,
        )
    with pytest.raises(InvalidAnnualPolicyError):
        AnnualUniversePolicy(
            minimum_listing_sessions=0,
            trailing_amount_sessions=60,
            minimum_cohort_size=20,
            maximum_cohort_size=50,
        )


def test_schedule_type_contract() -> None:
    schedule = form_annual_schedule(_base_records(YE_2020), SMALL_POLICY)

    assert isinstance(schedule, AnnualUniverseSchedule)
