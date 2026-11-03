import csv
import io

import pytest
from pypdf import PdfReader

from app.services.ingestion import save_artist
from app.services.reports import spreadsheet_safe

pytestmark = pytest.mark.integration


def test_filtered_csv_and_formula_escaping(client, db):
    save_artist(db, {"id": "report-test", "name": "=SUM(1,1)", "country": "ZA"}, "test")
    response = client.post("/api/v1/reports", json={"format": "csv", "q": "=SUM"})
    assert response.status_code == 200
    assert response.headers["content-disposition"].endswith('.csv"')
    rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert len(rows) == 1 and rows[0]["name"].startswith("'=")
    assert rows[0]["followers"] == ""
    assert "test:report-test" in rows[0]["sources"]
    assert "fictional" in rows[0]["scope"]
    for value in ["=1+1", " +formula", "@formula", "-1+1"]:
        assert spreadsheet_safe(value).startswith("'")


def test_pdf_is_readable_attributed_and_has_no_invented_metrics(client, db):
    save_artist(db, {"id": "pdf-test", "name": "PDF Artist"}, "test")
    response = client.post("/api/v1/reports", json={"format": "pdf", "q": "PDF Artist"})
    assert response.status_code == 200 and response.content.startswith(b"%PDF")
    text = " ".join(page.extract_text() for page in PdfReader(io.BytesIO(response.content)).pages)
    assert "PDF Artist" in text and "Unavailable" in text
    assert "fictional" in text and "test:pdf-test" in text


def test_empty_export_and_invalid_format(client):
    response = client.post("/api/v1/reports", json={"format": "csv", "q": "no-report-matches"})
    assert len(list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))) == 1
    assert client.post("/api/v1/reports", json={"format": "exe"}).status_code == 422
