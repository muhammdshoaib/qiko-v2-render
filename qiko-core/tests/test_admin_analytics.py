from app.modules.admin.analytics import period_change_pct, revenue_report, top_customers
from app.modules.admin.metrics import Subscription
from app.modules.billing.webhook import Invoice


def test_period_change_pct():
    assert period_change_pct(150, 100) == 50.0
    assert period_change_pct(80, 100) == -20.0
    assert period_change_pct(50, 0) == 100.0
    assert period_change_pct(0, 0) == 0.0


def test_top_customers_by_paid_total():
    invs = [
        Invoice("in1", "cus_a", 5000, "paid"),
        Invoice("in2", "cus_a", 3000, "paid"),
        Invoice("in3", "cus_b", 10000, "paid"),
        Invoice("in4", "cus_c", 9999, "void"),   # not paid -> excluded
    ]
    top = top_customers(invs, n=2)
    assert top[0] == {"customer_id": "cus_b", "paid_cents": 10000}
    assert top[1] == {"customer_id": "cus_a", "paid_cents": 8000}


def test_revenue_report_wraps_base_metrics():
    subs = [Subscription("c1", "pro", 5000, "month", "active"),
            Subscription("c2", "enterprise", 120000, "year", "active")]  # 10000/mo
    invs = [Invoice("in1", "c1", 5000, "paid")]
    report = revenue_report(subs, invs, previous_mrr_cents=10000)
    assert report["mrr_cents"] == 15000.0                 # reused from revenue_metrics, not re-derived
    assert report["mrr_change_pct"] == 50.0               # 10000 -> 15000
    assert report["top_customers"][0]["customer_id"] == "c1"
    assert report["paid_invoice_total_cents"] == 5000
