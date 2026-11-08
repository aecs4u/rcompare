"""Folder and text-diff report formatting helpers."""

from __future__ import annotations

import csv
import html
import json
from collections import Counter
from itertools import zip_longest
from pathlib import Path
from string import Template
from typing import Iterable
from xml.etree import ElementTree


STATUS_LABELS = {
    "same": "Identical",
    "identical": "Identical",
    "different": "Different",
    "orphanleft": "Left Only",
    "left_only": "Left Only",
    "orphanright": "Right Only",
    "right_only": "Right Only",
    "unchecked": "Unchecked",
}

_FIELDS = (
    "path",
    "status",
    "is_directory",
    "left_size",
    "left_modified_unix",
    "right_size",
    "right_modified_unix",
)


def records_from_nodes(nodes: Iterable, *, include_sizes: bool = True) -> list[dict]:
    """Convert the folder view's currently accepted tree nodes to report rows."""
    rows = []
    for node in nodes:
        status = getattr(node.status, "value", str(node.status)).lower()
        row = {
            "path": node.path,
            "status": status,
            "is_directory": bool(node.is_dir),
            "left_size": node.left_size,
            "left_modified_unix": node.left_modified,
            "right_size": node.right_size,
            "right_modified_unix": node.right_modified,
        }
        if not include_sizes:
            row.pop("left_size")
            row.pop("right_size")
        rows.append(row)
    return sorted(rows, key=lambda row: (row["path"].casefold(), row["path"]))


def summarize_records(rows: Iterable[dict]) -> dict[str, int]:
    counts = Counter(row.get("status", "unchecked") for row in rows)
    return {
        "total": sum(counts.values()),
        "identical": counts["same"] + counts["identical"],
        "different": counts["different"],
        "left_only": counts["orphanleft"] + counts["left_only"],
        "right_only": counts["orphanright"] + counts["right_only"],
        "unchecked": counts["unchecked"],
    }


def export_folder_report(
    rows: list[dict],
    file_path: str,
    fmt: str,
    *,
    left_root: str = "",
    right_root: str = "",
    include_sizes: bool = True,
) -> None:
    """Write visible folder rows to CSV, JSON, text, HTML, or XML."""
    fmt = fmt.strip().lower()
    if fmt not in {"csv", "json", "text", "html", "xml"}:
        raise ValueError(f"Unsupported report format: {fmt}")

    dest = Path(file_path)
    summary = summarize_records(rows)
    payload = {
        "schema_version": 1,
        "left": left_root,
        "right": right_root,
        "summary": summary,
        "entries": rows,
    }

    if fmt == "json":
        dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    elif fmt == "csv":
        fields = [field for field in _FIELDS if include_sizes or field not in {"left_size", "right_size"}]
        with dest.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    elif fmt == "text":
        lines = [
            "RCompare folder comparison report",
            f"Left: {left_root}",
            f"Right: {right_root}",
            "Summary: " + ", ".join(f"{key.replace('_', ' ')} {value}" for key, value in summary.items()),
            "",
        ]
        for row in rows:
            label = _status_label(row.get("status", "unchecked"))
            details = [f"{label}: {row.get('path', '')}"]
            if "left_size" in row:
                details.append(f"left={row.get('left_size') if row.get('left_size') is not None else '—'}")
                details.append(f"right={row.get('right_size') if row.get('right_size') is not None else '—'}")
            lines.append("  ".join(details))
        dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    elif fmt == "html":
        dest.write_text(_folder_report_html(payload, include_sizes=include_sizes), encoding="utf-8")
    else:
        dest.write_text(_folder_report_xml(payload), encoding="utf-8")


def _status_label(status: str) -> str:
    return STATUS_LABELS.get(status.lower(), status)


def _cell(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def _folder_report_html(payload: dict, *, include_sizes: bool = True) -> str:
    escaped = html.escape
    summary = payload["summary"]
    columns = [
        field for field in _FIELDS
        if include_sizes or field not in {"left_size", "right_size"}
    ]
    labels = {
        "path": "Path",
        "status": "Status",
        "is_directory": "Directory",
        "left_size": "Left size (bytes)",
        "left_modified_unix": "Left modified (Unix)",
        "right_size": "Right size (bytes)",
        "right_modified_unix": "Right modified (Unix)",
    }
    headings = "".join(f"<th>{escaped(labels[field])}</th>" for field in columns)
    body = []
    for row in payload["entries"]:
        values = dict(row)
        values["status"] = _status_label(str(values.get("status", "unchecked")))
        cells = "".join(f"<td>{escaped(_cell(values.get(field)))}</td>" for field in columns)
        body.append(f"<tr>{cells}</tr>")
    summary_items = "".join(
        f"<li>{escaped(key.replace('_', ' ').title())}: {value}</li>"
        for key, value in summary.items()
    )
    return Template("""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>RCompare folder report</title>
<style>body{font:14px sans-serif;margin:2rem;color:#222}table{border-collapse:collapse;width:100%}
th,td{border:1px solid #bbb;padding:.35rem .5rem;text-align:left}th{background:#eee}
td:first-child{overflow-wrap:anywhere}tbody tr:nth-child(even){background:#f7f7f7}</style></head><body>
<h1>RCompare folder comparison report</h1>
<p><b>Left:</b> $left<br><b>Right:</b> $right</p><h2>Summary</h2><ul>$summary</ul>
<h2>Entries</h2><table><thead><tr>$headings</tr></thead><tbody>$body</tbody></table>
</body></html>
""").substitute(
        left=escaped(str(payload["left"])),
        right=escaped(str(payload["right"])),
        summary=summary_items,
        headings=headings,
        body="\n".join(body),
    )


def _folder_report_xml(payload: dict) -> str:
    root = ElementTree.Element("comparison-report", {"schema-version": "1"})
    ElementTree.SubElement(root, "left").text = str(payload["left"])
    ElementTree.SubElement(root, "right").text = str(payload["right"])
    summary = ElementTree.SubElement(root, "summary", {"total": str(payload["summary"]["total"])})
    for name, count in payload["summary"].items():
        if name != "total":
            ElementTree.SubElement(summary, name.replace("_", "-"), {"count": str(count)})
    entries = ElementTree.SubElement(root, "entries")
    for row in payload["entries"]:
        item = ElementTree.SubElement(
            entries,
            "entry",
            {
                "status": str(row.get("status", "unchecked")),
                "directory": str(bool(row.get("is_directory", False))).lower(),
            },
        )
        ElementTree.SubElement(item, "path").text = str(row.get("path", ""))
        for field in _FIELDS[3:]:
            if field in row and row[field] is not None:
                ElementTree.SubElement(item, field.replace("_", "-")).text = str(row[field])
    return ElementTree.tostring(root, encoding="unicode", xml_declaration=True) + "\n"


def text_diff_html(
    left_label: str,
    right_label: str,
    left_lines: list[str],
    right_lines: list[str],
) -> str:
    """Create an escaped side-by-side HTML view of aligned text-diff rows."""
    escaped = html.escape
    rows = []
    for index, (left, right) in enumerate(zip_longest(left_lines, right_lines, fillvalue=""), 1):
        if left == right:
            kind = "same"
        elif not right:
            kind = "removed"
        elif not left:
            kind = "added"
        else:
            kind = "changed"
        rows.append(
            f'<tr class="{kind}"><th>{index}</th><td><pre>{escaped(left)}</pre></td>'
            f'<td><pre>{escaped(right)}</pre></td></tr>'
        )
    return Template("""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>RCompare text diff</title>
<style>body{font:14px sans-serif;margin:2rem;color:#222}table{border-collapse:collapse;width:100%;table-layout:fixed}
th,td{border:1px solid #bbb;padding:.25rem .5rem;vertical-align:top}th{width:3rem;background:#eee}
td{width:calc((100% - 4rem)/2)}pre{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}
.removed td:nth-child(2){background:#ffdddd}.added td:nth-child(3){background:#ddffdd}
.changed td:nth-child(2){background:#ffdddd}.changed td:nth-child(3){background:#ddffdd}</style></head><body>
<h1>RCompare text comparison</h1><table><thead><tr><th>#</th><th>$left</th><th>$right</th></tr></thead>
<tbody>$rows</tbody></table></body></html>
""").substitute(left=escaped(left_label), right=escaped(right_label), rows="\n".join(rows))
