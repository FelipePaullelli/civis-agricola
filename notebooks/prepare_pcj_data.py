from pathlib import Path
import unicodedata
import geopandas as gpd
import pandas as pd
import requests
import urllib3
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

# Desativa avisos de certificado SSL ICP-Brasil (.gov.br) no Windows
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Diretórios do projeto
BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
TARGET_CRS = "EPSG:4674"  # SIRGAS 2000 oficial

HEADERS = {"User-Agent": "civis-agricola-pcj-dataprep/1.0"}

# Lista completa de municípios inseridos nas Bacias PCJ (SP e MG)
MUNICIPIOS_PCJ = {
    "SP": [
        "Águas de Lindóia", "Águas de São Pedro", "Americana", "Amparo", "Analândia",
        "Araras", "Artur Nogueira", "Atibaia", "Bom Jesus dos Perdões", "Bragança Paulista",
        "Cabreúva", "Caieiras", "Campinas", "Campo Limpo Paulista", "Capivari",
        "Charqueada", "Conchal", "Cordeirópolis", "Corumbataí", "Cosmópolis",
        "Elias Fausto", "Engenheiro Coelho", "Espírito Santo do Pinhal", "Franco da Rocha",
        "Holambra", "Hortolândia", "Indaiatuba", "Ipeúna", "Iracemápolis", "Itatiba",
        "Itirapina", "Itu", "Itupeva", "Jaguariúna", "Jarinu", "Joanópolis", "Jundiaí",
        "Limeira", "Lindóia", "Louveira", "Mairiporã", "Mombuca", "Monte Alegre do Sul",
        "Monte Mor", "Morungaba", "Nazaré Paulista", "Nova Odessa", "Paulínia",
        "Pedra Bela", "Pedreira", "Pinhalzinho", "Piracaia", "Piracicaba", "Rafard",
        "Rio Claro", "Rio das Pedras", "Saltinho", "Salto", "Santa Bárbara d'Oeste",
        "Santa Cruz da Conceição", "Santa Gertrudes", "Santa Maria da Serra",
        "Santo Antônio de Posse", "São Pedro", "Serra Negra", "Socorro", "Sumaré",
        "Torrinha", "Tuiuti", "Valinhos", "Vargem", "Várzea Paulista", "Vinhedo"
    ],
    "MG": [
        "Camanducaia", "Extrema", "Itapeva", "Sapucaí-Mirim", "Toledo"
    ]
}

UF_CODES = {"SP": "35", "MG": "31"}


def normalize_text(text: str) -> str:
    """Remove acentos e padroniza para comparação segura de nomes."""
    nfkd = unicodedata.normalize("NFKD", str(text))
    return "".join([c for c in nfkd if not unicodedata.combining(c)]).lower().strip()


def standardize_to_sirgas2000(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Garante que o GeoDataFrame esteja no CRS SIRGAS 2000 (EPSG:4674)."""
    if gdf.crs is None:
        return gdf.set_crs(TARGET_CRS)
    if gdf.crs.to_epsg() != 4674:
        return gdf.to_crs(TARGET_CRS)
    return gdf


def fetch_municipios_pcj() -> gpd.GeoDataFrame:
    """Baixa as malhas estaduais (SP e MG) via API do IBGE e filtra todos os municípios do PCJ."""
    print("1. Baixando malhas estaduais (SP e MG) via API do IBGE...")
    gdfs_pcj = []

    for uf_sigla, uf_code in UF_CODES.items():
        alvos_norm = {normalize_text(m) for m in MUNICIPIOS_PCJ[uf_sigla]}

        # 1.1 Busca nomes e códigos IBGE de todos os municípios da UF
        loc_url = f"https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf_code}/municipios"
        resp_loc = requests.get(loc_url, headers=HEADERS, verify=False, timeout=30)
        resp_loc.raise_for_status()

        mapa_cod_nome = {}
        for item in resp_loc.json():
            nome_oficial = item["nome"]
            if normalize_text(nome_oficial) in alvos_norm:
                mapa_cod_nome[str(item["id"])] = nome_oficial

        # 1.2 Baixa a malha vetorial de todos os municípios da UF em uma única chamada
        malha_url = (
            f"https://servicodados.ibge.gov.br/api/v3/malhas/estados/{uf_code}"
            f"?formato=application/vnd.geo+json&qualidade=intermediaria&intrarregiao=municipio"
        )
        resp_malha = requests.get(malha_url, headers=HEADERS, verify=False, timeout=60)
        resp_malha.raise_for_status()

        gdf_uf = gpd.read_file(resp_malha.text)
        gdf_uf["cd_mun"] = gdf_uf["codarea"].astype(str)

        # Filtra apenas os municípios pertencentes ao PCJ e reprojeta para EPSG:4674
        gdf_filtrado = gdf_uf[gdf_uf["cd_mun"].isin(mapa_cod_nome.keys())].copy()
        gdf_filtrado["nm_mun"] = gdf_filtrado["cd_mun"].map(mapa_cod_nome)
        gdf_filtrado["uf"] = uf_sigla
        gdf_filtrado = standardize_to_sirgas2000(gdf_filtrado[["cd_mun", "nm_mun", "uf", "geometry"]])
        gdfs_pcj.append(gdf_filtrado)
        print(f"   -> {uf_sigla}: {len(gdf_filtrado)} municípios do PCJ carregados.")

    # Concatena mantendo o CRS original e garante SIRGAS 2000 (EPSG:4674)
    gdf_all = gpd.GeoDataFrame(pd.concat(gdfs_pcj, ignore_index=True))
    gdf_all = standardize_to_sirgas2000(gdf_all)

    output_path = PROCESSED_DIR / "municipios_pcj.geojson"
    gdf_all.to_file(output_path, driver="GeoJSON")
    print(f"   -> Total salvo: {len(gdf_all)} municípios em {output_path} | CRS: {gdf_all.crs}")
    return gdf_all


def build_limite_bacia_pcj(gdf_municipios: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Dissolve os municípios do PCJ para gerar o limite envolvente de referência em EPSG:4674."""
    print("2. Gerando camada de limite de referência das Bacias PCJ...")
    uniao = unary_union(gdf_municipios.geometry)
    gdf_bacia = gpd.GeoDataFrame(
        [{"id_bacia": "PCJ", "nome": "Bacias Hidrográficas dos Rios Piracicaba, Capivari e Jundiaí", "geometry": uniao}],
        crs=TARGET_CRS,
    )
    gdf_bacia = standardize_to_sirgas2000(gdf_bacia)
    output_path = PROCESSED_DIR / "limite_bacia_pcj.geojson"
    gdf_bacia.to_file(output_path, driver="GeoJSON")
    print(f"   -> Salvo em: {output_path} | CRS: {gdf_bacia.crs}")
    return gdf_bacia


def build_hidrografia_e_ucs_pcj():
    """Cria camadas vetoriais de referência da hidrografia principal e UCs da PCJ em EPSG:4674."""
    print("3. Preparando camadas de Hidrografia Principal e Unidades de Conservação PCJ...")

    rios = [
        {
            "nome_rio": "Rio Piracicaba",
            "largura_m": 80.0,
            "app_exigida_m": 100.0,
            "geometry": LineString([(-47.330, -22.740), (-47.480, -22.725), (-47.650, -22.715), (-47.780, -22.680)]),
        },
        {
            "nome_rio": "Rio Jaguari",
            "largura_m": 45.0,
            "app_exigida_m": 50.0,
            "geometry": LineString([(-46.250, -22.850), (-46.550, -22.880), (-46.950, -22.750), (-47.330, -22.740)]),
        },
        {
            "nome_rio": "Rio Atibaia",
            "largura_m": 35.0,
            "app_exigida_m": 50.0,
            "geometry": LineString([(-46.550, -23.110), (-46.850, -22.980), (-47.100, -22.820), (-47.330, -22.740)]),
        },
        {
            "nome_rio": "Rio Capivari",
            "largura_m": 25.0,
            "app_exigida_m": 50.0,
            "geometry": LineString([(-46.950, -22.980), (-47.150, -23.010), (-47.520, -22.990)]),
        },
        {
            "nome_rio": "Rio Jundiaí",
            "largura_m": 20.0,
            "app_exigida_m": 50.0,
            "geometry": LineString([(-46.820, -23.190), (-46.980, -23.170), (-47.220, -23.195)]),
        },
    ]
    gdf_hidro = standardize_to_sirgas2000(gpd.GeoDataFrame(rios, crs=TARGET_CRS))
    hidro_path = PROCESSED_DIR / "hidrografia_pcj.geojson"
    gdf_hidro.to_file(hidro_path, driver="GeoJSON")
    print(f"   -> Salvo em: {hidro_path} | CRS: {gdf_hidro.crs}")

    ucs = [
        {
            "nome_uc": "APA Tanquã - Rio Piracicaba",
            "categoria": "Uso Sustentável",
            "restricao": "Média",
            "geometry": Polygon([(-47.820, -22.710), (-47.730, -22.710), (-47.730, -22.650), (-47.820, -22.650)]),
        },
        {
            "nome_uc": "Estação Ecológica de Ibicatu (Piracicaba)",
            "categoria": "Proteção Integral",
            "restricao": "Alta",
            "geometry": Polygon([(-47.835, -22.785), (-47.805, -22.785), (-47.805, -22.765), (-47.835, -22.765)]),
        },
        {
            "nome_uc": "APA Sistema Cantareira (Setor PCJ)",
            "categoria": "Uso Sustentável",
            "restricao": "Média",
            "geometry": Polygon([(-46.650, -23.150), (-46.200, -23.150), (-46.200, -22.800), (-46.650, -22.800)]),
        },
    ]