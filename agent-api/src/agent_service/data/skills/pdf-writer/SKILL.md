---
name: pdf-writer
description: Create professional PDF documents — reports, invoices, certificates, data sheets — with custom layouts, styled tables, headers/footers, images, and multi-page flow using reportlab. Read and merge existing PDFs with PyPDF2.
---

# PDF Document Writer

Create professional PDF documents using `reportlab`. Read and merge existing PDFs with `PyPDF2`.

## Installation

```bash
pip install reportlab PyPDF2
```

## Imports

```python
from reportlab.lib.pagesizes import A4, letter, landscape
from reportlab.lib.units import inch, cm, mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.lib.colors import HexColor, Color, white, black
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image, KeepTogether, HRFlowable, Frame, PageTemplate
)
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os
```

## Color Palette & Custom Styles

```python
# Professional color palette
PRIMARY = HexColor('#1A477A')
SECONDARY = HexColor('#2C3E50')
ACCENT = HexColor('#E67E22')
LIGHT_BG = HexColor('#F8F9FA')
TABLE_HEADER = HexColor('#1A477A')
TABLE_ALT = HexColor('#F2F6FA')
TEXT_DARK = HexColor('#333333')
TEXT_LIGHT = HexColor('#666666')
BORDER = HexColor('#DEE2E6')

def build_styles():
    """Create a complete style set for professional documents."""
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        'DocTitle', parent=styles['Title'],
        fontSize=28, leading=34,
        textColor=PRIMARY, spaceAfter=6,
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        'DocSubtitle', parent=styles['Normal'],
        fontSize=14, leading=18,
        textColor=TEXT_LIGHT, spaceAfter=30,
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        'H1', parent=styles['Heading1'],
        fontSize=20, leading=26,
        textColor=PRIMARY, spaceBefore=24, spaceAfter=10,
    ))
    styles.add(ParagraphStyle(
        'H2', parent=styles['Heading2'],
        fontSize=14, leading=18,
        textColor=SECONDARY, spaceBefore=16, spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        'Body', parent=styles['Normal'],
        fontSize=10, leading=15,
        textColor=TEXT_DARK, spaceAfter=8,
        alignment=TA_JUSTIFY,
    ))
    styles.add(ParagraphStyle(
        'BodySmall', parent=styles['Normal'],
        fontSize=9, leading=13,
        textColor=TEXT_LIGHT, spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        'BulletItem', parent=styles['Normal'],
        fontSize=10, leading=15,
        textColor=TEXT_DARK,
        bulletIndent=18, leftIndent=36,
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        'CellText', parent=styles['Normal'],
        fontSize=9, leading=12,
        textColor=TEXT_DARK,
    ))
    styles.add(ParagraphStyle(
        'CellHeader', parent=styles['Normal'],
        fontSize=9, leading=12, alignment=TA_CENTER,
        textColor=white,
    ))
    return styles
```

## Document Template with Headers/Footers

```python
def create_pdf(filename, title="Document", pagesize=A4):
    """Create a SimpleDocTemplate with professional margins."""
    doc = SimpleDocTemplate(
        filename,
        pagesize=pagesize,
        leftMargin=0.75*inch,
        rightMargin=0.75*inch,
        topMargin=1*inch,
        bottomMargin=0.75*inch,
        title=title,
    )
    return doc

def header_footer_template(canvas_obj, doc, header_left="", header_right="", footer_text=""):
    """Draw header and footer on each page."""
    canvas_obj.saveState()
    w, h = doc.pagesize

    # Header line
    canvas_obj.setStrokeColor(BORDER)
    canvas_obj.setLineWidth(0.5)
    canvas_obj.line(0.75*inch, h - 0.7*inch, w - 0.75*inch, h - 0.7*inch)

    # Header text
    canvas_obj.setFont('Helvetica', 8)
    canvas_obj.setFillColor(TEXT_LIGHT)
    canvas_obj.drawString(0.75*inch, h - 0.6*inch, header_left)
    canvas_obj.drawRightString(w - 0.75*inch, h - 0.6*inch, header_right)

    # Footer line
    canvas_obj.line(0.75*inch, 0.55*inch, w - 0.75*inch, 0.55*inch)

    # Footer text + page number
    canvas_obj.drawString(0.75*inch, 0.4*inch, footer_text)
    canvas_obj.drawRightString(w - 0.75*inch, 0.4*inch, f"Page {doc.page}")

    canvas_obj.restoreState()

# Usage: wrap in a lambda for doc.build()
from functools import partial
on_page = partial(header_footer_template,
    header_left="Company Name",
    header_right="Confidential",
    footer_text="Generated 2024-01-15",
)
# doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
```

## Professional Tables

```python
def styled_table(data, col_widths=None, header_rows=1):
    """Create a professionally styled table with header, alternating rows, and borders."""
    table = Table(data, colWidths=col_widths, repeatRows=header_rows)

    style_commands = [
        # Header
        ('BACKGROUND', (0, 0), (-1, header_rows - 1), TABLE_HEADER),
        ('TEXTCOLOR', (0, 0), (-1, header_rows - 1), white),
        ('FONTNAME', (0, 0), (-1, header_rows - 1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, header_rows - 1), 10),
        ('ALIGN', (0, 0), (-1, header_rows - 1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        # Data
        ('FONTNAME', (0, header_rows), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, header_rows), (-1, -1), 9),
        ('TEXTCOLOR', (0, header_rows), (-1, -1), TEXT_DARK),
        # Grid
        ('LINEBELOW', (0, 0), (-1, -2), 0.5, BORDER),
        ('LINEBELOW', (0, -1), (-1, -1), 1, TABLE_HEADER),
        ('LINEABOVE', (0, 0), (-1, 0), 1, TABLE_HEADER),
    ]

    # Alternating row backgrounds
    for i in range(header_rows, len(data)):
        if (i - header_rows) % 2 == 1:
            style_commands.append(('BACKGROUND', (0, i), (-1, i), TABLE_ALT))

    table.setStyle(TableStyle(style_commands))
    return table
```

## Title Page

```python
def build_title_page(story, styles, title, subtitle=None, author=None, date=None):
    """Add a professional title page to the story."""
    story.append(Spacer(1, 2*inch))
    story.append(Paragraph(title, styles['DocTitle']))

    if subtitle:
        story.append(Spacer(1, 8))
        story.append(Paragraph(subtitle, styles['DocSubtitle']))

    story.append(Spacer(1, 1*inch))

    # Decorative line
    story.append(HRFlowable(
        width="40%", thickness=2, color=PRIMARY,
        spaceBefore=0, spaceAfter=20,
    ))

    if author:
        story.append(Paragraph(f"Prepared by: {author}", styles['BodySmall']))
    if date:
        story.append(Paragraph(date, styles['BodySmall']))

    story.append(PageBreak())
```

## Lists, Images & Utility

```python
# Bullet list
for item in items:
    story.append(Paragraph(f'<bullet>&bull;</bullet>{item}', styles['BulletItem']))

# Numbered list
for i, item in enumerate(items, 1):
    story.append(Paragraph(f'<bullet>{i}.</bullet>{item}', styles['BulletItem']))

# Horizontal rule
story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER, spaceBefore=12, spaceAfter=12))

# Image (auto-scaled to fit width)
img = Image('chart.png', width=5*inch, height=3.5*inch)
story.append(img)

# Keep heading + first paragraph together (no orphaned heading)
story.append(KeepTogether([
    Paragraph("Section Title", styles['H1']),
    Paragraph("First paragraph of this section...", styles['Body']),
]))

# Page break
story.append(PageBreak())

# Spacer
story.append(Spacer(1, 0.5*inch))
```

## Reading & Merging PDFs

```python
from PyPDF2 import PdfReader, PdfWriter

# Read text
reader = PdfReader("input.pdf")
for page in reader.pages:
    text = page.extract_text()

# Merge multiple PDFs
writer = PdfWriter()
for pdf_path in ["part1.pdf", "part2.pdf", "part3.pdf"]:
    reader = PdfReader(pdf_path)
    for page in reader.pages:
        writer.add_page(page)
writer.write("merged.pdf")

# Extract specific pages
reader = PdfReader("input.pdf")
writer = PdfWriter()
for i in [0, 2, 4]:  # pages 1, 3, 5
    writer.add_page(reader.pages[i])
writer.write("selected_pages.pdf")
```

## Full Example — Project Report

```python
styles = build_styles()
story = []

# Title page
build_title_page(story, styles,
    title="Q4 Project Report",
    subtitle="Engineering Division",
    author="Jane Smith",
    date="January 2025",
)

# Executive summary
story.append(Paragraph("Executive Summary", styles['H1']))
story.append(Paragraph(
    "This report covers the key achievements and metrics for Q4 2024. "
    "Revenue targets were exceeded by 12%, and user growth surpassed projections.",
    styles['Body'],
))

# Metrics table
story.append(Paragraph("Key Metrics", styles['H2']))
story.append(Spacer(1, 6))
table_data = [
    ['Metric', 'Target', 'Actual', 'Status'],
    ['Revenue', '$1.2M', '$1.35M', 'Exceeded'],
    ['Active Users', '10,000', '12,400', 'Exceeded'],
    ['Uptime', '99.9%', '99.95%', 'Met'],
    ['Latency (p99)', '<200ms', '145ms', 'Met'],
]
story.append(styled_table(table_data, col_widths=[2.5*inch, 1.5*inch, 1.5*inch, 1.2*inch]))

# Next steps
story.append(Spacer(1, 12))
story.append(Paragraph("Next Steps", styles['H1']))
for item in ["Scale infrastructure to handle 2x traffic", "Launch mobile app beta", "Hire 3 senior engineers"]:
    story.append(Paragraph(f'<bullet>&bull;</bullet>{item}', styles['BulletItem']))

# Build
output = os.path.join(workspace, "q4_report.pdf")
doc = create_pdf(output, title="Q4 Project Report")
on_page = partial(header_footer_template,
    header_left="Engineering Division",
    header_right="Confidential",
    footer_text="Q4 2024 Report",
)
doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
```

## Best Practices

1. Always save to workspace: `os.path.join(workspace, "filename.pdf")`
2. Use `build_styles()` to define all styles upfront — reference by name throughout
3. Use `SimpleDocTemplate` for auto-pagination; use `canvas.Canvas` only for pixel-precise layouts
4. Use `styled_table()` for any data table — it handles header, alternating rows, borders
5. Use `KeepTogether()` to prevent headings from being orphaned at page bottom
6. Use `HRFlowable` for horizontal rules (not manual drawing)
7. Use `partial(header_footer_template, ...)` to pass custom header/footer text
8. For charts: generate with matplotlib, save as PNG, embed with `Image()`
9. Set `repeatRows=1` on tables so headers repeat across pages
