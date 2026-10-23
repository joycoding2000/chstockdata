"""Canonical registry binds strategy identity to the checked-in source bytes."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from systematic_investing.research.contracts import implementation_digest_of
from systematic_investing.research.runner import build_canonical_strategy

ROOT = Path(__file__).parents[2]


@pytest.mark.parametrize(
    ("strategy_id", "module_name", "parameters"),
    (
        ("etf-absolute-trend", "etf_absolute_trend", {"sma_sessions": "3"}),
        (
            "etf-relative-momentum",
            "etf_relative_momentum",
            {"return_sessions": "3"},
        ),
        (
            "stock-relative-strength",
            "stock_relative_strength",
            {"return_sessions": "3", "top_n": "2"},
        ),
        (
            "stock-breakout",
            "stock_breakout",
            {"breakout_sessions": "3", "liquidity_sessions": "2", "top_n": "2"},
        ),
    ),
)
def test_canonical_builder_uses_current_module_bytes(
    strategy_id: str, module_name: str, parameters: dict[str, str]
) -> None:
    strategy = build_canonical_strategy(
        SimpleNamespace(strategy_id=strategy_id), parameters, ()
    )
    source_path = (
        ROOT / "src" / "systematic_investing" / "research" / "strategies" / f"{module_name}.py"
    )
    expected = implementation_digest_of(
        [(source_path.relative_to(ROOT / "src").as_posix(), source_path.read_bytes())]
    )
    assert strategy.identity.implementation_digest == expected
