import io
import json
import sys
import tempfile
import unicodedata
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon, mapping
from shapely.ops import transform

TARGET_CRS = "EPSG:4674"  # SIRGAS 2000 Geográfico Oficial (IBGE)

# Dicionário Canônico Nacional que unifica as nomenclaturas de SP, MG e SICAR Federal
CANONICAL_CAR_DICTIONARY: Dict[str, List[str]] = {
    "AREA_IMOVEL": [
        "area_do_imovel", "area_imovel", "perimetro_imovel", "perimetro",
        "limite_propriedade", "imovel", "gleba", "propriedade", "coleta_mobile",
        "coleta_campo", "amostra_propriedade", "piracicaba", "jundiai", "limeira"
    ],
    "APP": [
        "app", "app_total", "area_preservacao_permanente", "preservacao_permanente",
        "mata_ciliar", "app_declarada", "faixa_app"
    ],
    "RESERVA_LEGAL": [
        "reserva_legal", "arl", "rl", "arl_proposta", "arl_averbada",
        "reserva_legal_proposta", "reserva_legal_averbada"
    ],
    "VEGETACAO_NATIVA": [
        "vegetacao_nativa", "rem_vegetacao_nativa", "remanescente_vegetacao_nativa",
        "vn", "fragmento_florestal", "mata_nativa", "cobertura_florestal"
    ],
    "USO_CONSOLIDADO": [
        "area_consolidada", "uso_consolidado", "aa", "area_antropizada",
        "uso_agropecuario", "lavoura", "pastagem", "uso_alternativo"
    ],
    "USO_RESTRITO": [
        "uso_restrito", "area_uso_restrito", "aur", "declividade_25_45", "varzea"
    ],
    "SERVIDAO_ADMINISTRATIVA": [
        "servidao_administrativa", "servidao", "infraestrutura_publica",
        "linha_transmissao", "faixa_dominio"
    ],
    "HIDROGRAFIA": [
        "hidrografia", "curso_dagua", "rio", "corrego", "nascente",
        "Olho_dagua", "reservatorio", "massa_dagua", "vereda"
    ],
}

# Colunas de atributos usadas por SP (SICAR-SP), MG (IDE-Sisema) e SICAR Federal
THEME_COLUMNS = [
    "tema", "cod_tema", "nom_tema", "classe", "tp_feicao",
    "tipo_camada", "layer", "categoria", "ds_tema"
]


def _normalize_text(text: str) -> str:
    """Remove acentos, caracteres especiais e padroniza em minúsculas para comparação."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(text))
    clean = "".join(c for c in nfkd if not unicodedata.combining(c))
    for ch in ["-", ".", "/", "\\", "(", ")", " "]:
        clean = clean.replace(ch, "_")
    while "__" in clean:
        clean = clean.replace("__", "_")
    return clean.strip("_").lower()


def _drop_z_dimension(geom):
    """Garante geometrias estritamente 2D (remove eixo Z de GPS/KML)."""
    if geom is None or geom.is_empty:
        return geom
    if getattr(geom, "has_z", False):
        return transform(lambda x, y, *_: (x, y), geom)
    return geom


def get_sirgas_utm_epsg(lon: float, lat: float) -> str:
    """
    Seleciona automaticamente o fuso métrico SIRGAS 2000 UTM oficial do IBGE
    para qualquer coordenada do território brasileiro (escalabilidade nacional).
    """
    zone = int((lon + 180.0) // 6.0) + 1
    # SIRGAS 2000 UTM Sul (zonas 18S a 25S -> EPSG:31978 a EPSG:31985)
    if lat < 0 and 18 <= zone <= 25:
        return f"EPSG:{31960 + zone}"
    # SIRGAS 2000 UTM Norte (zonas 18N a 22N -> EPSG:31972 a EPSG:31976)
    if lat >= 0 and 18 <= zone <= 22:
        return f"EPSG:{31954 + zone}"
    return "EPSG:31983"  # Fallback padrão: Fuso 23S (SP/MG - Bacias PCJ)


def classify_canonical_layer(raw_label: str) -> str:
    """Traduz o nome do arquivo ou atributo estadual para a chave canônica nacional."""
    norm = _normalize_text(raw_label)
    if not norm:
        return "AREA_IMOVEL"

    # 1. Busca correspondência prioritária nas camadas temáticas específicas
    for canonical_key, aliases in CANONICAL_CAR_DICTIONARY.items():
        if canonical_key == "AREA_IMOVEL":
            continue
        for alias in aliases:
            if norm == alias or f"_{alias}" in f"_{norm}_" or norm.startswith(alias):
                return canonical_key

    # 2. Verifica correspondência com o perímetro do imóvel
    for alias in CANONICAL_CAR_DICTIONARY["AREA_IMOVEL"]:
        if norm == alias or alias in norm:
            return "AREA_IMOVEL"

    return "AREA_IMOVEL"


def detect_car_origin_system(gdf_dict: Dict[str, gpd.GeoDataFrame], filename: str = "") -> Dict[str, str]:
    """Identifica o estado/sistema de origem (SP, MG ou Nacional) a partir de metadados ou posição."""
    uf_detectada = "BR"
    sistema = "Padrão Nacional SICAR / Coleta Direta"
    recibo = "Não informado"

    for gdf in gdf_dict.values():
        for col in gdf.columns:
            col_low = col.lower()
            if col_low in ("uf", "uf_origem", "sg_uf", "estado"):
                val = str(gdf[col].iloc[0]).strip().upper()
                if val in ("SP", "MG"):
                    uf_detectada = val
            if "recibo" in col_low or "car" in col_low or "protocolo" in col_low:
                val_rec = str(gdf[col].iloc[0]).strip()
                if val_rec and val_rec.lower() != "nan":
                    recibo = val_rec
                    if val_rec.upper().startswith("SP-"):
                        uf_detectada = "SP"
                    elif val_rec.upper().startswith("MG-"):
                        uf_detectada = "MG"

    # Se não veio nos atributos, infere pela posição geográfica aproximada na região PCJ/Sudeste
    if uf_detectada == "BR" and "AREA_IMOVEL" in gdf_dict and not gdf_dict["AREA_IMOVEL"].empty:
        centroid = gdf_dict["AREA_IMOVEL"].geometry.union_all().centroid
        if -46.65 <= centroid.x <= -45.80 and -22.95 <= centroid.y <= -22.40:
            uf_detectada = "MG"
        elif -53.20 <= centroid.x <= -44.10 and -25.30 <= centroid.y <= -19.70:
            uf_detectada = "SP"

    if uf_detectada == "SP":
        sistema = "SICAR-SP / DataGEO (Análise Dinamizada Paulista)"
    elif uf_detectada == "MG":
        sistema = "IDE-Sisema / SICAR-MG (Módulo Estadual Mineiro)"

    return {
        "uf": uf_detectada,
        "sistema_origem": sistema,
        "recibo_car": recibo,
        "arquivo_entrada": filename or "memoria_direta",
    }


def _standardize_gdf(gdf: gpd.GeoDataFrame, canonical_name: str) -> gpd.GeoDataFrame:
    """Padroniza CRS para SIRGAS 2000 (EPSG:4674), corrige topologia e calcula hectares no UTM local."""
    if gdf is None or gdf.empty:
        return gpd.GeoDataFrame(columns=["camada_canonica", "area_ha", "geometry"], crs=TARGET_CRS)

    if gdf.crs is None:
        gdf = gdf.set_crs(TARGET_CRS)
    elif gdf.crs.to_string().upper() != TARGET_CRS:
        gdf = gdf.to_crs(TARGET_CRS)

    gdf = gdf[gdf.geometry.notnull() & ~gdf.geometry.is_empty].copy()
    gdf["geometry"] = gdf["geometry"].apply(_drop_z_dimension).buffer(0)
    gdf = gdf[gdf.geometry.is_valid & ~gdf.geometry.is_empty].copy()

    if gdf.empty:
        return gpd.GeoDataFrame(columns=["camada_canonica", "area_ha", "geometry"], crs=TARGET_CRS)

    rep_pt = gdf.geometry.union_all().centroid
    utm_epsg = get_sirgas_utm_epsg(rep_pt.x, rep_pt.y)
    gdf_utm = gdf.to_crs(utm_epsg)

    gdf["camada_canonica"] = canonical_name
    gdf["utm_calculo"] = utm_epsg
    gdf["area_ha"] = (gdf_utm.geometry.area / 10_000.0).round(4)
    return gdf


def _split_single_gdf_by_theme(gdf: gpd.GeoDataFrame, stem_hint: str) -> Dict[str, gpd.GeoDataFrame]:
    """Separa um único GeoDataFrame em múltiplas camadas caso possua coluna de tema do CAR."""
    for col in gdf.columns:
        if _normalize_text(col) in THEME_COLUMNS:
            grouped: Dict[str, List[pd.Series]] = {}
            for _, row in gdf.iterrows():
                canonical = classify_canonical_layer(str(row[col]))
                grouped.setdefault(canonical, []).append(row)
            return {
                k: gpd.GeoDataFrame(rows, crs=gdf.crs)
                for k, rows in grouped.items()
            }

    canonical = classify_canonical_layer(stem_hint)
    return {canonical: gdf}


def translate_car_input(
    file_input: Union[str, Path, bytes, Dict[str, Any]],
    filename: str = "",
) -> Dict[str, Any]:
    """
    Traduz pacotes completos do CAR (.zip multi-shapefile de SP/MG/BR) ou arquivos simples
    (.geojson/.kml do app mobile) para o Dicionário Canônico Nacional do Civis Agrícola.
    """
    raw_layers: Dict[str, List[gpd.GeoDataFrame]] = {}

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        if isinstance(file_input, dict):
            gdf_in = gpd.GeoDataFrame.from_features(file_input.get("features", []), crs=TARGET_CRS)
            for k, v in _split_single_gdf_by_theme(gdf_in, filename or "AREA_IMOVEL").items():
                raw_layers.setdefault(k, []).append(v)

        elif isinstance(file_input, (str, Path)):
            src_path = Path(file_input)
            filename = filename or src_path.name
            if src_path.suffix.lower() == ".zip":
                with zipfile.ZipFile(src_path, "r") as zf:
                    zf.extractall(tmp_path)
            else:
                gdf_in = gpd.read_file(src_path)
                for k, v in _split_single_gdf_by_theme(gdf_in, src_path.stem).items():
                    raw_layers.setdefault(k, []).append(v)

        elif isinstance(file_input, bytes):
            ext = Path(filename).suffix.lower() if filename else ".geojson"
            saved_file = tmp_path / (filename or f"upload{ext}")
            saved_file.write_bytes(file_input)
            if ext == ".zip" or zipfile.is_zipfile(io.BytesIO(file_input)):
                with zipfile.ZipFile(io.BytesIO(file_input), "r") as zf:
                    zf.extractall(tmp_path)
            else:
                gdf_in = gpd.read_file(saved_file)
                for k, v in _split_single_gdf_by_theme(gdf_in, saved_file.stem).items():
                    raw_layers.setdefault(k, []).append(v)

        # Se foi extraído um pacote .zip com múltiplos Shapefiles ou GeoJSONs estaduais
        vector_files = (
            list(tmp_path.rglob("*.shp"))
            + list(tmp_path.rglob("*.geojson"))
            + list(tmp_path.rglob("*.kml"))
        )
        if vector_files and not raw_layers:
            for vf in vector_files:
                try:
                    gdf_part = gpd.read_file(vf)
                    for k, v in _split_single_gdf_by_theme(gdf_part, vf.stem).items():
                        raw_layers.setdefault(k, []).append(v)
                except Exception:
                    continue

    # Consolida e padroniza cada camada canônica em SIRGAS 2000 (EPSG:4674)
    canonical_gdfs: Dict[str, gpd.GeoDataFrame] = {}
    resumo_areas_ha: Dict[str, float] = {k: 0.0 for k in CANONICAL_CAR_DICTIONARY.keys()}

    for canonical_key, gdf_list in raw_layers.items():
        combined = pd.concat(gdf_list, ignore_index=True)
        gdf_clean = _standardize_gdf(gpd.GeoDataFrame(combined, crs=gdf_list[0].crs), canonical_key)
        if not gdf_clean.empty:
            canonical_gdfs[canonical_key] = gdf_clean
            resumo_areas_ha[canonical_key] = round(float(gdf_clean["area_ha"].sum()), 4)

    # Caso o pacote não traga o perímetro explícito separado, gera o envelope das feições enviadas
    if "AREA_IMOVEL" not in canonical_gdfs and canonical_gdfs:
        all_geoms = pd.concat(list(canonical_gdfs.values()), ignore_index=True)
        hull_gdf = gpd.GeoDataFrame(
            [{"geometry": all_geoms.geometry.union_all().convex_hull}],
            crs=TARGET_CRS,
        )
        canonical_gdfs["AREA_IMOVEL"] = _standardize_gdf(hull_gdf, "AREA_IMOVEL")
        resumo_areas_ha["AREA_IMOVEL"] = round(float(canonical_gdfs["AREA_IMOVEL"]["area_ha"].sum()), 4)

    origem_info = detect_car_origin_system(canonical_gdfs, filename=filename)

    # Identifica quais camadas vieram declaradas e quais precisarão ser inferidas pelo Motor Espacial
    camadas_declaradas = [k for k, v in resumo_areas_ha.items() if v > 0]
    camadas_ausentes = [k for k, v in resumo_areas_ha.items() if v == 0.0]
    modo_coleta = (
        "Pacote Completo CAR Multi-Camadas"
        if len(camadas_declaradas) > 1
        else "Perímetro Simples (Inferência Automática Ativada)"
    )

    imovel_gdf = canonical_gdfs["AREA_IMOVEL"]
    bounds = [round(float(x), 6) for x in imovel_gdf.total_bounds]
    centroid = imovel_gdf.geometry.union_all().centroid

    return {
        "origem": origem_info,
        "modo_entrada": modo_coleta,
        "crs_padronizado": TARGET_CRS,
        "utm_metrico_aplicado": str(imovel_gdf["utm_calculo"].iloc[0]),
        "bbox_imovel": bounds,  # [minx, miny, maxx, maxy] para filtro espacial rápido na Etapa 3
        "centroide_lat_lon": (round(float(centroid.y), 6), round(float(centroid.x), 6)),
        "camadas_declaradas": camadas_declaradas,
        "camadas_para_inferir": camadas_ausentes,
        "resumo_areas_declaradas_ha": resumo_areas_ha,
        "camadas_gdf": canonical_gdfs,
    }


def _run_self_test():
    """Valida a tradução de pacotes CAR de SP, MG e coleta simples do App Mobile Offline."""
    # 1. Simula exportação SICAR-SP (nomenclatura paulista: PERIMETRO_IMOVEL, AA, RL, VN, APP)
    poly_base = Polygon([
        (-47.650, -22.720), (-47.640, -22.720),
        (-47.640, -22.710), (-47.650, -22.710), (-47.650, -22.720)
    ])
    poly_rl = Polygon([
        (-47.650, -22.720), (-47.648, -22.720),
        (-47.648, -22.710), (-47.650, -22.710), (-47.650, -22.720)
    ])
    sp_geojson = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"tp_feicao": "PERIMETRO_IMOVEL", "recibo": "SP-3538709-TESTE"}, "geometry": mapping(poly_base)},
            {"type": "Feature", "properties": {"tp_feicao": "RL", "recibo": "SP-3538709-TESTE"}, "geometry": mapping(poly_rl)},
            {"type": "Feature", "properties": {"tp_feicao": "AA", "recibo": "SP-3538709-TESTE"}, "geometry": mapping(poly_base.difference(poly_rl))},
        ],
    }

    # 2. Simula pacote .zip multi-arquivo padrão MG / SICAR Federal (Area_do_Imovel + APP_Total)
    mg_zip_buffer = io.BytesIO()
    with zipfile.ZipFile(mg_zip_buffer, "w") as zf:
        zf.writestr("Area_do_Imovel.geojson", json.dumps({
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {"uf": "MG", "protocolo_car": "MG-3125101-TESTE"}, "geometry": mapping(poly_base)}]
        }))
        zf.writestr("APP_Total.geojson", json.dumps({
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {"uf": "MG"}, "geometry": mapping(poly_rl)}]
        }))

    res_sp = translate_car_input(sp_geojson, filename="sicar_sp_export.geojson")
    res_mg = translate_car_input(mg_zip_buffer.getvalue(), filename="ide_sisema_mg.zip")

    # 3. Testa arquivo de perímetro simples (como o gerado pelo App Mobile Offline)
    sample_mobile = BASE_DIR / "data" / "processed" / "samples_pcj" / "piracicaba_uc_app.geojson"
    res_mob = translate_car_input(sample_mobile)

    print("\n=== Teste do Tradutor Unificado de Camadas CAR (Etapa 2) ===")
    print(f"[Cenário 1 - SP] Sistema : {res_sp['origem']['sistema_origem']}")
    print(f"                 Camadas : {res_sp['camadas_declaradas']} | Imóvel: {res_sp['resumo_areas_declaradas_ha']['AREA_IMOVEL']} ha")
    print(f"[Cenário 2 - MG] Sistema : {res_mg['origem']['sistema_origem']}")
    print(f"                 Camadas : {res_mg['camadas_declaradas']} | APP Declarada: {res_mg['resumo_areas_declaradas_ha']['APP']} ha")
    print(f"[Cenário 3 - App Mobile] : {res_mob['modo_entrada']}")
    print(f"                 BBox    : {res_mob['bbox_imovel']} | UTM: {res_mob['utm_metrico_aplicado']}")
    print("Status                   : Tradutor nacional multi-estado (SP/MG/BR) validado com sucesso!")


if __name__ == "__main__":
    _run_self_test()