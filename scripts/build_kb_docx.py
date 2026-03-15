"""Generate a minimal .docx file from the admissions knowledge text document.

Usage:
  a:/IIST-AdmissionChatBot/.venv/Scripts/python.exe scripts/build_kb_docx.py
"""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile


def _content_types_xml() -> str:
    return """<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>
<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">
  <Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>
  <Default Extension=\"xml\" ContentType=\"application/xml\"/>
  <Override PartName=\"/word/document.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml\"/>
  <Override PartName=\"/docProps/core.xml\" ContentType=\"application/vnd.openxmlformats-package.core-properties+xml\"/>
  <Override PartName=\"/docProps/app.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.extended-properties+xml\"/>
</Types>
"""


def _rels_xml() -> str:
    return """<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>
<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">
  <Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"word/document.xml\"/>
  <Relationship Id=\"rId2\" Type=\"http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties\" Target=\"docProps/core.xml\"/>
  <Relationship Id=\"rId3\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties\" Target=\"docProps/app.xml\"/>
</Relationships>
"""


def _document_xml(lines: list[str]) -> str:
    paragraphs = []
    for line in lines:
        if not line.strip():
            paragraphs.append("<w:p/>")
            continue
        text = escape(line)
        paragraphs.append(f"<w:p><w:r><w:t xml:space=\"preserve\">{text}</w:t></w:r></w:p>")

    body = "\n    ".join(paragraphs)
    return f"""<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>
<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\">
  <w:body>
    {body}
    <w:sectPr>
      <w:pgSz w:w=\"12240\" w:h=\"15840\"/>
      <w:pgMar w:top=\"1440\" w:right=\"1440\" w:bottom=\"1440\" w:left=\"1440\" w:header=\"708\" w:footer=\"708\" w:gutter=\"0\"/>
    </w:sectPr>
  </w:body>
</w:document>
"""


def _core_xml() -> str:
    return """<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>
<cp:coreProperties
  xmlns:cp=\"http://schemas.openxmlformats.org/package/2006/metadata/core-properties\"
  xmlns:dc=\"http://purl.org/dc/elements/1.1/\"
  xmlns:dcterms=\"http://purl.org/dc/terms/\"
  xmlns:dcmitype=\"http://purl.org/dc/dcmitype/\"
  xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\">
  <dc:title>IIST Admissions Knowledge Document</dc:title>
  <dc:creator>GitHub Copilot</dc:creator>
  <cp:lastModifiedBy>GitHub Copilot</cp:lastModifiedBy>
</cp:coreProperties>
"""


def _app_xml() -> str:
    return """<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>
<Properties xmlns=\"http://schemas.openxmlformats.org/officeDocument/2006/extended-properties\"
  xmlns:vt=\"http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes\">
  <Application>Microsoft Office Word</Application>
</Properties>
"""


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    source = root / "backend" / "chatbot" / "knowledge_base_document.txt"
    output = root / "docs" / "IIST_Admissions_KB.docx"
    output.parent.mkdir(parents=True, exist_ok=True)

    lines = source.read_text(encoding="utf-8").splitlines()

    with ZipFile(output, "w", compression=ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _content_types_xml())
        zf.writestr("_rels/.rels", _rels_xml())
        zf.writestr("word/document.xml", _document_xml(lines))
        zf.writestr("docProps/core.xml", _core_xml())
        zf.writestr("docProps/app.xml", _app_xml())

    print(f"Generated: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
