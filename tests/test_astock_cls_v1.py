from urllib.parse import urlsplit

from chstockdata import a_stock


class _Response:
    def __init__(self, payload, *, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise a_stock._requests.HTTPError(
                f"HTTP {self.status_code}", response=self
            )


def _roll_payload(title):
    return {
        "errno": 0,
        "data": {
            "roll_data": [
                {
                    "title": title,
                    "content": "content",
                    "ctime": 1789000000,
                }
            ]
        },
    }


def test_cls_v1_url_uses_sorted_query_and_md5_sha1_signature():
    url = a_stock._cls_v1_url(20)

    query = "appName=CailianpressWeb&last_time=&os=web&refresh_type=1&rn=20&sv=7.7.5"
    expected_sign = "d89fdd16805945016e0b9cb12e994a46"

    parsed = urlsplit(url)
    assert parsed.path == "/v1/roll/get_roll_list"
    assert parsed.query == f"{query}&sign={expected_sign}"


def test_cls_v1_is_primary_cls_news_route(monkeypatch):
    calls = []

    def fake_source_http_get(source_id, url, **kwargs):
        calls.append((source_id, url, kwargs))
        return _Response(_roll_payload("v1 headline"))

    monkeypatch.setattr(a_stock, "_source_http_get", fake_source_http_get)
    monkeypatch.setattr(
        a_stock,
        "_em_get",
        lambda *args, **kwargs: _Response({"data": {"fastNewsList": []}}),
    )

    result = a_stock.get_global_news("2026-09-10", limit=1)

    assert "v1 headline" in result
    assert len(calls) == 1
    assert calls[0][0] == "cls"
    assert "/v1/roll/get_roll_list?" in calls[0][1]
    assert "sign=" in calls[0][1]
    assert "params" not in calls[0][2]


def test_cls_v1_business_error_falls_back_to_cache(monkeypatch):
    urls = []

    def fake_source_http_get(source_id, url, **kwargs):
        urls.append(url)
        if "/v1/roll/get_roll_list?" in url:
            return _Response({"errno": 10012, "msg": "signature error"})
        assert url == "https://www.cls.cn/api/cache"
        assert kwargs["params"] == {"name": "telegraph", "rn": "1"}
        return _Response(_roll_payload("cache headline"))

    monkeypatch.setattr(a_stock, "_source_http_get", fake_source_http_get)
    monkeypatch.setattr(
        a_stock,
        "_em_get",
        lambda *args, **kwargs: _Response({"data": {"fastNewsList": []}}),
    )

    result = a_stock.get_global_news("2026-09-10", limit=1)

    assert "cache headline" in result
    assert len(urls) == 2
    assert "/v1/roll/get_roll_list?" in urls[0]
    assert urls[1] == "https://www.cls.cn/api/cache"
