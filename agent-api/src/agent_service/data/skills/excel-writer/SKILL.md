---
name: excel-writer
description: Create professional Excel spreadsheets (.xlsx) — dashboards, reports, data analysis — with styled tables, formulas, charts, conditional formatting, pivot-style summaries, and print layout using openpyxl.
---

# Excel Spreadsheet Writer

Create professional Excel spreadsheets using `openpyxl`. Produces polished reports, dashboards, and data analysis workbooks.

## Installation

```bash
pip install openpyxl
```

## Imports

```python
from openpyxl import Workbook
from openpyxl.styles import (
    Font, Alignment, Border, Side, PatternFill, NamedStyle, numbers
)
from openpyxl.utils import get_column_letter
from openpyxl.chart import BarChart, LineChart, PieChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.chart.series import DataPoint
from openpyxl.formatting.rule import CellIsRule, DataBarRule, ColorScaleRule
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.page import PageMargins
import os
```

## Reusable Styles

Define these once and reuse across the workbook:

```python
# Color palette
BLUE = '1A477A'
LIGHT_BLUE = 'D6E4F0'
WHITE = 'FFFFFF'
DARK_TEXT = '333333'
LIGHT_GRAY = 'F5F5F5'
MEDIUM_GRAY = 'E0E0E0'
GREEN = '27AE60'
RED = 'E74C3C'
ORANGE = 'F39C12'

def create_styles(wb):
    """Register reusable named styles on the workbook."""
    header_style = NamedStyle(name='header')
    header_style.font = Font(name='Calibri', bold=True, size=11, color=WHITE)
    header_style.fill = PatternFill('solid', fgColor=BLUE)
    header_style.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    header_style.border = Border(
        bottom=Side(style='medium', color=BLUE)
    )
    wb.add_named_style(header_style)

    data_style = NamedStyle(name='data')
    data_style.font = Font(name='Calibri', size=10, color=DARK_TEXT)
    data_style.alignment = Alignment(vertical='center')
    data_style.border = Border(
        bottom=Side(style='hair', color=MEDIUM_GRAY)
    )
    wb.add_named_style(data_style)

    currency_style = NamedStyle(name='currency')
    currency_style.font = Font(name='Calibri', size=10, color=DARK_TEXT)
    currency_style.number_format = '$#,##0.00'
    currency_style.alignment = Alignment(horizontal='right', vertical='center')
    currency_style.border = Border(bottom=Side(style='hair', color=MEDIUM_GRAY))
    wb.add_named_style(currency_style)

    pct_style = NamedStyle(name='pct')
    pct_style.font = Font(name='Calibri', size=10, color=DARK_TEXT)
    pct_style.number_format = '0.0%'
    pct_style.alignment = Alignment(horizontal='center', vertical='center')
    pct_style.border = Border(bottom=Side(style='hair', color=MEDIUM_GRAY))
    wb.add_named_style(pct_style)

    total_style = NamedStyle(name='total_row')
    total_style.font = Font(name='Calibri', bold=True, size=11, color=BLUE)
    total_style.fill = PatternFill('solid', fgColor=LIGHT_BLUE)
    total_style.border = Border(
        top=Side(style='medium', color=BLUE),
        bottom=Side(style='medium', color=BLUE),
    )
    wb.add_named_style(total_style)
```

## Data Table Helper

```python
def write_data_table(ws, headers, rows, start_row=1, start_col=1, col_widths=None, col_styles=None):
    """Write a styled data table with headers, alternating rows, and totals-ready formatting."""
    # Headers
    for c, header in enumerate(headers, start=start_col):
        cell = ws.cell(row=start_row, column=c, value=header)
        cell.style = 'header'

    # Data rows
    for r, row_data in enumerate(rows, start=start_row + 1):
        for c, value in enumerate(row_data, start=start_col):
            cell = ws.cell(row=r, column=c, value=value)
            # Apply column-specific style or default
            style_name = (col_styles or {}).get(c - start_col, 'data')
            cell.style = style_name
            # Alternating row background
            if (r - start_row) % 2 == 0:
                cell.fill = PatternFill('solid', fgColor=LIGHT_GRAY)

    # Column widths
    if col_widths:
        for i, width in enumerate(col_widths):
            ws.column_dimensions[get_column_letter(start_col + i)].width = width

    # Auto-filter
    end_col = get_column_letter(start_col + len(headers) - 1)
    end_row = start_row + len(rows)
    ws.auto_filter.ref = f"{get_column_letter(start_col)}{start_row}:{end_col}{end_row}"

    # Freeze header
    ws.freeze_panes = ws.cell(row=start_row + 1, column=start_col)

    return end_row  # return last data row for formulas
```

## Formulas & Summary Row

```python
def add_summary_row(ws, row, data_start, data_end, cols, label_col=1, label="Total"):
    """Add a styled totals row with SUM formulas."""
    ws.cell(row=row, column=label_col, value=label).style = 'total_row'
    for col in cols:
        letter = get_column_letter(col)
        cell = ws.cell(row=row, column=col, value=f"=SUM({letter}{data_start}:{letter}{data_end})")
        cell.style = 'total_row'
        cell.number_format = '$#,##0.00'

# Common formulas
ws['E2'] = '=C2-D2'              # Difference
ws['F2'] = '=E2/C2'              # Percentage
ws['B20'] = '=SUMIF(A2:A19,"Sales",B2:B19)'  # Conditional sum
ws['B21'] = '=COUNTIF(C2:C19,">90")'          # Conditional count
ws['B22'] = '=AVERAGE(B2:B19)'                 # Average
```

## Charts

```python
def add_bar_chart(ws, title, categories_range, values_range, anchor="E2", width=15, height=10):
    chart = BarChart()
    chart.type = "col"
    chart.title = title
    chart.y_axis.title = None
    chart.x_axis.title = None
    chart.style = 10
    chart.width = width
    chart.height = height

    chart.add_data(values_range, titles_from_data=True)
    chart.set_categories(categories_range)
    chart.shape = 4
    chart.legend.position = 'b'

    # Remove gridlines for cleaner look
    chart.y_axis.majorGridlines = None

    ws.add_chart(chart, anchor)
    return chart

def add_pie_chart(ws, title, categories_range, values_range, anchor="E2"):
    chart = PieChart()
    chart.title = title
    chart.width = 12
    chart.height = 10
    chart.add_data(values_range, titles_from_data=True)
    chart.set_categories(categories_range)

    # Data labels with percentages
    chart.dataLabels = DataLabelList()
    chart.dataLabels.showPercent = True
    chart.dataLabels.showVal = False
    chart.dataLabels.showCatName = True

    ws.add_chart(chart, anchor)
    return chart

# Usage
cats = Reference(ws, min_col=1, min_row=2, max_row=10)
vals = Reference(ws, min_col=2, min_row=1, max_row=10)
add_bar_chart(ws, "Revenue by Quarter", cats, vals, anchor="E2")
```

## Conditional Formatting

```python
# Color scale (green-yellow-red) on a range
ws.conditional_formatting.add('D2:D100', ColorScaleRule(
    start_type='min', start_color='27AE60',
    mid_type='percentile', mid_value=50, mid_color='F39C12',
    end_type='max', end_color='E74C3C',
))

# Data bars
ws.conditional_formatting.add('B2:B100', DataBarRule(
    start_type='min', end_type='max', color='5B9BD5'
))

# Highlight cells
ws.conditional_formatting.add('E2:E100', CellIsRule(
    operator='greaterThan', formula=['0'],
    fill=PatternFill('solid', fgColor='D5F5E3'),
    font=Font(color='27AE60'),
))
ws.conditional_formatting.add('E2:E100', CellIsRule(
    operator='lessThan', formula=['0'],
    fill=PatternFill('solid', fgColor='FADBD8'),
    font=Font(color='E74C3C'),
))
```

## Data Validation & Dropdowns

```python
# Dropdown list
status_dv = DataValidation(type="list", formula1='"Active,Inactive,Pending"')
status_dv.prompt = "Select status"
ws.add_data_validation(status_dv)
status_dv.add('F2:F100')

# Numeric range
num_dv = DataValidation(type="whole", operator="between", formula1=0, formula2=100)
num_dv.error = "Enter a number between 0 and 100"
ws.add_data_validation(num_dv)
num_dv.add('G2:G100')
```

## Multiple Sheets & Print Setup

```python
# Summary sheet referencing data sheet
ws_summary = wb.create_sheet("Summary", 0)  # insert at position 0
ws_summary['A1'] = "Total Revenue"
ws_summary['B1'] = "=Data!B20"
ws_summary['A2'] = "Average Score"
ws_summary['B2'] = "=Data!B22"

# Print setup
ws.sheet_properties.pageSetUpPr.fitToPage = True
ws.page_setup.fitToWidth = 1
ws.page_setup.fitToHeight = 0  # as many pages as needed vertically
ws.page_setup.orientation = 'landscape'
ws.page_margins = PageMargins(left=0.5, right=0.5, top=0.75, bottom=0.75)
ws.oddHeader.center.text = "Company Report"
ws.oddFooter.center.text = "Page &P of &N"

# Print title rows (repeat header on every page)
ws.print_title_rows = '1:1'
```

## Full Example — Sales Dashboard

```python
wb = Workbook()
create_styles(wb)

ws = wb.active
ws.title = "Sales Data"

headers = ["Rep", "Region", "Q1", "Q2", "Q3", "Q4", "Total", "% of Goal"]
data = [
    ["Alice", "North", 45000, 52000, 48000, 61000],
    ["Bob",   "South", 38000, 41000, 39000, 44000],
    ["Carol", "East",  55000, 49000, 63000, 58000],
    ["Dave",  "West",  42000, 47000, 45000, 51000],
]
# Add computed columns
for row in data:
    row.append(sum(row[2:6]))         # Total
    row.append(row[-1] / 200000)      # % of goal

last_row = write_data_table(ws, headers, data,
    col_widths=[14, 12, 14, 14, 14, 14, 16, 12],
    col_styles={2: 'currency', 3: 'currency', 4: 'currency', 5: 'currency', 6: 'currency', 7: 'pct'}
)
add_summary_row(ws, last_row + 1, 2, last_row, cols=[3, 4, 5, 6, 7])

# Chart
cats = Reference(ws, min_col=1, min_row=2, max_row=last_row)
vals = Reference(ws, min_col=7, min_row=1, max_row=last_row)
add_bar_chart(ws, "Total Sales by Rep", cats, vals, anchor="J2")

wb.save(os.path.join(workspace, "sales_dashboard.xlsx"))
```

## Best Practices

1. Always save to workspace: `os.path.join(workspace, "filename.xlsx")`
2. Call `create_styles(wb)` first — then use named styles everywhere for consistency
3. Use `ws.append()` for bulk data loading (faster than cell-by-cell)
4. Use `write_data_table()` for any data table — it handles headers, alternating rows, freeze, filter
5. Add conditional formatting to highlight outliers, trends, and status
6. Set print layout (margins, orientation, fit-to-page) so the file prints correctly
7. Put summary/dashboard on the first sheet, raw data on subsequent sheets
8. Use formulas referencing other sheets for live summaries
