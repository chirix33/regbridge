from app.schemas import check_schemas


def test_committed_schema_artifacts_match_models() -> None:
    assert check_schemas() == []

