"""v0.4.0 Phase 2.1 — daily-bars structured contract hardening 回归测试。

锁死（离线，adapters 显式注入，零网络）：

A. canonical validation enforcement —— provider 只有通过
   ``canonicalize_daily_bars_frame`` 才允许记 success；缺列 / 非法日期 /
   非法数值 → failed_structure → 继续回落后续 provider（routing 与 probe
   两条路径共用同一 validation）；
B. truthful provenance —— providers_used 列出所有实际 payload 贡献者
   （含 overlap-only 新浪补齐）；legacy ``# Data source`` label 与
   structured provenance 解耦（只由 ``sina_supplement_advanced_end``
   哨兵驱动后缀）；
C. request outcome —— provider 检索成功但请求窗口过滤后为空时，
   ``result.is_normal_empty`` 必须明确为 True（经 generic
   ``FetchMetadata.outcome_status`` 声明），consumer 不靠猜；
D. volume unit semantics —— vipdoc/sina = shares，mootdx =
   provider_native_unknown（未证实，不伪装成统一单位），混合 = mixed；
F. pre_close merge —— 新浪接管重叠日期后，该日 pre_close 不得继承
   vipdoc 旧值。
"""

import pandas as pd
import pytest

from chstockdata.capabilities import (
    capability_health_snapshot,
    reset_capability_health,
)
from chstockdata.daily_bars import (
    VOLUME_UNIT_MIXED,
    canonicalize_daily_bars_frame,
    fetch_daily_bars,
    legacy_source_label,
    probe_daily_bars_provider,
)
from chstockdata.fetch_result import (
    FETCH_FAILED_STRUCTURE,
    FETCH_NORMAL_EMPTY,
    FETCH_SUCCESS,
)

CODE = "600519"
START = "2026-09-08"
END = "2026-09-09"


@pytest.fixture(autouse=True)
def _fresh_health():
    reset_capability_health()
    yield
    reset_capability_health()


def _frame(dates, *, close=10.0, volume=1000.0, pre_close=False):
    frame = pd.DataFrame(
        {
            "Date": pd.to_datetime(dates),
            "Open": [close - 0.5] * len(dates),
            "High": [close + 1.0] * len(dates),
            "Low": [close - 1.0] * len(dates),
            "Close": [close] * len(dates),
            "Volume": [volume] * len(dates),
        }
    )
    if pre_close:
        frame["pre_close"] = [None] + [close] * (len(dates) - 1)
    return frame


def _ok(dates, **kwargs):
    def _adapter(code, start, end):
        return _frame(dates, **kwargs)

    return _adapter


def _unavailable(provider):
    def _adapter(*args, **kwargs):
        from chstockdata.vendor_errors import VendorNotConfiguredError

        raise VendorNotConfiguredError(f"{provider} unavailable")

    return _adapter


def _must_not_run(provider):
    def _adapter(*args, **kwargs):
        pytest.fail(f"{provider} must not be called")

    return _adapter


# ── A. canonical validation enforcement ─────────────────────────────────────


def _malformed_missing_close(dates):
    frame = _frame(dates)
    return frame.drop(columns=["Close"])


def test_missing_required_column_is_failed_structure_and_falls_back():
    """vipdoc 返回缺 Close 的非空帧 → failed_structure → mootdx 接管。"""
    result = fetch_daily_bars(
        CODE,
        START,
        END,
        adapters={
            "tdx_vipdoc": _ok([START, END]) and (
                lambda *a, **k: _malformed_missing_close([START, END])
            ),
            "mootdx": _ok([START, END]),
            "sina": _must_not_run("sina"),
        },
    )

    assert result.succeeded
    assert result.metadata.final_provider == "mootdx"
    assert result.metadata.degraded, "结构失败属于硬失败：degraded 必须为 True"
    statuses = [(a.provider, a.status) for a in result.metadata.attempts]
    assert statuses == [
        ("tdx_vipdoc", FETCH_FAILED_STRUCTURE),
        ("mootdx", FETCH_SUCCESS),
    ]
    health = capability_health_snapshot()
    assert health["tdx_vipdoc:daily_bars"].status == "failed"
    assert health["mootdx:bars"].status == FETCH_SUCCESS


def test_mootdx_malformed_frame_falls_back_to_sina():
    """mootdx malformed → mootdx:bars failed → Sina 成功 → routing success。"""
    result = fetch_daily_bars(
        CODE,
        START,
        END,
        adapters={
            "tdx_vipdoc": _unavailable("tdx_vipdoc"),
            "mootdx": lambda *a, **k: _malformed_missing_close([START, END]),
            "sina": _ok([START, END]),
        },
    )

    assert result.succeeded
    assert result.metadata.final_provider == "sina"
    assert result.metadata.degraded
    assert result.metadata.failed_providers == ["mootdx"]


def test_unparseable_date_is_failed_structure():
    def _bad_date(code, start, end):
        frame = _frame([START, END])
        frame["Date"] = frame["Date"].astype(object)
        frame.loc[frame.index[1], "Date"] = "not-a-date"
        return frame

    result = fetch_daily_bars(
        CODE, START, END,
        adapters={
            "tdx_vipdoc": _bad_date,
            "mootdx": _ok([START, END]),
            "sina": _must_not_run("sina"),
        },
    )

    assert result.metadata.attempts[0].status == FETCH_FAILED_STRUCTURE
    assert "unparseable Date" in result.metadata.attempts[0].message


def test_non_numeric_close_is_failed_structure():
    def _bad_close(code, start, end):
        frame = _frame([START, END])
        frame["Close"] = frame["Close"].astype(object)
        frame.loc[frame.index[0], "Close"] = "abc"
        return frame

    result = fetch_daily_bars(
        CODE, START, END,
        adapters={
            "tdx_vipdoc": _unavailable("tdx_vipdoc"),
            "mootdx": _bad_close,
            "sina": _ok([START, END]),
        },
    )

    # attempts[0] = vipdoc not_configured；mootdx 的 malformed 是 attempts[1]
    second = result.metadata.attempts[1]
    assert (second.provider, second.status) == ("mootdx", FETCH_FAILED_STRUCTURE)
    assert "non-numeric Close" in second.message
    assert result.metadata.final_provider == "sina"


def test_valid_numeric_strings_are_normalized():
    def _string_frame(code, start, end):
        frame = _frame([START, END])
        frame["Close"] = ["10.25", "10.75"]  # 合法数字字符串：允许并转换
        frame["Volume"] = [1000, 2000]
        return frame

    result = fetch_daily_bars(
        CODE, START, END,
        adapters={
            "tdx_vipdoc": _string_frame,
            "mootdx": _must_not_run("mootdx"),
            "sina": _must_not_run("sina"),
        },
    )

    assert result.succeeded
    assert result.data["Close"].tolist() == [10.25, 10.75]
    assert pd.api.types.is_numeric_dtype(result.data["Close"])


def test_duplicate_dates_dedupe_keep_last_preserving_order():
    """重复日期确定性 keep-last 去重，保留 provider 原生行序（不重排）。

    输入行序 [09-09, 09-08, 09-08]：幸存行 = 09-09(row1) + 09-08(row3,
    keep-last) → 输出顺序 [09-09, 09-08] 与原始行序一致 —— 排序会得到
    [09-08, 09-09]，据此同时锁死 keep-last 与"不排序"两个语义。
    """
    frame = pd.concat(
        [
            _frame(["2026-09-09"], close=11.0),
            _frame(["2026-09-08"], close=10.0),
            _frame(["2026-09-08"], close=12.0),
        ],
        ignore_index=True,
    )

    canonical = canonicalize_daily_bars_frame(frame, provider="fake")

    assert canonical["Date"].tolist() == pd.to_datetime(
        ["2026-09-09", "2026-09-08"]
    ).tolist(), "保留原生行序：不因去重而排序"
    assert canonical["Close"].tolist() == [11.0, 12.0], "同日 keep-last"


def test_date_normalized_to_daily_granularity():
    def _intraday(code, start, end):
        frame = _frame([START, END])
        frame["Date"] = pd.to_datetime(
            ["2026-09-08 15:00:00", "2026-09-09 15:00:00"]
        )
        return frame

    canonical = canonicalize_daily_bars_frame(_intraday(CODE, START, END), provider="fake")

    assert (canonical["Date"] == canonical["Date"].dt.normalize()).all()
    assert canonical["Date"].iloc[0] == pd.Timestamp("2026-09-08")


# ── E. probe path 走同一 canonical validation ───────────────────────────────


def test_probe_rejects_malformed_frame():
    result = probe_daily_bars_provider(
        "sina", CODE, START, END,
        lambda *a, **k: _malformed_missing_close([START, END]),
    )

    assert not result.succeeded
    assert result.metadata.attempts[0].status == FETCH_FAILED_STRUCTURE
    health = capability_health_snapshot()
    assert set(health) == {"sina:bars"}
    assert health["sina:bars"].status == "failed", (
        "probe 不能因帧非空就绿灯：malformed = failed"
    )


# ── B. truthful provenance + legacy label 解耦 ──────────────────────────────


def test_sina_overlap_only_contribution_is_recorded():
    """新浪整窗返回但只覆盖已有日期（未推进末根）：

    - providers_used 必须包含 sina（它实际接管了重叠行）；
    - final_provider = None（双贡献者）；
    - legacy label 不追加 supplement 后缀（末根未推进）。
    """

    def _sina_overlap(code, start, end):
        # 整窗 [start,end] 都有数据，但没有 09-10
        assert str(end)[:10] == "2026-09-10"
        return _frame([START, END], close=20.0)

    result = fetch_daily_bars(
        CODE, START, "2026-09-10",
        adapters={
            "tdx_vipdoc": _ok([START, END], close=10.0),
            "mootdx": _must_not_run("mootdx"),
            "sina": _sina_overlap,
        },
    )

    assert result.succeeded
    assert result.metadata.providers_used == ["tdx_vipdoc", "sina"]
    assert result.metadata.final_provider is None
    assert "sina_supplement_overlap_only" in result.metadata.limitations
    assert "sina_supplement_advanced_end" not in result.metadata.limitations
    # 重叠日期被新浪值接管（keep-last）
    assert result.data["Close"].tolist() == [20.0, 20.0]
    # legacy label：未推进末根 → 不加后缀（structured provenance 与
    # legacy presentation 解耦）
    assert legacy_source_label(result.metadata) == (
        "vipdoc local (TDX official hsjday package)"
    )


def test_sina_advancing_end_records_both_facts():
    """新浪实际推进末根：providers_used 含 sina，且 legacy 后缀出现。"""

    def _sina_advance(code, start, end):
        return _frame(["2026-09-10"], close=21.0)

    result = fetch_daily_bars(
        CODE, START, "2026-09-10",
        adapters={
            "tdx_vipdoc": _ok([START, END], close=10.0),
            "mootdx": _must_not_run("mootdx"),
            "sina": _sina_advance,
        },
    )

    assert result.metadata.providers_used == ["tdx_vipdoc", "sina"]
    assert result.metadata.final_provider is None
    assert "sina_supplement_advanced_end" in result.metadata.limitations
    assert legacy_source_label(result.metadata) == (
        "vipdoc local (TDX official hsjday package) + sina HTTP supplement"
    )


def test_base_only_has_no_supplement_limitations():
    result = fetch_daily_bars(
        CODE, START, END,
        adapters={
            "tdx_vipdoc": _ok([START, END]),
            "mootdx": _must_not_run("mootdx"),
            "sina": _must_not_run("sina"),
        },
    )

    assert result.metadata.providers_used == ["tdx_vipdoc"]
    assert result.metadata.final_provider == "tdx_vipdoc"
    assert not any(
        item.startswith("sina_supplement_")
        for item in result.metadata.limitations
    )


def test_sina_base_with_overlap_supplement_stays_single_provider():
    """base 就是新浪（mootdx 失败回落）+ 补齐重叠：providers_used 去重。"""

    def _sina_full(code, start, end):
        return _frame([START, END], close=30.0)

    result = fetch_daily_bars(
        CODE, START, "2026-09-10",
        adapters={
            "tdx_vipdoc": _unavailable("tdx_vipdoc"),
            "mootdx": _unavailable("mootdx"),
            "sina": _sina_full,
        },
    )

    assert result.succeeded
    assert result.metadata.providers_used == ["sina"]
    assert result.metadata.final_provider == "sina", (
        "同源补齐去重后仍是单贡献者，final_provider 不得为 None"
    )


# ── C. request outcome（provider success ≠ request satisfaction）────────────


def test_window_empty_is_explicit_request_normal_empty():
    """provider 成功但 800 根全在窗口外：request 级 empty 必须显式可读。"""
    result = fetch_daily_bars(
        CODE, START, END,
        adapters={
            "tdx_vipdoc": _unavailable("tdx_vipdoc"),
            "mootdx": _ok(["2020-01-02", "2020-01-03"]),
            "sina": _unavailable("sina"),
        },
    )

    # provider 路由完成（attempt 派生 truth 保持不变）
    assert result.metadata.final_status == FETCH_SUCCESS
    assert result.succeeded
    # 但 request 级结论明确：没有产出任何 bars
    assert result.is_normal_empty
    assert result.metadata.outcome_status == FETCH_NORMAL_EMPTY
    assert result.metadata.request_status == FETCH_NORMAL_EMPTY
    assert result.data.empty
    assert "no_bars_in_requested_window" in result.metadata.limitations
    # 序列化携带显式 outcome，consumer 不需要解析 limitation 字符串
    payload = result.metadata.to_dict()
    assert payload["outcome_status"] == FETCH_NORMAL_EMPTY
    assert payload["request_status"] == FETCH_NORMAL_EMPTY


def test_window_hit_keeps_attempt_derived_outcome():
    result = fetch_daily_bars(
        CODE, START, END,
        adapters={
            "tdx_vipdoc": _ok([START, END]),
            "mootdx": _must_not_run("mootdx"),
            "sina": _must_not_run("sina"),
        },
    )

    assert result.metadata.outcome_status is None
    assert result.metadata.request_status == FETCH_SUCCESS
    assert not result.is_normal_empty


def _no_data(provider):
    def _adapter(*args, **kwargs):
        from chstockdata.vendor_errors import VendorNoDataError

        raise VendorNoDataError(f"{provider} empty")

    return _adapter


def test_all_sources_empty_keeps_routing_level_normal_empty():
    result = fetch_daily_bars(
        CODE, START, END,
        adapters={
            "tdx_vipdoc": _no_data("tdx_vipdoc"),
            "mootdx": _no_data("mootdx"),
            "sina": _no_data("sina"),
        },
    )

    assert result.is_normal_empty
    assert result.metadata.outcome_status is None, (
        "无 provider 数据时不声明 request override：final_status 已是 normal_empty"
    )
    assert result.metadata.request_status == FETCH_NORMAL_EMPTY


# ── D. volume unit semantics ────────────────────────────────────────────────


def test_vipdoc_volume_unit_is_shares(tmp_path, monkeypatch):
    """vipdoc adapter 输出（.day 文件，Volume=股）→ unit 明确 shares。"""
    import struct

    from chstockdata import vipdoc_history as vh
    from chstockdata.daily_bars import fetch_vipdoc_daily_bars

    market = vh.market_for_code(CODE).lower()
    path = tmp_path / market / "lday" / f"{market}{CODE}.day"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"".join(
            struct.pack("<IIIIIfII", int(day), 10000, 10100, 9900, 10050, 1.0e9, 1000, 0)
            for day in ("20260908", "20260909")
        )
    )
    from chstockdata import config as dataflow_config

    monkeypatch.setattr(dataflow_config, "get_config", lambda: {
        "vipdoc_history_enabled": True,
        "vipdoc_history_max_staleness_days": 5,
    })

    result = fetch_daily_bars(
        CODE, START, END,
        adapters={
            "tdx_vipdoc": fetch_vipdoc_daily_bars,
            "mootdx": _must_not_run("mootdx"),
            "sina": _must_not_run("sina"),
        },
    )

    assert result.data.attrs["volume_unit"] == "shares"
    assert "volume_unit:shares" in result.metadata.limitations


def test_mootdx_volume_unit_is_provider_native_unknown():
    """mootdx 单位未实测：不得伪装成 shares，必须显式 unknown。"""
    result = fetch_daily_bars(
        CODE, START, END,
        adapters={
            "tdx_vipdoc": _unavailable("tdx_vipdoc"),
            "mootdx": _ok([START, END]),
            "sina": _must_not_run("sina"),
        },
    )

    assert result.data.attrs["volume_unit"] == "provider_native_unknown"
    assert "volume_unit:provider_native_unknown" in result.metadata.limitations


def test_sina_probe_volume_unit_is_shares():
    result = probe_daily_bars_provider("sina", CODE, START, END, _ok([START, END]))

    assert result.succeeded
    assert result.data.attrs["volume_unit"] == "shares"
    assert "volume_unit:shares" in result.metadata.limitations


def test_mixed_contributors_resolve_to_mixed_provider_native():
    """mootdx(unknown) + sina(shares) 同载荷：不冒充统一单位。"""
    result = fetch_daily_bars(
        CODE, START, "2026-09-10",
        adapters={
            "tdx_vipdoc": _unavailable("tdx_vipdoc"),
            "mootdx": _ok([START, END]),
            "sina": _ok(["2026-09-10"]),
        },
    )

    assert result.data.attrs["volume_unit"] == VOLUME_UNIT_MIXED
    assert (
        f"volume_unit:{VOLUME_UNIT_MIXED}" in result.metadata.limitations
    )


# ── F. pre_close merge semantics ────────────────────────────────────────────


def test_sina_takeover_does_not_inherit_vipdoc_pre_close():
    """新浪接管重叠日期后：该行 pre_close 不得继承 vipdoc 旧值（保持 NaN）。

    请求窗口 [09-08, 09-10]，新浪整窗返回但只有 09-08/09-09（overlap-only）：
    两行都被新浪接管 → pre_close 全 NaN，绝不冒充新浪行的前收盘。
    """

    def _vipdoc(code, start, end):
        frame = _frame([START, END], close=10.0)
        frame["pre_close"] = [9.5, 10.0]
        return frame

    def _sina_overlap(code, start, end):
        assert str(end)[:10] == "2026-09-10"
        return _frame([START, END], close=20.0)  # 无 pre_close

    result = fetch_daily_bars(
        CODE, START, "2026-09-10",
        adapters={
            "tdx_vipdoc": _vipdoc,
            "mootdx": _must_not_run("mootdx"),
            "sina": _sina_overlap,
        },
    )

    assert result.succeeded
    assert result.metadata.providers_used == ["tdx_vipdoc", "sina"]
    assert result.data["Close"].tolist() == [20.0, 20.0], "重叠行由新浪接管"
    assert result.data["pre_close"].isna().all()


# ── G. supplement 也必须通过唯一 canonicalization boundary（Phase 2.1.1）────


def test_malformed_supplement_is_failed_structure_not_success():
    """Sina supplement 非空但 malformed（缺 Close）：

    - 不得记 success（attempt/health 都不能）；
    - 不进 merge，base 保留；
    - routing 仍 success（base 已确立）+ degraded=True；
    - providers_used 不含 sina（收到响应 ≠ 贡献 canonical payload）；
    - legacy label 保持 base-only；
    - volume_unit 仍按 base 贡献者计算（shares），不得变 mixed。
    """
    base_rows = _frame([START, END], close=10.0)

    def _vipdoc(code, start, end):
        return base_rows.copy()

    def _sina_malformed(code, start, end):
        assert str(end)[:10] == "2026-09-10"
        return _malformed_missing_close([START, END])

    result = fetch_daily_bars(
        CODE, START, "2026-09-10",
        adapters={
            "tdx_vipdoc": _vipdoc,
            "mootdx": _must_not_run("mootdx"),
            "sina": _sina_malformed,
        },
    )

    sina_attempt = result.metadata.attempts[-1]
    assert (sina_attempt.provider, sina_attempt.status) == (
        "sina", FETCH_FAILED_STRUCTURE,
    ), f"malformed supplement 不得记 success：{sina_attempt}"
    assert "missing required columns: Close" in sina_attempt.message

    # routing：base 保留，请求仍成功但降级
    assert result.succeeded
    assert result.metadata.degraded
    assert result.metadata.providers_used == ["tdx_vipdoc"]
    assert result.metadata.final_provider == "tdx_vipdoc"
    assert result.data["Close"].tolist() == base_rows["Close"].tolist(), (
        "malformed supplement 不得进入 merge，base 数据原样保留"
    )

    # limitations：只有 supplement_failed，没有任何"成功贡献"语义
    assert "sina_supplement_failed" in result.metadata.limitations
    assert "sina_supplement_advanced_end" not in result.metadata.limitations
    assert "sina_supplement_overlap_only" not in result.metadata.limitations

    # health 同步 failed；volume_unit 仍按 base 贡献者 = shares
    health = capability_health_snapshot()
    assert health["sina:bars"].status == "failed"
    assert result.data.attrs["volume_unit"] == "shares"
    assert "volume_unit:shares" in result.metadata.limitations

    # legacy label：base-only，不加 supplement 后缀
    assert legacy_source_label(result.metadata) == (
        "vipdoc local (TDX official hsjday package)"
    )


def test_non_dataframe_supplement_is_failed_structure():
    """supplement 返回 list（非 DataFrame）→ failed_structure，base 保留。"""

    def _vipdoc(code, start, end):
        return _frame([START, END], close=10.0)

    def _sina_list(code, start, end):
        return [{"Date": "2026-09-10", "Open": 1.0, "High": 1.1,
                 "Low": 0.9, "Close": 1.05, "Volume": 100}]

    result = fetch_daily_bars(
        CODE, START, "2026-09-10",
        adapters={
            "tdx_vipdoc": _vipdoc,
            "mootdx": _must_not_run("mootdx"),
            "sina": _sina_list,
        },
    )

    sina_attempt = result.metadata.attempts[-1]
    assert (sina_attempt.provider, sina_attempt.status) == (
        "sina", FETCH_FAILED_STRUCTURE,
    )
    assert "must be a pandas DataFrame" in sina_attempt.message
    assert result.succeeded
    assert result.metadata.degraded
    assert result.metadata.providers_used == ["tdx_vipdoc"]
    assert len(result.data) == 2, "base 保留，list payload 不得混入"
    assert "sina_supplement_failed" in result.metadata.limitations
    assert legacy_source_label(result.metadata) == (
        "vipdoc local (TDX official hsjday package)"
    )


def test_non_dataframe_base_payload_is_failed_structure_and_falls_back():
    """base provider 返回 dict → failed_structure → 后续 provider 接管。"""

    def _vipdoc_dict(code, start, end):
        return {"Date": [START, END], "Close": [10.0, 10.5]}

    result = fetch_daily_bars(
        CODE, START, END,
        adapters={
            "tdx_vipdoc": _vipdoc_dict,
            "mootdx": _ok([START, END]),
            "sina": _must_not_run("sina"),
        },
    )

    first = result.metadata.attempts[0]
    assert (first.provider, first.status) == ("tdx_vipdoc", FETCH_FAILED_STRUCTURE)
    assert "must be a pandas DataFrame" in first.message
    health = capability_health_snapshot()
    assert health["tdx_vipdoc:daily_bars"].status == "failed"
    assert result.succeeded
    assert result.metadata.degraded
    assert result.metadata.final_provider == "mootdx"
