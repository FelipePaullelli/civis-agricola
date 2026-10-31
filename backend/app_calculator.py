import sys
from pathlib import Path

# Fix permanente para resolver o ModuleNotFoundError independente de como o script é chamado
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

from typing import Dict, Any
from backend.spatial_validator import validate_and_standardize
from backend.overlap_detector import analyze_environmental_overlap

PROCESSED_DIR = BASE_DIR / "data" / "processed"


def calculate_environmental_liability(file_input, filename: str = "") -> Dict[str, Any]:
    """
    Executa o pipeline completo de diagnóstico ambiental para o pequeno produtor:
    1. Validação geométrica e conversão para SIRGAS 2000 (EPSG:4674).
    2. Análise de sobreposição na Bacia PCJ (APP, Hidrografia e Unidades de Conservação).
    3. Cálculo de passivos, reserva legal exigida (20%) e recomendações estilo Sebrae/Embrapa.
    """
    # 1. Validação espacial (Dia 3)
    val_result = validate_and_standardize(file_input, filename=filename)
    gdf_imovel = val_result["gdf"]

    # 2. Análise de sobreposição (Dia 4)
    overlap_result = analyze_environmental_overlap(gdf_imovel)

    area_total = overlap_result["area_total_ha"]
    app_estimada = overlap_result["area_app_estimada_ha"]
    ucs = overlap_result["unidades_conservacao"]
    dentro_bacia = overlap_result["dentro_da_bacia_pcj"]

    # Cálculo de Reserva Legal de referência (20% no bioma Mata Atlântica/Cerrado em SP/MG)
    reserva_legal_exigida_ha = round(area_total * 0.20, 4)

    # 3. Regras de Negócio e Recomendações (Estilo Sebrae/Embrapa)
    recomendacoes = []
    possui_passivo_critico = False

    if not dentro_bacia:
        recomendacoes.append(
            "Atenção Territorial: Propriedade localizada fora da área de abrangência prioritária das Bacias PCJ. "
            "Verifique a UGRHI correspondente ao seu município."
        )

    if app_estimada > 0:
        recomendacoes.append(
            f"Gestão de APP: Foram estimadas {app_estimada} ha de Áreas de Preservação Permanente "
            "ao longo da hidrografia. Mantenha a mata ciliar protegida ou, caso exista uso rural consolidado, "
            "utilize as regras de recomposição escalonada do PRA (Programa de Regularização Ambiental)."
        )
    else:
        recomendacoes.append(
            "Hidrografia e APP: Não foram detectados cursos d'água principais cruzando diretamente o perímetro "
            "na base de referência atual. Verifique apenas eventuais nascentes locais no CAR."
        )

    recomendacoes.append(
        f"Reserva Legal (20%): A cota mínima de referência para o imóvel é de {reserva_legal_exigida_ha} ha "
        "(podendo incluir o cômputo de APP conforme Art. 15 do Código Florestal ou dispensa parcial para "
        "pequena propriedade familiar de até 4 módulos fiscais)."
    )

    if ucs:
        possui_passivo_critico = True
        n_ucs = len(ucs)
        recomendacoes.append(
            f"Restrição de UC: O imóvel intercepta {n_ucs} Unidade(s) de Conservação. "
            "Consulte o plano de manejo junto à Fundação Florestal/CETESB antes de novas intervenções."
        )
    else:
        recomendacoes.append(
            "Unidades de Conservação: Nenhuma sobreposição crítica detectada com as UCs mapeadas na Bacia PCJ."
        )

    if possui_passivo_critico:
        conclusao = (
            "O imóvel apresenta restrições ambientais sensíveis (sobreposição com UC). "
            "Recomenda-se assistência técnica presencial (CATI/EMATER ou Sebrae Rural) "
            "para validação do CAR e licenciamento."
        )
    else:
        conclusao = (
            "Imóvel com indicativos favoráveis de conformidade espacial perante os parâmetros gerais da Bacia PCJ. "
            "Mantenha o Cadastro Ambiental Rural (CAR) ativo para acesso a linhas de crédito verde (Pronaf)."
        )

    return {
        "imovel_valido": True,
        "metadados_espaciais": {
            "crs_original": val_result["crs_original"],
            "crs_padronizado": val_result["crs_padronizado"],
            "area_total_ha": area_total,
            "perimetro_m": val_result["perimetro_m"],
            "centroide": val_result["centroide_lat_lon"]
        },
        "diagnostico_bacia": {
            "dentro_da_bacia_pcj": dentro_bacia,
            "cursos_agua_cruzados": overlap_result["cursos_agua_cruzados"]
        },
        "balanco_uso_solo_ha": {
            "area_total_ha": area_total,
            "app_estimada_ha": app_estimada,
            "reserva_legal_referencia_ha": reserva_legal_exigida_ha,
            "area_util_produtiva_ha": overlap_result["area_util_produtiva_ha"]
        },
        "restricoes_uc": ucs,
        "status_geral": overlap_result["status_geral"],
        "alertas": overlap_result["alertas"],
        "recomendacoes_tecnicas": recomendacoes,
        "conclusao_tecnica": conclusao
    }


if __name__ == "__main__":
    sample_path = PROCESSED_DIR / "amostra_propriedade_pcj.geojson"

    if sample_path.exists():
        diagnostico = calculate_environmental_liability(sample_path)
        print("\n=== Teste da Calculadora de Passivos (Dia 5) ===")
        print(f"Status Geral         : {diagnostico['status_geral']}")
        print(f"Área Total           : {diagnostico['balanco_uso_solo_ha']['area_total_ha']} ha")
        print(f"APP Estimada         : {diagnostico['balanco_uso_solo_ha']['app_estimada_ha']} ha")
        print(f"Reserva Legal (20%)  : {diagnostico['balanco_uso_solo_ha']['reserva_legal_referencia_ha']} ha")
        print(f"Área Útil Produtiva  : {diagnostico['balanco_uso_solo_ha']['area_util_produtiva_ha']} ha")
        print(f"Conclusão Técnica    : {diagnostico['conclusao_tecnica']}")
    else:
        print(f"Arquivo de amostra não encontrado em: {sample_path}")