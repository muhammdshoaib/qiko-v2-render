from app.modules.admin.ga4 import GA4Analytics, top_by


class FakeGA4:
    def __init__(self, rows_by_start):
        self.rows_by_start = rows_by_start
        self.calls = []

    def run_report(self, start, end, metrics, dimensions):
        self.calls.append(start)
        return self.rows_by_start.get(start, [])


ROWS = [
    {"pagePath": "/", "sessions": 100, "activeUsers": 80},
    {"pagePath": "/pricing", "sessions": 40, "activeUsers": 35},
]


def test_dashboard_kpis_and_top_pages():
    ga = GA4Analytics(FakeGA4({"2026-07-01": ROWS}))
    d = ga.dashboard("2026-07-01", "2026-07-07")
    assert d["sessions"] == 140 and d["active_users"] == 115 and d["had_data"] is True
    assert d["top_pages"][0]["pagePath"] == "/"     # ranked by sessions


def test_resilient_shift_back_when_no_recent_data():
    ga = GA4Analytics(FakeGA4({"2026-06-01": ROWS}))  # only older window has data
    d = ga.dashboard("2026-07-01", "2026-07-07", fallback_start="2026-06-01")
    assert d["had_data"] is True and d["sessions"] == 140
    assert ga.gateway.calls == ["2026-07-01", "2026-06-01"]  # retried earlier window


def test_strict_mode_no_shift_back():
    ga = GA4Analytics(FakeGA4({"2026-06-01": ROWS}), strict=True)
    d = ga.dashboard("2026-07-01", "2026-07-07", fallback_start="2026-06-01")
    assert d["had_data"] is False and d["sessions"] == 0  # strict: no fallback


def test_top_by():
    assert top_by(ROWS, "pagePath", "sessions", n=1) == [{"pagePath": "/", "sessions": 100}]
