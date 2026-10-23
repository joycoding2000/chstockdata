"""Real r1 public boundary with deterministic transports, never live certification."""
import copy
import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from types import SimpleNamespace

import chstockdata
import pytest
from chstockdata.opening_evidence import OfficialOpeningEvent, OfficialOpeningReader, TdxOpeningReader
from systematic_investing.adapters.chstockdata.provider import ChStockDataProvider, LibraryChStockDataClient
from systematic_investing.data.contracts import ProviderFailure, ProviderSuccess
from systematic_investing.data.ports import HistoricalOpeningRequest
from systematic_investing.data.quality import CanonicalDataset
from systematic_investing.data.snapshots import SnapshotReader, SnapshotWriter
from systematic_investing.domain.historical_opening import HistoricalOpeningEvidence, ExecutionEligibilityMode
from systematic_investing.domain.identifiers import InstrumentId

I = InstrumentId.parse('XSHE:000002')
NOW = datetime(2026, 10, 14, tzinfo=UTC)


def seal(data):
    data = copy.deepcopy(data)
    data.pop('evidence_hash', None)
    data['evidence_hash'] = sha256(json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()
    return data


def fetch(day, *, activity=True, fault=False, events=()):
    class Client:
        def __init__(self):
            self.client = self

        def get_history_minute_time_data(self, **kwargs):
            return [{'price': 22.4, 'vol': 1 if activity else 0}]

        def get_history_transaction_data(self, market, code, start, count, rawdate):
            assert (market, code, start, count, rawdate) == (0, '000002', 0, 800, int(day.replace('-', '')))
            return [{'time': '09:30', 'price': 22.4, 'vol': 1}] if activity else []

        def close(self):
            pass

    class Http:
        def post(self, url, **kwargs):
            assert url == 'https://www.szse.cn/api/search/content'
            assert kwargs['timeout'] == (4, 8) and kwargs['allow_redirects'] is False
            assert kwargs['data']['keyword'] == '000002'
            if fault:
                raise ConnectionError('deterministic official failure')
            return SimpleNamespace(content=b'{"data":[],"totalSize":0}', status_code=200, raise_for_status=lambda: None)

    return chstockdata.fetch_historical_opening_evidence('000002', day,
        tdx_reader=TdxOpeningReader(client_factory=lambda **kw: Client(), versions=('0.11.7', '0.2.7'), page_offsets=(0,)),
        official_reader=OfficialOpeningReader(session=Http()), known_events=events)


def consume(result, monkeypatch):
    original = chstockdata.fetch_historical_opening_evidence
    monkeypatch.setattr(chstockdata, 'fetch_historical_opening_evidence', lambda *a, **kw: result)
    try:
        provider = ChStockDataProvider(client=LibraryChStockDataClient(library=chstockdata, historical_opening_candidate=True), clock=lambda: NOW)
        return provider.fetch_historical_opening_evidence(HistoricalOpeningRequest((I,), date.fromisoformat(result.data['session_date'])))
    finally:
        monkeypatch.setattr(chstockdata, 'fetch_historical_opening_evidence', original)


@pytest.mark.parametrize('day,status,blocked', [
    ('2015-12-18', 'OPEN_ACTIVITY_CONFIRMED', False),
    ('2016-01-04', 'UNKNOWN', True),
    ('2016-07-04', 'UNKNOWN', False),
    ('2016-07-05', 'OPEN_ACTIVITY_CONFIRMED', False),
    ('2022-12-30', 'OPEN_ACTIVITY_CONFIRMED', False),
])
def test_cross_repository_interval(day, status, blocked, monkeypatch):
    result = fetch(day)
    assert result.data['opening_status'] == status
    assert result.data['official_block_at_target'] is blocked
    response = consume(result, monkeypatch)
    assert isinstance(response, ProviderSuccess), response
    fact = response.records[0]
    assert fact.payload == result.data
    assert HistoricalOpeningEvidence.from_payload(result.data) == fact
    assert fact.evidence_hash == result.data['evidence_hash']
    assert fact.payload['official_events'][0]['effective_end'] is None
    assert fact.availability.information_known_at(fact.target_execution_at) is None


@pytest.mark.parametrize('activity,fault', [(False, False), (True, True)])
def test_later_session_requires_both_sources(activity, fault, monkeypatch):
    result = fetch('2022-12-30', activity=activity, fault=fault)
    response = consume(result, monkeypatch)
    assert isinstance(response, ProviderSuccess)
    assert response.records[0].opening_status == 'UNKNOWN'
    forged = seal(dict(result.data, opening_status='OPEN_ACTIVITY_CONFIRMED'))
    with pytest.raises(ValueError):
        HistoricalOpeningEvidence.from_payload(forged)


@pytest.mark.parametrize('mutation', ['resume_date', 'verified', 'source_url', 'source_sha', 'source_kind', 'new_halt'])
def test_caller_cannot_authenticate_resume(mutation, monkeypatch):
    original = fetch('2022-12-30').data['official_events'][0]
    forged = copy.deepcopy(original)
    if mutation == 'resume_date':
        forged['raw_fields']['resume_date'] = '2016-01-01'
    elif mutation == 'verified':
        forged['raw_fields'].update(verified=True, resume_date_verified=True)
    elif mutation == 'source_url':
        forged['source_url'] = 'https://example.invalid/self-asserted'
    elif mutation == 'source_sha':
        forged['raw_sha256'] = 'b' * 64
    elif mutation == 'source_kind':
        forged['source_kind'] = 'verified_official'
    else:
        forged['effective_start'] = '2022-12-29T09:30:00+08:00'
    result = fetch('2022-12-30', events=(OfficialOpeningEvent(**forged),))
    assert result.data['official_block_at_target'] and result.data['source_conflict']
    assert consume(result, monkeypatch).records[0].opening_status == 'UNKNOWN'
    positive = seal(dict(result.data, opening_status='OPEN_ACTIVITY_CONFIRMED', source_conflict=False, official_block_at_target=False))
    with pytest.raises(ValueError, match='interval'):
        HistoricalOpeningEvidence.from_payload(positive)


@pytest.mark.parametrize('day', ['2016-01-04', '2016-07-04'])
def test_hash_resealed_positive_cannot_override_halt_or_resume_day(day):
    positive = seal(dict(fetch(day).data, opening_status='OPEN_ACTIVITY_CONFIRMED', source_conflict=False, official_block_at_target=False))
    with pytest.raises(ValueError):
        HistoricalOpeningEvidence.from_payload(positive)


def test_payload_hash_snapshot_and_replay(tmp_path, monkeypatch, bar_factory):
    result = fetch('2022-12-30')
    response = consume(result, monkeypatch)
    assert isinstance(response, ProviderSuccess), response
    fact = response.records[0]
    data = CanonicalDataset((bar_factory(I, fact.session_date, open='22.4', close='22.4'),), (), (), (), (), (fact,))
    manifest = SnapshotWriter('chstockdata', '0.4.2', 'owner-r2').persist(data, snapshot_dir=tmp_path / 'snapshot',
        created_at=NOW, knowledge_cutoff=NOW, retrieved_at=NOW, execution_eligibility_mode=ExecutionEligibilityMode.HISTORICAL_OPENING_R21)
    loaded, replayed = SnapshotReader().load(tmp_path / 'snapshot', execution_eligibility_mode=ExecutionEligibilityMode.HISTORICAL_OPENING_R21)
    assert loaded == manifest and replayed == data
    assert replayed.historical_opening_evidence[0].payload == result.data
    altered = copy.deepcopy(result.data)
    altered['official_events'][0]['raw_fields']['resume_date'] = '2016-01-01'
    with pytest.raises(ValueError, match='hash'):
        HistoricalOpeningEvidence.from_payload(altered)
    with pytest.raises(ValueError, match='interval'):
        HistoricalOpeningEvidence.from_payload(seal(altered))


@pytest.mark.parametrize('day,previous,eligible', [
    ('2015-12-18', '2015-12-17', True),
    ('2016-01-04', '2015-12-31', False),
    ('2016-07-04', '2016-07-01', False),
    ('2016-07-05', '2016-07-04', True),
    ('2022-12-30', '2022-12-29', True),
])
@pytest.mark.parametrize('mode', [ExecutionEligibilityMode.HISTORICAL_OPENING_R21, ExecutionEligibilityMode.LEGACY])
def test_actual_execution_and_legacy(day, previous, eligible, mode, monkeypatch,
    make_engine, bar_factory, target_contribution, predetermined_targets, account_fees):
    from systematic_investing.backtest.engine import EngineClock
    from systematic_investing.domain.historical_opening import HISTORICAL_SUSPENSION_GAP, SHANGHAI
    from systematic_investing.domain.market import Availability, AvailabilityBasis, MarketCalendar, TradingSession, TradabilityStatus, TradabilityStatusKind
    from systematic_investing.instrument_master.repository import InstrumentMaster, default_m0_master

    result = consume(fetch(day), monkeypatch)
    assert isinstance(result, ProviderSuccess), result
    session, prior = date.fromisoformat(day), date.fromisoformat(previous)
    seed = default_m0_master()
    seed_id = InstrumentId.parse('XSHE:000001')
    master = InstrumentMaster()
    reference = seed.resolve_instrument(seed_id, date(2026, 9, 11))
    master.register_instrument(replace(reference, instrument_id=I, list_date=date(2000, 1, 1), valid_from=date(2000, 1, 1)))
    rules = seed.resolve_rules(seed_id, date(2026, 9, 11))
    for profile in (rules.lot, rules.settlement, rules.price_limit, rules.market_fee_tax):
        master.add_rule_profile(replace(profile, effective_from=date(2000, 1, 1)))
    fees = replace(account_fees, broker_profiles=tuple(replace(p, effective_from=date(2000, 1, 1)) for p in account_fees.broker_profiles))
    calendar = MarketCalendar('XSHE', 'r2-injected', tuple(TradingSession('XSHE', d, True, None, 'r2-injected') for d in (prior, session, session + timedelta(days=3))))
    bars = tuple(bar_factory(I, d, open='22.4', close='22.4', pre_close='22.4', available_at=datetime(d.year, d.month, d.day, 15, 5, tzinfo=SHANGHAI)) for d in (prior, session))
    gap = TradabilityStatus(I, session, TradabilityStatusKind.UNKNOWN, HISTORICAL_SUSPENSION_GAP, Availability(None, NOW, AvailabilityBasis.UNKNOWN), 'owner-r2-injected')
    target = predetermined_targets({prior: (target_contribution(I, '0.10'),)})
    run = make_engine(calendar=calendar, master=master, account_fees=fees, clock=EngineClock.shanghai(), bars=bars,
        tradability=(gap,), historical_opening_evidence=result.records,
        execution_eligibility_mode=mode, target_source=target).run(start_session=prior, end_session=session)
    assert bool(run.fills) is (eligible and mode is ExecutionEligibilityMode.HISTORICAL_OPENING_R21)
    if run.fills:
        assert len(run.fills) == 1 and run.fills[0].quantity == run.session(prior).plans[0].order_quantity
