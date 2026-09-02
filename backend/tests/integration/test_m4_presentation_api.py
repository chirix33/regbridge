from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_m4_presentation_endpoint_is_read_only_and_sanitized() -> None:
    response = client.get("/api/v1/presentation/m3")

    assert response.status_code == 200
    payload = response.json()["snapshot"]
    assert payload["source_run_id"] == "m3-live-phase2-20260901T170811002109Z"
    assert payload["current_fda_operational_availability"] == "not_operational"
    assert payload["expert_validated"] is False
    assert payload["completion_audit"]["completed_outcomes"] == 108
    assert "results/live/m3-live-phase2-20260901T170811002109Z" == payload["source_run_directory"]
    assert "response_id" not in response.text
    assert "final_json_text" not in response.text
    assert "C:\\" not in response.text


def test_m4_case_endpoint_rejects_unknown_and_traversal_case_ids() -> None:
    assert client.get("/api/v1/presentation/m3/cases/A002").status_code == 200
    assert client.get("/api/v1/presentation/m3/cases/UNKNOWN").status_code == 404

    traversal = client.get("/api/v1/presentation/m3/cases/..%2Fmanifest.json")
    assert traversal.status_code in {404, 422}


def test_demo_presets_are_fixture_mode_only_and_include_three_cases() -> None:
    response = client.get("/api/v1/demo/presets")

    assert response.status_code == 200
    presets = response.json()["presets"]
    assert {preset["route"] for preset in presets} == {
        "/demo/case-a",
        "/demo/case-b",
        "/demo/case-c",
    }
    assert all(preset["scenario_mode"] == "prospective_forward_compatibility" for preset in presets)

