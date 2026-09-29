from __future__ import annotations

import csv
import html
import io
import time
import zipfile
from pathlib import Path
from typing import Any

from .base import Tool, ToolRegistry
from ..workspace import Workspace


def xml_escape(s: Any) -> str:
    return html.escape(str(s), quote=True)


def write_zip_text(z: zipfile.ZipFile, name: str, text: str) -> None:
    z.writestr(name, text.encode("utf-8"))


def create_docx_file(path: Path, title: str, paragraphs: list[str]) -> None:
    body = []
    if title:
        body.append(f'<w:p><w:pPr><w:pStyle w:val="Title"/></w:pPr><w:r><w:t>{xml_escape(title)}</w:t></w:r></w:p>')
    for p in paragraphs:
        lines = str(p).split("\n") or [""]
        runs = []
        for i, line in enumerate(lines):
            if i:
                runs.append("<w:br/>")
            runs.append(f'<w:t xml:space="preserve">{xml_escape(line)}</w:t>')
        body.append("<w:p><w:r>" + "".join(runs) + "</w:r></w:p>")
    document_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{''.join(body)}<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr></w:body></w:document>'''
    styles_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:rPr><w:b/><w:sz w:val="36"/></w:rPr></w:style></w:styles>'''
    content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>'''
    rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'''
    doc_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'''
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        write_zip_text(z, "[Content_Types].xml", content_types)
        write_zip_text(z, "_rels/.rels", rels)
        write_zip_text(z, "word/document.xml", document_xml)
        write_zip_text(z, "word/styles.xml", styles_xml)
        write_zip_text(z, "word/_rels/document.xml.rels", doc_rels)


def create_xlsx_file(path: Path, sheets: list[dict[str, Any]]) -> None:
    if not sheets:
        sheets = [{"name": "Sheet1", "rows": []}]
    content_overrides = []
    workbook_sheets = []
    workbook_rels = []
    sheet_xmls = []
    for idx, sheet in enumerate(sheets, 1):
        name = str(sheet.get("name") or f"Sheet{idx}")[:31]
        rows = sheet.get("rows") or []
        workbook_sheets.append(f'<sheet name="{xml_escape(name)}" sheetId="{idx}" r:id="rId{idx}"/>')
        workbook_rels.append(f'<Relationship Id="rId{idx}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{idx}.xml"/>')
        content_overrides.append(f'<Override PartName="/xl/worksheets/sheet{idx}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
        row_xml = []
        for r_i, row in enumerate(rows, 1):
            cells = []
            for c_i, value in enumerate(row, 1):
                col = ""
                n = c_i
                while n:
                    n, rem = divmod(n - 1, 26)
                    col = chr(65 + rem) + col
                cell_ref = f"{col}{r_i}"
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    cells.append(f'<c r="{cell_ref}"><v>{value}</v></c>')
                else:
                    cells.append(f'<c r="{cell_ref}" t="inlineStr"><is><t>{xml_escape(value)}</t></is></c>')
            row_xml.append(f'<row r="{r_i}">{"".join(cells)}</row>')
        sheet_xmls.append(f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{''.join(row_xml)}</sheetData></worksheet>''')
    content_types = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>{''.join(content_overrides)}</Types>'''
    root_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'''
    workbook = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>{''.join(workbook_sheets)}</sheets></workbook>'''
    workbook_rels_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{''.join(workbook_rels)}</Relationships>'''
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        write_zip_text(z, "[Content_Types].xml", content_types)
        write_zip_text(z, "_rels/.rels", root_rels)
        write_zip_text(z, "xl/workbook.xml", workbook)
        write_zip_text(z, "xl/_rels/workbook.xml.rels", workbook_rels_xml)
        for idx, xml in enumerate(sheet_xmls, 1):
            write_zip_text(z, f"xl/worksheets/sheet{idx}.xml", xml)


def slide_xml(title: str, bullets: list[str]) -> str:
    bullet_paras = []
    for b in bullets:
        bullet_paras.append(f'<a:p><a:r><a:t>{xml_escape(b)}</a:t></a:r></a:p>')
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr><p:sp><p:nvSpPr><p:cNvPr id="2" name="Title"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="685800" y="457200"/><a:ext cx="7772400" cy="914400"/></a:xfrm></p:spPr><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr sz="3600" b="1"/><a:t>{xml_escape(title)}</a:t></a:r></a:p></p:txBody></p:sp><p:sp><p:nvSpPr><p:cNvPr id="3" name="Content"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="914400" y="1600200"/><a:ext cx="7315200" cy="4343400"/></a:xfrm></p:spPr><p:txBody><a:bodyPr/><a:lstStyle/>{''.join(bullet_paras)}</p:txBody></p:sp></p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>'''


def create_pptx_file(path: Path, title: str, slides: list[dict[str, Any]]) -> None:
    if not slides:
        slides = [{"title": title or "Slide 1", "bullets": []}]
    overrides = [
        '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>',
        '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>',
        '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>',
        '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>',
    ]
    sld_ids = []
    pres_rels = ['<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>']
    for i, _ in enumerate(slides, 1):
        overrides.append(f'<Override PartName="/ppt/slides/slide{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>')
        rid = i + 1
        sld_ids.append(f'<p:sldId id="{255+i}" r:id="rId{rid}"/>')
        pres_rels.append(f'<Relationship Id="rId{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{i}.xml"/>')
    content_types = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>{''.join(overrides)}</Types>'''
    root_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/></Relationships>'''
    presentation = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst><p:sldIdLst>{''.join(sld_ids)}</p:sldIdLst><p:sldSz cx="9144000" cy="6858000" type="screen4x3"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>'''
    pres_rels_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{''.join(pres_rels)}</Relationships>'''
    theme = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="LocalArena"><a:themeElements><a:clrScheme name="Office"><a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1><a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1><a:dk2><a:srgbClr val="1F497D"/></a:dk2><a:lt2><a:srgbClr val="EEECE1"/></a:lt2><a:accent1><a:srgbClr val="4F81BD"/></a:accent1><a:accent2><a:srgbClr val="C0504D"/></a:accent2><a:accent3><a:srgbClr val="9BBB59"/></a:accent3><a:accent4><a:srgbClr val="8064A2"/></a:accent4><a:accent5><a:srgbClr val="4BACC6"/></a:accent5><a:accent6><a:srgbClr val="F79646"/></a:accent6><a:hlink><a:srgbClr val="0000FF"/></a:hlink><a:folHlink><a:srgbClr val="800080"/></a:folHlink></a:clrScheme><a:fontScheme name="Office"><a:majorFont><a:latin typeface="Arial"/></a:majorFont><a:minorFont><a:latin typeface="Arial"/></a:minorFont></a:fontScheme><a:fmtScheme name="Office"><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst><a:lnStyleLst><a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst><a:effectStyleLst><a:effectStyle/></a:effectStyleLst><a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst></a:fmtScheme></a:themeElements></a:theme>'''
    slide_master = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld><p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/><p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst></p:sldMaster>'''
    slide_master_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/></Relationships>'''
    slide_layout = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank" preserve="1"><p:cSld name="Blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>'''
    slide_layout_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/></Relationships>'''
    empty_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'''
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        write_zip_text(z, "[Content_Types].xml", content_types)
        write_zip_text(z, "_rels/.rels", root_rels)
        write_zip_text(z, "ppt/presentation.xml", presentation)
        write_zip_text(z, "ppt/_rels/presentation.xml.rels", pres_rels_xml)
        write_zip_text(z, "ppt/theme/theme1.xml", theme)
        write_zip_text(z, "ppt/slideMasters/slideMaster1.xml", slide_master)
        write_zip_text(z, "ppt/slideMasters/_rels/slideMaster1.xml.rels", slide_master_rels)
        write_zip_text(z, "ppt/slideLayouts/slideLayout1.xml", slide_layout)
        write_zip_text(z, "ppt/slideLayouts/_rels/slideLayout1.xml.rels", slide_layout_rels)
        for i, s in enumerate(slides, 1):
            bullets = s.get("bullets") or s.get("body") or []
            if isinstance(bullets, str):
                bullets = bullets.split("\n")
            write_zip_text(z, f"ppt/slides/slide{i}.xml", slide_xml(str(s.get("title") or f"Slide {i}"), [str(b) for b in bullets]))
            write_zip_text(z, f"ppt/slides/_rels/slide{i}.xml.rels", empty_rels)


def pdf_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def create_pdf_file(path: Path, title: str, lines: list[str]) -> None:
    all_lines = ([title] if title else []) + [str(x) for x in lines]
    pages = [all_lines[i:i + 40] for i in range(0, max(len(all_lines), 1), 40)] or [[]]
    objects: list[bytes] = []
    def add(obj: str) -> int:
        objects.append(obj.encode("latin-1", errors="replace"))
        return len(objects)
    catalog_id = add("<< /Type /Catalog /Pages 2 0 R >>")
    pages_id = add("PLACEHOLDER")
    font_id = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_ids = []
    for page_lines in pages:
        stream_lines = ["BT", "/F1 12 Tf", "72 740 Td"]
        for i, line in enumerate(page_lines):
            if i:
                stream_lines.append("0 -16 Td")
            stream_lines.append(f"({pdf_escape(line[:1000])}) Tj")
        stream_lines.append("ET")
        stream = "\n".join(stream_lines)
        content_id = add(f"<< /Length {len(stream.encode('latin-1', errors='replace'))} >>\nstream\n{stream}\nendstream")
        page_id = add(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>")
        page_ids.append(page_id)
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects[pages_id - 1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("latin-1")
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out.extend(f"{i} 0 obj\n".encode("ascii"))
        out.extend(obj)
        out.extend(b"\nendobj\n")
    xref = len(out)
    out.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode("ascii"))
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    out.extend(f"trailer\n<< /Size {len(objects)+1} /Root {catalog_id} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii"))
    path.write_bytes(bytes(out))


def register_document_tools(reg: ToolRegistry, ws: Workspace) -> None:
    def create_docx(args: dict[str, Any]) -> dict[str, Any]:
        path = ws.safe_path(args.get("path", f"generated/document_{int(time.time())}.docx"))
        path.parent.mkdir(parents=True, exist_ok=True)
        paragraphs = args.get("paragraphs") or []
        if isinstance(paragraphs, str):
            paragraphs = paragraphs.split("\n\n")
        create_docx_file(path, str(args.get("title", "")), [str(p) for p in paragraphs])
        return {"ok": True, "file": ws.meta(path)}

    def create_xlsx(args: dict[str, Any]) -> dict[str, Any]:
        path = ws.safe_path(args.get("path", f"generated/workbook_{int(time.time())}.xlsx"))
        path.parent.mkdir(parents=True, exist_ok=True)
        create_xlsx_file(path, args.get("sheets") or [])
        return {"ok": True, "file": ws.meta(path)}

    def create_pptx(args: dict[str, Any]) -> dict[str, Any]:
        path = ws.safe_path(args.get("path", f"generated/deck_{int(time.time())}.pptx"))
        path.parent.mkdir(parents=True, exist_ok=True)
        create_pptx_file(path, str(args.get("title", "")), args.get("slides") or [])
        return {"ok": True, "file": ws.meta(path)}

    def create_pdf(args: dict[str, Any]) -> dict[str, Any]:
        path = ws.safe_path(args.get("path", f"generated/document_{int(time.time())}.pdf"))
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = args.get("lines") or args.get("paragraphs") or []
        if isinstance(lines, str):
            lines = lines.split("\n")
        create_pdf_file(path, str(args.get("title", "")), [str(x) for x in lines])
        return {"ok": True, "file": ws.meta(path)}

    def create_csv(args: dict[str, Any]) -> dict[str, Any]:
        path = ws.safe_path(args.get("path", f"generated/table_{int(time.time())}.csv"))
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = args.get("rows") or []
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            for row in rows:
                writer.writerow(row if isinstance(row, list) else [row])
        return {"ok": True, "file": ws.meta(path)}

    reg.add(Tool("create_docx", "Create a simple Microsoft Word .docx document using built-in OOXML generation.", {"type": "object", "properties": {"path": {"type": "string"}, "title": {"type": "string"}, "paragraphs": {"type": "array", "items": {"type": "string"}}}}, create_docx, requires_approval=True, category="documents"))
    reg.add(Tool("create_xlsx", "Create a simple Excel .xlsx workbook. sheets is a list of {name, rows}; rows is a 2D array.", {"type": "object", "properties": {"path": {"type": "string"}, "sheets": {"type": "array"}}}, create_xlsx, requires_approval=True, category="documents"))
    reg.add(Tool("create_pptx", "Create a simple PowerPoint .pptx deck. slides is a list of {title, bullets}.", {"type": "object", "properties": {"path": {"type": "string"}, "title": {"type": "string"}, "slides": {"type": "array"}}}, create_pptx, requires_approval=True, category="documents"))
    reg.add(Tool("create_pdf", "Create a simple text PDF document.", {"type": "object", "properties": {"path": {"type": "string"}, "title": {"type": "string"}, "lines": {"type": "array", "items": {"type": "string"}}}}, create_pdf, requires_approval=True, category="documents"))
    reg.add(Tool("create_csv", "Create a CSV file from rows.", {"type": "object", "properties": {"path": {"type": "string"}, "rows": {"type": "array"}}}, create_csv, requires_approval=True, category="documents"))
