def test_labs_contact_sends_email(client):
    resp = client.post("/api/v1/marketing/labs-contact", json={
        "name": "Jane Doe",
        "work_email": "jane@example.com",
        "company": "Acme Corp",
        "company_size": "51 - 250",
        "build_request": "A workflow agent for support triage.",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert "message" in body


def test_labs_contact_requires_valid_email(client):
    resp = client.post("/api/v1/marketing/labs-contact", json={
        "name": "Jane Doe",
        "work_email": "not-an-email",
        "company": "Acme Corp",
        "company_size": "51 - 250",
        "build_request": "A workflow agent for support triage.",
    })
    assert resp.status_code == 422


def test_labs_contact_requires_all_fields(client):
    resp = client.post("/api/v1/marketing/labs-contact", json={"name": "Jane Doe"})
    assert resp.status_code == 422
