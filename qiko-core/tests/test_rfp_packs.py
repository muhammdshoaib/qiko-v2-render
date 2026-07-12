import pytest

from app.modules.rfp.service import RequirementService, RfpPackNotFound, RfpPackService

from tests.helpers import auth_cookies


# --- service-level ---
async def test_rfp_pack_lifecycle():
    svc = RfpPackService()
    pack = await svc.create("idg", "worker-1", "Tender BOC 2171", client_name="Basra Oil Company",
                            deadline="2026-07-12")
    assert pack.stage == "parsed"
    assert (await svc.list("idg"))[0].id == pack.id
    assert (await svc.list("idg", agent_id="other-worker")) == []

    updated = await svc.set_stage("idg", pack.id, "drafting")
    assert updated.stage == "drafting"

    with pytest.raises(ValueError):
        await svc.set_stage("idg", pack.id, "not-a-real-stage")

    with pytest.raises(RfpPackNotFound):
        await svc.get("idg", "missing")

    await svc.delete("idg", pack.id)
    assert await svc.list("idg") == []


async def test_rfp_pack_is_tenant_scoped():
    svc = RfpPackService()
    await svc.create("acme", "w1", "Acme tender")
    assert await svc.list("beta") == []
    with pytest.raises(RfpPackNotFound):
        pack = (await svc.list("acme"))[0]
        await svc.get("beta", pack.id)


# --- Win/Loss Analysis ---
async def test_set_outcome_won_and_lost():
    svc = RfpPackService()
    won = await svc.create("idg", "w1", "Won tender")
    lost = await svc.create("idg", "w1", "Lost tender")
    pending = await svc.create("idg", "w1", "Still pending")

    updated = await svc.set_outcome("idg", won.id, outcome="won", value=50000.0)
    assert updated.outcome == "won" and updated.outcome_value == 50000.0 and updated.outcome_at is not None

    await svc.set_outcome("idg", lost.id, outcome="lost", reason="price")
    refetched = await svc.get("idg", lost.id)
    assert refetched.outcome == "lost" and refetched.outcome_reason == "price"

    assert (await svc.get("idg", pending.id)).outcome is None


async def test_set_outcome_rejects_invalid_outcome_and_reason():
    svc = RfpPackService()
    pack = await svc.create("idg", "w1", "T")
    with pytest.raises(ValueError):
        await svc.set_outcome("idg", pack.id, outcome="bogus")
    with pytest.raises(ValueError):
        await svc.set_outcome("idg", pack.id, outcome="lost", reason="bogus-reason")


async def test_set_outcome_can_be_cleared():
    svc = RfpPackService()
    pack = await svc.create("idg", "w1", "T")
    await svc.set_outcome("idg", pack.id, outcome="lost", reason="price")
    cleared = await svc.set_outcome("idg", pack.id, outcome=None)
    assert cleared.outcome is None and cleared.outcome_at is None


async def test_stats_computes_win_rate_and_loss_reasons():
    svc = RfpPackService()
    for i in range(3):
        p = await svc.create("idg", "w1", f"Won {i}")
        await svc.set_outcome("idg", p.id, outcome="won", value=10000.0)
    for reason in ("price", "price", "technical"):
        p = await svc.create("idg", "w1", "Lost")
        await svc.set_outcome("idg", p.id, outcome="lost", reason=reason)
    await svc.create("idg", "w1", "Still drafting")  # pending, not decided

    stats = await svc.stats("idg")
    assert stats["won"] == 3 and stats["lost"] == 3 and stats["pending"] == 1
    assert stats["win_rate"] == 0.5
    assert stats["won_value"] == 30000.0
    assert stats["loss_reasons"] == {"price": 2, "technical": 1}


async def test_stats_with_no_decided_packs_has_null_win_rate():
    svc = RfpPackService()
    await svc.create("idg", "w1", "Still drafting")
    stats = await svc.stats("idg")
    assert stats["win_rate"] is None and stats["total_decided"] == 0


# --- API-level ---
def test_rfp_pack_api_crud(client):
    c = auth_cookies("rfpco", "owner")
    created = client.post("/api/v1/rfp/packs",
                          json={"agent_id": "w1", "title": "Tender A", "client_name": "Client A"},
                          cookies=c).json()
    assert created["stage"] == "parsed"

    listed = client.get("/api/v1/rfp/packs", cookies=c).json()
    assert len(listed) == 1 and listed[0]["id"] == created["id"]

    detail = client.get(f"/api/v1/rfp/packs/{created['id']}", cookies=c).json()
    assert detail["title"] == "Tender A"

    staged = client.put(f"/api/v1/rfp/packs/{created['id']}/stage", json={"stage": "review"},
                        cookies=c).json()
    assert staged["stage"] == "review"

    assert client.put(f"/api/v1/rfp/packs/{created['id']}/stage", json={"stage": "bogus"},
                      cookies=c).status_code == 422
    assert client.get("/api/v1/rfp/packs/missing", cookies=c).status_code == 404

    assert client.delete(f"/api/v1/rfp/packs/{created['id']}", cookies=c).json()["deleted"] == created["id"]
    assert client.get("/api/v1/rfp/packs", cookies=c).json() == []


def test_deleting_pack_also_deletes_its_requirements(client):
    c = auth_cookies("rfpco2", "owner")
    created = client.post("/api/v1/rfp/packs",
                          json={"agent_id": "w1", "title": "Tender B"}, cookies=c).json()
    pack_id = created["id"]

    reqs: RequirementService = client.app.state.requirements
    import asyncio
    asyncio.run(reqs.save_extracted("rfpco2", pack_id, [
        {"id": "1", "title": "Req one", "classification": "KB", "requirement": "text"},
    ]))
    assert len(client.get(f"/api/v1/rfp/packs/{pack_id}/requirements", cookies=c).json()) == 1

    client.delete(f"/api/v1/rfp/packs/{pack_id}", cookies=c)
    assert client.get(f"/api/v1/rfp/packs/{pack_id}/requirements", cookies=c).json() == []


def test_rfp_pack_write_requires_editor_role(client):
    r = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "x"},
                    cookies=auth_cookies("t", "viewer"))
    assert r.status_code == 403


def test_rfp_pack_scoped_to_tenant_via_api(client):
    c1 = auth_cookies("tenant1", "owner")
    c2 = auth_cookies("tenant2", "owner")
    client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "Tenant1 tender"}, cookies=c1)
    assert client.get("/api/v1/rfp/packs", cookies=c2).json() == []


def test_outcome_api_roundtrip_and_stats(client):
    c = auth_cookies("winlossco", "owner")
    won = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "Won deal"}, cookies=c).json()
    lost = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "Lost deal"}, cookies=c).json()

    r = client.put(f"/api/v1/rfp/packs/{won['id']}/outcome", json={"outcome": "won", "value": 25000}, cookies=c)
    assert r.status_code == 200 and r.json()["outcome"] == "won" and r.json()["outcome_value"] == 25000

    r = client.put(f"/api/v1/rfp/packs/{lost['id']}/outcome",
                   json={"outcome": "lost", "reason": "technical"}, cookies=c)
    assert r.status_code == 200 and r.json()["outcome_reason"] == "technical"

    bad = client.put(f"/api/v1/rfp/packs/{won['id']}/outcome", json={"outcome": "not-real"}, cookies=c)
    assert bad.status_code == 422

    missing = client.put("/api/v1/rfp/packs/does-not-exist/outcome", json={"outcome": "won"}, cookies=c)
    assert missing.status_code == 404

    stats = client.get("/api/v1/rfp/packs/stats", cookies=c).json()
    assert stats["won"] == 1 and stats["lost"] == 1 and stats["win_rate"] == 0.5


def test_outcome_write_requires_editor_role(client):
    c = auth_cookies("winlossco2", "owner")
    pack = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "T"}, cookies=c).json()
    viewer = auth_cookies("winlossco2", "viewer")
    r = client.put(f"/api/v1/rfp/packs/{pack['id']}/outcome", json={"outcome": "won"}, cookies=viewer)
    assert r.status_code == 403


def test_stats_is_tenant_scoped(client):
    c1 = auth_cookies("statst1", "owner")
    c2 = auth_cookies("statst2", "owner")
    pack = client.post("/api/v1/rfp/packs", json={"agent_id": "w1", "title": "T"}, cookies=c1).json()
    client.put(f"/api/v1/rfp/packs/{pack['id']}/outcome", json={"outcome": "won", "value": 999}, cookies=c1)

    assert client.get("/api/v1/rfp/packs/stats", cookies=c1).json()["won"] == 1
    assert client.get("/api/v1/rfp/packs/stats", cookies=c2).json()["won"] == 0
