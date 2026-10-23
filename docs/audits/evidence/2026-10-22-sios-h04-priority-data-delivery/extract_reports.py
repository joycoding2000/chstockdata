"""Extract issuer reports locally, keeping page identities for audit."""
from __future__ import annotations

import json
import io
import re
import zipfile
from xml.etree import ElementTree
from pathlib import Path


def report_pdf_bytes(body):
    if body.startswith(b"PK\x03\x04"):
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            members = [m for m in archive.infolist() if m.filename.lower().endswith(".pdf")]
            if len(members) != 1:
                raise ValueError("report archive must contain exactly one PDF")
            if members[0].file_size > 40_000_000:
                raise ValueError("report archive exceeds local extraction limit")
            body = archive.read(members[0])
    if not body.startswith(b"%PDF-"):
        raise ValueError("report response is not a PDF")
    return body


def report_text_blocks(body):
    if body.startswith(b"PK\x03\x04"):
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            if "word/document.xml" in archive.namelist():
                if archive.getinfo("word/document.xml").file_size > 40_000_000:
                    raise ValueError("Word report exceeds local extraction limit")
                tree = ElementTree.fromstring(archive.read("word/document.xml"))
                ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                blocks = []
                for child in tree.find("w:body", ns):
                    if child.tag.endswith("}tbl"):
                        blocks.append("\n".join(
                            "\t".join("".join(cell.itertext()) for cell in row.findall("w:tc", ns))
                            for row in child.findall("w:tr", ns)
                        ))
                    else:
                        blocks.append("".join(t.text or "" for t in child.findall(".//w:t", ns)))
                return "ooxml_body_block", blocks
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise SystemExit("Optional pypdf is required only for report extraction") from exc
    return "pdf_page", [p.extract_text() for p in PdfReader(io.BytesIO(report_pdf_bytes(body))).pages]


def main():
    root = Path(__file__).resolve().parent
    out = root / "extracted"
    out.mkdir(exist_ok=True)
    for source in sorted((root / "sources").glob("*-official-annual.raw")):
        kind, pages = report_text_blocks(source.read_bytes())
        (out / (source.stem + ".json")).write_text(
            json.dumps({"source_file": source.name, "locator_kind": kind, "blocks": pages}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(source.name, len(pages), kind)
        for index, text in enumerate(pages):
            compact = re.sub(r"\s+", "", text)
            phrases = ("过去三年基金的利润分配", "本报告期的利润分配", "7.4.11利润分配", "7.4.7.7实收基金", "基金份额折算变动份额", "份额折算", "未进行收益分配", "未进行利润分配")
            hits = [compact[max(0, compact.find(phrase) - 40):compact.find(phrase) + 350] for phrase in phrases if phrase in compact]
            if hits and index > 4:
                print(kind, index + 1, " | ".join(hits))


if __name__ == "__main__":
    main()
