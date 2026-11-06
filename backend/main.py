import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional

# Fix permanente para resolver o ModuleNotFoundError independente de como o script é chamado
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.spatial_validator import SpatialValidationError
from backend.app_calculator import calculate_environmental_liability
from backend.citizen_translator import CitizenForestCodeTranslator
import backend.car_translator as car_translator_module

PROCESSED_DIR = BASE_DIR / "data" / "processed"

SISTEMAS_CAR_UF = {
    "SP": "SICAR-SP / DataGEO (Análise Dinamizada Paulista)",
    "MG": "IDE-Sisema / SICAR-MG (Módulo Estadual Mineiro)",
    "BR": "SICAR Federal (Padrão Nacional Multi-Camadas)",
}

app = FastAPI(
    title="Civis Agricola - API de Consultoria Ambiental e Cidadania Rural",
    description=(
        "API assíncrona 100% Software Livre para validação espacial em SIRGAS 2000, "
        "tradução multi-estado de camadas do CAR (SP, MG, BR), cálculo de passivos "
        "ambientais na Bacia PCJ e geração da Cartilha Cidadã do Código Florestal."
    ),
    version="1.2.0",
)

# Habilita CORS para integração com o frontend em Streamlit e PWA Mobile Offline
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

citizen_translator = CitizenForestCodeTranslator()


def _extrair_metadados_geojson(conteudo_bytes: Optional[bytes], uf_padrao: str = "SP") -> Dict[str, str]:
    """Extrai UF, nome do imóvel e protocolo CAR caso o arquivo enviado seja um GeoJSON do App Mobile."""
    meta = {
        "uf": uf_padrao.upper(),
        "nome_imovel": "Imóvel Rural Analisado",
        "recibo_car": "Não informado",
    }
    if not conteudo_bytes:
        return meta

    try:
        dados = json.loads(conteudo_bytes.decode("utf-8"))
        features = dados.get("features", [])
        if features and isinstance(features[0], dict):
            props = features[0].get("properties") or {}
            if props.get("uf_origem"):
                meta["uf"] = str(props["uf_origem"]).strip().upper()
            elif props.get("uf"):
                meta["uf"] = str(props["uf"]).strip().upper()
            if props.get("nome_imovel"):
                meta["nome_imovel"] = str(props["nome_imovel"]).strip()
            if props.get("recibo_car"):
                meta["recibo_car"] = str(props["recibo_car"]).strip()
    except Exception:
        pass

    return meta


def _anexar_inteligencia_cidada(
    diagnostico: Dict[str, Any],
    conteudo_bytes: Optional[bytes] = None,
    uf: str = "SP",
    municipio: str = "Piracicaba",
) -> Dict[str, Any]:
    """Enriquece o diagnóstico técnico com a tradução do CAR estadual e a Cartilha Cidadã."""
    meta = _extrair_metadados_geojson(conteudo_bytes, uf_padrao=uf)
    uf_final = meta["uf"] if meta["uf"] in ("SP", "MG", "BR") else "BR"

    balanco = diagnostico.get("balanco_uso_solo_ha", {})
    area_total_ha = float(balanco.get("area_total_ha", 0.0))
    app_estimada_ha = float(balanco.get("app_estimada_ha", 0.0))

    cartilha = citizen_translator.gerar_cartilha(
        area_imovel_ha=area_total_ha,
        uf=uf_final,
        municipio=municipio,
        area_app_exigida_ha=app_estimada_ha,
        area_conflito_app_ha=app_estimada_ha,
        area_reserva_legal_declarada_ha=0.0,
        possui_uso_consolidado_2008=True,
    )

    diagnostico["traducao_car"] = {
        "uf": uf_final,
        "sistema_estadual": SISTEMAS_CAR_UF.get(uf_final, SISTEMAS_CAR_UF["BR"]),
        "nome_imovel": meta["nome_imovel"],
        "recibo_car": meta["recibo_car"],
        "modulo_tradutor_ativo": hasattr(car_translator_module, "__file__"),
    }
    diagnostico["cartilha_cidada"] = cartilha.to_dict()

    # Enriquece as recomendações para exibição direta no App Mobile (PWA) e no Painel
    recs = list(diagnostico.get("recomendacoes_tecnicas", []))
    if cartilha.seus_direitos:
        recs.append(f"DIREITO GARANTIDO: {cartilha.seus_direitos[0]}")
    if cartilha.seus_deveres:
        recs.append(f"DEVER PRÁTICO: {cartilha.seus_deveres[0]}")
    if cartilha.beneficios_destravados:
        recs.append(f"CRÉDITO E PSA: {cartilha.beneficios_destravados[0]}")
    diagnostico["recomendacoes_tecnicas"] = recs

    return diagnostico


@app.get("/", tags=["Status"])
async def health_check() -> Dict[str, str]:
    """Verifica se o servidor da API está online e operacional."""
    return {
        "servico": "Civis Agricola API",
        "recorte_espacial": "Bacias Hidrográficas PCJ & Multi-Estado (SP/MG/BR)",
        "crs_padrao": "SIRGAS 2000 (EPSG:4674)",
        "status": "online",
    }


@app.post("/api/v1/analisar", tags=["Diagnóstico Ambiental"])
async def analisar_propriedade(
    arquivo: UploadFile = File(
        ...,
        description="Arquivo espacial da propriedade (.geojson, .json, .kml, .shp ou .zip)",
    ),
    uf: str = "SP",
    municipio: str = "Piracicaba",
) -> Dict[str, Any]:
    """
    Recebe o polígono da propriedade rural, executa a validação geométrica,
    o cruzamento espacial na Bacia PCJ, o cálculo de passivos e a Cartilha Cidadã.
    """
    if not arquivo.filename:
        raise HTTPException(status_code=400, detail="Nome de arquivo inválido ou ausente.")

    try:
        conteudo_bytes = await arquivo.read()
        if not conteudo_bytes:
            raise HTTPException(status_code=400, detail="O arquivo enviado está vazio.")

        diagnostico = calculate_environmental_liability(
            file_input=conteudo_bytes,
            filename=arquivo.filename,
        )
        diagnostico = _anexar_inteligencia_cidada(
            diagnostico=diagnostico,
            conteudo_bytes=conteudo_bytes,
            uf=uf,
            municipio=municipio,
        )
        return {
            "sucesso": True,
            "arquivo_processado": arquivo.filename,
            "resultado": diagnostico,
        }

    except SpatialValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Erro interno ao processar o diagnóstico ambiental: {exc}",
        ) from exc


@app.get("/api/v1/analisar-amostra", tags=["Diagnóstico Ambiental"])
async def analisar_amostra_pcj(uf: str = "SP", municipio: str = "Piracicaba") -> Dict[str, Any]:
    """Executa o diagnóstico completo e gera a Cartilha Cidadã sobre a propriedade de referência na Bacia PCJ."""
    sample_path = PROCESSED_DIR / "amostra_propriedade_pcj.geojson"
    if not sample_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Arquivo de amostra não encontrado em data/processed.",
        )

    diagnostico = calculate_environmental_liability(sample_path)
    diagnostico = _anexar_inteligencia_cidada(
        diagnostico=diagnostico,
        conteudo_bytes=sample_path.read_bytes(),
        uf=uf,
        municipio=municipio,
    )
    return {
        "sucesso": True,
        "arquivo_processado": sample_path.name,
        "resultado": diagnostico,
    }


@app.get("/api/v1/cartilha-cidada", tags=["Cidadania Rural"])
async def consultar_cartilha_cidada(
    area_ha: float = 12.0,
    uf: str = "SP",
    municipio: str = "Piracicaba",
    app_conflito_ha: float = 0.5,
) -> Dict[str, Any]:
    """Gera instantaneamente a Cartilha Cidadã (Direitos, Deveres e Benefícios) para qualquer área rural."""
    cartilha = citizen_translator.gerar_cartilha(
        area_imovel_ha=area_ha,
        uf=uf,
        municipio=municipio,
        area_app_exigida_ha=app_conflito_ha,
        area_conflito_app_ha=app_conflito_ha,
    )
    return {
        "sucesso": True,
        "sistema_car": SISTEMAS_CAR_UF.get(uf.upper(), SISTEMAS_CAR_UF["BR"]),
        "cartilha_cidada": cartilha.to_dict(),
    }


if __name__ == "__main__":
    # Autoteste assíncrono das rotas da API sem precisar abrir um segundo terminal
    async def _run_self_test():
        status_resp = await health_check()
        amostra_resp = await analisar_amostra_pcj()
        res = amostra_resp["resultado"]
        cartilha = res["cartilha_cidada"]

        print("\n=== Teste da API FastAPI Integrada (Etapa 4) ===")
        print(f"Status da API        : {status_resp['status']} ({status_resp['servico']})")
        print(f"Arquivo Processado   : {amostra_resp['arquivo_processado']}")
        print(f"Sistema CAR Detectado: {res['traducao_car']['sistema_estadual']}")
        print(f"Status Técnico       : {res['status_geral']}")
        print(f"Área Total Calculada : {res['balanco_uso_solo_ha']['area_total_ha']} ha ({cartilha['qtd_modulos_fiscais']} Módulos Fiscais)")
        print(f"Enquadramento Legal  : {cartilha['classificacao_fundiaria']}")
        print(f"Escadinha APP (61-A) : {cartilha['faixa_recomposicao_app_m']} metros")
        print(f"Status Cidadão       : {cartilha['status_cidadao']}")

    asyncio.run(_run_self_test())