import asyncio
import sys
from pathlib import Path

# Fix permanente para resolver o ModuleNotFoundError independente de como o script é chamado
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

from typing import Dict, Any
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.spatial_validator import SpatialValidationError
from backend.app_calculator import calculate_environmental_liability

PROCESSED_DIR = BASE_DIR / "data" / "processed"

app = FastAPI(
    title="Civis Agricola - API de Consultoria Ambiental PCJ",
    description=(
        "API assíncrona para validação espacial em SIRGAS 2000, detecção de sobreposições "
        "e cálculo de passivos ambientais (APP, Reserva Legal e UCs) na Bacia PCJ."
    ),
    version="1.0.0",
)

# Habilita CORS para integração futura com o frontend em Streamlit
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["Status"])
async def health_check() -> Dict[str, str]:
    """Verifica se o servidor da API está online e operacional."""
    return {
        "servico": "Civis Agricola API",
        "recorte_espacial": "Bacias Hidrográficas PCJ",
        "crs_padrao": "SIRGAS 2000 (EPSG:4674)",
        "status": "online",
    }


@app.post("/api/v1/analisar", tags=["Diagnóstico Ambiental"])
async def analisar_propriedade(
    arquivo: UploadFile = File(
        ...,
        description="Arquivo espacial da propriedade (.geojson, .json, .kml, .shp ou .zip)",
    )
) -> Dict[str, Any]:
    """
    Recebe o polígono da propriedade rural, executa a validação geométrica (Dia 3),
    o cruzamento espacial na Bacia PCJ (Dia 4) e o cálculo de passivos (Dia 5).
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
async def analisar_amostra_pcj() -> Dict[str, Any]:
    """Executa o diagnóstico sobre a propriedade de referência na Bacia PCJ."""
    sample_path = PROCESSED_DIR / "amostra_propriedade_pcj.geojson"
    if not sample_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Arquivo de amostra não encontrado em data/processed.",
        )

    diagnostico = calculate_environmental_liability(sample_path)
    return {
        "sucesso": True,
        "arquivo_processado": sample_path.name,
        "resultado": diagnostico,
    }


if __name__ == "__main__":
    # Autoteste assíncrono das rotas da API sem precisar abrir um segundo terminal
    async def _run_self_test():
        status_resp = await health_check()
        amostra_resp = await analisar_amostra_pcj()
        res = amostra_resp["resultado"]

        print("\n=== Teste da API FastAPI (Dia 6) ===")
        print(f"Status da API        : {status_resp['status']} ({status_resp['servico']})")
        print(f"Endpoint Testado     : POST /api/v1/analisar (via amostra local)")
        print(f"Arquivo Processado   : {amostra_resp['arquivo_processado']}")
        print(f"Status do Imóvel     : {res['status_geral']}")
        print(f"Área Total Calculada : {res['balanco_uso_solo_ha']['area_total_ha']} ha")
        print(f"APP Estimada         : {res['balanco_uso_solo_ha']['app_estimada_ha']} ha")
        print(f"Reserva Legal (20%)  : {res['balanco_uso_solo_ha']['reserva_legal_referencia_ha']} ha")

    asyncio.run(_run_self_test())