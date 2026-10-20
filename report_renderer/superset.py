"""Chart images and chart data from Superset.

The stack's Superset cannot render screenshots, so the default image provider is
NoImageProvider; SupersetScreenshotProvider is used only when REPORT_CHART_IMAGES=superset.
No message ever carries the password or the access token.
"""
from __future__ import annotations

import threading
import time

import httpx


class ImagesUnavailable(Exception):
    """No image for this chart."""


class ImagesDisabled(ImagesUnavailable):
    """Chart images are switched off on this platform (not a failure)."""


class NoImageProvider:
    def image(self, chart_id, width, height) -> bytes:
        raise ImagesDisabled("Superset screenshots are not enabled")


class FakeImageProvider:
    def __init__(self, png: bytes):
        self.png = png

    def image(self, chart_id, width, height) -> bytes:
        return self.png


def _login(http, base_url, username, password) -> str:
    r = http.post(f"{base_url}/api/v1/security/login",
                  json={"username": username, "password": password, "provider": "db", "refresh": False})
    if r.status_code != 200:
        raise RuntimeError(f"Superset login answered {r.status_code}")
    token = r.json().get("access_token")
    if not token:
        raise RuntimeError("Superset login gave no access token")
    return token


class SupersetScreenshotProvider:
    def __init__(self, base_url, username, password, http=None, monotonic=time.monotonic, sleep=time.sleep,
                 timeout=30.0):
        self.base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._http = http or httpx.Client(timeout=30.0)
        self._monotonic = monotonic
        self._sleep = sleep
        self.timeout = timeout
        self._token = None
        self._lock = threading.Lock()

    def __repr__(self):
        return f"SupersetScreenshotProvider({self.base_url!r})"

    def _auth(self) -> dict:
        with self._lock:
            if self._token is None:
                try:
                    self._token = _login(self._http, self.base_url, self._username, self._password)
                except (httpx.HTTPError, ValueError, RuntimeError) as exc:
                    raise ImagesUnavailable(f"Superset login failed ({type(exc).__name__})") from None
            return {"Authorization": f"Bearer {self._token}"}

    def _get(self, url, **kwargs):
        """A GET with the token; a 401 (the token expired) logs in again and asks once more."""
        r = self._http.get(url, headers=self._auth(), **kwargs)
        if r.status_code == 401:
            with self._lock:
                self._token = None
            r = self._http.get(url, headers=self._auth(), **kwargs)
        return r

    def image(self, chart_id, width, height) -> bytes:
        start = self._monotonic()
        q = f"(window_size:!({int(width)},{int(height)}),thumb_size:!({int(width)},{int(height)}))"
        try:
            r = self._get(f"{self.base_url}/api/v1/chart/{int(chart_id)}/cache_screenshot/", params={"q": q})
        except httpx.HTTPError as exc:
            raise ImagesUnavailable(f"Superset did not answer ({type(exc).__name__})") from None
        if r.status_code not in (200, 202):
            raise ImagesUnavailable(f"Superset answered {r.status_code} to the screenshot request")
        try:
            image_url = r.json()["image_url"]
        except (ValueError, KeyError, TypeError):
            raise ImagesUnavailable("Superset gave no image URL") from None
        while True:
            if self._monotonic() > start + self.timeout:
                raise ImagesUnavailable(f"no chart image within {self.timeout:g} s")
            try:
                img = self._get(image_url)
            except httpx.HTTPError as exc:
                raise ImagesUnavailable(f"Superset did not answer ({type(exc).__name__})") from None
            if img.status_code == 200 and img.headers.get("content-type", "").startswith("image/"):
                return img.content
            if img.status_code in (202, 404):
                self._sleep(1)
                continue
            raise ImagesUnavailable(f"Superset answered {img.status_code} for the chart image")


class BoundedImages:
    """At most `limit` image fetches at a time."""

    def __init__(self, inner, limit=3):
        self.inner = inner
        self._sem = threading.BoundedSemaphore(limit)

    def image(self, chart_id, width, height) -> bytes:
        with self._sem:
            return self.inner.image(chart_id, width, height)


class ChartDataUnavailable(Exception):
    """No data table for this chart."""


class NoChartData:
    def data(self, chart_id) -> dict:
        raise ChartDataUnavailable("chart data is not configured")


class FakeChartData:
    def __init__(self, columns, rows):
        self.columns, self.rows = list(columns), [list(r) for r in rows]

    def data(self, chart_id) -> dict:
        return {"columns": list(self.columns), "rows": [list(r) for r in self.rows]}


class SupersetChartData:
    MAX_ROWS = 50

    def __init__(self, base_url, username, password, http=None):
        self.base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._http = http or httpx.Client(timeout=30.0)
        self._token = None

    def __repr__(self):
        return f"SupersetChartData({self.base_url!r})"

    def data(self, chart_id) -> dict:
        try:
            url = f"{self.base_url}/api/v1/chart/{int(chart_id)}/data/"
            for _ in range(2):                                        # a 401: the token expired, log in again
                if self._token is None:
                    self._token = _login(self._http, self.base_url, self._username, self._password)
                r = self._http.get(url, params={"format": "json"}, headers={"Authorization": f"Bearer {self._token}"})
                if r.status_code != 401:
                    break
                self._token = None
            if r.status_code != 200:
                raise ChartDataUnavailable(f"Superset answered {r.status_code} for the chart data")
            result = r.json()["result"][0]
            columns = list(result["colnames"])
            rows = []
            for row in result["data"][: self.MAX_ROWS]:
                rows.append([row.get(c) for c in columns] if isinstance(row, dict) else list(row))
            return {"columns": columns, "rows": rows}
        except ChartDataUnavailable:
            raise
        except Exception as exc:
            raise ChartDataUnavailable(f"no chart data ({type(exc).__name__})") from None


def image_provider_from_env(env):
    if env.get("REPORT_CHART_IMAGES") == "superset":
        return SupersetScreenshotProvider(env["REPORT_SUPERSET_URL"], env.get("REPORT_SUPERSET_USER", "aisc-report"),
                                          env.get("REPORT_SUPERSET_PASSWORD", ""))
    return NoImageProvider()


def chart_data_from_env(env):
    if env.get("REPORT_SUPERSET_URL") and env.get("REPORT_SUPERSET_USER") and env.get("REPORT_SUPERSET_PASSWORD"):
        return SupersetChartData(env["REPORT_SUPERSET_URL"], env["REPORT_SUPERSET_USER"],
                                 env["REPORT_SUPERSET_PASSWORD"])
    return NoChartData()
