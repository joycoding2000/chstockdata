"""v0.4.0 correctness regression: configure() validation + warmup retry."""

import pytest

from chstockdata.config import configure, get_setting, reset_config


@pytest.fixture(autouse=True)
def _clean_config():
    reset_config()
    yield
    reset_config()


class TestConfigureValueValidation:
    def test_truthy_string_for_boolean_flag_is_rejected(self):
        """``vipdoc_enabled="false"`` 是字符串不是布尔，必须拒绝而不是
        当 truthy 接受。"""
        with pytest.raises(ValueError, match="boolean"):
            configure(vipdoc_enabled="false")
        with pytest.raises(ValueError, match="boolean"):
            configure(vipdoc_enabled="true")
        # 拒绝后全局配置不得被污染（atomic）。
        assert get_setting("vipdoc_history_enabled") is True  # default

    def test_valid_boolean_still_accepted(self):
        configure(vipdoc_enabled=False)
        assert get_setting("vipdoc_history_enabled") is False

    def test_staleness_string_rejected(self):
        with pytest.raises(ValueError, match="number"):
            configure(vipdoc_max_staleness_days="5")
        assert get_setting("vipdoc_history_max_staleness_days") == 5  # default

    def test_negative_staleness_rejected(self):
        with pytest.raises(ValueError, match=">= 0"):
            configure(vipdoc_history_max_staleness_days=-1)

    def test_non_string_dir_rejected(self):
        with pytest.raises(ValueError, match="string or null"):
            configure(vipdoc_dir=123)

    def test_unknown_key_still_rejected(self):
        with pytest.raises(ValueError, match="unknown chstockdata settings"):
            configure(nope=1)

    def test_atomic_commit_invalid_call_pollutes_nothing(self):
        """合法 + 非法混合提交：整体拒绝，合法部分也不落盘。"""
        with pytest.raises(ValueError):
            configure(cache_dir="/tmp/ok", vipdoc_enabled="false")
        assert get_setting("data_cache_dir") != "/tmp/ok"

    def test_valid_batch_commits_all(self):
        configure(cache_dir="/tmp/ok", vipdoc_enabled=False,
                  vipdoc_max_staleness_days=3)
        assert get_setting("data_cache_dir") == "/tmp/ok"
        assert get_setting("vipdoc_history_enabled") is False
        assert get_setting("vipdoc_history_max_staleness_days") == 3


class TestWarmupRetry:
    @pytest.mark.allow_name_map_warmup
    def test_failed_warmup_allows_retry(self, monkeypatch):
        """首次 _build_name_code_map 失败后，后续 warmup 可以重试
        （v0.4.0 修复：一次性标志不再永久禁止重试）。"""
        from chstockdata import a_stock

        calls = []
        monkeypatch.setattr(
            a_stock, "_build_name_code_map",
            lambda: calls.append(1) or (_ for _ in ()).throw(
                ValueError("mootdx down")
            ),
        )
        monkeypatch.setattr(a_stock, "_name_to_code", None)
        monkeypatch.setattr(a_stock, "_name_map_warmup_started", False)

        a_stock.ensure_name_code_map_warmup()
        _join_warmup_thread()
        assert calls, "first warmup should have attempted the build"
        assert a_stock._name_map_warmup_started is False, (
            "failed warmup must reset the one-shot flag"
        )

        # 第二次调用可以再次尝试（第一次失败后不永久跳过）。
        a_stock.ensure_name_code_map_warmup()
        _join_warmup_thread()
        assert len(calls) == 2

    @pytest.mark.allow_name_map_warmup
    def test_successful_warmup_stays_idempotent(self, monkeypatch):
        from chstockdata import a_stock

        calls = []
        monkeypatch.setattr(
            a_stock, "_build_name_code_map",
            lambda: calls.append(1) or ({"茅": "600519"}, {"600519": "茅"}),
        )
        monkeypatch.setattr(a_stock, "_name_to_code", None)
        monkeypatch.setattr(a_stock, "_name_map_warmup_started", False)

        a_stock.ensure_name_code_map_warmup()
        _join_warmup_thread()
        a_stock.ensure_name_code_map_warmup()
        _join_warmup_thread()
        # 成功后标志保持，不再重复构建（幂等语义不变）。
        assert len(calls) == 1
        assert a_stock._name_map_warmup_started is True


def _join_warmup_thread():
    import time

    for _ in range(100):
        time.sleep(0.01)
        if not any(t.name == "ta-name-map-warmup" and t.is_alive()
                   for t in __import__("threading").enumerate()):
            return
    pytest.fail("warmup thread did not finish")
