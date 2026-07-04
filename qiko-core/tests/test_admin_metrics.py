from app.modules.admin.metrics import Subscription, revenue_metrics


def test_revenue_metrics_from_single_source():
    subs = [
        Subscription("c1", "pro", 5000, "month", "active"),
        Subscription("c2", "pro", 5000, "month", "active"),
        Subscription("c3", "enterprise", 120000, "year", "active"),  # 10000/mo
        Subscription("c4", "pro", 5000, "month", "canceled"),        # excluded
    ]
    m = revenue_metrics(subs)
    assert m["active_subscriptions"] == 3
    assert m["mrr_cents"] == 20000.0            # 5000 + 5000 + 10000
    assert m["arpu_cents"] == round(20000 / 3, 2)
    assert m["plan_distribution"] == {"pro": 2, "enterprise": 1}


def test_revenue_metrics_empty():
    m = revenue_metrics([])
    assert m["mrr_cents"] == 0 and m["arpu_cents"] == 0.0 and m["active_subscriptions"] == 0
