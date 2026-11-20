from pathlib import Path
import html
import re

ROOT = Path("C:/doc/project/UnifiedMessagesManagement")
DOCS = [
    ("submission-01", "01-requirements-analysis.md", "需求分析"),
    ("submission-02", "02-prototype-design.md", "原型设计"),
    ("submission-03", "03-database-design.md", "数据库设计"),
    ("submission-04", "04-api-design.md", "接口设计"),
    ("submission-05", "05-preliminary-validation.md", "初步验证"),
    ("submission-06-feasibility", "06-feasibility-analysis.md", "可行性分析"),
    ("submission-06-design", "06-preliminary-design.md", "设计文档精简版"),
]


def inline(text):
    value = html.escape(text.strip())
    value = re.sub(r"`([^`]+)`", r"<code>\1</code>", value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", value)
    return value


def split_row(line):
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def clean_caption(text):
    value = re.sub(r"^\d+(?:\.\d+)*\.?\s*", "", text)
    value = re.sub(r"^表\s*\d+\s*", "", value)
    return value.replace("`", "")


def markdown_to_html(md, title):
    lines = md.splitlines()
    cover_status = "提交整理稿"
    start = 0
    for index, line in enumerate(lines):
        if line.startswith("> 状态："):
            cover_status = line[2:].strip()
        if index > 0 and not line.strip() and index + 1 < len(lines) and lines[index + 1].startswith("## "):
            start = index + 1
            break
    body_lines = lines[start:]
    headings = []
    for line in body_lines:
        match = re.match(r"^(#{2,4})\s+(.+)$", line)
        if match:
            headings.append([len(match.group(1)) - 1, match.group(2).strip(), ""])
    h1_no = 0
    h2_no = 0
    for item in headings:
        if item[0] == 1:
            h1_no += 1
            h2_no = 0
            item[2] = f"section-{h1_no}"
        elif item[0] == 2:
            h2_no += 1
            item[2] = f"section-{h1_no}-{h2_no}"
        else:
            item[2] = f"section-{h1_no}-{h2_no}-detail"

    toc = []
    h1_open = False
    sub_open = False
    for level, text, anchor in headings:
        if level == 1:
            if sub_open:
                toc.append("</ol>")
                sub_open = False
            if h1_open:
                toc.append("</li>")
            toc.append(f'<li><a href="#{anchor}">{html.escape(text)}</a>')
            h1_open = True
        elif level == 2 and h1_open:
            if not sub_open:
                toc.append("<ol>")
                sub_open = True
            toc.append(f'<li><a href="#{anchor}">{html.escape(text)}</a></li>')
    if sub_open:
        toc.append("</ol>")
    if h1_open:
        toc.append("</li>")

    output = []
    i = 0
    heading_index = -1
    table_no = 0
    current_heading = title
    while i < len(body_lines):
        line = body_lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        heading = re.match(r"^(#{2,4})\s+(.+)$", stripped)
        if heading:
            heading_index += 1
            level = len(heading.group(1)) - 1
            text = heading.group(2).strip()
            anchor = headings[heading_index][2]
            current_heading = text
            output.append(f'<h{level} id="{anchor}">{inline(text)}</h{level}>')
            i += 1
            continue
        image = re.match(r"^!\[([^]]*)\]\(([^)]+)\)$", stripped)
        if image:
            alt, target = image.groups()
            image_path = (ROOT / "docs/submissions/source" / target).resolve()
            output.append(f'<figure><p><img src="{html.escape(str(image_path))}" alt="{html.escape(alt)}"></p><figcaption><p>{html.escape(alt)}</p></figcaption></figure>')
            i += 1
            continue
        if stripped.startswith("```"):
            language = stripped[3:].strip()
            code = []
            i += 1
            while i < len(body_lines) and not body_lines[i].strip().startswith("```"):
                code.append(body_lines[i])
                i += 1
            i += 1
            output.append(f'<pre><code class="language-{html.escape(language)}">{html.escape(chr(10).join(code))}</code></pre>')
            continue
        if stripped.startswith("|") and i + 1 < len(body_lines) and re.match(r"^\|?[\s:|-]+\|", body_lines[i + 1].strip()):
            table_no += 1
            header = split_row(stripped)
            i += 2
            rows = []
            while i < len(body_lines) and body_lines[i].strip().startswith("|"):
                rows.append(split_row(body_lines[i]))
                i += 1
            caption = clean_caption(current_heading)
            suffix = "字段内容" if current_heading.startswith("表 ") else ""
            output.append(f'<table><caption>表 {table_no} {html.escape(caption)}{suffix}</caption><thead><tr>')
            output.extend(f"<th>{inline(cell)}</th>" for cell in header)
            output.append("</tr></thead><tbody>")
            for row in rows:
                output.append("<tr>")
                output.extend(f"<td>{inline(cell)}</td>" for cell in row)
                output.append("</tr>")
            output.append("</tbody></table>")
            continue
        if re.match(r"^[-*]\s+", stripped):
            output.append("<ul>")
            while i < len(body_lines) and re.match(r"^[-*]\s+", body_lines[i].strip()):
                output.append(f"<li>{inline(re.sub(r'^[-*]\\s+', '', body_lines[i].strip()))}</li>")
                i += 1
            output.append("</ul>")
            continue
        if re.match(r"^\d+\.\s+", stripped):
            output.append("<ol>")
            while i < len(body_lines) and re.match(r"^\d+\.\s+", body_lines[i].strip()):
                output.append(f"<li>{inline(re.sub(r'^\\d+\\.\\s+', '', body_lines[i].strip()))}</li>")
                i += 1
            output.append("</ol>")
            continue
        paragraph = [stripped]
        i += 1
        while i < len(body_lines):
            candidate = body_lines[i].strip()
            if not candidate or re.match(r"^(#{2,4})\s+|^!\[|^```|^\||^[-*]\s+|^\d+\.\s+", candidate):
                break
            paragraph.append(candidate)
            i += 1
        output.append(f"<p>{inline(' '.join(paragraph))}</p>")

    css = """
:root {
  --ff-body: SimSun, 宋体, serif;
  --ff-heading: SimSun, 宋体, serif;
  --ff-mono: Consolas, monospace;
  --fs-body: 12pt;
  --fs-h1: 12pt;
  --fs-h2: 12pt;
  --fs-h3: 12pt;
  --fs-cover-project: 16pt;
  --fs-cover-title: 14pt;
  --fs-caption: 12pt;
  --lh-body: 1.5;
  --fw-bold: 700;
  --fw-normal: 400;
  --color-text: #000000;
  --color-muted: #444444;
  --color-border: #666666;
  --color-table-header: #E7E6E6;
  --color-background: #FFFFFF;
  --spacing-paragraph: 0.55em;
  --spacing-section: 1.25em;
  --spacing-block: 0.75em;
  --spacing-cover: 2.5em;
  --spacing-image: 0.5em;
  --margin-page: 2.54cm 2.4cm 2.54cm 2.8cm;
  --margin-auto: auto;
  --page-content-width: 15.6cm;
  --border-table: 1px solid var(--color-border);
  --align-center: center;
  --align-justify: justify;
  --align-left: left;
  --indent-body: 2em;
  --indent-none: 0;
  --width-full: 100%;
  --width-image: 100%;
  --weight-normal: normal;
  --style-none: none;
}
@page { margin: var(--margin-page); @bottom-center { content: counter(page); font-family: var(--ff-body); font-size: var(--fs-body); } }
@page cover { @bottom-center { content: none; } }
section[role="cover"] { page: cover; }
body { max-width: var(--page-content-width); margin-left: var(--margin-auto); margin-right: var(--margin-auto); background: var(--color-background); color: var(--color-text); font-family: var(--ff-body); font-size: var(--fs-body); line-height: var(--lh-body); }
p { font-family: var(--ff-body); font-size: var(--fs-body); font-weight: var(--fw-normal); line-height: var(--lh-body); text-align: var(--align-justify); text-indent: var(--indent-body); margin-top: var(--spacing-paragraph); margin-bottom: var(--spacing-paragraph); }
h1, h2, h3 { font-family: var(--ff-heading); color: var(--color-text); font-weight: var(--fw-bold); line-height: var(--lh-body); text-align: var(--align-left); margin-top: var(--spacing-section); margin-bottom: var(--spacing-block); }
h1 { font-size: var(--fs-h1); }
h2 { font-size: var(--fs-h2); }
h3 { font-size: var(--fs-h3); }
.cover-project { font-family: var(--ff-body); font-size: var(--fs-cover-project); font-weight: var(--fw-bold); text-align: var(--align-center); text-indent: var(--indent-none); margin-top: var(--spacing-cover); }
.cover-title { font-family: var(--ff-body); font-size: var(--fs-cover-title); font-weight: var(--fw-bold); text-align: var(--align-center); text-indent: var(--indent-none); margin-top: var(--spacing-cover); }
.cover-meta, .cover-status { font-family: var(--ff-body); font-size: var(--fs-cover-title); font-weight: var(--fw-normal); text-align: var(--align-center); text-indent: var(--indent-none); line-height: var(--lh-body); }
.cover-status { font-size: var(--fs-body); color: var(--color-muted); margin-top: var(--spacing-cover); }
.toc-title { font-family: var(--ff-body); font-size: var(--fs-cover-title); font-weight: var(--fw-bold); text-align: var(--align-center); text-indent: var(--indent-none); }
.toc-list, .toc-list ol, .toc-list ul { list-style: var(--style-none); }
.toc-list li, .toc-list li a { font-family: var(--ff-body); font-size: var(--fs-body); color: var(--color-text); line-height: var(--lh-body); text-indent: var(--indent-none); }
table { width: var(--width-full); border-collapse: collapse; margin-top: var(--spacing-block); margin-bottom: var(--spacing-block); }
caption { font-family: var(--ff-body); font-size: var(--fs-caption); font-weight: var(--fw-bold); text-align: var(--align-center); margin-bottom: var(--spacing-image); }
th, td { border: var(--border-table); font-family: var(--ff-body); font-size: var(--fs-body); line-height: var(--lh-body); color: var(--color-text); text-align: var(--align-left); padding: var(--spacing-image); vertical-align: top; }
th { font-weight: var(--fw-bold); text-align: var(--align-center); background: var(--color-table-header); }
figure { margin-top: var(--spacing-block); margin-bottom: var(--spacing-block); }
figure p, figcaption p { text-align: var(--align-center); text-indent: var(--indent-none); font-family: var(--ff-body); font-size: var(--fs-caption); }
img { max-width: var(--width-image); }
ul, ol { font-family: var(--ff-body); font-size: var(--fs-body); line-height: var(--lh-body); }
li { font-family: var(--ff-body); font-size: var(--fs-body); line-height: var(--lh-body); color: var(--color-text); }
code { font-family: var(--ff-mono); font-size: var(--fs-body); }
pre { font-family: var(--ff-mono); font-size: var(--fs-body); line-height: var(--lh-body); white-space: pre-wrap; text-align: var(--align-left); }
pre code { font-family: var(--ff-mono); font-size: var(--fs-body); }
"""
    return f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="docx-page-size" content="A4"><title>{html.escape(title)}</title><style>{css}</style></head>
<body>
<section role="cover">
<p class="cover-project">UnifiedMessagesManagement<br>多平台连接器与统一消息管理</p>
<p class="cover-title">{html.escape(title)}</p>
<p class="cover-meta">报名序号：47</p>
<p class="cover-meta">队长：廖俊健　队员：姚峰</p>
<p class="cover-status">{html.escape(cover_status)}</p>
</section>
<section role="cover"><nav class="doc-toc" aria-label="文档目录"><p class="toc-title">目录</p><ol class="toc-list">{''.join(toc)}</ol></nav></section>
<section role="body" data-page-restart="1">{''.join(output)}<p>　</p></section>
</body></html>'''


for request_id, filename, title in DOCS:
    source = ROOT / "docs/submissions/source" / filename
    text = source.read_text(encoding="utf-8")
    if filename == "03-database-design.md":
        schema = (ROOT / "contracts/schema.sql").read_text(encoding="utf-8")
        statements = re.findall(r"CREATE TABLE\s+(\w+)\s*\(.*?\) ENGINE=.*?;", schema, flags=re.S)
        parts = re.split(r"(?=CREATE TABLE\s+\w+)", schema)
        sql_sections = []
        for part in parts:
            match = re.match(r"CREATE TABLE\s+(\w+)", part)
            if match:
                sql_sections.append(f"### {match.group(1)}\n\n```sql\n{part.strip()}\n```")
        anchor = "完整建表 SQL 与字段、约束和索引的最终版本见 `contracts/schema.sql`。提交版 Word 将按表拆分为独立 `CREATE TABLE` 语句，确保每张表均可独立审查。"
        replacement = "以下 SQL 与 `contracts/schema.sql` 一致，每张表单独列出可执行建表语句。\n\n" + "\n\n".join(sql_sections)
        text = text.replace(anchor, replacement)
    out = ROOT / "output" / request_id
    digest = f"# 资料摘要\n\n- 主资料：{source}\n- 整理方式：只根据资料整理，保留事实边界与原始结构。\n- 文档：{title}\n- 补充约束：封面、自动目录、正文页码；正文与三级标题经用户确认采用宋体小四 12pt。\n"
    if filename == "03-database-design.md":
        digest += f"- SQL 来源：{ROOT / 'contracts/schema.sql'}\n"
    (out / "sources/materials_digest.md").write_text(digest, encoding="utf-8")
    (out / "stage1/organized_draft.md").write_text(text, encoding="utf-8")
    rendered = markdown_to_html(text, title)
    (out / f"stage2/formatted-{title}.html").write_text(rendered, encoding="utf-8")
    print(f"{request_id}: {len(text)} chars, {len(rendered)} html chars")
