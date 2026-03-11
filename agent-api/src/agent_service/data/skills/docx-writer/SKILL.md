---
name: docx-writer
description: Create professional Word documents (.docx) — reports, proposals, letters, manuals — with polished styling, tables, images, headers/footers, and table of contents using python-docx.
---

# Word Document Writer

Create professional Word documents using `python-docx`. Produces polished reports, proposals, letters, and manuals.

## Installation

```bash
pip install python-docx
```

## Imports

```python
from docx import Document
from docx.shared import Inches, Pt, Cm, Emu, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.enum.section import WD_ORIENT
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml
import os
```

## Complete Document Template

Use this as the starting scaffold for any document:

```python
def create_document(title, subtitle=None, author=None):
    doc = Document()

    # -- Page setup --
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(0.75)

    # -- Base styles --
    style = doc.styles['Normal']
    style.font.name = 'Calibri'
    style.font.size = Pt(11)
    style.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
    style.paragraph_format.space_after = Pt(6)
    style.paragraph_format.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
    style.paragraph_format.line_spacing = 1.15

    for level in range(1, 4):
        heading = doc.styles[f'Heading {level}']
        heading.font.color.rgb = RGBColor(0x1A, 0x47, 0x7A)
        heading.font.name = 'Calibri'
        heading.paragraph_format.space_before = Pt(18 if level == 1 else 12)
        heading.paragraph_format.space_after = Pt(6)

    # -- Title page --
    for _ in range(6):
        doc.add_paragraph()
    tp = doc.add_paragraph()
    tp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = tp.add_run(title)
    run.bold = True
    run.font.size = Pt(28)
    run.font.color.rgb = RGBColor(0x1A, 0x47, 0x7A)

    if subtitle:
        sp = doc.add_paragraph()
        sp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        sr = sp.add_run(subtitle)
        sr.font.size = Pt(14)
        sr.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    if author:
        doc.add_paragraph()
        ap = doc.add_paragraph()
        ap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        ar = ap.add_run(author)
        ar.font.size = Pt(12)
        ar.font.color.rgb = RGBColor(0x99, 0x99, 0x99)

    doc.add_page_break()
    return doc
```

## Professional Tables

```python
HEADER_BG = RGBColor(0x1A, 0x47, 0x7A)
HEADER_FG = RGBColor(0xFF, 0xFF, 0xFF)
ALT_ROW_BG = RGBColor(0xF2, 0xF6, 0xFA)

def set_cell_bg(cell, color):
    """Set background color of a table cell."""
    shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{color}"/>')
    cell._tc.get_or_add_tcPr().append(shading)

def add_styled_table(doc, headers, rows, col_widths=None):
    """Add a professionally styled table."""
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = 'Table Grid'
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    # Header row
    for i, header in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = header
        cell.paragraphs[0].runs[0].font.bold = True
        cell.paragraphs[0].runs[0].font.color.rgb = HEADER_FG
        cell.paragraphs[0].runs[0].font.size = Pt(10)
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        set_cell_bg(cell, '1A477A')

    # Data rows with alternating colors
    for row_idx, row_data in enumerate(rows):
        row = table.add_row()
        for col_idx, value in enumerate(row_data):
            cell = row.cells[col_idx]
            cell.text = str(value)
            cell.paragraphs[0].runs[0].font.size = Pt(10)
            if row_idx % 2 == 1:
                set_cell_bg(cell, 'F2F6FA')

    # Column widths
    if col_widths:
        for i, width in enumerate(col_widths):
            for row in table.rows:
                row.cells[i].width = width

    doc.add_paragraph()  # spacing after table
    return table
```

## Headers and Footers

```python
def add_header_footer(doc, header_text, footer_left="", include_page_number=True):
    """Add headers and footers to all sections."""
    for section in doc.sections:
        # Header
        header = section.header
        header.is_linked_to_previous = False
        hp = header.paragraphs[0]
        hp.text = header_text
        hp.style.font.size = Pt(9)
        hp.style.font.color.rgb = RGBColor(0x99, 0x99, 0x99)
        hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT

        # Footer with page number
        footer = section.footer
        footer.is_linked_to_previous = False
        fp = footer.paragraphs[0]
        if footer_left:
            fp.add_run(footer_left).font.size = Pt(8)
        if include_page_number:
            fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = fp.add_run()
            fld = parse_xml(
                f'<w:fldSimple {nsdecls("w")} w:instr=" PAGE "/>'
            )
            run._r.append(fld)
```

## Table of Contents

```python
def add_toc(doc, title="Table of Contents"):
    """Insert a table of contents field (updates when opened in Word)."""
    doc.add_heading(title, level=1)
    p = doc.add_paragraph()
    run = p.add_run()
    fld = parse_xml(
        f'<w:fldSimple {nsdecls("w")} w:instr=" TOC \\o &quot;1-3&quot; \\h \\z \\u">'
        f'<w:r><w:t>Right-click to update table of contents</w:t></w:r>'
        f'</w:fldSimple>'
    )
    run._r.append(fld)
    doc.add_page_break()
```

## Lists, Images & Misc

```python
# Bullet list
for item in items:
    doc.add_paragraph(item, style='List Bullet')

# Numbered list
for item in steps:
    doc.add_paragraph(item, style='List Number')

# Image centered
doc.add_picture('chart.png', width=Inches(5.5))
doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER

# Horizontal rule
p = doc.add_paragraph()
p.paragraph_format.space_before = Pt(12)
p.paragraph_format.space_after = Pt(12)
pBdr = parse_xml(f'<w:pBdr {nsdecls("w")}><w:bottom w:val="single" w:sz="6" w:space="1" w:color="CCCCCC"/></w:pBdr>')
p._p.get_or_add_pPr().append(pBdr)

# Landscape section (for wide tables)
new_section = doc.add_section(WD_ORIENT.LANDSCAPE)
new_section.page_width = Inches(11)
new_section.page_height = Inches(8.5)

# Page break
doc.add_page_break()
```

## Full Example — Project Report

```python
doc = create_document("Q4 Project Report", "Engineering Division", "Jane Smith")
add_header_footer(doc, "Q4 Report — Confidential")
add_toc(doc)

doc.add_heading("Executive Summary", level=1)
doc.add_paragraph("This report covers the key achievements and metrics for Q4 2024.")

doc.add_heading("Key Metrics", level=2)
add_styled_table(doc,
    headers=["Metric", "Target", "Actual", "Status"],
    rows=[
        ["Revenue", "$1.2M", "$1.35M", "Exceeded"],
        ["Users", "10,000", "12,400", "Exceeded"],
        ["Uptime", "99.9%", "99.95%", "Met"],
    ],
    col_widths=[Inches(2), Inches(1.5), Inches(1.5), Inches(1.5)],
)

doc.add_heading("Next Steps", level=1)
for item in ["Scale infrastructure", "Launch mobile app", "Hire 3 engineers"]:
    doc.add_paragraph(item, style='List Bullet')

doc.save(os.path.join(workspace, "q4_report.docx"))
```

## Best Practices

1. Always save to the workspace directory: `os.path.join(workspace, "filename.docx")`
2. Set up base styles (Normal, Headings) first — everything inherits from them
3. Use the `create_document()` template for consistent professional appearance
4. Use `set_cell_bg()` for table cell colors — the XML approach is the only reliable method
5. Use `Inches()` or `Cm()` for dimensions, `Pt()` for font sizes
6. Add `doc.add_paragraph()` after tables for spacing
7. For TOC: insert the field code — it auto-updates when the user opens the file in Word
8. Test with both Microsoft Word and LibreOffice for compatibility
