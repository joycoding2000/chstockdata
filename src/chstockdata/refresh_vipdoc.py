#!/usr/bin/env python3
"""vipdoc 官方日线包刷新工具（离线；不进运行时请求路径）。

从通达信官方盘后数据服务器下载 ``hsjday.zip``（沪深京日线完整包，约 549MB），
只解压 ``<market>/lday/*.day``，校验后原子替换本地 ``vipdoc`` 树并写入
``manifest.json``。由外部定时（交易日收盘后）触发，例如：

    python scripts/refresh_vipdoc_history.py            # HEAD 未更新则跳过
    python scripts/refresh_vipdoc_history.py --force    # 强制重下
    python scripts/refresh_vipdoc_history.py --dry-run  # 只看 HEAD 结果

设计约束（计划 §3.2 / §6）：
- 下载到 ``*.zip.part`` → 解压到 staging → 结构校验 → 原子替换；任何一步失败
  都保留旧版本；
- 只信任成员路径中的 ``<sh|sz|bj>/lday/<market><code>.day`` 结构，绝不使用
  zip 成员原始路径落盘（zip-slip 免疫）；含 ``..``/绝对路径的成员直接拒绝；
- HTTPS 域名当前会被 EdgeOne JS 反爬挑战拦截（返回 text/html），工具自动回落
  同源 HTTP 变体；manifest 记录实际生效的 ``source_url``；
- 不落任何研究数据，只记数值（记录数、最新日期、耗时、是否跳过）。
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import vipdoc_history as vh

DEFAULT_TIMEOUT_S = 60.0
DEFAULT_RETRIES = 2
_CHUNK = 1 << 20
_MIN_PACKAGE_BYTES = 10 * 1024 * 1024
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0"
_HEADERS = {"User-Agent": _UA, "Accept": "application/zip,*/*"}
_MARKET_LDAY_FILE_RE = re.compile(r"^(sh|sz|bj)(\d{6})\.day$", re.IGNORECASE)


class VipdocRefreshError(RuntimeError):
    """刷新失败；调用方（或 main）保证旧版本不受影响。"""


# ── HTTP ────────────────────────────────────────────────────────────────────


def candidate_urls(url: str) -> Iterable[str]:
    """同源 scheme 互换候选：HTTPS 反爬挑战时自动回落 HTTP，反之亦然。"""
    yield url
    if url.startswith("https://"):
        yield "http://" + url[len("https://") :]
    elif url.startswith("http://"):
        yield "https://" + url[len("http://") :]


def head_source(url: str, timeout: float = DEFAULT_TIMEOUT_S) -> dict[str, Any]:
    """HEAD 取元数据；HTTP 错误码也返回结构化结果（ok=False），网络异常上抛。"""
    request = urllib.request.Request(url, method="HEAD", headers=_HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            headers = response.headers
            return {
                "ok": True,
                "status": response.status,
                "content_type": (headers.get("Content-Type") or "").lower(),
                "content_length": _int_or_none(headers.get("Content-Length")),
                "last_modified": headers.get("Last-Modified"),
                "etag": headers.get("ETag"),
            }
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "status": exc.code,
            "content_type": (exc.headers.get("Content-Type") or "").lower() if exc.headers else "",
            "content_length": _int_or_none(exc.headers.get("Content-Length") if exc.headers else None),
            "last_modified": exc.headers.get("Last-Modified") if exc.headers else None,
            "etag": exc.headers.get("ETag") if exc.headers else None,
        }


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _reject_reason(meta: dict[str, Any]) -> str | None:
    """候选不可用的原因；HEAD 失败（无元数据）放行给下载做 fail-closed。"""
    if not meta.get("ok"):
        return None
    content_type = meta.get("content_type") or ""
    if "html" in content_type or "json" in content_type:
        return f"not a zip payload ({content_type or 'unknown content-type'})"
    content_length = meta.get("content_length")
    if content_length is not None and content_length < _MIN_PACKAGE_BYTES:
        return f"payload too small ({content_length} bytes)"
    return None


def download_source(
    url: str,
    dest: Path,
    *,
    timeout: float = DEFAULT_TIMEOUT_S,
    retries: int = DEFAULT_RETRIES,
) -> dict[str, Any]:
    """流式下载到 ``dest``，返回 {bytes, sha256}；失败清理半成品并有限重试。"""
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return _download_once(url, dest, timeout)
        except Exception as exc:  # noqa: BLE001 - 统一转成刷新错误
            last_error = exc
            _remove_file(dest)
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise VipdocRefreshError(
        f"download failed: {type(last_error).__name__}: {str(last_error)[:200]}"
    ) from last_error


def _download_once(url: str, dest: Path, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=_HEADERS)
    digest = hashlib.sha256()
    size = 0
    expected: int | None = None
    with urllib.request.urlopen(request, timeout=timeout) as response, open(dest, "wb") as fh:
        content_type = (response.headers.get("Content-Type") or "").lower()
        if "html" in content_type:
            raise VipdocRefreshError(f"unexpected content-type {content_type!r} (anti-bot page?)")
        expected = _int_or_none(response.headers.get("Content-Length"))
        while True:
            chunk = response.read(_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
            fh.write(chunk)
            size += len(chunk)
    if expected is not None and expected != size:
        raise VipdocRefreshError(f"incomplete download: {size} of {expected} bytes")
    if not zipfile.is_zipfile(dest):
        raise VipdocRefreshError("downloaded payload is not a zip archive")
    return {"url": url, "path": str(dest), "bytes": size, "sha256": digest.hexdigest()}


# ── 解压 / 校验 / 原子替换 ──────────────────────────────────────────────────


def _member_target(member: str) -> tuple[str, str] | None:
    """把 zip 成员映射为 ``(market, filename)``；非 lday 成员返回 None。

    输出路径完全由经校验的 market + filename 重建，不使用成员原始路径，
    因此不存在路径穿越落盘；含 ``..``/绝对路径的成员显式拒绝（zip-slip）。
    """
    name = member.replace("\\", "/")
    if name.startswith("/") or re.match(r"^[A-Za-z]:", name):
        raise VipdocRefreshError(f"zip member has absolute path: {member!r}")
    parts = [part for part in name.split("/") if part not in ("", ".")]
    if ".." in parts:
        raise VipdocRefreshError(f"zip member escapes target directory: {member!r}")
    filename = parts[-1]
    match = _MARKET_LDAY_FILE_RE.fullmatch(filename)
    if match is None:
        return None
    market = match.group(1).lower()
    if len(parts) < 3 or parts[-3].lower() != market or parts[-2].lower() != "lday":
        return None
    return market, filename.lower()


def _extract_lday(zip_path: Path, staging: Path) -> dict[str, int]:
    """只解压 ``<market>/lday/<market><code>.day``；结构不达标 fail-closed。"""
    counts: dict[str, int] = {"sh": 0, "sz": 0, "bj": 0}
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            if member.is_dir():
                continue
            mapped = _member_target(member.filename)
            if mapped is None:
                continue
            market, filename = mapped
            if member.file_size % vh._DAY_RECORD_SIZE != 0:
                raise VipdocRefreshError(
                    f"zip member has misaligned .day size: {member.filename} "
                    f"({member.file_size}B)"
                )
            out = staging / market / "lday" / filename
            out.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, open(out, "wb") as dst:
                shutil.copyfileobj(src, dst)
            counts[market] += 1
    if not counts["sh"] or not counts["sz"]:
        raise VipdocRefreshError(f"vipdoc package missing sh/sz lday members: {counts}")
    return counts


def replace_tree(staging: Path, target: Path) -> None:
    """staging → target 原子替换；失败时恢复旧目录。"""
    backup = target.with_name(target.name + ".old")
    if backup.exists():
        shutil.rmtree(backup)
    if target.exists():
        if not target.is_dir():
            raise VipdocRefreshError(f"target exists and is not a directory: {target}")
        target.rename(backup)
    try:
        staging.rename(target)
    except OSError:
        if backup.exists() and not target.exists():
            backup.rename(target)
        raise
    shutil.rmtree(backup, ignore_errors=True)


def _remove_file(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


def _remove_tree(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)


# ── 主流程 ──────────────────────────────────────────────────────────────────


def refresh_history(
    url: str,
    target_dir: str | Path,
    *,
    force: bool = False,
    dry_run: bool = False,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> dict[str, Any]:
    """刷新本地 vipdoc 树；返回状态字典，失败抛 :class:`VipdocRefreshError`。"""
    target = Path(target_dir).expanduser().resolve()
    manifest = vh._read_manifest(target / "manifest.json")

    errors: list[str] = []
    for candidate in candidate_urls(url):
        try:
            meta = head_source(candidate, timeout=timeout)
        except Exception as exc:  # noqa: BLE001 - HEAD 失败仍允许下载尝试
            meta = {"ok": False, "error": f"{type(exc).__name__}"}
        reason = _reject_reason(meta)
        if reason:
            errors.append(f"{candidate}: {reason}")
            continue

        last_modified = meta.get("last_modified")
        if (
            not force
            and last_modified
            and manifest
            and manifest.get("source_last_modified") == last_modified
        ):
            return {
                "status": "skipped",
                "reason": "source not modified",
                "source_url": candidate,
                "dir": str(target),
                "source_last_modified": last_modified,
            }

        if dry_run:
            return {
                "status": "would_download",
                "source_url": candidate,
                "dir": str(target),
                "content_length": meta.get("content_length"),
                "last_modified": last_modified,
            }

        return _download_and_install(candidate, target, meta, timeout=timeout)

    raise VipdocRefreshError("no usable vipdoc source: " + "; ".join(errors))


def _download_and_install(
    url: str, target: Path, meta: dict[str, Any], *, timeout: float
) -> dict[str, Any]:
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    part = parent / (target.name + ".zip.part")
    staging = parent / (target.name + ".staging")
    _remove_file(part)
    _remove_tree(staging)

    try:
        info = download_source(url, part, timeout=timeout)
        _extract_lday(part, staging)
        scan = vh.scan_lday_tree(staging)
        manifest = {
            "schema_version": vh.MANIFEST_SCHEMA_VERSION,
            "source_url": url,
            "source_last_modified": meta.get("last_modified"),
            "downloaded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "record_counts": scan["record_counts"],
            "max_bar_date": scan["max_bar_date"],
            "zip_sha256": info["sha256"],
        }
        vh.write_manifest(staging, manifest)
        replace_tree(staging, target)
    except Exception:
        _remove_tree(staging)
        _remove_file(part)
        raise

    _remove_file(part)
    return {
        "status": "refreshed",
        "source_url": url,
        "dir": str(target),
        "bytes": info["bytes"],
        "zip_sha256": info["sha256"],
        "record_counts": scan["record_counts"],
        "latest_bar_date": max(scan["max_bar_date"].values(), default=None),
    }


def _config_url() -> str:
    try:
        from .config import get_config

        return str(get_config().get("vipdoc_history_url") or vh.VIPDOC_SOURCE_URL)
    except Exception:  # noqa: BLE001 - 配置不可用不影响刷新
        return vh.VIPDOC_SOURCE_URL


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="刷新通达信官方 vipdoc 日线包（离线工具）")
    parser.add_argument("--dir", default=None, help="本地 vipdoc 库存根（默认取配置）")
    parser.add_argument("--url", default=None, help="数据包 URL（默认取配置/官方 URL）")
    parser.add_argument("--force", action="store_true", help="忽略 Last-Modified 强制重下")
    parser.add_argument("--dry-run", action="store_true", help="只做 HEAD，不下载")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S, help="HTTP 超时秒")
    args = parser.parse_args(argv)

    target = args.dir or vh.vipdoc_history_dir()
    url = args.url or _config_url()
    started = time.time()
    try:
        result = refresh_history(
            url,
            target,
            force=args.force,
            dry_run=args.dry_run,
            timeout=args.timeout,
        )
    except (VipdocRefreshError, OSError) as exc:
        print(f"[vipdoc] 刷新失败：{exc}", file=sys.stderr)
        return 1

    elapsed = time.time() - started
    if result["status"] == "skipped":
        print(f"[vipdoc] 跳过（源未更新）：{result['dir']}，上次源时间 {result['source_last_modified']}")
    elif result["status"] == "would_download":
        print(
            f"[vipdoc] dry-run：将下载 {result['source_url']} "
            f"({result.get('content_length')} bytes) → {result['dir']}"
        )
    else:
        print(
            f"[vipdoc] 刷新完成：{result['dir']}，"
            f"记录数 {result['record_counts']}，最新 bar {result['latest_bar_date']}，"
            f"{result['bytes'] / 1024 / 1024:.0f}MB / {elapsed:.1f}s"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
