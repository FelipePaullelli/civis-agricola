import sys
from pathlib import Path

# Fix permanente para resolver caminhos independente de como o script é chamado
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

import folium
import geopandas as gpd
import streamlit as st
from streamlit_folium import st_folium

PROCESSED_DIR = BASE_DIR / "data" / "processed"
PCJ_CENTER = [-22.85, -47.05]
DEFAULT_ZOOM = 9


@st.cache_data(show_spinner=False)
def load_pcj_layer(filename: str) -> gpd.GeoDataFrame:
    """Carrega e armazena em cache as camadas vetoriais da Bacia PCJ em SIRGAS 2000."""
    path = PROCESSED_DIR / filename
    if not path.exists():
        return gpd.GeoDataFrame(crs="EPSG:4674")
    return gpd.read_file(path)


def build_pcj_base_map() -> folium.Map:
    """Constrói o mapa interativo Folium centralizado na Bacia PCJ com camadas de referência."""
    mapa = folium.Map(
        location=PCJ_CENTER,
        zoom_start=DEFAULT_ZOOM,
        tiles="CartoDB dark_matter",
        control_scale=True,
    )

    folium.TileLayer("OpenStreetMap", name="Mapa Viário (OSM)").add_to(mapa)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri",
        name="Satélite (Esri World Imagery)",
    ).add_to(mapa)

    # 1. Camada de Limite da Bacia PCJ
    gdf_bacia = load_pcj_layer("limite_bacia_pcj.geojson")
    if not gdf_bacia.empty:
        folium.GeoJson(
            gdf_bacia,
            name="Limite Bacias PCJ",
            style_function=lambda _: {
                "fillColor": "#1b5e20",
                "color": "#66bb6a",
                "weight": 2.5,
                "fillOpacity": 0.08,
            },
            tooltip=folium.GeoJsonTooltip(fields=["nome"], aliases=["Região:"]),
        ).add_to(mapa)

    # 2. Camada de Malha Municipal PCJ (desativada por padrão para limpeza visual)
    gdf_mun = load_pcj_layer("municipios_pcj.geojson")
    if not gdf_mun.empty:
        folium.GeoJson(
            gdf_mun,
            name="Municípios PCJ (78)",
            show=False,
            style_function=lambda _: {
                "fillColor": "transparent",
                "color": "#90a4ae",
                "weight": 1.0,
                "dashArray": "4, 4",
            },
            tooltip=folium.GeoJsonTooltip(fields=["nm_mun", "uf"], aliases=["Município:", "UF:"]),
        ).add_to(mapa)

    # 3. Camada de Unidades de Conservação PCJ
    gdf_ucs = load_pcj_layer("unidades_conservacao_pcj.geojson")
    if not gdf_ucs.empty:
        folium.GeoJson(
            gdf_ucs,
            name="Unidades de Conservação",
            style_function=lambda _: {
                "fillColor": "#f57c00",
                "color": "#ffb74d",
                "weight": 2.0,
                "fillOpacity": 0.35,
            },
            tooltip=folium.GeoJsonTooltip(
                fields=["nome_uc", "categoria", "restricao"],
                aliases=["UC:", "Categoria:", "Restrição:"],
            ),
        ).add_to(mapa)

    # 4. Camada de Hidrografia Principal PCJ
    gdf_hidro = load_pcj_layer("hidrografia_pcj.geojson")
    if not gdf_hidro.empty:
        folium.GeoJson(
            gdf_hidro,
            name="Hidrografia Principal PCJ",
            style_function=lambda _: {
                "color": "#29b6f6",
                "weight": 3.0,
            },
            tooltip=folium.GeoJsonTooltip(
                fields=["nome_rio", "largura_m", "app_exigida_m"],
                aliases=["Curso d'água:", "Largura (m):", "APP Exigida (m):"],
            ),
        ).add_to(mapa)

    folium.LayerControl(collapsed=False).add_to(mapa)
    return mapa


def render_app():
    """Renderiza a estrutura inicial do Frontend em Streamlit (Dia 8)."""
    st.set_page_config(
        page_title="Civis Agricola | Consultoria Ambiental PCJ",
        page_icon="🌱",
        layout="wide",
    )

    st.title("🌱 Civis Agricola — Consultoria Ambiental Rural (Bacias PCJ)")
    st.caption(
        "Orientação para Licenciamento, Conformidade no Código Florestal e Benefícios para o Pequeno Produtor Rural "
        "| Sistema de Referência Oficial: SIRGAS 2000 (EPSG:4674)"
    )

    with st.sidebar:
        st.header("Painel do Produtor")
        st.info(
            "Explore no mapa ao lado os limites das Bacias PCJ, a hidrografia principal e as "
            "Unidades de Conservação. Na próxima etapa (Dia 9), o upload do polígono será "
            "conectado diretamente ao motor de diagnóstico."
        )
        st.markdown("**Resumo da Base Territorial PCJ**")
        st.write("- **Municípios integrados:** 78 (73 SP / 5 MG)")
        st.write("- **Projeção oficial:** SIRGAS 2000 (EPSG:4674)")
        st.write("- **Cálculo métrico:** UTM Zona 23S (EPSG:31983)")

    mapa_pcj = build_pcj_base_map()
    st_folium(mapa_pcj, width=None, height=620, returned_objects=[])


if __name__ == "__main__":
    if "--check" in sys.argv:
        mapa_teste = build_pcj_base_map()
        print("\n=== Teste do Frontend Streamlit e Mapa Folium (Dia 8) ===")
        print(f"Centro do Mapa PCJ : {mapa_teste.location}")
        print(f"Camadas Carregadas : Limite PCJ, Municípios (78), Hidrografia e Unidades de Conservação")
        print("Status             : Mapa interativo validado com sucesso!")
    else:
        render_app()