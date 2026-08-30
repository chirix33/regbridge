from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "data" / "demo-cases"

FIXTURES = {
    "case-b-normalize-all": {
        "leaf": "leaf-b-normalize-all",
        "title": "Manufacturer overview - normalize metadata",
        "text": "Current manufacturer overview for Northstar Therapeutics. No embedded hyperlinks.",
        "attributes": 'manufacturer="all"',
    },
    "case-b-preserve-all": {
        "leaf": "leaf-b-preserve-all",
        "title": "Manufacturer overview - preserve lifecycle",
        "text": "Current manufacturer overview for Northstar Therapeutics. No embedded hyperlinks.",
        "attributes": 'manufacturer="all"',
    },
    "case-b-unspecified-all": {
        "leaf": "leaf-b-unspecified-all",
        "title": "Manufacturer overview - intent unspecified",
        "text": "Current manufacturer overview for Northstar Therapeutics. No embedded hyperlinks.",
        "attributes": 'manufacturer=" ALL "',
    },
    "case-b-clean-specific": {
        "leaf": "leaf-b-clean-specific",
        "title": "Manufacturer overview - stable value",
        "text": "Manufacturing information for Northstar River Site. No embedded hyperlinks.",
        "attributes": 'manufacturer="Northstar River Site"',
    },
    "case-b-out-of-scope-product-all": {
        "leaf": "leaf-b-product-all",
        "title": "Product keyword control",
        "text": "Product overview using an out-of-scope keyword for this rule.",
        "attributes": 'product="all"',
    },
    "case-c-stale-heading": {
        "leaf": "leaf-c-stale-heading",
        "title": "Stale internal heading",
        "text": "See legacy section 3.2.S.1.1 Name and Nomenclature for the controlling description.",
        "attributes": "",
    },
    "case-c-stale-applicant": {
        "leaf": "leaf-c-stale-applicant",
        "title": "Stale applicant name",
        "text": "Prepared for Old Applicant Laboratories. This dossier now targets Northstar Therapeutics.",
        "attributes": "",
    },
    "case-c-irrelevant-link": {
        "leaf": "leaf-c-irrelevant-link",
        "title": "Legacy external hyperlink",
        "text": "The legacy applicant portal is linked below for the former dossier context.",
        "attributes": "",
        "url": "https://legacy.example.invalid/old-applicant/3.2.S.1.1",
    },
    "case-c-clean": {
        "leaf": "leaf-c-clean",
        "title": "Current clean content",
        "text": "Northstar Therapeutics general drug substance information for section 3.2.S.1.",
        "attributes": "",
    },
    "case-c-ambiguous": {
        "leaf": "leaf-c-ambiguous",
        "title": "Ambiguous historical wording",
        "text": "Prior placement may have differed; confirm whether the referenced description remains current.",
        "attributes": "",
    },
    "case-c-relevant-link": {
        "leaf": "leaf-c-relevant-link",
        "title": "Verified relevant internal link",
        "text": "See the supporting details on the next page in this current document.",
        "attributes": "",
        "internal_link": True,
    },
}


def write_pdf(path: Path, title: str, text: str, url: str | None, internal: bool) -> None:
    pdf = canvas.Canvas(str(path), pagesize=letter, pageCompression=0)
    pdf.setTitle(title)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(72, 730, title)
    pdf.setFont("Helvetica", 11)
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > 82:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    y = 690
    for line in lines:
        pdf.drawString(72, y, line)
        y -= 18
    if url:
        pdf.setFillColorRGB(0.05, 0.25, 0.65)
        pdf.drawString(72, y - 18, "Open legacy applicant portal")
        pdf.linkURL(url, (72, y - 22, 250, y - 6), relative=0)
    if internal:
        pdf.setFillColorRGB(0.05, 0.25, 0.65)
        pdf.drawString(72, y - 18, "Go to supporting details")
        pdf.linkRect("", "supporting-details", (72, y - 22, 220, y - 6), relative=0)
        pdf.showPage()
        pdf.bookmarkPage("supporting-details")
        pdf.setFont("Helvetica-Bold", 16)
        pdf.drawString(72, 730, "Supporting details")
        pdf.setFont("Helvetica", 11)
        pdf.drawString(72, 690, "Current supporting information for Northstar Therapeutics.")
    pdf.save()


def main() -> None:
    for fixture_id, item in FIXTURES.items():
        directory = CASES / fixture_id
        documents = directory / "documents"
        documents.mkdir(parents=True, exist_ok=True)
        pdf_name = f"{fixture_id}.pdf"
        write_pdf(
            documents / pdf_name,
            item["title"],
            item["text"],
            item.get("url"),
            bool(item.get("internal_link")),
        )
        attributes = f" {item['attributes']}" if item["attributes"] else ""
        (directory / "index.xml").write_text(
            "\n".join(
                (
                    '<?xml version="1.0" encoding="UTF-8"?>',
                    '<ectd:ectd xmlns:ectd="urn:ich:ectd:v3.2.2" '
                    'xmlns:xlink="http://www.w3.org/1999/xlink">',
                    f"  <m3-2-s-1{attributes}>",
                    f'    <leaf ID="{item["leaf"]}" operation="new" '
                    f'xlink:href="documents/{pdf_name}">',
                    f"      <title>{escape(item['title'])}</title>",
                    "    </leaf>",
                    "  </m3-2-s-1>",
                    "</ectd:ectd>",
                    "",
                )
            ),
            encoding="utf-8",
        )
        (directory / "us-regional.xml").write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<regional:us-regional xmlns:regional="urn:fda:us-regional">
  <application-number>123456</application-number>
  <submission-type>original</submission-type>
  <applicant-name>Northstar Therapeutics</applicant-name>
</regional:us-regional>
""",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
