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
