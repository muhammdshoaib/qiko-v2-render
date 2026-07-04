from app.modules.admin.customers import CustomerDirectory, CustomerRecord


def _dir():
    d = CustomerDirectory()
    d.add(CustomerRecord("u1", "alice@x.com", "pro", stripe_paid_cents=10000, local_paid_cents=8000))
    d.add(CustomerRecord("u2", "bob@x.com", "free", stripe_paid_cents=0, local_paid_cents=0))
    d.add(CustomerRecord("u3", "carol@x.com", "pro", stripe_paid_cents=3000, local_paid_cents=5000))
    return d


def test_earnings_is_higher_of_two_sources():
    assert CustomerRecord("u", "e", stripe_paid_cents=3000, local_paid_cents=5000).earnings_cents == 5000


def test_list_search_plan_and_sort():
    d = _dir()
    # sorted by earnings desc
    assert [r.user_id for r in d.list()["items"]] == ["u1", "u3", "u2"]
    # plan filter
    assert {r.user_id for r in d.list(plan="pro")["items"]} == {"u1", "u3"}
    # search
    res = d.list(search="bob")
    assert res["total"] == 1 and res["items"][0].user_id == "u2"


def test_pagination():
    d = _dir()
    page1 = d.list(page=1, page_size=2)
    assert page1["total"] == 3 and len(page1["items"]) == 2
    assert len(d.list(page=2, page_size=2)["items"]) == 1


def test_studio_toggle_and_soft_delete_anonymises():
    d = _dir()
    d.set_studio("u1", True)
    assert d.details("u1").is_studio is True
    d.soft_delete("u2")
    assert d.details("u2") is None                       # excluded once deleted
    assert "anonymized.invalid" in d._by_id["u2"].email  # PII anonymised
    assert all(r.user_id != "u2" for r in d.list()["items"])
