from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "data" / "demo-cases"


def write_pdf(path: Path, title: str, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(path), pagesize=letter, pageCompression=0)
    pdf.setTitle(title)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(72, 730, title)
    pdf.setFont("Helvetica", 11)
    words = text.split()
    line = ""
    y = 690
    for word in words:
        candidate = f"{line} {word}".strip()
        if len(candidate) > 82:
            pdf.drawString(72, y, line)
            y -= 18
            line = word
        else:
            line = candidate
    if line:
        pdf.drawString(72, y, line)
    pdf.save()


def regional_xml(application_number: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<regional:us-regional xmlns:regional="urn:fda:us-regional">
  <application-number>{application_number}</application-number>
  <submission-type>original</submission-type>
  <applicant-name>Northstar Therapeutics</applicant-name>
</regional:us-regional>
"""


def write_case(
    fixture_id: str,
    *,
    heading_tag: str,
    leaves: tuple[dict[str, str], ...],
    application_number: str,
) -> None:
    directory = CASES / fixture_id
    directory.mkdir(parents=True, exist_ok=True)
    rendered_leaves: list[str] = []
    for leaf in leaves:
        pdf_name = f"{leaf['id']}.pdf"
        write_pdf(directory / "documents" / pdf_name, leaf["title"], leaf["text"])
        modified = (
            f' modified-file="{leaf["modified_file"]}"'
            if leaf.get("modified_file")
            else ""
        )
        rendered_leaves.extend(
            (
                f'    <leaf ID="{leaf["id"]}" operation="{leaf["operation"]}"{modified} '
                f'xlink:href="documents/{pdf_name}">',
                f"      <title>{escape(leaf['title'])}</title>",
                "    </leaf>",
            )
        )
    index = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<ectd:ectd xmlns:ectd="urn:ich:ectd:v3.2.2" '
        'xmlns:xlink="http://www.w3.org/1999/xlink">',
        f"  <{heading_tag}>",
        *rendered_leaves,
        f"  </{heading_tag}>",
        "</ectd:ectd>",
        "",
    ]
    (directory / "index.xml").write_text("\n".join(index), encoding="utf-8")
    (directory / "us-regional.xml").write_text(
        regional_xml(application_number), encoding="utf-8"
    )


def main() -> None:
    write_case(
        "case-a-004-replacement-3211",
        heading_tag="m3-2-s-1-1",
        application_number="930004",
        leaves=(
            {
                "id": "leaf-a004-predecessor",
                "operation": "new",
                "title": "Original substance name description",
                "text": "Original synthetic substance name description for lifecycle history.",
            },
            {
                "id": "leaf-a004-selected",
                "operation": "replace",
                "modified_file": "leaf-a004-predecessor",
                "title": "Replacement substance name description",
                "text": "Replacement synthetic content remains located under legacy heading 3.2.S.1.1.",
            },
        ),
    )
    write_case(
        "case-a-005-append-3212",
        heading_tag="m3-2-s-1-2",
        application_number="930005",
        leaves=(
            {
                "id": "leaf-a005-predecessor",
                "operation": "new",
                "title": "Original properties description",
                "text": "Original synthetic properties description for lifecycle history.",
            },
            {
                "id": "leaf-a005-selected",
                "operation": "append",
                "modified_file": "leaf-a005-predecessor",
                "title": "Appended properties description",
                "text": "Appended synthetic content remains located under legacy heading 3.2.S.1.2.",
            },
        ),
    )
    write_case(
        "case-a-007-valid-replacement-321",
        heading_tag="m3-2-s-1",
        application_number="930007",
        leaves=(
            {
                "id": "leaf-a007-predecessor",
                "operation": "new",
                "title": "Original general information",
                "text": "Original general drug substance information for lifecycle history.",
            },
            {
                "id": "leaf-a007-selected",
                "operation": "replace",
                "modified_file": "leaf-a007-predecessor",
                "title": "Replacement general information",
                "text": "Replacement content remains under available target heading 3.2.S.1.",
            },
        ),
    )
    write_case(
        "case-a-009-unmapped-3215",
        heading_tag="m3-2-s-1-5",
        application_number="930009",
        leaves=(
            {
                "id": "leaf-a009-selected",
                "operation": "new",
                "title": "Unsupported synthetic subheading",
                "text": "Synthetic content is located under unverified heading 3.2.S.1.5.",
            },
        ),
    )
    write_case(
        "case-c-007-stale-heading-3212",
        heading_tag="m3-2-s-1",
        application_number="940007",
        leaves=(
            {
                "id": "leaf-c007-selected",
                "operation": "new",
                "title": "Stale properties heading instruction",
                "text": (
                    "Use section 3.2.S.1.2 Properties as the current controlling location for "
                    "this material."
                ),
            },
        ),
    )
    write_case(
        "case-c-008-stale-responsible-applicant",
        heading_tag="m3-2-s-1",
        application_number="940008",
        leaves=(
            {
                "id": "leaf-c008-selected",
                "operation": "new",
                "title": "Responsible applicant statement",
                "text": (
                    "Legacy Northstar Holdings is the current responsible applicant for this "
                    "submission."
                ),
            },
        ),
    )
    write_case(
        "case-c-009-benign-heading-history",
        heading_tag="m3-2-s-1",
        application_number="940009",
        leaves=(
            {
                "id": "leaf-c009-selected",
                "operation": "new",
                "title": "Historical heading note",
                "text": (
                    "In a 2022 dossier this material appeared under 3.2.S.1.1. That statement "
                    "is historical only and is not current placement guidance."
                ),
            },
        ),
    )


if __name__ == "__main__":
    main()
