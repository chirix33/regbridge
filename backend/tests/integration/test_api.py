from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from app.config import REPOSITORY_ROOT
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
    assert payload["operational_status"] == "not_operational"
    assert payload["expert_validated"] is False
    assert "not FDA-certified" in payload["disclaimer"]
    assert "not operational" in " ".join(payload["limitations"])


def test_standards_endpoint_redacts_local_path() -> None:
    response = client.get("/api/v1/standards/snapshots")

    assert response.status_code == 200
    payload = response.json()
    assert payload["snapshot_id"] == "fda-cder-demo-v1"
    assert payload["sources"][0]["review_status"] == "source_verified"
    assert payload["sources"][0]["expert_validated"] is False
    assert "local_path" not in payload["sources"][0]


def test_case_a_runs_through_parse_analysis_and_graph_endpoints() -> None:
    parsed = client.post(
        "/api/v1/applications/parse",
        params={"fixture_id": "case-a-removed-3211"},
    )
    assert parsed.status_code == 200
    inventory = parsed.json()
    assert inventory["leaves"][0]["heading"] == "3.2.S.1.1"

    analyzed = client.post(
        "/api/v1/analyses",
        json={
            "inventory_id": inventory["id"],
            "leaf_id": inventory["leaves"][0]["id"],
            "target_context": {
                "authority": "FDA",
                "center": "CDER",
                "application_type": "NDA",
                "source_standard": "eCTD-3.2.2",
                "target_standard": "eCTD-4.0",
                "analysis_date": "2026-08-29",
                "reuse_operation": "reference-existing-content",
                "standards_snapshot_id": "fda-cder-demo-v1",
                "scenario_mode": "prospective_forward_compatibility",
            },
        },
    )
    assert analyzed.status_code == 200
    result = analyzed.json()["analysis"]
    assert result["decision"] == "REUSE_WITH_NEW_CONTEXT"
    assert result["operational_status"] == "not_operational"
    assert len(result["evidence"]) == 4

    graph = client.get(f"/api/v1/analyses/{result['id']}/graph")
    assert graph.status_code == 200
    assert any(edge["type"] == "MAPS_TO" for edge in graph.json()["graph"]["edges"])


def test_raw_zip_upload_uses_the_same_parser_endpoint() -> None:
    fixture_root = REPOSITORY_ROOT / "data" / "demo-cases" / "case-a-clean-321"
    payload = BytesIO()
    with ZipFile(payload, "w", ZIP_DEFLATED) as archive:
        for path in fixture_root.rglob("*"):
            if path.is_file():
                archive.writestr(path.relative_to(fixture_root).as_posix(), path.read_bytes())

    response = client.post(
        "/api/v1/applications/parse",
        content=payload.getvalue(),
        headers={"Content-Type": "application/zip"},
    )
    assert response.status_code == 200
    assert response.json()["leaves"][0]["heading"] == "3.2.S.1"


def test_upload_rejects_unexpected_mime_type() -> None:
    response = client.post(
        "/api/v1/applications/parse",
        content=b"not a zip",
        headers={"Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 422
    assert "ZIP MIME type" in response.json()["detail"]
