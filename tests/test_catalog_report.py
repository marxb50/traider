import json

import pandas as pd
from PIL import Image

from super_trader_quant.backend.app.reporting.catalog_report import (
    build_catalog_report,
    google_sheet_csv_url,
)


def _create_image(path, color):
    Image.new("RGB", (120, 120), color=color).save(path)


def test_google_sheet_csv_url_converts_edit_link():
    url = "https://docs.google.com/spreadsheets/d/abc123/edit?gid=456#gid=456"
    assert google_sheet_csv_url(url) == "https://docs.google.com/spreadsheets/d/abc123/export?format=csv&gid=456"


def test_build_catalog_report_generates_html_pdf_and_ten_charts(tmp_path):
    logo_path = tmp_path / "logo.png"
    _create_image(logo_path, (20, 93, 141))

    image_paths = []
    for index, color in enumerate([(10, 90, 180), (30, 130, 190), (90, 180, 210)], start=1):
        image_path = tmp_path / f"photo_{index}.png"
        _create_image(image_path, color)
        image_paths.append(image_path)

    rows = []
    for index in range(12):
        rows.append(
            {
                "item_id": index + 1,
                "nome": f"Item {index + 1}",
                "categoria": ["Selim", "Acessorio", "Performance"][index % 3],
                "status": ["Novo", "Revisao"][index % 2],
                "score": 80 + index,
                "preco": 100 + (index * 7),
                "created_at": f"2026-01-{index + 1:02d}",
                "foto": str(image_paths[index % len(image_paths)]),
            }
        )
    source_path = tmp_path / "dataset.csv"
    pd.DataFrame(rows).to_csv(source_path, index=False)

    artifacts = build_catalog_report(
        sources=[str(source_path)],
        output_dir=tmp_path / "out",
        logo_path=str(logo_path),
        footer_text="feito por marx bruno",
        title="SELIM AZUL | Dashboard Premium",
        expected_records=12,
        image_quality=50,
    )

    assert artifacts.html_path.exists()
    assert artifacts.offline_html_path.exists()
    assert artifacts.pdf_path.exists()
    assert artifacts.summary_path.exists()
    assert artifacts.dataset_path.exists()
    assert len(artifacts.charts) == 10
    assert artifacts.image_count == 12
    html = artifacts.html_path.read_text(encoding="utf-8")
    offline_html = artifacts.offline_html_path.read_text(encoding="utf-8")
    assert "feito por marx bruno" in html
    assert "SELIM AZUL | Dashboard Premium" in html
    assert "data:image/" in offline_html

    summary = json.loads(artifacts.summary_path.read_text(encoding="utf-8"))
    assert summary["records"] == 12
    assert summary["expected_records"] == 12
    assert summary["image_count"] == 12
