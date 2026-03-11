---
name: ppt-writer
description: Create professional PowerPoint presentations (.pptx) — pitch decks, reports, training materials — with styled slides, charts, tables, images, speaker notes, and consistent themes using python-pptx.
---

# PowerPoint Presentation Writer

Create professional PowerPoint presentations using `python-pptx`. Produces polished pitch decks, reports, and training materials.

## Installation

```bash
pip install python-pptx
```

## Imports

```python
from pptx import Presentation
from pptx.util import Inches, Pt, Cm, Emu
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR, MSO_AUTO_SIZE
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.dml.color import RGBColor
from pptx.chart.data import CategoryChartData
import os
```

## Theme Constants

Define once and use across all slides for visual consistency:

```python
# Color palette
PRIMARY = RGBColor(0x1A, 0x47, 0x7A)     # Deep blue
SECONDARY = RGBColor(0x2C, 0x3E, 0x50)   # Dark slate
ACCENT = RGBColor(0xE6, 0x7E, 0x22)      # Orange
LIGHT_BG = RGBColor(0xF8, 0xF9, 0xFA)    # Near-white
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
DARK_TEXT = RGBColor(0x33, 0x33, 0x33)
LIGHT_TEXT = RGBColor(0x99, 0x99, 0x99)

# Slide dimensions (standard 16:9)
SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)

# Common positions
CONTENT_LEFT = Inches(0.8)
CONTENT_TOP = Inches(1.6)
CONTENT_WIDTH = Inches(11.7)
TITLE_LEFT = Inches(0.8)
TITLE_TOP = Inches(0.4)
TITLE_WIDTH = Inches(11.7)
TITLE_HEIGHT = Inches(1.0)
```

## Slide Builder Helpers

```python
def new_blank_slide(prs):
    """Add a blank slide (layout 6)."""
    return prs.slides.add_slide(prs.slide_layouts[6])

def add_slide_title(slide, text, left=TITLE_LEFT, top=TITLE_TOP,
                    width=TITLE_WIDTH, height=TITLE_HEIGHT,
                    font_size=Pt(32), color=PRIMARY, bold=True):
    """Add a styled title to any slide."""
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = font_size
    p.font.bold = bold
    p.font.color.rgb = color
    return txBox

def add_text_box(slide, text, left, top, width, height,
                 font_size=Pt(16), color=DARK_TEXT, bold=False,
                 alignment=PP_ALIGN.LEFT):
    """Add a positioned text box."""
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = font_size
    p.font.color.rgb = color
    p.font.bold = bold
    p.alignment = alignment
    return txBox

def add_bullet_list(slide, items, left=CONTENT_LEFT, top=CONTENT_TOP,
                    width=CONTENT_WIDTH, height=Inches(4.5),
                    font_size=Pt(18), color=DARK_TEXT, spacing=Pt(8)):
    """Add a bullet list to a slide."""
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True

    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = item
        p.font.size = font_size
        p.font.color.rgb = color
        p.level = 0
        p.space_after = spacing
        # Bullet character
        pPr = p._pPr
        if pPr is None:
            from pptx.oxml.ns import qn
            pPr = p._p.get_or_add_pPr()
    return txBox

def add_speaker_notes(slide, text):
    """Add speaker notes to a slide."""
    notes_slide = slide.notes_slide
    notes_slide.notes_text_frame.text = text
```

## Slide Templates

### Title Slide

```python
def make_title_slide(prs, title, subtitle=None):
    slide = new_blank_slide(prs)

    # Background fill
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = PRIMARY

    # Title
    add_text_box(slide, title,
        left=Inches(1), top=Inches(2.2), width=Inches(11.3), height=Inches(1.5),
        font_size=Pt(44), color=WHITE, bold=True, alignment=PP_ALIGN.CENTER)

    # Subtitle
    if subtitle:
        add_text_box(slide, subtitle,
            left=Inches(1), top=Inches(3.8), width=Inches(11.3), height=Inches(1),
            font_size=Pt(20), color=RGBColor(0xBB, 0xCC, 0xDD), alignment=PP_ALIGN.CENTER)

    # Decorative accent line
    shape = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(4.5), Inches(3.6), Inches(4.3), Inches(0.06)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = ACCENT
    shape.line.fill.background()

    return slide
```

### Section Header

```python
def make_section_slide(prs, title, number=None):
    slide = new_blank_slide(prs)

    if number:
        add_text_box(slide, f"0{number}" if number < 10 else str(number),
            left=Inches(0.8), top=Inches(1.5), width=Inches(2), height=Inches(1.5),
            font_size=Pt(64), color=ACCENT, bold=True)

    add_text_box(slide, title,
        left=Inches(0.8), top=Inches(3.2), width=Inches(11), height=Inches(1.2),
        font_size=Pt(36), color=PRIMARY, bold=True)

    # Bottom accent line
    shape = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(0.8), Inches(4.5), Inches(3), Inches(0.06)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = ACCENT
    shape.line.fill.background()

    return slide
```

### Content Slide (Title + Bullets)

```python
def make_content_slide(prs, title, bullets, notes=None):
    slide = new_blank_slide(prs)
    add_slide_title(slide, title)
    add_bullet_list(slide, bullets)
    if notes:
        add_speaker_notes(slide, notes)
    return slide
```

### Two-Column Slide

```python
def make_two_column_slide(prs, title, left_items, right_items,
                          left_title=None, right_title=None):
    slide = new_blank_slide(prs)
    add_slide_title(slide, title)

    col_w = Inches(5.5)
    left_x = CONTENT_LEFT
    right_x = Inches(7)

    if left_title:
        add_text_box(slide, left_title,
            left=left_x, top=Inches(1.4), width=col_w, height=Inches(0.5),
            font_size=Pt(16), color=ACCENT, bold=True)
    if right_title:
        add_text_box(slide, right_title,
            left=right_x, top=Inches(1.4), width=col_w, height=Inches(0.5),
            font_size=Pt(16), color=ACCENT, bold=True)

    add_bullet_list(slide, left_items,
        left=left_x, top=Inches(2), width=col_w, height=Inches(4.5), font_size=Pt(14))
    add_bullet_list(slide, right_items,
        left=right_x, top=Inches(2), width=col_w, height=Inches(4.5), font_size=Pt(14))

    return slide
```

### Metric / KPI Cards

```python
def make_kpi_slide(prs, title, kpis):
    """kpis: list of (label, value, subtitle) tuples, max 4."""
    slide = new_blank_slide(prs)
    add_slide_title(slide, title)

    n = len(kpis)
    card_w = Inches(2.5)
    gap = Inches(0.4)
    total = n * card_w + (n - 1) * gap
    start_x = (SLIDE_W - total) / 2

    for i, (label, value, sub) in enumerate(kpis):
        x = start_x + i * (card_w + gap)
        y = Inches(2.5)

        # Card background
        shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, card_w, Inches(3))
        shape.fill.solid()
        shape.fill.fore_color.rgb = LIGHT_BG
        shape.line.color.rgb = RGBColor(0xDE, 0xE2, 0xE6)
        shape.line.width = Pt(1)

        # Value (large number)
        add_text_box(slide, str(value),
            left=x, top=y + Inches(0.5), width=card_w, height=Inches(1.2),
            font_size=Pt(36), color=PRIMARY, bold=True, alignment=PP_ALIGN.CENTER)

        # Label
        add_text_box(slide, label,
            left=x, top=y + Inches(1.6), width=card_w, height=Inches(0.5),
            font_size=Pt(14), color=DARK_TEXT, bold=True, alignment=PP_ALIGN.CENTER)

        # Subtitle
        if sub:
            add_text_box(slide, sub,
                left=x, top=y + Inches(2.1), width=card_w, height=Inches(0.5),
                font_size=Pt(11), color=LIGHT_TEXT, alignment=PP_ALIGN.CENTER)

    return slide
```

## Tables

```python
def add_styled_table(slide, headers, rows, left=CONTENT_LEFT, top=CONTENT_TOP,
                     width=CONTENT_WIDTH, row_height=Inches(0.45)):
    """Add a styled table to a slide."""
    n_rows = len(rows) + 1
    n_cols = len(headers)
    height = row_height * n_rows

    table_shape = slide.shapes.add_table(n_rows, n_cols, left, top, width, height)
    table = table_shape.table

    # Header row
    for i, header in enumerate(headers):
        cell = table.cell(0, i)
        cell.text = header
        cell.fill.solid()
        cell.fill.fore_color.rgb = PRIMARY
        for p in cell.text_frame.paragraphs:
            p.font.bold = True
            p.font.size = Pt(11)
            p.font.color.rgb = WHITE
            p.alignment = PP_ALIGN.CENTER

    # Data rows
    for r, row_data in enumerate(rows, start=1):
        for c, value in enumerate(row_data):
            cell = table.cell(r, c)
            cell.text = str(value)
            # Alternating background
            if r % 2 == 0:
                cell.fill.solid()
                cell.fill.fore_color.rgb = RGBColor(0xF2, 0xF6, 0xFA)
            else:
                cell.fill.background()
            for p in cell.text_frame.paragraphs:
                p.font.size = Pt(10)
                p.font.color.rgb = DARK_TEXT

    return table
```

## Charts

```python
def add_column_chart(slide, title, categories, series_data,
                     left=CONTENT_LEFT, top=CONTENT_TOP,
                     width=CONTENT_WIDTH, height=Inches(4.5)):
    """series_data: dict of {series_name: [values]}"""
    chart_data = CategoryChartData()
    chart_data.categories = categories
    for name, values in series_data.items():
        chart_data.add_series(name, values)

    chart_frame = slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED,
        left, top, width, height, chart_data,
    )
    chart = chart_frame.chart
    chart.has_legend = True
    chart.legend.position = XL_LEGEND_POSITION.BOTTOM
    chart.legend.include_in_layout = False

    # Style
    plot = chart.plots[0]
    plot.gap_width = 100
    for i, series in enumerate(plot.series):
        fill = series.format.fill
        fill.solid()
        fill.fore_color.rgb = [PRIMARY, ACCENT, SECONDARY][i % 3]

    return chart

def add_pie_chart(slide, title, categories, values,
                  left=Inches(3), top=CONTENT_TOP,
                  width=Inches(7), height=Inches(5)):
    chart_data = CategoryChartData()
    chart_data.categories = categories
    chart_data.add_series('Data', values)

    chart_frame = slide.shapes.add_chart(
        XL_CHART_TYPE.PIE, left, top, width, height, chart_data,
    )
    chart = chart_frame.chart
    chart.has_legend = True
    chart.legend.position = XL_LEGEND_POSITION.BOTTOM

    plot = chart.plots[0]
    plot.has_data_labels = True
    plot.data_labels.number_format = '0%'
    plot.data_labels.show_percentage = True
    plot.data_labels.show_category_name = False

    return chart
```

## Full Example — Quarterly Report Deck

```python
prs = Presentation()
prs.slide_width = SLIDE_W
prs.slide_height = SLIDE_H

# Slide 1: Title
make_title_slide(prs, "Q4 2024 Report", "Engineering Division — January 2025")

# Slide 2: KPIs
make_kpi_slide(prs, "Key Metrics", [
    ("Revenue", "$1.35M", "+12% vs target"),
    ("Users", "12,400", "+24% QoQ"),
    ("Uptime", "99.95%", "Above SLA"),
    ("Deploy Freq", "47/mo", "+35% QoQ"),
])

# Slide 3: Highlights
make_content_slide(prs, "Q4 Highlights", [
    "Launched v2.0 platform with redesigned dashboard",
    "Reduced API latency by 40% (p99: 145ms)",
    "Expanded to 3 new regions (APAC)",
    "Zero critical incidents for 90 consecutive days",
], notes="Emphasize the zero-incident streak — this is a first for the team.")

# Slide 4: Revenue chart
slide = new_blank_slide(prs)
add_slide_title(slide, "Revenue Trend")
add_column_chart(slide, "Quarterly Revenue",
    categories=["Q1", "Q2", "Q3", "Q4"],
    series_data={
        "Revenue": [850000, 980000, 1120000, 1350000],
        "Target": [900000, 1000000, 1100000, 1200000],
    },
)

# Slide 5: Two-column next steps
make_two_column_slide(prs, "Next Steps",
    left_items=["Scale infrastructure 2x", "Launch mobile app beta", "Hire 3 senior engineers"],
    right_items=["Implement SOC2 compliance", "Expand to EU region", "Build ML pipeline"],
    left_title="Engineering", right_title="Operations",
)

prs.save(os.path.join(workspace, "q4_report.pptx"))
```

## Best Practices

1. Always save to workspace: `os.path.join(workspace, "filename.pptx")`
2. Define theme constants (colors, positions) at the top — never hardcode colors in slide builders
3. Use `new_blank_slide()` + helpers for full control; avoid built-in layouts for custom designs
4. Use the slide template functions (`make_title_slide`, `make_content_slide`, etc.) for consistency
5. Keep text minimal — slides are visual aids, not documents
6. Add speaker notes with `add_speaker_notes()` for presenter context
7. Use 16:9 aspect ratio (set `slide_width` and `slide_height`)
8. Use `MSO_SHAPE.ROUNDED_RECTANGLE` for card-style layouts
9. Limit to 4-6 bullet points per slide, max 8 words per bullet
10. For images: `slide.shapes.add_picture(path, left, top, width=Inches(N))`
