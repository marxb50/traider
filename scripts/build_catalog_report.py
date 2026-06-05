from __future__ import annotations

import argparse

from super_trader_quant.backend.app.reporting import build_catalog_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera um dashboard premium em HTML e PDF a partir de planilhas locais ou na nuvem.")
    parser.add_argument("--source", action="append", required=True, help="Fonte de dados. Aceita CSV/TSV/XLSX/JSON local ou URL do Google Sheets/CSV.")
    parser.add_argument("--output-dir", help="Diretorio de saida para os artefatos.")
    parser.add_argument("--logo", help="Caminho da logo que deve aparecer em todas as paginas.")
    parser.add_argument("--footer", default="feito por marx bruno", help="Texto do rodape do HTML e PDF.")
    parser.add_argument("--title", default="SELIM AZUL | Dashboard Premium", help="Titulo principal do relatorio.")
    parser.add_argument("--expected-records", type=int, default=780, help="Meta esperada de registros para validar cobertura.")
    parser.add_argument("--image-quality", type=int, default=55, help="Qualidade JPEG das imagens otimizadas para HTML/PDF.")
    parser.add_argument("--image-max-size", type=int, default=1440, help="Lado maximo das imagens processadas.")
    args = parser.parse_args()

    artifacts = build_catalog_report(
        sources=args.source,
        output_dir=args.output_dir,
        logo_path=args.logo,
        footer_text=args.footer,
        title=args.title,
        expected_records=args.expected_records,
        image_quality=args.image_quality,
        image_max_size=args.image_max_size,
    )
    print(f"records: {artifacts.record_count}")
    print(f"images: {artifacts.image_count}")
    print(f"html: {artifacts.html_path}")
    print(f"offline_html: {artifacts.offline_html_path}")
    print(f"pdf: {artifacts.pdf_path}")
    print(f"summary: {artifacts.summary_path}")
    print(f"dataset: {artifacts.dataset_path}")
    print(f"charts: {len(artifacts.charts)}")
    for issue in artifacts.issues:
        print(f"issue: {issue}")


if __name__ == "__main__":
    main()
