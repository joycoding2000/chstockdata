"""vipdoc 刷新工具契约测试（计划 Task 2）。

全部离线：用本地伪 zip（zipfile 构造）验证 HEAD 跳过逻辑、staging → 原子
替换、zip-slip 拒绝、只解压 lday、失败保留旧版。下载函数通过 monkeypatch
注入，不触碰网络。
"""

import importlib.util
import struct
import zipfile
from pathlib import Path

import pytest

def _load_module():
    import chstockdata.refresh_vipdoc as module

    return module


@pytest.fixture()
def refresh():
    return _load_module()


def _record(date=20260909):
    return struct.pack("<IIIIIfII", date, 1000, 1100, 900, 1050, 1.5e8, 12345, 0)


def _fake_zip(tmp_path, *, sh_records=2, sz_records=1, extra_members=()):
    zip_path = tmp_path / "hsjday.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("sh/lday/sh600519.day", _record() * sh_records)
        zf.writestr("sz/lday/sz000001.day", _record() * sz_records)
        zf.writestr("sh/minline/sh600519.lc1", b"x" * 64)
        zf.writestr("sh/fzline/sh600519.lc5", b"x" * 64)
        for name, payload in extra_members:
            zf.writestr(name, payload)
    return zip_path


def _zip_meta(**overrides):
    meta = {
        "ok": True,
        "status": 200,
        "content_type": "application/zip",
        "content_length": 549205235,
        "last_modified": "Fri, 10 Sep 2026 07:58:52 GMT",
        "etag": None,
    }
    meta.update(overrides)
    return meta


# ── 1. 解压：只取 lday + zip-slip 拒绝 ─────────────────────────────────────


def test_extract_lday_keeps_only_market_lday_members(tmp_path, refresh):
    zip_path = _fake_zip(tmp_path)
    staging = tmp_path / "staging"

    counts = refresh._extract_lday(zip_path, staging)

    assert counts == {"sh": 1, "sz": 1, "bj": 0}
    assert (staging / "sh" / "lday" / "sh600519.day").is_file()
    assert (staging / "sz" / "lday" / "sz000001.day").is_file()
    assert not (staging / "sh" / "minline").exists()
    assert not (staging / "sh" / "fzline").exists()


def test_extract_lday_rejects_zip_slip_members(tmp_path, refresh):
    zip_path = tmp_path / "evil.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("sh/lday/sh600519.day", _record())
        zf.writestr("../evil/day/evil.day", _record())

    with pytest.raises(refresh.VipdocRefreshError):
        refresh._extract_lday(zip_path, tmp_path / "staging")

    assert not (tmp_path / "evil").exists()
    assert not (tmp_path.parent / "evil").exists()


def test_extract_lday_requires_sh_and_sz(tmp_path, refresh):
    zip_path = tmp_path / "sh-only.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("sh/lday/sh600519.day", _record())

    with pytest.raises(refresh.VipdocRefreshError):
        refresh._extract_lday(zip_path, tmp_path / "staging")


def test_extract_lday_rejects_misaligned_record_member(tmp_path, refresh):
    zip_path = tmp_path / "bad.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("sh/lday/sh600519.day", b"x" * 5)
        zf.writestr("sz/lday/sz000001.day", _record())

    with pytest.raises(refresh.VipdocRefreshError):
        refresh._extract_lday(zip_path, tmp_path / "staging")


# ── 2. HEAD 跳过逻辑 ───────────────────────────────────────────────────────


def test_refresh_skips_when_source_not_modified(tmp_path, refresh, monkeypatch):
    target = tmp_path / "vipdoc"
    target.mkdir()
    (target / "manifest.json").write_text(
        '{"source_last_modified": "Fri, 10 Sep 2026 07:58:52 GMT"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        refresh, "head_source", lambda url, timeout=None: _zip_meta()
    )
    monkeypatch.setattr(
        refresh,
        "download_source",
        lambda *args, **kwargs: pytest.fail("未更新时不得下载"),
    )

    result = refresh.refresh_history("https://example.test/hsjday.zip", target)

    assert result["status"] == "skipped"
    assert not (tmp_path / "vipdoc.zip.part").exists()


def test_refresh_force_ignores_last_modified(tmp_path, refresh, monkeypatch):
    target = tmp_path / "vipdoc"
    target.mkdir()
    (target / "manifest.json").write_text(
        '{"source_last_modified": "Fri, 10 Sep 2026 07:58:52 GMT"}',
        encoding="utf-8",
    )
    zip_path = _fake_zip(tmp_path)
    monkeypatch.setattr(refresh, "head_source", lambda url, timeout=None: _zip_meta())
    downloaded = []

    def _fake_download(url, dest, *, timeout=None, retries=None):
        downloaded.append(url)
        dest.write_bytes(zip_path.read_bytes())
        return {"url": url, "path": str(dest), "bytes": dest.stat().st_size, "sha256": "0" * 64}

    monkeypatch.setattr(refresh, "download_source", _fake_download)

    result = refresh.refresh_history(
        "https://example.test/hsjday.zip", target, force=True
    )

    assert result["status"] == "refreshed"
    assert downloaded == ["https://example.test/hsjday.zip"]


# ── 3. 下载 → staging → 原子替换 ──────────────────────────────────────────


def test_refresh_installs_tree_and_manifest_atomically(tmp_path, refresh, monkeypatch):
    target = tmp_path / "vipdoc"
    target.mkdir()
    old_file = target / "old-marker.txt"
    old_file.write_text("old", encoding="utf-8")
    zip_path = _fake_zip(tmp_path, sh_records=3, sz_records=2)

    monkeypatch.setattr(refresh, "head_source", lambda url, timeout=None: _zip_meta())

    def _fake_download(url, dest, *, timeout=None, retries=None):
        dest.write_bytes(zip_path.read_bytes())
        return {"url": url, "path": str(dest), "bytes": dest.stat().st_size, "sha256": "a" * 64}

    monkeypatch.setattr(refresh, "download_source", _fake_download)

    result = refresh.refresh_history("https://example.test/hsjday.zip", target, force=True)

    assert result["status"] == "refreshed"
    assert result["record_counts"] == {"sh": 3, "sz": 2, "bj": 0}
    assert (target / "sh" / "lday" / "sh600519.day").is_file()
    assert (target / "sz" / "lday" / "sz000001.day").is_file()
    assert not old_file.exists()

    import json

    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == refresh.vh.MANIFEST_SCHEMA_VERSION
    assert manifest["source_last_modified"] == "Fri, 10 Sep 2026 07:58:52 GMT"
    assert manifest["zip_sha256"] == "a" * 64
    assert manifest["record_counts"] == {"sh": 3, "sz": 2, "bj": 0}
    assert manifest["max_bar_date"]["600519"] == "2026-09-09"
    assert manifest["downloaded_at"].endswith("Z")

    # 无 staging/.part/backup 残留
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith("vipdoc.")]
    assert leftovers == []


def test_refresh_failure_keeps_old_tree(tmp_path, refresh, monkeypatch):
    target = tmp_path / "vipdoc"
    target.mkdir()
    marker = target / "manifest.json"
    marker.write_text('{"schema_version": 1}', encoding="utf-8")
    monkeypatch.setattr(refresh, "head_source", lambda url, timeout=None: _zip_meta())
    monkeypatch.setattr(
        refresh,
        "download_source",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            refresh.VipdocRefreshError("network reset")
        ),
    )

    with pytest.raises(refresh.VipdocRefreshError):
        refresh.refresh_history("https://example.test/hsjday.zip", target, force=True)

    assert marker.read_text(encoding="utf-8") == '{"schema_version": 1}'
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith("vipdoc.")]
    assert leftovers == []


# ── 4. scheme 回落（HTTPS 反爬挑战 → HTTP） ───────────────────────────────


def test_refresh_falls_back_to_http_when_https_serves_html(tmp_path, refresh, monkeypatch):
    target = tmp_path / "vipdoc"
    zip_path = _fake_zip(tmp_path)
    seen = []

    def _fake_head(url, timeout=None):
        seen.append(url)
        if url.startswith("https://"):
            return _zip_meta(content_type="text/html", content_length=985, last_modified=None)
        return _zip_meta()

    monkeypatch.setattr(refresh, "head_source", _fake_head)

    def _fake_download(url, dest, *, timeout=None, retries=None):
        dest.write_bytes(zip_path.read_bytes())
        return {"url": url, "path": str(dest), "bytes": dest.stat().st_size, "sha256": "b" * 64}

    monkeypatch.setattr(refresh, "download_source", _fake_download)

    result = refresh.refresh_history("https://data.tdx.com.cn/vipdoc/hsjday.zip", target)

    assert seen[0].startswith("https://")
    assert result["source_url"].startswith("http://")
    assert result["status"] == "refreshed"


def test_refresh_dry_run_does_not_touch_disk(tmp_path, refresh, monkeypatch, capsys):
    target = tmp_path / "vipdoc"
    monkeypatch.setattr(refresh, "head_source", lambda url, timeout=None: _zip_meta())
    monkeypatch.setattr(
        refresh,
        "download_source",
        lambda *args, **kwargs: pytest.fail("dry-run 不得下载"),
    )

    result = refresh.refresh_history(
        "https://example.test/hsjday.zip", target, dry_run=True
    )

    assert result["status"] == "would_download"
    assert not target.exists()
