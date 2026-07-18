from io import BytesIO
from zipfile import ZipFile

from docx import Document

from document_rendering import render_docx_bytes


def test_docx_output_opens_and_preserves_expected_structure():
    content = render_docx_bytes(
        {
            "title": "The Holy Eucharist",
            "rite": "Renewed Ancient Text",
            "service_title": "First Sunday of Epiphanytide",
            "service_date_display": "January 11, 2026",
            "generated_at_display": "January 1, 2026 at 10:00 AM",
            "ordinaries": [
                {
                    "type": "ordinary",
                    "show_title": True,
                    "title_inline_html": "The Collect",
                    "body_html": (
                        "<p><em>Celebrant</em> The Lord be with you.</p>"
                        "<p><strong>People</strong> And with your spirit.</p>"
                    ),
                }
            ],
        }
    )

    assert content.startswith(b"PK\x03\x04")
    with ZipFile(BytesIO(content)) as archive:
        names = set(archive.namelist())
        assert "[Content_Types].xml" in names
        assert "word/document.xml" in names
        assert "word/styles.xml" in names

    document = Document(BytesIO(content))
    paragraphs = [paragraph.text for paragraph in document.paragraphs]
    assert paragraphs[:4] == [
        "The Holy Eucharist\nRenewed Ancient Text",
        "First Sunday of Epiphanytide",
        "The Collect",
        "Celebrant The Lord be with you.",
    ]
    assert "People And with your spirit." in paragraphs
    assert paragraphs[-1].endswith("Generated as of January 1, 2026 at 10:00 AM")
