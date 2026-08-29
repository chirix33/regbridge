from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health_reports_fixture_mode_without_secrets() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "regbridge",
        "version": "0.1.0",
        "model_mode": "fixture",
        "standards_snapshot_id": "fda-cder-demo-v1",
    }
    assert "key" not in response.text.lower()


def test_scope_endpoint_exposes_boundary_and_disclaimer() -> None:
    response = client.get("/api/v1/config/scope")

    assert response.status_code == 200
    payload = response.json()
    assert payload["authority"] == "FDA"
    assert payload["center"] == "CDER"
    assert payload["supported_application_types"] == ["NDA"]
    assert payload["network_required"] is False
    assert "not FDA-certified" in payload["disclaimer"]
    assert "M0" in " ".join(payload["limitations"])


def test_standards_endpoint_redacts_local_path() -> None:
    response = client.get("/api/v1/standards/snapshots")

    assert response.status_code == 200
    payload = response.json()
    assert payload["snapshot_id"] == "fda-cder-demo-v1"
    assert payload["sources"][0]["review_status"] == "reviewed"
    assert "local_path" not in payload["sources"][0]

