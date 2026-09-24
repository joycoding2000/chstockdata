from __future__ import annotations

import json
import math
import os
import socket
import ssl
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

import requests


ENDPOINT = "https://datacenter-web.eastmoney.com/api/data/v1/get"
PAGE_SIZE = 500
BASE_PARAMS = {
    "reportName": "RPT_CUSTOM_SUSPEND_DATA_INTERFACE",
    "columns": "ALL",
    "filter": '(MARKET="全部")(DATETIME=\'2026-09-11\')',
    "pageSize": PAGE_SIZE,
    "pageNumber": 1,
    "sortColumns": "SUSPEND_START_DATE",
    "sortTypes": -1,
    "source": "WEB",
    "client": "WEB",
}
ROOT = Path(__file__).resolve().parent


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def parse_payload(path: Path) -> tuple[dict | None, str | None]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        return None, type(error).__name__
    if not isinstance(value, dict):
        return None, "JSONRootNotObject"
    result = value.get("result")
    if not isinstance(result, dict):
        return None, "ResultNotObject"
    return result, None


def int_field(result: dict, key: str) -> int | None:
    try:
        return int(result[key])
    except (KeyError, TypeError, ValueError):
        return None


def summarize(label: str, result: dict | None, error: str | None) -> tuple[int | None, int | None, list | None]:
    if error or result is None:
        print(f"{label}_JSON_VALID=False")
        print(f"{label}_JSON_ERROR_TYPE={error or 'InvalidResult'}")
        return None, None, None
    data = result.get("data")
    pages = int_field(result, "pages")
    count = int_field(result, "count")
    rows = data if isinstance(data, list) else None
    print(f"{label}_JSON_VALID=True")
    print(f"{label}_PAGES={pages}")
    print(f"{label}_COUNT={count}")
    print(f"{label}_PAGE_ROWS={len(rows) if rows is not None else 'INVALID'}")
    if rows is None:
        print(f"{label}_DATA_ERROR=not-a-list")
    return pages, count, rows


def main() -> int:
    print(f"RUN_STARTED_LOCAL={now()}")
    print(f"EXECUTION_HOST={socket.gethostname()}")
    print(f"PYTHON_VERSION={sys.version.split()[0]}")
    proxy_names = (
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
        "http_proxy", "https_proxy", "all_proxy",
    )
    print(f"PROXY_ENV_CONFIGURED={any(os.environ.get(name) for name in proxy_names)}")
    print("PROXY_USE=curl forced bypass; requests.Session(trust_env=False)")
    print(f"ENDPOINT={ENDPOINT}")
    for key, value in BASE_PARAMS.items():
        print(f"PARAM_{key}={value}")

    try:
        addresses = sorted({
            item[4][0]
            for item in socket.getaddrinfo(
                "datacenter-web.eastmoney.com", 443, type=socket.SOCK_STREAM
            )
            if item[0] == socket.AF_INET
        })
    except Exception as error:
        print(f"DNS_RESULT=FAIL")
        print(f"DNS_EXCEPTION_TYPE={type(error).__name__}")
        return 2
    print(f"DNS_RESULT={'PASS' if addresses else 'FAIL'}")
    print(f"DNS_IPV4_ADDRESSES={','.join(addresses)}")
    if not addresses:
        return 2

    address = addresses[0]
    tcp_started = time.monotonic()
    try:
        raw = socket.create_connection((address, 443), timeout=10)
    except Exception as error:
        print("TCP_443_RESULT=FAIL")
        print(f"TCP_443_EXCEPTION_TYPE={type(error).__name__}")
        return 2
    tcp_ms = (time.monotonic() - tcp_started) * 1000
    print(f"TCP_443_RESULT=PASS")
    print(f"TCP_443_ADDRESS={address}:443")
    print(f"TCP_443_ELAPSED_MS={tcp_ms:.1f}")

    tls_started = time.monotonic()
    try:
        context = ssl.create_default_context()
        with context.wrap_socket(raw, server_hostname="datacenter-web.eastmoney.com") as tls:
            tls_version = tls.version()
            cert_verified = bool(tls.getpeercert())
    except Exception as error:
        print("TLS_RESULT=FAIL")
        print(f"TLS_EXCEPTION_TYPE={type(error).__name__}")
        return 2
    tls_ms = (time.monotonic() - tls_started) * 1000
    print("TLS_RESULT=PASS")
    print("TLS_CERTIFICATE_VERIFICATION=PASS" if cert_verified else "TLS_CERTIFICATE_VERIFICATION=FAIL")
    print(f"TLS_VERSION={tls_version}")
    print(f"TLS_ELAPSED_MS={tls_ms:.1f}")
    if not cert_verified:
        return 2

    curl_body = ROOT / "curl-page-1.json"
    curl_argv = [
        "curl", "--noproxy", "*", "--silent", "--show-error", "--max-time", "30",
        "--get", ENDPOINT,
    ]
    for key, value in BASE_PARAMS.items():
        curl_argv.extend(("--data-urlencode", f"{key}={value}"))
    curl_argv.extend(("--output", str(curl_body), "--write-out", "HTTP_STATUS=%{http_code}\\n"))
    print(f"CURL_ARGV={json.dumps(curl_argv, ensure_ascii=False)}")
    curl_started = now()
    print(f"CURL_REQUEST_STARTED_LOCAL={curl_started}")
    try:
        curl_run = subprocess.run(curl_argv, capture_output=True, text=True, timeout=40)
        curl_stdout = curl_run.stdout.strip()
        curl_stderr = curl_run.stderr.strip()
        curl_exit = curl_run.returncode
    except Exception as error:
        print("CURL_RESULT=FAIL")
        print(f"CURL_EXCEPTION_TYPE={type(error).__name__}")
        return 2
    print(f"CURL_EXIT_CODE={curl_exit}")
    print(f"CURL_STDOUT={curl_stdout}")
    print(f"CURL_STDERR={curl_stderr}")
    print(f"CURL_RESPONSE_RECEIVED_LOCAL={now()}")
    try:
        curl_status = int(curl_stdout.split("HTTP_STATUS=", 1)[1])
    except (IndexError, ValueError):
        curl_status = None
    curl_result, curl_error = parse_payload(curl_body) if curl_body.exists() else (None, "BodyMissing")
    curl_pages, curl_count, curl_rows = summarize("CURL", curl_result, curl_error)
    if curl_exit != 0 or curl_status != 200 or curl_result is None:
        print("CURL_RESULT=FAIL")
        return 2
    print("CURL_RESULT=PASS")

    session = requests.Session()
    session.trust_env = False
    params = dict(BASE_PARAMS)
    requests_pages: int | None = None
    requests_count: int | None = None
    all_rows: list = []
    page_summaries: list[tuple[int, int, int]] = []
    for page_number in range(1, (curl_pages or 1) + 1):
        params["pageNumber"] = page_number
        target = ROOT / f"requests-page-{page_number}.json"
        print(f"REQUESTS_PAGE_{page_number}_STARTED_LOCAL={now()}")
        try:
            response = session.get(ENDPOINT, params=params, timeout=(10, 30))
        except Exception as error:
            print(f"REQUESTS_PAGE_{page_number}_RESULT=FAIL")
            print(f"REQUESTS_PAGE_{page_number}_EXCEPTION_TYPE={type(error).__name__}")
            return 2
        target.write_bytes(response.content)
        print(f"REQUESTS_PAGE_{page_number}_HTTP_STATUS={response.status_code}")
        print(f"REQUESTS_PAGE_{page_number}_RECEIVED_LOCAL={now()}")
        if response.status_code != 200:
            print(f"REQUESTS_PAGE_{page_number}_RESULT=FAIL")
            return 2
        result, error = parse_payload(target)
        pages, count, rows = summarize(f"REQUESTS_PAGE_{page_number}", result, error)
        if result is None or pages is None or count is None or rows is None:
            print(f"REQUESTS_PAGE_{page_number}_RESULT=FAIL")
            return 2
        if requests_pages is None:
            requests_pages, requests_count = pages, count
        if pages != requests_pages or count != requests_count:
            print(f"REQUESTS_PAGE_{page_number}_RESULT=FAIL")
            print("PAGINATION_METADATA_CONSISTENT=False")
            return 2
        all_rows.extend(rows)
        page_summaries.append((page_number, pages, len(rows)))
        print(f"REQUESTS_PAGE_{page_number}_RESULT=PASS")

    expected_pages = math.ceil(requests_count / PAGE_SIZE) if requests_count is not None else None
    expected_rows_by_page = [
        min(PAGE_SIZE, requests_count - PAGE_SIZE * index)
        for index in range(requests_pages or 0)
    ]
    actual_rows_by_page = [row_count for _, _, row_count in page_summaries]
    complete = (
        requests_pages is not None
        and requests_count is not None
        and requests_pages > 0
        and requests_pages == expected_pages
        and len(page_summaries) == requests_pages
        and actual_rows_by_page == expected_rows_by_page
        and len(all_rows) == requests_count
        and curl_pages == requests_pages
        and curl_count == requests_count
        and curl_rows is not None
        and len(curl_rows) == min(PAGE_SIZE, requests_count)
    )
    print(f"REQUESTS_PAGES_FETCHED={len(page_summaries)}")
    print(f"REQUESTS_PAGES_EXPECTED={requests_pages}")
    print(f"SNAPSHOT_DECLARED_COUNT={requests_count}")
    print(f"SNAPSHOT_ACTUAL_DATA_ROWS={len(all_rows)}")
    print(f"SNAPSHOT_PAGE_ROWS={actual_rows_by_page}")
    print(f"SNAPSHOT_COMPLETENESS={'PASS' if complete else 'FAIL'}")
    print(f"RUN_FINISHED_LOCAL={now()}")
    return 0 if complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
