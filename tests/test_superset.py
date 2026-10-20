"""Chart images and chart data.

The chart block uses NoImageProvider by default; SupersetScreenshotProvider is tested against a mocked
Superset API, and is used only when REPORT_CHART_IMAGES=superset.
"""
import json

import httpx
import pytest

from conftest import PNG, need

S = "report_renderer.superset"


def test_no_image_provider_by_default():
    provider = need(S, "image_provider_from_env")({})
    assert isinstance(provider, need(S, "NoImageProvider"))


@pytest.mark.parametrize("value", ["", "none", "off", "SUPERSET "])
def test_only_the_exact_setting_turns_screenshots_on(value):
    provider = need(S, "image_provider_from_env")({"REPORT_CHART_IMAGES": value})
    assert isinstance(provider, need(S, "NoImageProvider"))


def test_chart_screenshots_when_asked(monkeypatch):
    env = {"REPORT_CHART_IMAGES": "superset", "REPORT_SUPERSET_URL": "http://host.docker.internal:8188",
           "REPORT_SUPERSET_USER": "aisc-report", "REPORT_SUPERSET_PASSWORD": "pw"}
    provider = need(S, "image_provider_from_env")(env)
    assert isinstance(provider, need(S, "SupersetScreenshotProvider"))


def test_the_fake_returns_the_fixed_png():
    assert need(S, "FakeImageProvider")(PNG).image(33, 1200, 700) == PNG


def test_no_image_provider_gives_no_image():
    NoImageProvider = need(S, "NoImageProvider")
    ImagesUnavailable = need(S, "ImagesUnavailable")
    with pytest.raises(ImagesUnavailable):
        NoImageProvider().image(33, 1200, 700)


class FakeSuperset:
    """A mocked Superset 4.1 API: login, cache_screenshot, then the image after `ready_after` polls."""

    def __init__(self, ready_after=2, image_status=200):
        self.ready_after, self.image_status = ready_after, image_status
        self.requests = []
        self.polls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path == "/api/v1/security/login":
            body = json.loads(request.content)
            assert body["provider"] == "db" and body["username"] == "aisc-report"
            return httpx.Response(200, json={"access_token": "tok"})
        assert request.headers.get("authorization") == "Bearer tok"
        if path.startswith("/api/v1/chart/33/cache_screenshot"):
            return httpx.Response(202, json={"image_url": "http://sup/api/v1/chart/33/screenshot/abc/", "cache_key": "abc"})
        if path == "/api/v1/chart/33/screenshot/abc/":
            self.polls += 1
            if self.polls < self.ready_after:
                return httpx.Response(404)
            return httpx.Response(self.image_status, content=PNG, headers={"content-type": "image/png"})
        return httpx.Response(404)


def provider(fake, **kw):
    cls = need(S, "SupersetScreenshotProvider")
    client = httpx.Client(transport=httpx.MockTransport(fake), base_url="http://sup")
    clock = {"t": 0.0}

    def now():
        return clock["t"]

    def sleep(s):
        clock["t"] += s

    return cls(base_url="http://sup", username="aisc-report", password="pw", http=client,
               monotonic=now, sleep=sleep, **kw), clock


# the screenshot: log in, request it, poll until it is ready
def test_screenshot_login_request_and_poll():
    fake = FakeSuperset(ready_after=3)
    p, _ = provider(fake)
    assert p.image(33, 1200, 700) == PNG
    shot = [r for r in fake.requests if "cache_screenshot" in r.url.path][0]
    assert "window_size" in str(shot.url) and "1200" in str(shot.url) and "700" in str(shot.url)
    assert fake.polls == 3


def test_the_poll_gives_up_after_30_seconds_without_retry():
    fake = FakeSuperset(ready_after=10**9)
    p, clock = provider(fake)
    Unavailable = need(S, "ImagesUnavailable")
    with pytest.raises(Unavailable):
        p.image(33, 1200, 700)
    assert 30 <= clock["t"] <= 31
    assert sum(1 for r in fake.requests if "cache_screenshot" in r.url.path) == 1  # no retry


def test_a_failed_image_raises_unavailable():
    fake = FakeSuperset(ready_after=1, image_status=500)
    p, _ = provider(fake)
    with pytest.raises(need(S, "ImagesUnavailable")):
        p.image(33, 1200, 700)


def test_the_password_never_reaches_an_exception_message():
    fake = FakeSuperset(ready_after=10**9)
    p, _ = provider(fake)
    with pytest.raises(Exception) as err:
        p.image(33, 1200, 700)
    assert "pw" not in str(err.value).split()


# the chart data table
def test_the_fake_chart_data_returns_its_columns_and_rows():
    data = need(S, "FakeChartData")(columns=["system_version", "bias_rate"], rows=[[1, 0.25], [2, 0.125]])
    assert data.data(33) == {"columns": ["system_version", "bias_rate"], "rows": [[1, 0.25], [2, 0.125]]}


# the chart data table from Superset's chart-data API
def test_chart_data_from_the_api():
    def fake(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/security/login":
            return httpx.Response(200, json={"access_token": "tok"})
        assert request.headers.get("authorization") == "Bearer tok"
        if request.url.path == "/api/v1/chart/33/data/":
            return httpx.Response(200, json={"result": [{"colnames": ["system_version", "bias_rate"],
                                                         "data": [{"system_version": 1, "bias_rate": 0.25}]}]})
        return httpx.Response(404)

    cls = need(S, "SupersetChartData")
    client = httpx.Client(transport=httpx.MockTransport(fake), base_url="http://sup")
    data = cls(base_url="http://sup", username="aisc-report", password="pw", http=client)
    assert data.data(33) == {"columns": ["system_version", "bias_rate"], "rows": [[1, 0.25]]}


def test_chart_data_off_without_a_login():
    provider = need(S, "chart_data_from_env")({"REPORT_SUPERSET_URL": "http://x"})
    assert isinstance(provider, need(S, "NoChartData"))


class ExpiringSuperset:
    """Superset whose first token expires after one use: a later request with it answers 401."""

    def __init__(self):
        self.logins, self.used = 0, {}

    def __call__(self, request):
        path = request.url.path
        if path == "/api/v1/security/login":
            self.logins += 1
            return httpx.Response(200, json={"access_token": f"tok{self.logins}"})
        token = request.headers.get("authorization", "").removeprefix("Bearer ")
        self.used[token] = self.used.get(token, 0) + 1
        if token == "tok1" and self.used[token] > 1:
            return httpx.Response(401, json={"msg": "Token has expired"})
        if path.startswith("/api/v1/chart/33/data"):
            return httpx.Response(200, json={"result": [{"colnames": ["a"], "data": [{"a": 1}]}]})
        if path.startswith("/api/v1/chart/33/cache_screenshot"):
            return httpx.Response(202, json={"image_url": "http://sup/api/v1/chart/33/screenshot/abc/"})
        if path == "/api/v1/chart/33/screenshot/abc/":
            return httpx.Response(200, content=PNG, headers={"content-type": "image/png"})
        return httpx.Response(404)


def test_chart_data_logs_in_again_when_its_token_expired():
    """The token was cached for the life of the process: after it expired every chart answered 401
    and every report's charts disappeared until a restart."""
    fake = ExpiringSuperset()
    cls = need(S, "SupersetChartData")
    data = cls("http://sup", "aisc-report", "pw", http=httpx.Client(transport=httpx.MockTransport(fake)))
    assert data.data(33)["rows"] == [[1]]
    assert data.data(33)["rows"] == [[1]]
    assert fake.logins == 2


def test_screenshots_log_in_again_when_the_token_expired():
    fake = ExpiringSuperset()
    p, _ = provider(fake)
    assert p.image(33, 100, 100) == PNG
    assert p.image(33, 100, 100) == PNG
    assert fake.logins == 2
