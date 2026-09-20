#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
零依赖 xlsx 生成器（不依赖 openpyxl / pandas）

背景：本机 WorkBuddy 环境无法通过 pip 安装 openpyxl（沙箱网络受限），
但交付物规范要求 xlsx。故用标准库 zipfile 直接拼最小可用的 OOXML。

用法：
  python make_xlsx.py <输出路径> --data <数据json>

数据 json 结构：
{
  "sheets": [
    {
      "name": "竞品对比",
      "freeze": 1,                  # 冻结前 N 行，0/省略 = 不冻结
      "autofilter": true,           # 是否加筛选
      "columns": [ {"title": "字段", "width": 22}, ... ],
      "rows": [ ["ASIN", "B0GZ...", null], ... ]   # null → 空单元格
    }
  ]
}
"""
import json
import os
import re
import sys
import zipfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def col_letter(i):
    """0 → A, 25 → Z, 26 → AA"""
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
{sheet_overrides}
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>"""

RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="2">
<font><sz val="11"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><name val="Calibri"/></font>
</fonts>
<fills count="3">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFEDEDED"/><bgColor indexed="64"/></patternFill></fill>
</fills>
<borders count="2">
<border><left/><right/><top/><bottom/><diagonal/></border>
<border><left style="thin"><color rgb="FFBFBFBF"/></left><right style="thin"><color rgb="FFBFBFBF"/></right><top style="thin"><color rgb="FFBFBFBF"/></top><bottom style="thin"><color rgb="FFBFBFBF"/></bottom><diagonal/></border>
</borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="3">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""


def build_sheet_xml(sheet, idx):
    cols = sheet.get("columns") or []
    rows = sheet.get("rows") or []
    freeze = sheet.get("freeze") or 0

    parts = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>']
    parts.append('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">')

    # 冻结窗格
    if freeze:
        parts.append(
            '<sheetViews><sheetView workbookViewId="0">'
            f'<pane ySplit="{freeze}" topLeftCell="A{freeze + 1}" '
            'activePane="bottomLeft" state="frozen"/>'
            '</sheetView></sheetViews>'
        )
    else:
        parts.append('<sheetViews><sheetView workbookViewId="0"/></sheetViews>')

    # 列宽
    if cols:
        parts.append("<cols>")
        for i, c in enumerate(cols):
            w = c.get("width") or 18
            parts.append(f'<col min="{i+1}" max="{i+1}" width="{w}" customWidth="1"/>')
        parts.append("</cols>")

    parts.append("<sheetData>")

    # 表头
    if cols:
        parts.append('<row r="1" ht="26" customHeight="1">')
        for i, c in enumerate(cols):
            parts.append(
                f'<c r="{col_letter(i)}1" t="inlineStr" s="1">'
                f'<is><t>{esc(c.get("title", ""))}</t></is></c>'
            )
        parts.append("</row>")

    # 数据行
    for ri, row in enumerate(rows, start=2):
        parts.append(f'<row r="{ri}">')
        for ci, val in enumerate(row):
            if val is None or val == "":
                continue
            ref = f"{col_letter(ci)}{ri}"
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                parts.append(f'<c r="{ref}" s="2"><v>{val}</v></c>')
            else:
                parts.append(
                    f'<c r="{ref}" t="inlineStr" s="2">'
                    f'<is><t xml:space="preserve">{esc(val)}</t></is></c>'
                )
        parts.append("</row>")

    parts.append("</sheetData>")

    if sheet.get("autofilter") and cols and rows:
        last = f"{col_letter(len(cols) - 1)}{len(rows) + 1}"
        parts.append(f'<autoFilter ref="A1:{last}"/>')

    parts.append("</worksheet>")
    return "".join(parts)


def build(path, data):
    sheets = data["sheets"]
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    overrides = "\n".join(
        f'<Override PartName="/xl/worksheets/sheet{i+1}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for i in range(len(sheets))
    )

    sheet_tags = "".join(
        f'<sheet name="{esc(s["name"])}" sheetId="{i+1}" r:id="rId{i+1}"/>'
        for i, s in enumerate(sheets)
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{sheet_tags}</sheets></workbook>"
    )

    rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
    for i in range(len(sheets)):
        rels.append(
            f'<Relationship Id="rId{i+1}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{i+1}.xml"/>'
        )
    rels.append(
        f'<Relationship Id="rId{len(sheets)+1}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'
    )
    rels.append("</Relationships>")

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES.format(sheet_overrides=overrides))
        z.writestr("_rels/.rels", RELS)
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", "".join(rels))
        z.writestr("xl/styles.xml", STYLES)
        for i, s in enumerate(sheets):
            z.writestr(f"xl/worksheets/sheet{i+1}.xml", build_sheet_xml(s, i))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    out = sys.argv[1]
    if "--data" not in sys.argv:
        print("缺少 --data <json路径>", file=sys.stderr)
        sys.exit(1)
    src = sys.argv[sys.argv.index("--data") + 1]
    with open(src, encoding="utf-8") as f:
        data = json.load(f)
    build(out, data)
    print(f"已生成 {out}（{len(data['sheets'])} 个工作表，{os.path.getsize(out)} bytes）")


if __name__ == "__main__":
    main()
