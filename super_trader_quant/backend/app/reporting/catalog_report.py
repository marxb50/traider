from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO, StringIO
from math import ceil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from base64 import b64encode
import hashlib
import json
import re
from urllib.parse import parse_qs, urlparse

import matplotlib

matplotlib.use("Agg")

from matplotlib import pyplot as plt
from matplotlib import colors as mcolors
import numpy as np
import pandas as pd
from PIL import Image, ImageOps
import requests
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image as PdfImage,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from ..config import settings


LIKELY_IMAGE_COLUMNS = (
    "image",
    "images",
    "img",
    "photo",
    "photos",
    "foto",
    "fotos",
    "thumbnail",
    "logo",
    "picture",
)
LIKELY_DATETIME_COLUMNS = ("date", "data", "created", "updated", "time", "timestamp")
LIKELY_CATEGORICAL_COLUMNS = (
    "category",
    "categoria",
    "type",
    "tipo",
    "status",
    "segment",
    "grupo",
    "group",
    "brand",
    "marca",
    "city",
    "cidade",
    "state",
    "estado",
    "region",
    "regiao",
)


@dataclass(frozen=True)
class BrandPalette:
    background: str
    surface: str
    primary: str
    secondary: str
    accent: str
    muted: str
    text: str

    def chart_colors(self) -> list[str]:
        return [
            self.primary,
            self.secondary,
            self.accent,
            "#4FB0C6",
            "#6C7A89",
            "#96C93D",
            "#F9A03F",
            "#E55934",
        ]


@dataclass(frozen=True)
class ChartArtifact:
    title: str
    chart_type: str
    path: Path
    summary: str


@dataclass(frozen=True)
class ReportArtifacts:
    html_path: Path
    offline_html_path: Path
    pdf_path: Path
    summary_path: Path
    dataset_path: Path
    charts: list[ChartArtifact]
    image_count: int
    record_count: int
    issues: list[str]


def _slugify(value: str) -> str:
    lowered = re.sub(r"[^a-zA-Z0-9]+", "_", str(value).strip().lower())
    return lowered.strip("_") or "col"


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    return tuple(int(value.lstrip("#")[index : index + 2], 16) for index in (0, 2, 4))


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _mix(color_a: str, color_b: str, weight: float) -> str:
    rgb_a = np.array(_hex_to_rgb(color_a))
    rgb_b = np.array(_hex_to_rgb(color_b))
    mixed = np.clip((rgb_a * (1 - weight)) + (rgb_b * weight), 0, 255).astype(int)
    return _rgb_to_hex(tuple(int(value) for value in mixed))


def _luminance(color: str) -> float:
    red, green, blue = [channel / 255 for channel in _hex_to_rgb(color)]
    return (0.2126 * red) + (0.7152 * green) + (0.0722 * blue)


def google_sheet_csv_url(url: str) -> str:
    parsed = urlparse(url)
    if "docs.google.com" not in parsed.netloc or "/spreadsheets/" not in parsed.path:
        return url
    match = re.search(r"/d/([a-zA-Z0-9-_]+)", parsed.path)
    if not match:
        return url
    sheet_id = match.group(1)
    gid = parse_qs(parsed.query).get("gid", ["0"])[0]
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"


def _read_url(url: str, timeout: int = 60) -> bytes:
    response = requests.get(google_sheet_csv_url(url), timeout=timeout)
    response.raise_for_status()
    return response.content


def _read_tabular_source(source: str | Path) -> pd.DataFrame:
    source_str = str(source)
    if re.match(r"^https?://", source_str, re.IGNORECASE):
        source_key = google_sheet_csv_url(source_str)
        suffix = Path(urlparse(source_key).path).suffix.lower()
        content = _read_url(source_key)
        if "format=csv" in source_key or suffix in {".csv", ".tsv"}:
            separator = "\t" if suffix == ".tsv" else ","
            return pd.read_csv(StringIO(content.decode("utf-8-sig")), sep=separator)
        if suffix in {".json"}:
            return pd.read_json(BytesIO(content))
        if suffix in {".xlsx", ".xls"}:
            return pd.read_excel(BytesIO(content))
        return pd.read_csv(StringIO(content.decode("utf-8-sig")))

    path = Path(source_str)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".tsv":
        return pd.read_csv(path, sep="\t")
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    if suffix == ".json":
        return pd.read_json(path)
    raise ValueError(f"Fonte nao suportada: {source_str}")


def _normalize_dataframe(df: pd.DataFrame, source_label: str) -> pd.DataFrame:
    normalized = df.copy()
    normalized.columns = [_slugify(column) for column in normalized.columns]
    normalized = normalized.dropna(how="all").reset_index(drop=True)
    normalized["_source"] = source_label
    normalized["_row_number"] = np.arange(1, len(normalized) + 1)
    return normalized


def _split_image_values(value: object) -> list[str]:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return []
    if isinstance(value, (list, tuple, set)):
        raw_values = list(value)
    else:
        raw_values = re.split(r"[|;,]\s*|\s{2,}", str(value))
    return [str(item).strip() for item in raw_values if str(item).strip()]


def _extract_drive_id(value: str) -> str | None:
    patterns = [
        r"/file/d/([a-zA-Z0-9_-]+)",
        r"/d/([a-zA-Z0-9_-]+)",
        r"[?&]id=([a-zA-Z0-9_-]+)",
        r"open\?id=([a-zA-Z0-9_-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, value)
        if match:
            return match.group(1)
    return None


def _normalize_image_reference(value: str) -> str:
    drive_id = _extract_drive_id(value)
    if drive_id:
        return f"https://drive.google.com/uc?export=download&id={drive_id}"
    return value


def _looks_like_image_reference(value: str) -> bool:
    lowered = _normalize_image_reference(value).lower()
    return lowered.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")) or lowered.startswith(("http://", "https://"))


def _detect_image_columns(df: pd.DataFrame) -> list[str]:
    candidates: list[str] = []
    for column in df.columns:
        if str(column).startswith("_"):
            continue
        if any(token in column for token in LIKELY_IMAGE_COLUMNS):
            candidates.append(column)
            continue
        sample = df[column].dropna().astype(str).head(5)
        if not sample.empty and sample.map(_looks_like_image_reference).any():
            candidates.append(column)
    return candidates


def _detect_datetime_column(df: pd.DataFrame) -> str | None:
    for column in df.columns:
        if column.startswith("_"):
            continue
        if any(token in column for token in LIKELY_DATETIME_COLUMNS):
            parsed = pd.to_datetime(df[column], errors="coerce", dayfirst=True)
            if parsed.notna().sum() >= max(3, len(df) // 5):
                return column
    return None


def _detect_categorical_columns(df: pd.DataFrame) -> list[str]:
    candidates: list[str] = []
    for column in df.columns:
        if column.startswith("_"):
            continue
        if any(token in column for token in LIKELY_DATETIME_COLUMNS):
            continue
        series = df[column]
        if pd.api.types.is_numeric_dtype(series):
            continue
        if any(token in column for token in LIKELY_CATEGORICAL_COLUMNS):
            candidates.append(column)
            continue
        unique_values = series.dropna().astype(str).nunique()
        if 1 < unique_values <= max(12, len(df) // 5):
            candidates.append(column)
    return candidates


def _is_informative_categorical(df: pd.DataFrame, column: str) -> bool:
    series = df[column].fillna("").astype(str).str.strip()
    non_empty = series[series != ""]
    if non_empty.empty:
        return False
    coverage = len(non_empty) / len(df)
    if coverage < 0.25:
        return False
    normalized = non_empty.str.lower()
    if normalized.value_counts(normalize=True).iloc[0] > 0.88:
        return False
    return True


def _source_bucket(value: str) -> str:
    lowered = str(value).lower()
    if "788519212" in lowered:
        return "Veiculos abandonados"
    if "376419273" in lowered:
        return "Obras e entulhos"
    if "1489192321" in lowered:
        return "Containers"
    return "Fonte consolidada"


def _numeric_columns(df: pd.DataFrame) -> list[str]:
    columns: list[str] = []
    for column in df.columns:
        if column.startswith("_"):
            continue
        numeric = pd.to_numeric(df[column], errors="coerce")
        if numeric.notna().sum() >= max(3, len(df) // 4):
            df[column] = numeric
            columns.append(column)
    return columns


def _prepare_report_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    report_df = df.copy()
    image_columns = _detect_image_columns(report_df)
    report_df["_image_refs"] = [
        [item for column in image_columns for item in _split_image_values(report_df.iloc[index][column])]
        for index in range(len(report_df))
    ]
    report_df["_photo_count"] = report_df["_image_refs"].map(len)
    report_df["_has_image"] = report_df["_photo_count"].gt(0).astype(int)
    report_df["_source"] = report_df.get("_source", "fonte")
    numeric_columns = _numeric_columns(report_df)
    if not numeric_columns:
        report_df["_row_number_metric"] = np.arange(1, len(report_df) + 1)
    datetime_column = _detect_datetime_column(report_df)
    if datetime_column:
        report_df["_event_date"] = pd.to_datetime(report_df[datetime_column], errors="coerce", dayfirst=True)
    else:
        report_df["_event_date"] = pd.date_range("2026-01-01", periods=len(report_df), freq="D")
    categorical_columns = _detect_categorical_columns(report_df)
    informative_columns = [column for column in categorical_columns if _is_informative_categorical(report_df, column)]
    multiple_sources = report_df["_source"].astype(str).nunique() > 1
    if multiple_sources:
        report_df["_primary_category"] = report_df["_source"].map(_source_bucket).astype(str)
    elif informative_columns:
        report_df["_primary_category"] = report_df[informative_columns[0]].fillna("Nao informado").astype(str)
    else:
        report_df["_primary_category"] = report_df["_source"].map(_source_bucket).astype(str)
    secondary_candidates = informative_columns if multiple_sources else informative_columns[1:]
    if secondary_candidates:
        report_df["_secondary_category"] = report_df[secondary_candidates[0]].fillna("Nao informado").astype(str)
    else:
        report_df["_secondary_category"] = np.where(
            report_df["_has_image"].eq(1),
            "Com foto",
            "Sem foto",
        )
    return report_df


def _download_image(reference: str, output_path: Path, quality: int, max_size: int) -> bool:
    try:
        normalized_reference = _normalize_image_reference(reference.strip())
        if re.match(r"^https?://", normalized_reference, re.IGNORECASE):
            content = _read_url(normalized_reference, timeout=90)
            image = Image.open(BytesIO(content))
        else:
            image = Image.open(normalized_reference)
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail((max_size, max_size))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path, format="JPEG", quality=quality, optimize=True)
        return True
    except Exception:
        return False


def _optimize_images(df: pd.DataFrame, output_dir: Path, quality: int, max_size: int) -> tuple[pd.DataFrame, int, list[str]]:
    issues: list[str] = []
    all_refs = sorted({reference for refs in df["_image_refs"] for reference in refs})
    ref_to_relative: dict[str, Path] = {}
    for ref in all_refs:
        extension_seed = hashlib.sha1(ref.encode("utf-8")).hexdigest()[:16]
        ref_to_relative[ref] = Path("assets") / "images" / f"{extension_seed}.jpg"

    success_by_ref: dict[str, bool] = {}
    max_workers = min(24, max(4, len(all_refs) // 20 or 4))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _download_image,
                reference,
                output_dir / ref_to_relative[reference],
                quality,
                max_size,
            ): reference
            for reference in all_refs
        }
        for future in as_completed(futures):
            reference = futures[future]
            try:
                success_by_ref[reference] = bool(future.result())
            except Exception:
                success_by_ref[reference] = False

    gallery_paths: list[list[str]] = []
    image_count = 0
    for references in df["_image_refs"]:
        optimized_paths: list[str] = []
        for reference in references:
            if success_by_ref.get(reference):
                optimized_paths.append(ref_to_relative[reference].as_posix())
                image_count += 1
            else:
                issues.append(f"Falha ao baixar/otimizar imagem: {reference}")
        gallery_paths.append(optimized_paths)
    result = df.copy()
    result["_optimized_images"] = gallery_paths
    result["_cover_image"] = [paths[0] if paths else None for paths in gallery_paths]
    return result, image_count, issues


def _safe_series(df: pd.DataFrame, column: str) -> pd.Series:
    return df[column].dropna() if column in df.columns else pd.Series(dtype="object")


def _top_categories(df: pd.DataFrame, column: str, top_n: int = 8) -> pd.Series:
    return _safe_series(df, column).astype(str).value_counts().head(top_n)


def _chart_figure(title: str, palette: BrandPalette, nrows: int = 1, ncols: int = 1, figsize: tuple[int, int] = (10, 6)):
    figure, axes = plt.subplots(nrows=nrows, ncols=ncols, figsize=figsize)
    figure.patch.set_facecolor(palette.background)
    if isinstance(axes, np.ndarray):
        axes_list = axes.flatten()
    else:
        axes_list = [axes]
    for axis in axes_list:
        axis.set_facecolor(palette.surface)
        axis.grid(alpha=0.15, color=palette.muted)
        axis.tick_params(colors=palette.text)
        for spine in axis.spines.values():
            spine.set_color(palette.muted)
            spine.set_alpha(0.25)
    figure.suptitle(title, fontsize=16, color=palette.text, fontweight="bold")
    return figure, axes


def _save_chart(figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.tight_layout()
    figure.savefig(path, dpi=180, bbox_inches="tight", facecolor=figure.get_facecolor())
    plt.close(figure)


def _build_charts(df: pd.DataFrame, output_dir: Path, palette: BrandPalette) -> list[ChartArtifact]:
    charts_dir = output_dir / "assets" / "charts"
    colors_cycle = palette.chart_colors()
    top_category = _top_categories(df, "_primary_category")
    second_category = _top_categories(df, "_secondary_category")
    numeric_columns = [column for column in _numeric_columns(df.copy()) if not column.startswith("_")]
    if not numeric_columns:
        numeric_columns = ["_photo_count", "_has_image", "_row_number"]
    datetime_group = (
        df.assign(_event_date_group=df["_event_date"].dt.to_period("M").dt.to_timestamp())
        .groupby("_event_date_group")
        .size()
        .sort_index()
    )
    scatter_x = numeric_columns[0]
    scatter_y = numeric_columns[1] if len(numeric_columns) > 1 and numeric_columns[1] != scatter_x else "_photo_count"
    charts: list[ChartArtifact] = []

    figure, axis = _chart_figure("1. Top categorias", palette)
    axis.bar(top_category.index, top_category.values, color=colors_cycle[: len(top_category)])
    axis.set_ylabel("Registros")
    axis.tick_params(axis="x", rotation=25)
    path = charts_dir / "01_top_categorias.png"
    _save_chart(figure, path)
    charts.append(ChartArtifact("Top categorias", "bar", path, "Mostra onde o volume de registros se concentra."))

    figure, axis = _chart_figure("2. Ranking horizontal", palette)
    axis.barh(top_category.index[::-1], top_category.values[::-1], color=colors_cycle[: len(top_category)])
    axis.set_xlabel("Registros")
    path = charts_dir / "02_ranking_horizontal.png"
    _save_chart(figure, path)
    charts.append(ChartArtifact("Ranking horizontal", "horizontal_bar", path, "Facilita a leitura das categorias com maior peso."))

    cross = (
        df.groupby(["_primary_category", "_secondary_category"])
        .size()
        .unstack(fill_value=0)
        .head(6)
    )
    figure, axis = _chart_figure("3. Composicao por status", palette)
    bottom = np.zeros(len(cross.index))
    for series_index, column in enumerate(cross.columns[:5]):
        axis.bar(
            cross.index,
            cross[column].values,
            bottom=bottom,
            label=str(column),
            color=colors_cycle[series_index % len(colors_cycle)],
        )
        bottom = bottom + cross[column].values
    axis.tick_params(axis="x", rotation=25)
    axis.legend(frameon=False)
    path = charts_dir / "03_stacked_bar.png"
    _save_chart(figure, path)
    charts.append(ChartArtifact("Composicao por status", "stacked_bar", path, "Cruza categoria principal com um segundo corte operacional."))

    figure, axis = _chart_figure("4. Participacao percentual", palette)
    wedges, _ = axis.pie(
        top_category.values,
        colors=colors_cycle[: len(top_category)],
        wedgeprops={"width": 0.42, "edgecolor": palette.background},
        startangle=90,
    )
    axis.legend(wedges, top_category.index, loc="center left", bbox_to_anchor=(1.02, 0.5), frameon=False)
    path = charts_dir / "04_donut.png"
    _save_chart(figure, path)
    charts.append(ChartArtifact("Participacao percentual", "donut", path, "Mostra a fatia relativa de cada categoria principal."))

    figure, axis = _chart_figure("5. Evolucao temporal", palette)
    axis.plot(datetime_group.index, datetime_group.values, color=palette.primary, linewidth=2.4, marker="o")
    axis.fill_between(datetime_group.index, datetime_group.values, color=mcolors.to_rgba(palette.primary, 0.15))
    axis.set_ylabel("Registros")
    path = charts_dir / "05_linha_tempo.png"
    _save_chart(figure, path)
    charts.append(ChartArtifact("Evolucao temporal", "line", path, "Resume a distribuicao dos registros ao longo do tempo."))

    figure, axis = _chart_figure("6. Area acumulada", palette)
    cumulative = datetime_group.cumsum()
    axis.fill_between(cumulative.index, cumulative.values, color=mcolors.to_rgba(palette.secondary, 0.35))
    axis.plot(cumulative.index, cumulative.values, color=palette.secondary, linewidth=2.2)
    axis.set_ylabel("Acumulado")
    path = charts_dir / "06_area_acumulada.png"
    _save_chart(figure, path)
    charts.append(ChartArtifact("Area acumulada", "area", path, "Evidencia a evolucao acumulada do conjunto auditado."))

    figure, axis = _chart_figure("7. Distribuicao numerica", palette)
    histogram_series = pd.to_numeric(df[scatter_x], errors="coerce").dropna()
    axis.hist(histogram_series.values, bins=min(16, max(6, int(np.sqrt(len(histogram_series))))), color=palette.accent, alpha=0.85)
    axis.set_xlabel(scatter_x.replace("_", " ").title())
    axis.set_ylabel("Frequencia")
    path = charts_dir / "07_histograma.png"
    _save_chart(figure, path)
    charts.append(ChartArtifact("Distribuicao numerica", "histogram", path, "Ajuda a enxergar concentracao, cauda e dispersao."))

    figure, axis = _chart_figure("8. Boxplot por categoria", palette)
    boxplot_source = df[["_primary_category", scatter_x]].dropna().copy()
    grouped = [
        group[scatter_x].values
        for _, group in boxplot_source.groupby("_primary_category")
    ][:6]
    labels = list(boxplot_source["_primary_category"].dropna().astype(str).value_counts().head(len(grouped)).index)
    axis.boxplot(
        grouped,
        tick_labels=labels,
        patch_artist=True,
        boxprops={"facecolor": mcolors.to_rgba(palette.primary, 0.4), "color": palette.primary},
        medianprops={"color": palette.secondary, "linewidth": 2},
    )
    axis.tick_params(axis="x", rotation=20)
    path = charts_dir / "08_boxplot.png"
    _save_chart(figure, path)
    charts.append(ChartArtifact("Boxplot por categoria", "boxplot", path, "Compara dispersao e outliers entre grupos."))

    figure, axis = _chart_figure("9. Correlacao visual", palette)
    scatter_columns = list(dict.fromkeys([scatter_x, scatter_y, "_photo_count"]))
    scatter_df = df[scatter_columns].apply(pd.to_numeric, errors="coerce").dropna()
    scatter_sizes = 40 + (scatter_df["_photo_count"].fillna(0) * 16)
    axis.scatter(
        scatter_df[scatter_x].to_numpy(),
        scatter_df[scatter_y].to_numpy(),
        s=scatter_sizes,
        c=scatter_df["_photo_count"],
        cmap="Blues",
        alpha=0.7,
        edgecolor="white",
        linewidth=0.5,
    )
    axis.set_xlabel(scatter_x.replace("_", " ").title())
    axis.set_ylabel(scatter_y.replace("_", " ").title())
    path = charts_dir / "09_scatter.png"
    _save_chart(figure, path)
    charts.append(ChartArtifact("Correlacao visual", "scatter", path, "Cruza duas metricas para destacar padroes e excecoes."))

    heatmap_columns = list(dict.fromkeys([*numeric_columns[:4], "_photo_count", "_has_image"]))
    heatmap_df = df[heatmap_columns].apply(pd.to_numeric, errors="coerce").dropna(axis=1, how="all")
    figure, axis = _chart_figure("10. Heatmap de correlacao", palette)
    correlation = heatmap_df.corr(numeric_only=True).fillna(0)
    image = axis.imshow(correlation.values, cmap="YlGnBu", vmin=-1, vmax=1)
    axis.set_xticks(range(len(correlation.columns)))
    axis.set_xticklabels([column.replace("_", " ") for column in correlation.columns], rotation=25, ha="right")
    axis.set_yticks(range(len(correlation.index)))
    axis.set_yticklabels([index.replace("_", " ") for index in correlation.index])
    figure.colorbar(image, ax=axis, fraction=0.046, pad=0.04)
    path = charts_dir / "10_heatmap.png"
    _save_chart(figure, path)
    charts.append(ChartArtifact("Heatmap de correlacao", "heatmap", path, "Resume como as metricas se relacionam entre si."))

    return charts


def _extract_palette_from_logo(logo_path: str | None) -> BrandPalette:
    default = BrandPalette(
        background="#f2f7fb",
        surface="#ffffff",
        primary="#135d8d",
        secondary="#2f8fb8",
        accent="#7cc4d8",
        muted="#5f7485",
        text="#102532",
    )
    if not logo_path:
        return default
    try:
        image = Image.open(logo_path).convert("RGB")
        reduced = image.resize((64, 64))
        colors_found = reduced.getcolors(64 * 64) or []
        ordered = sorted(colors_found, key=lambda item: item[0], reverse=True)
        palette = [_rgb_to_hex(rgb) for _, rgb in ordered if max(rgb) - min(rgb) > 12]
        if len(palette) < 2:
            return default
        primary = palette[0]
        secondary = palette[1]
        accent = palette[2] if len(palette) > 2 else _mix(primary, "#ffffff", 0.4)
        background = _mix(primary, "#ffffff", 0.92)
        surface = "#ffffff"
        muted = _mix(primary, "#7f8c8d", 0.5)
        text = "#0e2230" if _luminance(background) > 0.55 else "#f4fbff"
        return BrandPalette(
            background=background,
            surface=surface,
            primary=primary,
            secondary=secondary,
            accent=accent,
            muted=muted,
            text=text,
        )
    except Exception:
        return default


def _html_escape(value: object) -> str:
    text = "" if value is None else str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _resolve_logo_relative(output_dir: Path, logo_path: str | None) -> str | None:
    if not logo_path:
        return None
    source = Path(logo_path)
    if not source.exists():
        return None
    target = output_dir / "assets" / "brand" / source.name
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != target.resolve():
        target.write_bytes(source.read_bytes())
    return target.relative_to(output_dir).as_posix()


def _build_summary(df: pd.DataFrame, image_count: int, issues: list[str], expected_records: int | None) -> dict[str, object]:
    numeric_columns = [column for column in df.columns if pd.api.types.is_numeric_dtype(df[column]) and not column.startswith("_")]
    completion = None
    if expected_records:
        completion = round((len(df) / expected_records) * 100, 2)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "records": int(len(df)),
        "expected_records": expected_records,
        "completion_pct": completion,
        "image_count": int(image_count),
        "sources": sorted(df["_source"].astype(str).unique().tolist()),
        "primary_categories": df["_primary_category"].value_counts().head(8).to_dict(),
        "numeric_columns": numeric_columns,
        "issues": issues,
    }


def _build_html(
    df: pd.DataFrame,
    charts: list[ChartArtifact],
    palette: BrandPalette,
    output_dir: Path,
    logo_relative: str | None,
    footer_text: str,
    title: str,
    summary: dict[str, object],
) -> Path:
    chart_cards = "".join(
        f"""
        <article class="chart-card">
          <img src="{chart.path.relative_to(output_dir).as_posix()}" alt="{_html_escape(chart.title)}">
          <div class="chart-copy">
            <p class="eyebrow">{_html_escape(chart.chart_type.replace('_', ' ').upper())}</p>
            <h3>{_html_escape(chart.title)}</h3>
            <p>{_html_escape(chart.summary)}</p>
          </div>
        </article>
        """
        for chart in charts
    )
    highlights = [
        ("Registros auditados", summary["records"]),
        ("Meta de registros", summary["expected_records"] or "n/d"),
        ("Cobertura da meta", f"{summary['completion_pct']}%" if summary["completion_pct"] is not None else "n/d"),
        ("Fotos tratadas", summary["image_count"]),
    ]
    stats_cards = "".join(
        f"""
        <article class="stat-card">
          <p>{_html_escape(label)}</p>
          <strong>{_html_escape(value)}</strong>
        </article>
        """
        for label, value in highlights
    )
    preview_columns = [column for column in df.columns if not column.startswith("_")][:6]
    preview_header = "".join(f"<th>{_html_escape(column.replace('_', ' ').title())}</th>" for column in preview_columns)
    preview_rows = "".join(
        "<tr>" + "".join(f"<td>{_html_escape(row[column])}</td>" for column in preview_columns) + "</tr>"
        for _, row in df.head(18).iterrows()
    )
    gallery_items = "".join(
        f"""
        <article class="gallery-card">
          <img src="{_html_escape(row['_cover_image'])}" alt="{_html_escape(row.get(preview_columns[0], 'Imagem'))}">
          <div>
            <h4>{_html_escape(row.get(preview_columns[0], f'Registro {index + 1}'))}</h4>
            <p>{_html_escape(row.get(preview_columns[1], row.get('_primary_category', 'Sem descricao')))}</p>
          </div>
        </article>
        """
        for index, (_, row) in enumerate(df[df["_cover_image"].notna()].head(24).iterrows())
    )
    logo_markup = f'<img class="brand-logo" src="{logo_relative}" alt="Logo">' if logo_relative else ""
    issues_markup = "".join(f"<li>{_html_escape(issue)}</li>" for issue in summary["issues"]) or "<li>Nenhuma pendencia critica na geracao.</li>"
    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_html_escape(title)}</title>
  <style>
    :root {{
      --bg: {palette.background};
      --surface: {palette.surface};
      --primary: {palette.primary};
      --secondary: {palette.secondary};
      --accent: {palette.accent};
      --muted: {palette.muted};
      --text: {palette.text};
      --line: rgba(16, 37, 50, 0.12);
      --shadow: 0 24px 60px rgba(16, 37, 50, 0.10);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", Tahoma, sans-serif;
      background:
        radial-gradient(circle at top left, rgba(124, 196, 216, 0.20), transparent 24%),
        linear-gradient(180deg, #ffffff 0%, var(--bg) 100%);
      color: var(--text);
    }}
    .wrap {{
      width: min(1280px, calc(100% - 32px));
      margin: 0 auto;
      padding: 28px 0 48px;
    }}
    .hero, .section {{
      background: rgba(255, 255, 255, 0.88);
      border: 1px solid var(--line);
      border-radius: 28px;
      box-shadow: var(--shadow);
    }}
    .hero {{
      padding: 32px;
      position: relative;
      overflow: hidden;
    }}
    .hero::after {{
      content: "";
      position: absolute;
      inset: auto -60px -60px auto;
      width: 220px;
      height: 220px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(19, 93, 141, 0.18), transparent 68%);
    }}
    .hero-top {{
      display: flex;
      justify-content: space-between;
      gap: 24px;
      align-items: flex-start;
    }}
    .brand-logo {{
      width: 180px;
      max-width: 30vw;
      object-fit: contain;
      filter: drop-shadow(0 10px 18px rgba(16, 37, 50, 0.12));
    }}
    .eyebrow {{
      margin: 0 0 10px;
      text-transform: uppercase;
      letter-spacing: 0.18em;
      color: var(--primary);
      font-size: 0.78rem;
      font-weight: 700;
    }}
    h1, h2, h3, h4 {{ margin: 0 0 12px; line-height: 1.1; }}
    h1 {{ font-size: clamp(2.4rem, 5vw, 4.6rem); max-width: 12ch; }}
    p {{ margin: 0 0 12px; color: var(--muted); }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 16px;
      margin-top: 28px;
    }}
    .stat-card, .chart-card, .gallery-card {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 22px;
      box-shadow: 0 14px 32px rgba(16, 37, 50, 0.08);
    }}
    .stat-card {{ padding: 20px; }}
    .stat-card strong {{ display: block; font-size: 2rem; color: var(--text); }}
    .section {{ margin-top: 26px; padding: 26px; }}
    .chart-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 18px;
    }}
    .chart-card {{ overflow: hidden; }}
    .chart-card img {{
      display: block;
      width: 100%;
      height: auto;
      background: #fff;
    }}
    .chart-copy {{ padding: 18px; }}
    .table-wrap {{
      overflow: auto;
      border-radius: 18px;
      border: 1px solid var(--line);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 720px;
      background: var(--surface);
    }}
    th, td {{
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      font-size: 0.94rem;
    }}
    th {{
      color: var(--primary);
      background: rgba(19, 93, 141, 0.06);
    }}
    .gallery {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 16px;
    }}
    .gallery-card {{
      overflow: hidden;
    }}
    .gallery-card img {{
      display: block;
      width: 100%;
      aspect-ratio: 1 / 1;
      object-fit: cover;
      background: linear-gradient(135deg, rgba(19, 93, 141, 0.08), rgba(124, 196, 216, 0.12));
    }}
    .gallery-card div {{ padding: 14px; }}
    .footer {{
      margin-top: 20px;
      text-align: center;
      color: var(--muted);
      font-size: 0.92rem;
      letter-spacing: 0.04em;
    }}
    ul {{ margin: 0; color: var(--muted); }}
    @media (max-width: 980px) {{
      .stats, .chart-grid, .gallery {{ grid-template-columns: 1fr 1fr; }}
    }}
    @media (max-width: 720px) {{
      .wrap {{ width: min(100% - 14px, 1280px); padding: 14px 0 32px; }}
      .hero, .section {{ padding: 18px; border-radius: 22px; }}
      .hero-top {{ flex-direction: column; }}
      .stats, .chart-grid, .gallery {{ grid-template-columns: 1fr; }}
      h1 {{ max-width: none; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <div class="hero-top">
        <div>
          <p class="eyebrow">Dashboard Premium</p>
          <h1>{_html_escape(title)}</h1>
          <p>Relatorio visual em HTML com leitura executiva, 10 graficos, galeria comprimida de imagens e rastreio consolidado das fontes configuradas.</p>
          <p>Meta de volume: {_html_escape(summary["expected_records"] or "n/d")} registros | Cobertura atual: {_html_escape(summary["completion_pct"] if summary["completion_pct"] is not None else "n/d")}{"%" if summary["completion_pct"] is not None else ""}</p>
        </div>
        {logo_markup}
      </div>
      <div class="stats">{stats_cards}</div>
    </section>

    <section class="section">
      <p class="eyebrow">Analitico</p>
      <h2>Conjunto de 10 graficos</h2>
      <div class="chart-grid">{chart_cards}</div>
    </section>

    <section class="section">
      <p class="eyebrow">Amostra</p>
      <h2>Preview estruturado dos dados</h2>
      <div class="table-wrap">
        <table>
          <thead><tr>{preview_header}</tr></thead>
          <tbody>{preview_rows}</tbody>
        </table>
      </div>
    </section>

    <section class="section">
      <p class="eyebrow">Galeria</p>
      <h2>Fotos otimizadas para o HTML</h2>
      <div class="gallery">{gallery_items or "<p>Nenhuma imagem disponivel na amostra renderizada.</p>"}</div>
    </section>

    <section class="section">
      <p class="eyebrow">Auditoria</p>
      <h2>Pendencias e observacoes</h2>
      <ul>{issues_markup}</ul>
    </section>

    <p class="footer">{_html_escape(footer_text)}</p>
  </div>
</body>
</html>
"""
    html_path = output_dir / "catalog_dashboard.html"
    html_path.write_text(html, encoding="utf-8")
    return html_path


def _mime_type_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
    }.get(suffix, "application/octet-stream")


def _build_offline_html(html_path: Path) -> Path:
    html = html_path.read_text(encoding="utf-8")

    def replace_src(match: re.Match[str]) -> str:
        original = match.group(0)
        src = match.group(1)
        if src.startswith(("http://", "https://", "data:")):
            return original
        asset_path = (html_path.parent / src).resolve()
        if not asset_path.exists() or not asset_path.is_file():
            return original
        mime_type = _mime_type_for_path(asset_path)
        encoded = b64encode(asset_path.read_bytes()).decode("ascii")
        return original.replace(src, f"data:{mime_type};base64,{encoded}")

    offline_html = re.sub(r'src="([^"]+)"', replace_src, html)
    offline_path = html_path.with_name("catalog_dashboard_offline.html")
    offline_path.write_text(offline_html, encoding="utf-8")
    return offline_path


def _pdf_header_footer(canvas, doc, logo_path: str | None, footer_text: str, palette: BrandPalette) -> None:
    width, height = A4
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor(palette.primary))
    canvas.setLineWidth(1)
    canvas.line(1.4 * cm, height - 1.8 * cm, width - 1.4 * cm, height - 1.8 * cm)
    if logo_path and Path(logo_path).exists():
        canvas.drawImage(str(logo_path), width - 5.0 * cm, height - 3.0 * cm, width=3.2 * cm, height=1.4 * cm, preserveAspectRatio=True, mask="auto")
    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(colors.HexColor(palette.muted))
    canvas.drawCentredString(width / 2, 1.0 * cm, footer_text)
    canvas.restoreState()


def _build_pdf(
    df: pd.DataFrame,
    charts: list[ChartArtifact],
    palette: BrandPalette,
    output_dir: Path,
    logo_path: str | None,
    footer_text: str,
    title: str,
    summary: dict[str, object],
) -> Path:
    pdf_path = output_dir / "catalog_dashboard.pdf"
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Hero", fontName="Helvetica-Bold", fontSize=24, leading=28, textColor=colors.HexColor(palette.text), spaceAfter=12))
    styles.add(ParagraphStyle(name="Section", fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=colors.HexColor(palette.primary), spaceBefore=8, spaceAfter=10))
    styles.add(ParagraphStyle(name="Body", fontName="Helvetica", fontSize=10, leading=14, textColor=colors.HexColor(palette.muted)))
    doc = SimpleDocTemplate(str(pdf_path), pagesize=A4, leftMargin=1.5 * cm, rightMargin=1.5 * cm, topMargin=2.6 * cm, bottomMargin=1.8 * cm)
    story = [
        Paragraph(title, styles["Hero"]),
        Paragraph(
            f"Registros auditados: <b>{summary['records']}</b> | Meta: <b>{summary['expected_records'] or 'n/d'}</b> | Fotos tratadas: <b>{summary['image_count']}</b>",
            styles["Body"],
        ),
        Spacer(1, 0.35 * cm),
    ]

    overview_rows = [["Indicador", "Valor"]]
    overview_rows.extend(
        [
            ["Registros auditados", str(summary["records"])],
            ["Meta esperada", str(summary["expected_records"] or "n/d")],
            ["Cobertura", f"{summary['completion_pct']}%" if summary["completion_pct"] is not None else "n/d"],
            ["Fotos tratadas", str(summary["image_count"])],
            ["Fontes", ", ".join(summary["sources"])],
        ]
    )
    overview_table = Table(overview_rows, colWidths=[6 * cm, 10 * cm])
    overview_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(palette.primary)),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#ffffff")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor(palette.accent)),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.extend([overview_table, Spacer(1, 0.45 * cm), Paragraph("Graficos executivos", styles["Section"])])
    for index, chart in enumerate(charts, start=1):
        story.append(Paragraph(f"{index}. {chart.title}", styles["Body"]))
        story.append(PdfImage(str(chart.path), width=17.4 * cm, height=9.8 * cm))
        story.append(Paragraph(chart.summary, styles["Body"]))
        story.append(Spacer(1, 0.3 * cm))
        if index % 2 == 0 and index != len(charts):
            story.append(PageBreak())

    preview_columns = [column for column in df.columns if not column.startswith("_")][:5]
    preview_rows = [[column.replace("_", " ").title() for column in preview_columns]]
    for _, row in df.head(18).iterrows():
        preview_rows.append([str(row[column])[:38] for column in preview_columns])
    story.extend([PageBreak(), Paragraph("Preview dos registros", styles["Section"])])
    preview_table = Table(preview_rows, repeatRows=1)
    preview_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(palette.secondary)),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor(palette.accent)),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.extend([preview_table, Spacer(1, 0.45 * cm)])

    image_rows = df[df["_cover_image"].notna()].head(12)
    if not image_rows.empty:
        story.append(Paragraph("Galeria de imagens otimizadas", styles["Section"]))
        for _, row in image_rows.iterrows():
            cover_path = output_dir / row["_cover_image"]
            if not cover_path.exists():
                continue
            story.append(Paragraph(str(row.get(preview_columns[0], "Registro")), styles["Body"]))
            story.append(PdfImage(str(cover_path), width=5.2 * cm, height=5.2 * cm))
            story.append(Spacer(1, 0.25 * cm))

    doc.build(
        story,
        onFirstPage=lambda canvas, document: _pdf_header_footer(canvas, document, logo_path, footer_text, palette),
        onLaterPages=lambda canvas, document: _pdf_header_footer(canvas, document, logo_path, footer_text, palette),
    )
    return pdf_path


def build_catalog_report(
    *,
    sources: list[str] | None = None,
    output_dir: str | Path | None = None,
    logo_path: str | None = None,
    footer_text: str = "feito por marx bruno",
    title: str = "SELIM AZUL | Dashboard Premium",
    expected_records: int | None = None,
    image_quality: int = 55,
    image_max_size: int = 1440,
) -> ReportArtifacts:
    report_sources = sources or [item.strip() for item in settings.report_data_sources.split(",") if item.strip()]
    if not report_sources:
        raise ValueError("Nenhuma fonte de dados informada para o relatorio.")
    destination = Path(output_dir or settings.resolved_report_output_dir / datetime.now().strftime("%Y%m%d_%H%M%S"))
    destination.mkdir(parents=True, exist_ok=True)

    frames = []
    for source in report_sources:
        frame = _normalize_dataframe(_read_tabular_source(source), source)
        if not frame.empty:
            frames.append(frame)
    if not frames:
        raise ValueError("Nenhum dado foi carregado das fontes informadas.")
    raw_df = pd.concat(frames, ignore_index=True)
    report_df = _prepare_report_dataframe(raw_df)
    report_df, image_count, issues = _optimize_images(report_df, destination, quality=image_quality, max_size=image_max_size)

    expected = expected_records if expected_records is not None else settings.report_expected_records or None
    if expected and len(report_df) < expected:
        issues.append(f"Meta nao atingida: {len(report_df)} de {expected} registros carregados.")
    palette = _extract_palette_from_logo(logo_path or settings.report_logo_path or None)
    logo_relative = _resolve_logo_relative(destination, logo_path or settings.report_logo_path or None)

    charts = _build_charts(report_df.copy(), destination, palette)
    dataset_path = destination / "dataset_normalized.csv"
    report_df.drop(columns=["_image_refs"], errors="ignore").to_csv(dataset_path, index=False, encoding="utf-8-sig")
    summary = _build_summary(report_df, image_count=image_count, issues=issues, expected_records=expected)
    summary_path = destination / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    html_path = _build_html(
        report_df,
        charts,
        palette,
        destination,
        logo_relative,
        footer_text,
        title,
        summary,
    )
    offline_html_path = _build_offline_html(html_path)
    pdf_path = _build_pdf(
        report_df,
        charts,
        palette,
        destination,
        str(destination / logo_relative) if logo_relative else None,
        footer_text,
        title,
        summary,
    )
    return ReportArtifacts(
        html_path=html_path,
        offline_html_path=offline_html_path,
        pdf_path=pdf_path,
        summary_path=summary_path,
        dataset_path=dataset_path,
        charts=charts,
        image_count=image_count,
        record_count=len(report_df),
        issues=issues,
    )
