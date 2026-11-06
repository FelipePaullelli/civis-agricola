import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

# Fix permanente para resolver caminhos independente de como o script é chamado
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

import folium
import geopandas as gpd
import requests
import streamlit as st
from streamlit_folium import st_folium

from backend.app_calculator import calculate_environmental_liability
from backend.main import _anexar_inteligencia_cidada
from backend.spatial_validator import SpatialValidationError, validate_and_standardize
from backend.report_generator import generate_pdf_report

PROCESSED_DIR = BASE_DIR / "data" / "processed"
SAMPLES_DIR = PROCESSED_DIR / "samples_pcj"
LOGO_PATH = BASE_DIR / "frontend" / "assets" / "logo_dark.jpeg"
API_URL = os.getenv("CIVIS_API_URL", "http://127.0.0.1:8000/api/v1/analisar")

PCJ_CENTER = [-22.85, -47.05]
DEFAULT_ZOOM = 9

SAMPLE_OPTIONS = {
    "Piracicaba (SP) — Sítio Tanquã (Com APP + UC)": ("piracicaba_uc_app.geojson", "SP", "Piracicaba"),
    "Jundiaí (SP) — Chácara Vale do Jundiaí (Com APP)": ("jundiai_app.geojson", "SP", "Jundiaí"),
    "Limeira (SP) — Fazenda Boa Vista (Regular / Sem Restrições)": ("limeira_regular.geojson", "SP", "Limeira"),
}

UF_OPTIONS = {
    "SP — SICAR-SP / DataGEO (Paulista)": "SP",
    "MG — IDE-Sisema / SICAR-MG (Mineiro)": "MG",
    "BR — SICAR Federal (Padrão Nacional)": "BR",
}

MUNICIPIOS_REF = [
    "Piracicaba",
    "Jundiaí",
    "Limeira",
    "Campinas",
    "Bragança Paulista",
    "Joanópolis",
    "Nazaré Paulista",
    "Rio Claro",
    "Americana",
    "Atibaia",
    "Extrema",
    "Camanducaia",
    "Toledo",
    "Itapeva",
]


def load_pcj_layer(filename: str) -> gpd.GeoDataFrame:
    """Carrega as camadas vetoriais da Bacia PCJ padronizadas em SIRGAS 2000 (EPSG:4674)."""
    path = PROCESSED_DIR / filename
    if not path.exists():
        return gpd.GeoDataFrame(crs="EPSG:4674")
    return gpd.read_file(path)


def request_property_analysis(
    file_bytes: bytes,
    filename: str,
    uf: str = "SP",
    municipio: str = "Piracicaba",
) -> Tuple[Dict[str, Any], str]:
    """Envia o arquivo vetorial via HTTP POST para a API FastAPI ou aciona o motor local integrado."""
    try:
        files = {"arquivo": (filename, file_bytes, "application/octet-stream")}
        params = {"uf": uf, "municipio": municipio}
        response = requests.post(API_URL, params=params, files=files, timeout=10)
        if response.status_code == 200:
            return response.json(), "HTTP FastAPI (POST /api/v1/analisar)"
        detail = response.json().get("detail", response.text)
        raise SpatialValidationError(f"Erro na API ({response.status_code}): {detail}")
    except requests.exceptions.ConnectionError:
        diagnostico = calculate_environmental_liability(file_input=file_bytes, filename=filename)
        diagnostico = _anexar_inteligencia_cidada(
            diagnostico=diagnostico,
            conteudo_bytes=file_bytes,
            uf=uf,
            municipio=municipio,
        )
        payload = {
            "sucesso": True,
            "arquivo_processado": filename,
            "resultado": diagnostico,
        }
        return payload, "Motor Backend Direto (Fallback Local)"


def build_pcj_map(
    gdf_imovel: Optional[gpd.GeoDataFrame] = None,
    centro_imovel: Optional[Tuple[float, float]] = None,
) -> folium.Map:
    """Constrói o mapa interativo Folium centralizado na Bacia PCJ ou no imóvel analisado."""
    center = list(centro_imovel) if centro_imovel else PCJ_CENTER
    zoom = 14 if centro_imovel else DEFAULT_ZOOM

    mapa = folium.Map(
        location=center,
        zoom_start=zoom,
        tiles=None,
        control_scale=True,
    )

    folium.TileLayer(
        tiles="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
        attr="&copy; OpenStreetMap contributors &copy; CARTO",
        name="Tema Escuro (CartoDB Dark)",
        subdomains="abcd",
        max_zoom=20,
    ).add_to(mapa)

    folium.TileLayer("OpenStreetMap", name="Mapa Viário (OSM)").add_to(mapa)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri",
        name="Satélite (Esri World Imagery)",
    ).add_to(mapa)

    gdf_bacia = load_pcj_layer("limite_bacia_pcj.geojson")
    if not gdf_bacia.empty:
        folium.GeoJson(
            gdf_bacia,
            name="Limite Bacia PCJ",
            style_function=lambda _: {
                "fillColor": "#1b5e20",
                "color": "#66bb6a",
                "weight": 2.0,
                "fillOpacity": 0.06,
            },
            tooltip=folium.GeoJsonTooltip(fields=["nome"], aliases=["Região:"]),
        ).add_to(mapa)

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

    if gdf_imovel is not None and not gdf_imovel.empty:
        folium.GeoJson(
            gdf_imovel,
            name="Propriedade Analisada",
            style_function=lambda _: {
                "fillColor": "#ffd600",
                "color": "#ffff00",
                "weight": 3.5,
                "fillOpacity": 0.40,
            },
            tooltip=folium.GeoJsonTooltip(
                fields=["area_ha", "perimetro_m", "crs_original"],
                aliases=["Área Total (ha):", "Perímetro (m):", "CRS Original:"],
            ),
        ).add_to(mapa)

    folium.LayerControl(collapsed=False).add_to(mapa)
    return mapa


def render_app():
    icone_pagina = str(LOGO_PATH) if LOGO_PATH.exists() else "🌱"

    st.set_page_config(
        page_title="Civis Agricola | Consultoria Ambiental e Cidadania Rural",
        page_icon=icone_pagina,
        layout="wide",
    )

    if LOGO_PATH.exists():
        st.logo(str(LOGO_PATH), size="large")
        col_logo, col_titulo = st.columns([1, 9], vertical_alignment="center")
        with col_logo:
            st.image(str(LOGO_PATH), width=110)
        with col_titulo:
            st.title("Civis Agricola — Consultoria Ambiental e Cidadania Rural")
            st.caption(
                "Tradutor Multi-Estado do CAR (SP, MG e BR), Conformidade no Código Florestal e Cartilha Cidadã "
                "| 100% Software Livre | SIRGAS 2000 (EPSG:4674)"
            )
    else:
        st.title("🌱 Civis Agricola — Consultoria Ambiental e Cidadania Rural")
        st.caption(
            "Tradutor Multi-Estado do CAR (SP, MG e BR), Conformidade no Código Florestal e Cartilha Cidadã "
            "| 100% Software Livre | SIRGAS 2000 (EPSG:4674)"
        )

    with st.sidebar:
        st.header("1. Entrada da Propriedade")
        modo_entrada = st.radio(
            "Escolha a fonte do polígono:",
            ["Upload de Arquivo Vetorial / App Mobile", "Cenários de Teste (Bacia PCJ)"],
        )

        file_bytes: Optional[bytes] = None
        filename: str = ""
        uf_selecionada: str = "SP"
        municipio_selecionado: str = "Piracicaba"

        if modo_entrada == "Upload de Arquivo Vetorial / App Mobile":
            uf_label = st.selectbox("Sistema Estadual do CAR:", list(UF_OPTIONS.keys()))
            uf_selecionada = UF_OPTIONS[uf_label]
            municipio_selecionado = st.selectbox("Município de Referência (Módulo Fiscal):", MUNICIPIOS_REF)

            uploaded = st.file_uploader(
                "Envie o polígono ou pacote CAR (.geojson, .kml, .shp ou .zip)",
                type=["geojson", "json", "kml", "shp", "zip"],
            )
            if uploaded is not None:
                file_bytes = uploaded.getvalue()
                filename = uploaded.name
        else:
            cenario_label = st.selectbox("Selecione o imóvel de exemplo:", list(SAMPLE_OPTIONS.keys()))
            arq_nome, uf_cenario, mun_cenario = SAMPLE_OPTIONS[cenario_label]
            uf_selecionada = uf_cenario
            municipio_selecionado = mun_cenario
            sample_file = SAMPLES_DIR / arq_nome
            if sample_file.exists():
                file_bytes = sample_file.read_bytes()
                filename = sample_file.name

        executar = st.button(
            "🔍 Executar Diagnóstico e Cartilha Cidadã",
            type="primary",
            use_container_width=True,
            disabled=(file_bytes is None),
        )

        st.divider()
        st.markdown("**Arquitetura 100% Software Livre**")
        st.write("- **App Campo:** PWA Offline (`mobile/`) < 15 KB")
        st.write("- **Tradutor CAR:** SP (DataGEO), MG (Sisema) e BR")
        st.write("- **Municípios PCJ:** 78 (73 SP / 5 MG)")
        st.write("- **Projeção oficial:** SIRGAS 2000 (EPSG:4674)")

    if executar and file_bytes and filename:
        try:
            with st.spinner("Processando geometria, traduzindo camadas CAR e gerando Cartilha Cidadã..."):
                resposta_api, modo_conexao = request_property_analysis(
                    file_bytes=file_bytes,
                    filename=filename,
                    uf=uf_selecionada,
                    municipio=municipio_selecionado,
                )
                val_local = validate_and_standardize(file_bytes, filename=filename)

                pdf_path = generate_pdf_report(file_bytes, filename=filename)
                pdf_bytes = pdf_path.read_bytes()

                st.session_state["resposta_api"] = resposta_api
                st.session_state["modo_conexao"] = modo_conexao
                st.session_state["gdf_imovel"] = val_local["gdf"]
                st.session_state["centro_imovel"] = val_local["centroide_lat_lon"]
                st.session_state["pdf_bytes"] = pdf_bytes
                st.session_state["pdf_filename"] = f"laudo_{Path(filename).stem}.pdf"
        except Exception as exc:
            st.error(f"Falha ao processar o arquivo enviado: {exc}")

    col_mapa, col_painel = st.columns([3, 2])

    with col_mapa:
        st.subheader("Mapa Interativo de Diagnóstico Territorial")
        mapa_pcj = build_pcj_map(
            gdf_imovel=st.session_state.get("gdf_imovel"),
            centro_imovel=st.session_state.get("centro_imovel"),
        )
        st_folium(mapa_pcj, width=None, height=620, returned_objects=[])

    with col_painel:
        st.subheader("Diagnóstico Técnico e Cartilha Cidadã")
        if "resposta_api" in st.session_state:
            res = st.session_state["resposta_api"]["resultado"]
            status = res["status_geral"]
            cartilha = res.get("cartilha_cidada")
            trad_car = res.get("traducao_car")

            if "Regular" in status:
                st.success(f"**Status Técnico:** {status}")
            else:
                st.warning(f"**Status Técnico:** {status}")

            if trad_car:
                st.caption(
                    f"**Sistema CAR:** {trad_car.get('sistema_estadual')} | "
                    f"**Imóvel:** {trad_car.get('nome_imovel')} | "
                    f"**Protocolo:** {trad_car.get('recibo_car')}"
                )

            if "pdf_bytes" in st.session_state:
                st.download_button(
                    label="📥 Baixar Laudo Técnico em PDF",
                    data=st.session_state["pdf_bytes"],
                    file_name=st.session_state["pdf_filename"],
                    mime="application/pdf",
                    type="primary",
                    use_container_width=True,
                )

            m1, m2, m3 = st.columns(3)
            m1.metric("Área Total", f"{res['balanco_uso_solo_ha']['area_total_ha']:.2f} ha")
            m2.metric("APP Estimada", f"{res['balanco_uso_solo_ha']['app_estimada_ha']:.2f} ha")
            m3.metric("Reserva Legal (Ref.)", f"{res['balanco_uso_solo_ha']['reserva_legal_referencia_ha']:.2f} ha")

            if cartilha:
                c1, c2, c3 = st.columns(3)
                c1.metric("Módulos Fiscais", f"{cartilha['qtd_modulos_fiscais']:.2f} MF")
                c2.metric("Escadinha APP (61-A)", f"{cartilha['faixa_recomposicao_app_m']} m")
                c3.metric(
                    "Isenção RL (Art. 67)",
                    "Sim (Familiar)" if cartilha["isento_recomposicao_rl_art67"] else "Não (Regra Geral)",
                )

                st.info(
                    f"**📋 Enquadramento Cidadão ({cartilha['status_cidadao']}):**\n\n"
                    f"{cartilha['resumo_linguagem_simples']}"
                )

                with st.expander("✅ Seus Direitos Garantidos (Código Florestal)", expanded=True):
                    for direito in cartilha.get("seus_direitos", []):
                        st.write(f"• {direito}")

                with st.expander("🛠️ Seus Deveres Práticos (Regularização / PRA)", expanded=True):
                    for dever in cartilha.get("seus_deveres", []):
                        st.write(f"• {dever}")

                with st.expander("💰 Benefícios Verdes, Crédito Rural e PSA Destravados", expanded=False):
                    for beneficio in cartilha.get("beneficios_destravados", []):
                        st.write(f"• {beneficio}")

            st.markdown("##### 📌 Conclusão Técnica")
            st.write(res["conclusao_tecnica"])

            if res["alertas"]:
                with st.expander("⚠️ Alertas Territoriais Identificados", expanded=False):
                    for alerta in res["alertas"]:
                        st.write(f"- {alerta}")

            with st.expander("📄 Visualizar JSON Completo da API", expanded=False):
                st.json(st.session_state["resposta_api"])
        else:
            st.info(
                "Selecione um arquivo vetorial (ou coleta do App Mobile) ou escolha um cenário de teste "
                "na barra lateral e clique em **Executar Diagnóstico e Cartilha Cidadã**."
            )


def _run_cli_check():
    """Autoteste End-to-End (Etapa 5) via terminal."""
    sample_path = SAMPLES_DIR / "piracicaba_uc_app.geojson"
    if not sample_path.exists():
        sample_path = PROCESSED_DIR / "amostra_propriedade_pcj.geojson"

    raw_bytes = sample_path.read_bytes()
    payload, origem = request_property_analysis(
        raw_bytes,
        sample_path.name,
        uf="SP",
        municipio="Piracicaba",
    )
    val = validate_and_standardize(raw_bytes, filename=sample_path.name)
    pdf_out = generate_pdf_report(raw_bytes, filename=sample_path.name)
    res = payload["resultado"]
    cartilha = res.get("cartilha_cidada", {})

    print("\n=== Teste End-to-End Frontend + Cartilha Cidadã (Etapa 5) ===")
    print(f"Canal de Conexão      : {origem}")
    print(f"Sistema CAR           : {res.get('traducao_car', {}).get('sistema_estadual')}")
    print(f"Status Técnico        : {res['status_geral']}")
    print(f"Status Cidadão        : {cartilha.get('status_cidadao')} ({cartilha.get('qtd_modulos_fiscais')} MF)")
    print(f"Escadinha APP (61-A)  : {cartilha.get('faixa_recomposicao_app_m')} metros")
    print(f"PDF Gerado com Sucesso: {pdf_out.name} ({pdf_out.stat().st_size} bytes)")
    print("Status                : Integração Completa Streamlit + CAR + Cartilha Cidadã + PDF validada!")


if __name__ == "__main__":
    if "--check" in sys.argv:
        _run_cli_check()
    else:
        render_app()