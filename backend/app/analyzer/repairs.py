from app.domain.models import RuntimeRepairAction


def complete_document_inspection_action() -> RuntimeRepairAction:
    """Return the runtime-only action for a valid semantic abstention gate."""

    return RuntimeRepairAction(
        type="COMPLETE_DOCUMENT_INSPECTION",
        description=(
            "Complete the bounded semantic inspection before deciding whether the document "
            "content is eligible for legacy reference reuse."
        ),
    )
