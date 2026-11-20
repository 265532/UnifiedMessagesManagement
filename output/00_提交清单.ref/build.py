from pathlib import Path
try:
    import openpyxl
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "openpyxl>=3.1.0"])
    import openpyxl
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

OUTPUT = Path("C:/doc/project/UnifiedMessagesManagement/docs/submissions/release/00_提交清单.xlsx")


def xl_color(css_hex: str) -> str:
    value = css_hex.removeprefix("#").upper()
    if len(value) != 6:
        raise ValueError(f"Expected #RRGGBB, got: {css_hex}")
    return "FF" + value


XL_PRIMARY = xl_color("#4472C4")
XL_WHITE = xl_color("#FFFFFF")
XL_LIGHT = xl_color("#D9E2F3")
XL_BORDER = xl_color("#666666")
XL_TEXT = xl_color("#000000")

rows = [
    (1, "01_需求分析.docx", "需求理解、功能清单、相对题目基础条目的设计增强、核心流程图及 AI 对话链接占位。"),
    (2, "02_原型设计.docx", "软件界面清单、界面内容说明及 8 张静态原型设计图；明确不作为真实产品运行证据。"),
    (3, "03_数据库设计.docx", "7 张数据表清单、逐表字段、数据表关系图及与 contracts/schema.sql 一致的逐表建表 SQL。"),
    (4, "04_接口设计.docx", "12 个 REST/Webhook/WebSocket 接口的清单及详情，含请求参数、响应示例、错误码、数据表和契约校验说明。"),
    (5, "05_初步验证.docx", "技术选择、验证清单、契约与原型的可复核结果，以及钉钉、飞书、统一 Web 闭环仍待补充的真实证据位。"),
    (6, "06_其他/可行性分析.docx", "技术、数据、时间三维可行性及主要难点与应对预案；如实区分设计、用户陈述与待归档证据。"),
    (7, "06_其他/设计文档精简版.docx", "业务闭环、系统架构、核心接口、关键表结构和状态机的精简设计可编辑版；官方要求的 PDF 成品待另行导出并实测页数。"),
    (8, "06_其他/代码仓库与运行说明.md", "仓库地址、当前代码边界、目标运行方式与健康检查口径；明确尚无产品源码及干净 checkout 运行记录。"),
]

wb = Workbook()
wb.properties.title = "初赛提交资料清单"
ws = wb.active
ws.title = "提交清单"

thin_side = Side(style="thin", color=XL_BORDER)
border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
header_fill = PatternFill("solid", fgColor=XL_PRIMARY)
title_fill = PatternFill("solid", fgColor=XL_LIGHT)

ws.merge_cells("A1:C1")
ws["A1"] = "初赛提交资料清单"
ws["A1"].font = Font(name="宋体", size=16, bold=True, color=XL_TEXT)
ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
ws["A1"].fill = title_fill
for col in range(1, 4):
    ws.cell(row=1, column=col).border = border

ws.merge_cells("A2:C2")
ws["A2"] = "报名序号：47　队长：廖俊健　队员：姚峰"
ws["A2"].font = Font(name="宋体", size=12, color=XL_TEXT)
ws["A2"].alignment = Alignment(horizontal="center", vertical="center")
for col in range(1, 4):
    ws.cell(row=2, column=col).border = border

headers = ["序号", "提交文档名", "内容简介"]
for col, value in enumerate(headers, 1):
    cell = ws.cell(row=3, column=col, value=value)
    cell.font = Font(name="宋体", size=12, bold=True, color=XL_WHITE)
    cell.fill = header_fill
    cell.alignment = Alignment(horizontal="center", vertical="center")
    cell.border = border

for offset, (serial, name, description) in enumerate(rows):
    row = 4 + offset
    values = [serial, name, description]
    for col, value in enumerate(values, 1):
        cell = ws.cell(row=row, column=col, value=value)
        cell.font = Font(name="宋体", size=12, color=XL_TEXT)
        cell.border = border
        if col in (1, 2):
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        else:
            cell.alignment = Alignment(horizontal="justify", vertical="top", wrap_text=True)
    ws.row_dimensions[row].height = 52

ws.column_dimensions["A"].width = 10
ws.column_dimensions["B"].width = 34
ws.column_dimensions["C"].width = 72
ws.freeze_panes = "A4"
ws.print_area = f"A1:C{3 + len(rows)}"
ws.page_setup.orientation = "portrait"
ws.page_setup.fitToWidth = 1
ws.page_setup.fitToHeight = 0
ws.sheet_properties.pageSetUpPr.fitToPage = True
ws.print_title_rows = "3:3"
ws.sheet_view.showGridLines = False

wb.save(OUTPUT)
print(f"generated: {OUTPUT}")
