import sys
from pathlib import Path

# Fix permanente para resolver o ModuleNotFoundError independente de como o script é chamado
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

from typing import Dict, Any
import geopandas as gpd
import shapely

# Diretórios de dados processados
PROCESSED_DIR = BASE_DIR / "data" / "processed"
METRIC_CRS = "EPSG:31983"  # SIRGAS 2000 / UTM 23S para cálculos de área métrica


def _load_layer(filename: str) -> gpd.GeoDataFrame:
    """Carrega uma camada geoespacial processada da Bacia PCJ."""
    path = PROCESSED_DIR / filename
    if not path.exists():
        # Retorna GeoDataFrame vazio caso a camada não exista
        return gpd.GeoDataFrame(crs="EPSG:4674")
    return gpd.read_file(path)


def analyze_environmental_overlap(gdf_imovel: gpd.GeoDataFrame) -> Dict[str, Any]:
    """
    Cruza o polígono da propriedade com as camadas ambientais da Bacia PCJ:
    - Verificação de pertencimento à Bacia PCJ.
    - Sobreposição com Unidades de Conservação e Áreas Protegidas.
    - Estimativa de Áreas de Preservação Permanente (APP) ao longo da hidrografia.
    """
    # Garante CRS padronizado
    if gdf_imovel.crs is None or gdf_imovel.crs.to_epsg() != 4674:
        gdf_imovel = gdf_imovel.set_crs("EPSG:4674", allow_override=True)

    imovel_geom = gdf_imovel.geometry.iloc[0]
    
    # Validação defensiva caso 'area_ha' não exista nas colunas
    if "area_ha" in gdf_imovel.columns:
        area_total_ha = float(gdf_imovel["area_ha"].iloc[0])
    else:
        # Calcula dinamicamente em UTM se não vier calculado no GeoJSON
        gdf_metrico = gdf_imovel.to_crs(METRIC_CRS)
        area_total_ha = round(float(gdf_metrico.geometry.iloc[0].area / 10_000.0), 4)

    # 1. Validação de Limite da Bacia PCJ
    gdf_bacia = _load_layer("limite_bacia_pcj.geojson")
    dentro_da_bacia = True
    if not gdf_bacia.empty:
        bacia_unida = gdf_bacia.geometry.unary_union
        dentro_da_bacia = imovel_geom.intersects(bacia_unida)

    # 2. Análise de Unidades de Conservação e Restrições
    gdf_ucs = _load_layer("unidades_conservacao_pcj.geojson")
    ucs_encontradas = []
    
    if not gdf_ucs.empty:
        # Usa intersection para calcular a área exata sobreposta em hectares
        imovel_metrico = gdf_imovel.to_crs(METRIC_CRS).geometry.iloc[0]
        gdf_ucs_metrico = gdf_ucs.to_crs(METRIC_CRS)

        for _, uc in gdf_ucs_metrico.iterrows():
            if imovel_metrico.intersects(uc.geometry):
                interseccao = imovel_metrico.intersection(uc.geometry)
                area_uc_ha = round(interseccao.area / 10_000.0, 4)
                if area_uc_ha > 0.001:
                    ucs_encontradas.append({
                        "nome_uc": uc.get("nome_uc", "Unidade de Conservação"),
                        "categoria": uc.get("categoria", "Desconhecida"),
                        "nivel_restricao": uc.get("restricao", "Média"),
                        "area_sobreposta_ha": area_uc_ha
                    })

    # 3. Análise Preliminar de APP de Rios (Buffer Baseado na Largura)
    gdf_hidro = _load_layer("hidrografia_pcj.geojson")
    app_estimada_ha = 0.0
    cursos_agua_proximos = 0

    if not gdf_hidro.empty:
        imovel_metrico = gdf_imovel.to_crs(METRIC_CRS).geometry.iloc[0]
        gdf_hidro_metrico = gdf_hidro.to_crs(METRIC_CRS)

        app_geometrias = []
        for _, rio in gdf_hidro_metrico.iterrows():
            if imovel_metrico.intersects(rio.geometry):
                cursos_agua_proximos += 1
                largura_app = float(rio.get("app_exigida_m", 30.0))
                # Cria a faixa de buffer da APP ao longo do trecho de rio dentro da propriedade
                buffer_app = rio.geometry.buffer(largura_app)
                intersec_app = imovel_metrico.intersection(buffer_app)
                if not intersec_app.is_empty:
                    app_geometrias.append(intersec_app)

        if app_geometrias:
            app_unida = shapely.ops.unary_union(app_geometrias)
            app_estimada_ha = round(app_unida.area / 10_000.0, 4)

    # Garante que a APP estimada não ultrapasse a área total da propriedade
    app_estimada_ha = min(app_estimada_ha, area_total_ha)
    area_util_ha = round(max(0.0, area_total_ha - app_estimada_ha), 4)

    # 4. Geração de Alertas e Status de Conformidade
    alertas = []
    if not dentro_da_bacia:
        alertas.append("Aviso: O imóvel encontra-se fora do perímetro de referência oficial das Bacias PCJ.")
    if ucs_encontradas:
        alertas.append(f"Atenção: Identificada sobreposição com {len(ucs_encontradas)} Unidade(s) de Conservação.")
    if app_estimada_ha > 0:
        alertas.append(f"Conformidade APP: Estimada faixa de Área de Preservação Permanente de {app_estimada_ha} ha.")

    status_geral = "Regular / Em Análise"
    if ucs_encontradas or not dentro_da_bacia:
        status_geral = "Requer Verificação Técnico-Especializada"

    return {
        "status_geral": status_geral,
        "dentro_da_bacia_pcj": dentro_da_bacia,
        "area_total_ha": area_total_ha,
        "area_app_estimada_ha": app_estimada_ha,
        "area_util_produtiva_ha": area_util_ha,
        "unidades_conservacao": ucs_encontradas,
        "cursos_agua_cruzados": cursos_agua_proximos,
        "alertas": alertas
    }


if __name__ == "__main__":
    # Teste integrado usando o validador espacial
    from backend.spatial_validator import validate_and_standardize

    sample_path = PROCESSED_DIR / "amostra_propriedade_pcj.geojson"

    if sample_path.exists():
        valido_dict = validate_and_standardize(sample_path)
        resultado_analise = analyze_environmental_overlap(valido_dict["gdf"])
        
        print("\n=== Teste do Motor de Sobreposição (Dia 4) ===")
        print(f"Status Geral       : {resultado_analise['status_geral']}")
        print(f"Dentro da Bacia PCJ: {resultado_analise['dentro_da_bacia_pcj']}")
        print(f"Área Total         : {resultado_analise['area_total_ha']} ha")
        print(f"APP Estimada       : {resultado_analise['area_app_estimada_ha']} ha")
        print(f"Área Útil Produtiva: {resultado_analise['area_util_produtiva_ha']} ha")
        print(f"Cursos d'Água      : {resultado_analise['cursos_agua_cruzados']} cruzamento(s) identificado(s)")
        print(f"Alertas Emitidos   : {resultado_analise['alertas']}")
    else:
        print(f"Arquivo de amostra não encontrado em: {sample_path}")
        print("Certifique-se de que o validador gerou o arquivo 'amostra_propriedade_pcj.geojson'.")
