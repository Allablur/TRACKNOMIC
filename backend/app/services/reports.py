import csv
import io
from datetime import UTC, datetime
from html import escape
from pathlib import Path

import reportlab
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def spreadsheet_safe(value):
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def csv_report(artists: list[dict], filters: dict) -> bytes:
    output = io.StringIO(newline="")
    fields = [
        "name",
        "country",
        "album_count",
        "track_count",
        "followers",
        "popularity",
        "metrics_provider",
        "metrics_captured_at",
        "sources",
        "scope",
        "generated_at",
        "filters",
    ]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    generated = datetime.now(UTC).isoformat()
    for artist in artists:
        row = {key: artist.get(key) for key in fields}
        row.update(
            sources="; ".join(f"{s['provider']}:{s['external_id']}" for s in artist["sources"]),
            scope="Tracked catalogue; demo sources are fictional; missing metrics unavailable",
            generated_at=generated,
            filters=str(filters),
        )
        writer.writerow({key: spreadsheet_safe(value) for key, value in row.items()})
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def pdf_report(
    artists: list[dict],
    filters: dict,
    summary: dict,
    genre_rows: list[dict],
    release_rows: list[dict],
) -> bytes:
    buffer = io.BytesIO()
    if "Catalogue" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(
            TTFont("Catalogue", str(Path(reportlab.__file__).parent / "fonts/Vera.ttf"))
        )
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName = "Catalogue"
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=30,
        rightMargin=30,
        topMargin=30,
        bottomMargin=30,
        title="Trackonomics catalogue report",
    )

    def paragraph(value):
        return Paragraph(escape(str(value)), styles["BodyText"])

    content = [
        Paragraph("Trackonomics / Catalogue report", styles["Title"]),
        paragraph("Generated " + datetime.now(UTC).isoformat()),
        paragraph("Filters: " + str(filters)),
        paragraph(
            "Scope: tracked catalogue, not global music popularity. "
            "Demo records are fictional. Missing audience metrics are unavailable. "
            "Imported discographies may be partial."
        ),
        Spacer(1, 12),
        paragraph(
            f"Artists: {summary['artists']} | Release editions: {summary['albums']} | "
            f"Unique recordings: {summary['tracks']}"
        ),
        paragraph(
            "Genres (artists may have multiple tags): "
            + (", ".join(f"{g['genre']}: {g['artists']}" for g in genre_rows) or "Unavailable")
        ),
        paragraph(
            "Release activity (known dates): "
            + (", ".join(f"{y['year']}: {y['releases']}" for y in release_rows) or "Unavailable")
        ),
        Spacer(1, 15),
    ]
    rows = [
        [
            paragraph(h)
            for h in [
                "Artist / country",
                "Releases",
                "Tracks",
                "Followers",
                "Popularity",
                "Sources / metric capture",
            ]
        ]
    ]
    for artist in artists:

        def metric(key, item=artist):
            return "Unavailable" if item[key] is None else str(item[key])

        sources = ", ".join(f"{s['provider']}:{s['external_id']}" for s in artist["sources"])
        source_text = (
            sources
            + " | Metrics: "
            + (artist["metrics_provider"] or "Unavailable")
            + " / "
            + (artist["metrics_captured_at"] or "Unavailable")
        )
        rows.append(
            [
                paragraph(v)
                for v in [
                    artist["name"] + " / " + (artist["country"] or "Unavailable"),
                    artist["album_count"],
                    artist["track_count"],
                    metric("followers"),
                    metric("popularity"),
                    source_text,
                ]
            ]
        )
    if not artists:
        content.append(paragraph("No matching artists. Try another filter."))
    table = Table(rows, colWidths=[165, 55, 50, 85, 85, 340], repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8edf0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#d8e0e3")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    content.append(table)
    document.build(content)
    return buffer.getvalue()
