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

    def __init__(self, ready_after=2, image_status=200, dataset_columns=("question", "score")):
        self.ready_after, self.image_status = ready_after, image_status
        self.dataset_columns = dataset_columns
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
        if path.rstrip("/") in ("/api/v1/chart/33", "/api/v1/dataset/7"):
            return superset_reads(path, None, self.dataset_columns)
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


# the chart data table from Superset's chart-data API: the chart's saved query, asked again

QUERY_CONTEXT = {"datasource": {"id": 7, "type": "table"},
                 "queries": [{"columns": ["system_version"], "metrics": ["bias_rate"], "filters": []}]}
RUN_COLUMNS = ("system_version", "bias_rate", "target_status")


def superset_reads(path, query_context=QUERY_CONTEXT, dataset_columns=RUN_COLUMNS):
    """Superset's answer to reading chart 33 (its saved query) or dataset 7 (its columns)."""
    if path.rstrip("/") == "/api/v1/chart/33":
        result = {"id": 33, "params": json.dumps({"datasource": "7__table"}),
                  "query_context": None if query_context is None else json.dumps(query_context)}
        return httpx.Response(200, json={"result": result})
    if path.rstrip("/") == "/api/v1/dataset/7":
        return httpx.Response(200, json={"result": {"columns": [{"column_name": c} for c in dataset_columns]}})
    return None


class ChartDataSuperset:
    """Superset answering the chart's saved query; `rows` is what the posted query returns."""

    def __init__(self, rows, colnames=("system_version", "bias_rate"), query_context=QUERY_CONTEXT,
                 dataset_columns=RUN_COLUMNS):
        self.rows, self.colnames = rows, list(colnames)
        self.query_context, self.dataset_columns = query_context, dataset_columns
        self.posted = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v1/security/login":
            return httpx.Response(200, json={"access_token": "tok"})
        assert request.headers.get("authorization") == "Bearer tok"
        read = superset_reads(path, self.query_context, self.dataset_columns)
        if read is not None:
            return read
        if request.method == "POST" and path.rstrip("/") == "/api/v1/chart/data":
            self.posted.append(json.loads(request.content))
            return httpx.Response(200, json={"result": [{"colnames": self.colnames, "data": self.rows}]})
        return httpx.Response(404)


def chart_data(fake):
    cls = need(S, "SupersetChartData")
    return cls(base_url="http://sup", username="aisc-report", password="pw",
               http=httpx.Client(transport=httpx.MockTransport(fake), base_url="http://sup"))


LOCAL_FILTER = {"col": "target_status", "op": "NOT IN", "val": ["local"]}


def test_chart_data_from_the_api():
    fake = ChartDataSuperset([{"system_version": 1, "bias_rate": 0.25}])
    assert chart_data(fake).data(33) == {"columns": ["system_version", "bias_rate"], "rows": [[1, 0.25]]}
    (posted,) = fake.posted
    assert posted["datasource"] == QUERY_CONTEXT["datasource"] and posted["result_format"] == "json"


def test_chart_data_leaves_out_runs_on_a_local_model_file():
    """The chart's query is asked again with a filter on its dataset's target_status: a run on a local
    model file never reaches a report, whatever the chart aggregates."""
    fake = ChartDataSuperset([{"system_version": 1, "bias_rate": 0.25}])
    chart_data(fake).data(33)
    (posted,) = fake.posted
    assert all(LOCAL_FILTER in q["filters"] for q in posted["queries"])


def test_chart_data_drops_a_local_row_the_query_still_returns():
    fake = ChartDataSuperset([{"system_version": 1, "target_status": "current"},
                              {"system_version": 1, "target_status": "local"}],
                             colnames=("system_version", "target_status"))
    assert chart_data(fake).data(33)["rows"] == [[1, "current"]]


def test_chart_data_of_a_dataset_without_runs_is_not_filtered():
    fake = ChartDataSuperset([{"question": "q1", "score": 4}], colnames=("question", "score"),
                             dataset_columns=("question", "score"))
    assert chart_data(fake).data(33)["rows"] == [["q1", 4]]
    assert all(LOCAL_FILTER not in q["filters"] for q in fake.posted[0]["queries"])


def test_a_chart_without_a_saved_query_has_no_data_table():
    fake = ChartDataSuperset([{"system_version": 1, "bias_rate": 0.25}], query_context=None)
    with pytest.raises(need(S, "ChartDataUnavailable")):
        chart_data(fake).data(33)
    assert fake.posted == []


# a screenshot cannot leave rows out: none of a chart on run data
def test_no_screenshot_of_a_chart_whose_dataset_holds_runs():
    fake = FakeSuperset(ready_after=1, dataset_columns=RUN_COLUMNS)
    p, _ = provider(fake)
    with pytest.raises(need(S, "ImageWouldShowLocalRuns")):
        p.image(33, 1200, 700)
    assert not [r for r in fake.requests if "cache_screenshot" in r.url.path]


def test_a_screenshot_would_show_local_runs_is_unavailable_not_disabled():
    error = need(S, "ImageWouldShowLocalRuns")
    assert issubclass(error, need(S, "ImagesUnavailable")) and not issubclass(error, need(S, "ImagesDisabled"))


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
        read = superset_reads(path, QUERY_CONTEXT, ("a",))
        if read is not None:
            return read
        if path.rstrip("/") == "/api/v1/chart/data":
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
