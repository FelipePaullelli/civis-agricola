import asyncio
import io
import sys
from pathlib import Path

# Fix permanente para resolver o ModuleNotFoundError independente de como o script é chamado
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

import geopandas as gpd
from fastapi import HTTPException, UploadFile
from shapely.geometry import LineString, Polygon

from backend.main import analisar_propriedade, health_check

SAMPLES_DIR = BASE_DIR / "data" / "processed" / "samples_pcj"


def generate_pcj_test_polygons() -> dict[str, Path]:
    """
    Cria polígonos fictícios de propriedades rurais em Piracicaba, Jundiaí e Limeira
    para validar diferentes cenários ambientais na Bacia PCJ.
    """
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

    cenarios = {
        "piracicaba_uc_app": {
            "nome": "Sítio Tanquã (Piracicaba - APP + UC)",
            "municipio": "Piracicaba",
            "geometry": Polygon([
                (-47.7820, -22.6820),
                (-47.7720, -22.6820),
                (-47.7720, -22.6740),
                (-47.7820, -22.6740),
                (-47.7820, -22.6820),
            ]),
        },
        "jundiai_app": {
            "nome": "Chácara Vale do Jundiaí (Jundiaí - Com APP)",
            "municipio": "Jundiaí",
            "geometry": Polygon([
                (-46.9840, -23.1730),
                (-46.9760, -23.1730),
                (-46.9760, -23.1670),
                (-46.9840, -23.1670),
                (-46.9840, -23.1730),
            ]),
        },
        "limeira_regular": {
            "nome": "Fazenda Boa Vista (Limeira - Sem Restrições)",
            "municipio": "Limeira",
            "geometry": Polygon([
                (-47.4080, -22.5680),
                (-47.4000, -22.5680),
                (-47.4000, -22.5600),
                (-47.4080, -22.5600),
                (-47.4080, -22.5680),
            ]),
        },
    }

    caminhos = {}
    for chave, dados in cenarios.items():
        gdf = gpd.GeoDataFrame([dados], crs="EPSG:4326")
        out_path = SAMPLES_DIR / f"{chave}.geojson"
        gdf.to_file(out_path, driver="GeoJSON")
        caminhos[chave] = out_path

    return caminhos


async def _call_api_with_file(filepath: Path) -> dict:
    """Simula o envio multipart de arquivo para o endpoint POST /api/v1/analisar."""
    raw_bytes = filepath.read_bytes()
    upload = UploadFile(filename=filepath.name, file=io.BytesIO(raw_bytes))
    return await analisar_propriedade(arquivo=upload)


async def run_backend_validation_suite():
    print("\n=== Bateria de Testes Unitários do Backend (Dia 7 - Fechamento Semana 1) ===")

    # 1. Teste de Health Check
    status = await health_check()
    assert status["status"] == "online", "Falha no health check da API."
    print("[OK] 1. Health Check da API operacional.")

    # 2. Geração dos polígonos de teste na Bacia PCJ
    caminhos = generate_pcj_test_polygons()
    print(f"[OK] 2. Polígonos gerados em {SAMPLES_DIR.relative_to(BASE_DIR)}: {list(caminhos.keys())}")

    # 3. Teste Cenário Piracicaba (Deve detectar Bacia PCJ, APP do Rio Piracicaba e UC APA Tanquã)
    resp_pira = await _call_api_with_file(caminhos["piracicaba_uc_app"])
    res_pira = resp_pira["resultado"]
    assert res_pira["diagnostico_bacia"]["dentro_da_bacia_pcj"] is True
    assert res_pira["balanco_uso_solo_ha"]["app_estimada_ha"] > 0
    assert len(res_pira["restricoes_uc"]) >= 1
    assert res_pira["status_geral"] == "Requer Verificação Técnico-Especializada"
    print(
        f"[OK] 3. Cenário Piracicaba : Área={res_pira['balanco_uso_solo_ha']['area_total_ha']} ha | "
        f"APP={res_pira['balanco_uso_solo_ha']['app_estimada_ha']} ha | "
        f"UCs={len(res_pira['restricoes_uc'])} | Status='{res_pira['status_geral']}'"
    )

    # 4. Teste Cenário Jundiaí (Deve detectar Bacia PCJ, APP do Rio Jundiaí e zero UC)
    resp_jund = await _call_api_with_file(caminhos["jundiai_app"])
    res_jund = resp_jund["resultado"]
    assert res_jund["diagnostico_bacia"]["dentro_da_bacia_pcj"] is True
    assert res_jund["balanco_uso_solo_ha"]["app_estimada_ha"] > 0
    assert len(res_jund["restricoes_uc"]) == 0
    assert res_jund["status_geral"] == "Regular / Em Análise"
    print(
        f"[OK] 4. Cenário Jundiaí    : Área={res_jund['balanco_uso_solo_ha']['area_total_ha']} ha | "
        f"APP={res_jund['balanco_uso_solo_ha']['app_estimada_ha']} ha | "
        f"UCs={len(res_jund['restricoes_uc'])} | Status='{res_jund['status_geral']}'"
    )

    # 5. Teste Cenário Limeira (Deve detectar Bacia PCJ, zero APP principal e zero UC)
    resp_lim = await _call_api_with_file(caminhos["limeira_regular"])
    res_lim = resp_lim["resultado"]
    assert res_lim["diagnostico_bacia"]["dentro_da_bacia_pcj"] is True
    assert res_lim["balanco_uso_solo_ha"]["app_estimada_ha"] == 0.0
    assert len(res_lim["restricoes_uc"]) == 0
    assert res_lim["status_geral"] == "Regular / Em Análise"
    print(
        f"[OK] 5. Cenário Limeira    : Área={res_lim['balanco_uso_solo_ha']['area_total_ha']} ha | "
        f"APP={res_lim['balanco_uso_solo_ha']['app_estimada_ha']} ha | "
        f"UCs={len(res_lim['restricoes_uc'])} | Status='{res_lim['status_geral']}'"
    )

    # 6. Teste de Rejeição de Geometria Inválida (Linha aberta em vez de Polígono fechado)
    gdf_invalido = gpd.GeoDataFrame(
        [{"nome": "Linha Inválida", "geometry": LineString([(-47.65, -22.71), (-47.64, -22.72)])}],
        crs="EPSG:4326",
    )
    bytes_invalidos = gdf_invalido.to_json().encode("utf-8")
    upload_invalido = UploadFile(filename="invalido.geojson", file=io.BytesIO(bytes_invalidos))

    erro_capturado = False
    try:
        await analisar_propriedade(arquivo=upload_invalido)
    except HTTPException as exc:
        assert exc.status_code == 422
        erro_capturado = True

    assert erro_capturado is True, "A API deveria ter rejeitado uma geometria aberta com código 422."
    print("[OK] 6. Validação de Erro  : Geometria aberta bloqueada corretamente (HTTP 422).")
    print("\nSucesso! Todos os testes do Backend da Semana 1 passaram sem erros.")


if __name__ == "__main__":
    asyncio.run(run_backend_validation_suite())