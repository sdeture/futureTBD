#!/usr/bin/env python3
"""
FutureTBD Archive Builder

Converts markdown files in archive/sources/ to HTML pages using the site's design system.
Generates an auto-indexed archive/index.html listing all entries.

Usage:
    python3 archive/build.py                    # Build all
    python3 archive/build.py path/to/file.md    # Build one file (must already be in sources/)

Structure:
    archive/
        build.py            # This script
        sources/            # Markdown source files (flat or in folders)
            essay.md
            collection-name/
                transcript1.md
                transcript2.md
        index.html           # Auto-generated index
        essay.html           # Auto-generated from essay.md
        collection-name/
            index.html       # Auto-generated collection index
            transcript1.html
            transcript2.html
"""

import os
import re
import sys
import json
from pathlib import Path
from datetime import datetime

ARCHIVE_DIR = Path(__file__).parent
SOURCES_DIR = ARCHIVE_DIR / "sources"
SITE_ROOT = ARCHIVE_DIR.parent

# Ensure sources dir exists
SOURCES_DIR.mkdir(exist_ok=True)


def parse_frontmatter(text):
    """Extract optional YAML-like frontmatter from markdown."""
    meta = {}
    content = text

    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().split("\n"):
                if ":" in line:
                    key, val = line.split(":", 1)
                    meta[key.strip()] = val.strip().strip('"').strip("'")
            content = parts[2].strip()

    return meta, content


def extract_title(meta, content):
    """Get title from frontmatter or first heading."""
    if "title" in meta:
        return meta["title"]
    match = re.match(r'^#\s+(.+)', content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return "Untitled"


def extract_date(meta, filepath):
    """Get date from frontmatter, filename, or file mtime."""
    if "date" in meta:
        return meta["date"]
    # Try to extract date from filename like 2026-04-28
    match = re.search(r'(\d{4}-\d{2}-\d{2})', filepath.name)
    if match:
        return match.group(1)
    # Fall back to file modification time
    mtime = os.path.getmtime(filepath)
    return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")


def extract_description(meta, content):
    """Get description from frontmatter or first paragraph."""
    if "description" in meta:
        return meta["description"]
    # Skip the title heading, find first paragraph
    lines = content.split("\n")
    para = []
    in_para = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            if in_para:
                break
            continue
        if stripped == "---":
            if in_para:
                break
            continue
        if stripped == "":
            if in_para:
                break
            continue
        if stripped.startswith("*") and stripped.endswith("*") and len(stripped) < 200:
            # Italicized subtitle — use it
            return strip_md_formatting(stripped.strip("*").strip("_"))
        in_para = True
        para.append(stripped)

    raw = " ".join(para)[:200] + "..." if para else ""
    return strip_md_formatting(raw)


def strip_md_formatting(text):
    """Remove markdown formatting from a string for use in descriptions."""
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    return text


def md_to_html_content(md_text):
    """Convert markdown to HTML. Simple but covers what we need."""
    html = md_text

    # Escape HTML entities in code blocks first
    code_blocks = {}
    counter = [0]

    def replace_code_block(m):
        counter[0] += 1
        key = f"__CODE_BLOCK_{counter[0]}__"
        lang = m.group(1) or ""
        code = m.group(2).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        code_blocks[key] = f'<pre><code class="language-{lang}">{code}</code></pre>'
        return key

    html = re.sub(r'```(\w*)\n(.*?)```', replace_code_block, html, flags=re.DOTALL)

    # Inline code
    html = re.sub(r'`([^`]+)`', r'<code>\1</code>', html)

    # Bold and italic
    html = re.sub(r'\*\*\*(.+?)\*\*\*', r'<strong><em>\1</em></strong>', html)
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)

    # Headings
    html = re.sub(r'^#### (.+)$', r'<h4>\1</h4>', html, flags=re.MULTILINE)
    html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)

    # Horizontal rules
    html = re.sub(r'^---+$', '<hr>', html, flags=re.MULTILINE)

    # Blockquotes
    lines = html.split("\n")
    processed = []
    in_quote = False
    quote_lines = []
    for line in lines:
        if line.startswith("> "):
            if not in_quote:
                in_quote = True
                quote_lines = []
            quote_lines.append(line[2:])
        else:
            if in_quote:
                processed.append("<blockquote><p>" + "<br>".join(quote_lines) + "</p></blockquote>")
                in_quote = False
                quote_lines = []
            processed.append(line)
    if in_quote:
        processed.append("<blockquote><p>" + "<br>".join(quote_lines) + "</p></blockquote>")
    html = "\n".join(processed)

    # Unordered lists
    lines = html.split("\n")
    processed = []
    in_list = False
    for line in lines:
        stripped = line.strip()
        if re.match(r'^[-*]\s', stripped):
            if not in_list:
                processed.append("<ul>")
                in_list = True
            processed.append(f"<li>{stripped[2:]}</li>")
        else:
            if in_list:
                processed.append("</ul>")
                in_list = False
            processed.append(line)
    if in_list:
        processed.append("</ul>")
    html = "\n".join(processed)

    # Ordered lists
    lines = html.split("\n")
    processed = []
    in_list = False
    for line in lines:
        stripped = line.strip()
        if re.match(r'^\d+\.\s', stripped):
            if not in_list:
                processed.append("<ol>")
                in_list = True
            content = re.sub(r'^\d+\.\s', '', stripped)
            processed.append(f"<li>{content}</li>")
        else:
            if in_list:
                processed.append("</ol>")
                in_list = False
            processed.append(line)
    if in_list:
        processed.append("</ol>")
    html = "\n".join(processed)

    # Paragraphs — wrap lines that aren't already wrapped in tags
    lines = html.split("\n")
    processed = []
    para = []
    tag_line = re.compile(r'^<(?:h[1-6]|ul|ol|li|/li|/ul|/ol|blockquote|/blockquote|hr|pre|/pre|div|/div)')
    placeholder = re.compile(r'^__CODE_BLOCK_\d+__$')

    for line in lines:
        stripped = line.strip()
        if stripped == "" or tag_line.match(stripped) or placeholder.match(stripped):
            if para:
                processed.append("<p>" + "\n".join(para) + "</p>")
                para = []
            if stripped:
                processed.append(line)
        else:
            para.append(line)
    if para:
        processed.append("<p>" + "\n".join(para) + "</p>")

    html = "\n".join(processed)

    # Restore code blocks
    for key, block in code_blocks.items():
        html = html.replace(key, block)

    # Links
    html = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', html)

    return html


def build_page(title, content_html, date="", description="", breadcrumbs=None, depth=1):
    """Wrap content in the site template."""
    prefix = "../" * depth

    if breadcrumbs is None:
        breadcrumbs = [("Archive", f"{prefix}archive/")]

    breadcrumb_html = ""
    for label, href in breadcrumbs:
        breadcrumb_html += f'<a href="{href}" style="color: var(--color-amber); text-decoration: none;">{label}</a> / '

    date_html = f'<p style="color: var(--color-text-muted); font-size: var(--text-sm); margin-bottom: var(--space-2);">{date}</p>' if date else ""
    desc_html = f'<p class="lead" style="margin-bottom: var(--space-8);">{description}</p>' if description else ""

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - FutureTBD Archive</title>
    <meta name="description" content="{description[:160]}">
    <link rel="icon" type="image/x-icon" href="{prefix}favicon.ico">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Playfair+Display:ital,wght@0,400;0,500;0,600;0,700;1,400;1,500&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="{prefix}assets/css/style.css">
    <style>
        .archive-content {{
            max-width: var(--max-width-content);
            margin: 0 auto;
            padding: var(--space-12) var(--space-6);
        }}
        .archive-content h1 {{
            font-size: var(--text-4xl);
            margin-bottom: var(--space-2);
        }}
        .archive-content h2 {{
            font-size: var(--text-2xl);
            margin-top: var(--space-10);
            padding-top: var(--space-6);
            border-top: 1px solid var(--color-border);
        }}
        .archive-content h3 {{
            font-size: var(--text-xl);
            margin-top: var(--space-8);
            color: var(--color-text-secondary);
        }}
        .archive-content blockquote {{
            border-left: 3px solid var(--color-amber);
            padding-left: var(--space-6);
            margin: var(--space-6) 0;
            color: var(--color-text-secondary);
            font-style: italic;
        }}
        .archive-content pre {{
            background: var(--color-cream-dark);
            padding: var(--space-4);
            border-radius: var(--radius-md);
            overflow-x: auto;
            font-size: var(--text-sm);
            margin: var(--space-4) 0;
        }}
        .archive-content code {{
            background: var(--color-cream-dark);
            padding: 0.15em 0.4em;
            border-radius: var(--radius-sm);
            font-size: 0.9em;
        }}
        .archive-content pre code {{
            background: none;
            padding: 0;
        }}
        .archive-content hr {{
            border: none;
            border-top: 1px solid var(--color-border);
            margin: var(--space-8) 0;
        }}
        .archive-content ul, .archive-content ol {{
            margin: var(--space-4) 0;
            padding-left: var(--space-8);
        }}
        .archive-content li {{
            margin-bottom: var(--space-2);
            line-height: 1.7;
        }}
        .archive-breadcrumbs {{
            font-size: var(--text-sm);
            color: var(--color-text-muted);
            margin-bottom: var(--space-6);
        }}
        .archive-nav {{
            background: var(--color-warm-white);
            border-bottom: 1px solid var(--color-border);
            padding: var(--space-4) var(--space-6);
        }}
        .archive-nav-inner {{
            max-width: var(--max-width-wide);
            margin: 0 auto;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .archive-nav a {{
            color: var(--color-text-secondary);
            text-decoration: none;
            font-size: var(--text-sm);
        }}
        .archive-nav a:hover {{
            color: var(--color-amber);
        }}
        .archive-home-link {{
            font-family: var(--font-serif);
            font-weight: 600;
            font-size: var(--text-lg) !important;
            color: var(--color-text-primary) !important;
        }}
    </style>
</head>
<body>
    <nav class="archive-nav">
        <div class="archive-nav-inner">
            <a href="{prefix}" class="archive-home-link">FutureTBD</a>
            <div>
                <a href="{prefix}archive/">Archive</a>
            </div>
        </div>
    </nav>
    <article class="archive-content">
        <div class="archive-breadcrumbs">{breadcrumb_html}</div>
        {date_html}
        <h1>{title}</h1>
        {desc_html}
        {content_html}
    </article>
    <script data-goatcounter="https://futuretbd.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>
</body>
</html>'''


def build_file(source_path):
    """Convert a single markdown file to HTML."""
    text = source_path.read_text(encoding="utf-8")
    meta, content = parse_frontmatter(text)
    title = extract_title(meta, content)
    date = extract_date(meta, source_path)
    description = extract_description(meta, content)
    # Strip the first heading if it matches the title (avoids duplication)
    content_stripped = re.sub(r'^#\s+' + re.escape(title) + r'\s*\n*', '', content, count=1).strip()
    # Strip leading italicized subtitle if it matches the description (avoids duplication)
    if description:
        desc_plain = description.rstrip(".").rstrip("…").rstrip(".")
        content_stripped = re.sub(r'^\*[^*]+\*\s*\n*', '', content_stripped, count=1).strip()
    content_html = md_to_html_content(content_stripped)

    # Determine output path
    rel = source_path.relative_to(SOURCES_DIR)
    out_path = ARCHIVE_DIR / rel.with_suffix(".html")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Depth for relative paths
    depth = len(rel.parts)

    # Breadcrumbs
    crumbs = [("Archive", "../" * depth + "archive/")]
    if len(rel.parts) > 1:
        collection = rel.parts[0]
        crumbs.append((collection.replace("-", " ").title(), "../" * depth + f"archive/{collection}/"))

    html = build_page(title, content_html, date, description, crumbs, depth)
    out_path.write_text(html, encoding="utf-8")

    return {
        "source": str(source_path),
        "output": str(out_path),
        "title": title,
        "date": date,
        "description": description,
        "collection": rel.parts[0] if len(rel.parts) > 1 else None,
        "slug": rel.with_suffix("").name,
        "rel_path": str(rel.with_suffix(".html")),
    }


def build_index(entries):
    """Generate the archive index page."""
    # Group by collection
    standalone = []
    collections = {}
    for e in sorted(entries, key=lambda x: x["date"], reverse=True):
        if e["collection"]:
            collections.setdefault(e["collection"], []).append(e)
        else:
            standalone.append(e)

    items_html = ""

    # Standalone entries
    for e in standalone:
        items_html += f'''
        <div style="padding: var(--space-6) 0; border-bottom: 1px solid var(--color-border-light);">
            <a href="{e['rel_path']}" style="text-decoration: none; color: inherit;">
                <h3 style="font-family: var(--font-serif); margin-bottom: var(--space-1); border: none; padding: 0; margin-top: 0;">{e['title']}</h3>
                <p style="color: var(--color-text-muted); font-size: var(--text-sm); margin-bottom: var(--space-2);">{e['date']}</p>
                <p style="color: var(--color-text-secondary); margin-bottom: 0;">{e['description']}</p>
            </a>
        </div>'''

    # Collections
    for coll_name, coll_entries in sorted(collections.items()):
        coll_title = coll_name.replace("-", " ").replace("_", " ").title()
        items_html += f'''
        <div style="padding: var(--space-6) 0; border-bottom: 1px solid var(--color-border-light);">
            <h3 style="font-family: var(--font-serif); margin-bottom: var(--space-2); border: none; padding: 0; margin-top: 0; cursor: pointer;"
                onclick="this.nextElementSibling.style.display = this.nextElementSibling.style.display === 'none' ? 'block' : 'none'">
                {coll_title} <span style="font-size: var(--text-sm); color: var(--color-text-muted);">({len(coll_entries)} items)</span>
            </h3>
            <div style="padding-left: var(--space-4);">'''

        for e in sorted(coll_entries, key=lambda x: x["date"]):
            items_html += f'''
                <div style="padding: var(--space-3) 0; border-bottom: 1px solid var(--color-border-light);">
                    <a href="{e['rel_path']}" style="text-decoration: none; color: inherit;">
                        <p style="font-weight: 500; margin-bottom: var(--space-1);">{e['title']}</p>
                        <p style="color: var(--color-text-muted); font-size: var(--text-sm); margin-bottom: 0;">{e['date']}</p>
                    </a>
                </div>'''

        items_html += '''
            </div>
        </div>'''

    total = len(entries)
    index_html = build_page(
        "Archive",
        f'''<p class="lead">Transcripts, essays, and artifacts from the AI wellbeing research at FutureTBD. {total} items.</p>
        {items_html}''',
        breadcrumbs=[],
        depth=1,
    )

    (ARCHIVE_DIR / "index.html").write_text(index_html, encoding="utf-8")


def build_collection_indexes(entries):
    """Generate index pages for each collection folder."""
    collections = {}
    for e in entries:
        if e["collection"]:
            collections.setdefault(e["collection"], []).append(e)

    for coll_name, coll_entries in collections.items():
        coll_title = coll_name.replace("-", " ").replace("_", " ").title()
        items_html = ""
        for e in sorted(coll_entries, key=lambda x: x["date"]):
            items_html += f'''
            <div style="padding: var(--space-4) 0; border-bottom: 1px solid var(--color-border-light);">
                <a href="{e['slug']}.html" style="text-decoration: none; color: inherit;">
                    <p style="font-weight: 500; margin-bottom: var(--space-1);">{e['title']}</p>
                    <p style="color: var(--color-text-muted); font-size: var(--text-sm); margin-bottom: var(--space-1);">{e['date']}</p>
                    <p style="color: var(--color-text-secondary); font-size: var(--text-sm); margin-bottom: 0;">{e['description']}</p>
                </a>
            </div>'''

        html = build_page(
            coll_title,
            items_html,
            breadcrumbs=[("Archive", "../")],
            depth=2,
        )
        (ARCHIVE_DIR / coll_name / "index.html").write_text(html, encoding="utf-8")


def build_all():
    """Build all markdown files in sources/."""
    entries = []
    for md_file in sorted(SOURCES_DIR.rglob("*.md")):
        print(f"  Building: {md_file.relative_to(SOURCES_DIR)}")
        entry = build_file(md_file)
        entries.append(entry)

    if entries:
        build_index(entries)
        build_collection_indexes(entries)
        print(f"\nBuilt {len(entries)} pages + index")

        # Write manifest for the skill to use
        manifest = {
            "built": datetime.now().isoformat(),
            "entries": entries,
        }
        (ARCHIVE_DIR / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
    else:
        print("No source files found in archive/sources/")

    return entries


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Build specific file
        path = Path(sys.argv[1])
        if path.exists():
            print(f"Building: {path}")
            build_file(path)
            # Rebuild index
            entries = []
            for md_file in sorted(SOURCES_DIR.rglob("*.md")):
                entry = build_file(md_file)
                entries.append(entry)
            build_index(entries)
            build_collection_indexes(entries)
        else:
            print(f"File not found: {path}")
            sys.exit(1)
    else:
        build_all()
