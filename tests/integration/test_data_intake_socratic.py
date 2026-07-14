from src.frontend_api.dataset_service import DatasetService


def test_ambiguous_intake_asks_one_socratic_question_then_builds_manifest(tmp_path):
    service = DatasetService(output_root=str(tmp_path / "standardized"))

    inspection = service.inspect_path("tests/fixtures/data_intake/ambiguous")

    assert inspection.ready is False
    assert inspection.unresolved_questions == [
        "请确认标签列：groups.csv 中是否使用 status 作为分组标签？"
    ]

    answered = service.answer_clarification(
        inspection.session_id,
        "是，status 是标签列，tumor 为阳性，normal 为阴性",
    )
    manifest = service.build_manifest(answered.session_id)

    assert answered.ready is True
    assert manifest.label_col == "status"
    assert manifest.positive_label == "tumor"
    assert manifest.negative_label == "normal"
