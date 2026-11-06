"""
Civis Agrícola - Etapa 3: Tradutor Cidadão do Código Florestal (Lei 12.651/2012)
Converte métricas geoespaciais e camadas do CAR (SP, MG e Padrão Federal)
em orientações acessíveis sobre Direitos, Deveres e Benefícios ao Produtor Rural.
100% Software Livre, sem dependências proprietárias.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any


# Tabela de referência de Módulos Fiscais (INCRA) em hectares para municípios das Bacias PCJ, SP, MG e média nacional
MODULO_FISCAL_HA_REF: Dict[str, float] = {
    "PIRACICABA": 10.0,
    "CAMPINAS": 10.0,
    "JUNDIAI": 10.0,
    "BRAGANCA PAULISTA": 12.0,
    "JOANOPOLIS": 16.0,
    "NAZARE PAULISTA": 16.0,
    "RIO CLARO": 12.0,
    "LIMEIRA": 10.0,
    "AMERICANA": 10.0,
    "ATIBAIA": 10.0,
    "EXTREMA": 22.0,
    "CAMANDUCAIA": 26.0,
    "TOLEDO": 22.0,
    "ITAPEVA": 22.0,
    "DEFAULT_SP": 14.0,
    "DEFAULT_MG": 24.0,
    "DEFAULT_BR": 20.0,
}


@dataclass
class CartilhaCidada:
    """Estrutura de saída em linguagem acessível para o aplicativo móvel e painel web."""
    uf: str
    municipio_ref: str
    area_imovel_ha: float
    modulo_fiscal_ha: float
    qtd_modulos_fiscais: float
    classificacao_fundiaria: str
    regime_codigo_florestal: str
    faixa_recomposicao_app_m: int
    exigencia_reserva_legal_pct: float
    isento_recomposicao_rl_art67: bool
    deficit_estimado_app_ha: float
    status_cidadao: str
    resumo_linguagem_simples: str
    seus_direitos: List[str] = field(default_factory=list)
    seus_deveres: List[str] = field(default_factory=list)
    beneficios_destravados: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CitizenForestCodeTranslator:
    """
    Tradutor Cidadão do Código Florestal Brasileiro (Lei Federal nº 12.651/2012).
    Calcula Módulos Fiscais, aplica as regras de áreas consolidadas (Art. 61-A e Art. 67)
    e gera a Cartilha Cidadã de Direitos, Deveres e Acesso a Crédito/PSA.
    """

    def __init__(self, tabela_mf: Optional[Dict[str, float]] = None):
        self.tabela_mf = tabela_mf or MODULO_FISCAL_HA_REF

    def obter_modulo_fiscal_ha(self, uf: str = "SP", municipio: Optional[str] = None) -> float:
        """Retorna o tamanho de 1 Módulo Fiscal (em ha) para o município ou média estadual."""
        if municipio:
            chave_mun = (
                municipio.strip()
                .upper()
                .replace("Á", "A")
                .replace("Ã", "A")
                .replace("Â", "A")
                .replace("É", "E")
                .replace("Ê", "E")
                .replace("Í", "I")
                .replace("Ó", "O")
                .replace("Õ", "O")
                .replace("Ç", "C")
            )
            if chave_mun in self.tabela_mf:
                return self.tabela_mf[chave_mun]

        uf_norm = (uf or "BR").strip().upper()
        return self.tabela_mf.get(f"DEFAULT_{uf_norm}", self.tabela_mf["DEFAULT_BR"])

    @staticmethod
    def calcular_faixa_escadinha_art61a(qtd_mf: float, largura_rio_m: float = 5.0) -> int:
        """
        Aplica a 'Regra da Escadinha' (Art. 61-A da Lei 12.651/2012) para recomposição
        de mata ciliar (APP) em áreas rurais com uso consolidado até 22/07/2008.
        """
        if qtd_mf <= 1.0:
            return 5
        if qtd_mf <= 2.0:
            return 8
        if qtd_mf <= 4.0:
            return 15

        # Acima de 4 Módulos Fiscais (varia conforme largura do curso d'água, mínimo 20m, máximo 100m)
        if largura_rio_m <= 10.0:
            return 20
        return min(100, max(30, int(largura_rio_m / 2.0)))

    def gerar_cartilha(
        self,
        area_imovel_ha: float,
        uf: str = "SP",
        municipio: Optional[str] = None,
        area_app_exigida_ha: float = 0.0,
        area_conflito_app_ha: float = 0.0,
        area_reserva_legal_declarada_ha: float = 0.0,
        possui_uso_consolidado_2008: bool = True,
        largura_rio_m: float = 5.0,
    ) -> CartilhaCidada:
        """
        Gera o diagnóstico jurídico-ambiental traduzido para o produtor rural.
        """
        uf_norm = (uf or "SP").strip().upper()
        mf_ha = self.obter_modulo_fiscal_ha(uf=uf_norm, municipio=municipio)
        qtd_mf = round(max(area_imovel_ha, 0.01) / mf_ha, 2)

        # 1. Classificação Fundiária (Lei 8.629/1993 e Art. 3º, V da Lei 12.651/2012)
        if qtd_mf <= 4.0:
            classificacao = "Pequena Propriedade ou Posse Rural Familiar (Até 4 Módulos Fiscais)"
            pequeno_produtor = True
        elif qtd_mf <= 15.0:
            classificacao = "Média Propriedade Rural (De 4 a 15 Módulos Fiscais)"
            pequeno_produtor = False
        else:
            classificacao = "Grande Propriedade Rural (Acima de 15 Módulos Fiscais)"
            pequeno_produtor = False

        # 2. Enquadramento de APP (Art. 4º vs Art. 61-A - Escadinha)
        if possui_uso_consolidado_2008:
            faixa_app_m = self.calcular_faixa_escadinha_art61a(qtd_mf, largura_rio_m)
            regime = "Regime Especial de Área Consolidada até 22/07/2008 (Art. 61-A e Art. 67)"
            # Fator de redução proporcional na recomposição obrigatória (frente aos 30m padrão)
            fator_reducao = min(1.0, faixa_app_m / 30.0)
            deficit_efetivo_app = round(area_conflito_app_ha * fator_reducao, 4)
        else:
            faixa_app_m = 30 if largura_rio_m <= 10.0 else 50
            regime = "Regime Geral de Proteção Permanente (Art. 4º do Código Florestal)"
            deficit_efetivo_app = round(area_conflito_app_ha, 4)

        # 3. Enquadramento de Reserva Legal (Art. 12 vs Art. 67)
        exigencia_rl_pct = 20.0  # Padrão Mata Atlântica / Cerrado em SP e MG
        isento_rl_art67 = pequeno_produtor and possui_uso_consolidado_2008
        perc_rl_atual = (
            round((area_reserva_legal_declarada_ha / area_imovel_ha) * 100.0, 1)
            if area_imovel_ha > 0
            else 0.0
        )

        # 4. Construção da Cartilha Cidadã (Direitos, Deveres e Benefícios)
        direitos: List[str] = []
        deveres: List[str] = []
        beneficios: List[str] = []

        if pequeno_produtor:
            direitos.append(
                f"Redução da Mata Ciliar (Regra da Escadinha - Art. 61-A): Como seu terreno tem {qtd_mf} "
                f"Módulos Fiscais ({area_imovel_ha:.2f} ha), sua faixa obrigatória de recomposição na beira "
                f"do córrego cai de 30 metros para apenas {faixa_app_m} metros."
            )
            direitos.append(
                "Isenção de Replantio de Reserva Legal (Art. 67): Você não precisa desmatar áreas de plantio "
                "nem comprar terras fora para completar 20% de Reserva Legal; basta manter a mata nativa que "
                "já existia em julho de 2008."
            )
            direitos.append(
                "Apoio Técnico Público Gratuito (Art. 53 e 58): O órgão estadual (CATI/SP ou Emater/MG) tem o "
                "dever legal de prestar assistência técnica gratuita para o seu cadastro no CAR e plano de recomposição."
            )
        else:
            direitos.append(
                f"Continuidade das Atividades Consolidadas (Art. 61-A): Atividades agrossilvipastoris existentes "
                f"antes de 22/07/2008 são respeitadas, com faixa de recomposição ajustada para {faixa_app_m} metros."
            )
            direitos.append(
                "Flexibilidade na Reserva Legal (Art. 66): Caso a mata nativa seja inferior a 20% "
                f"(atual: {perc_rl_atual}%), você pode regularizar por regeneração natural, plantio intercalado "
                "com exóticas ou compensação em outra área do mesmo bioma."
            )

        # Deveres Práticos
        if deficit_efetivo_app > 0.01:
            status_cidadao = "REGULARIZAÇÃO SIMPLIFICADA DISPONÍVEL (PRA)"
            deveres.append(
                f"Proteger e recompor {deficit_efetivo_app:.2f} ha na faixa mínima de {faixa_app_m} metros "
                "ao redor do curso d'água (isolando contra pisoteio de gado ou plantio direto com espécies nativas)."
            )
            deveres.append(
                f"Assinar o Termo de Compromisso do PRA (Programa de Regularização Ambiental) no sistema "
                f"{'SICAR-SP / DataGEO' if uf_norm == 'SP' else ('IDE-Sisema / SICAR-MG' if uf_norm == 'MG' else 'SICAR Federal')}, "
                "o que suspende imediatamente multas antigas durante a recuperação."
            )
        else:
            status_cidadao = "CONFORME — APTO A BENEFÍCIOS VERDES"
            deveres.append(
                f"Manter a faixa de proteção hídrica ({faixa_app_m}m) preservada e atualizar o recibo do CAR "
                "apenas se houver alteração de divisa ou titularidade."
            )

        if not isento_rl_art67 and perc_rl_atual < exigencia_rl_pct:
            deveres.append(
                f"Averbar no CAR a proposta de recomposição ou compensação da Reserva Legal para atingir a meta de {exigencia_rl_pct:.0f}%."
            )

        # Benefícios Destravados
        if pequeno_produtor:
            beneficios.append(
                "Pronaf Floresta e Pronaf ABC+ Agroecologia: Linhas de crédito rural com juros subsidiados e "
                "carência estendida para financiar mudas, cercamento e sistemas agroflorestais (SAFs)."
            )
        beneficios.append(
            "Desconto no Juro do Crédito Rural (Resolução CMN/BCB): Propriedades com CAR validado e sem "
            "passivo ambiental ganham redução de até 0,5 ponto percentual nas taxas do Plano Safra."
        )
        beneficios.append(
            "Pagamento por Serviços Ambientais (PSA Águas PCJ / Produtor de Água): Elegibilidade para receber "
            "remuneração financeira anual por hectare de nascente e mata ciliar conservada ou em restauração."
        )

        resumo = (
            f"Imóvel classificado como {classificacao} ({area_imovel_ha:.2f} ha = {qtd_mf} MF). "
            f"Pelo Código Florestal, sua faixa exigida de mata ciliar é de {faixa_app_m}m. "
            f"Situação atual: {status_cidadao}."
        )

        return CartilhaCidada(
            uf=uf_norm,
            municipio_ref=municipio or f"Média Estadual ({uf_norm})",
            area_imovel_ha=round(area_imovel_ha, 4),
            modulo_fiscal_ha=mf_ha,
            qtd_modulos_fiscais=qtd_mf,
            classificacao_fundiaria=classificacao,
            regime_codigo_florestal=regime,
            faixa_recomposicao_app_m=faixa_app_m,
            exigencia_reserva_legal_pct=0.0 if isento_rl_art67 else exigencia_rl_pct,
            isento_recomposicao_rl_art67=isento_rl_art67,
            deficit_estimado_app_ha=deficit_efetivo_app,
            status_cidadao=status_cidadao,
            resumo_linguagem_simples=resumo,
            seus_direitos=direitos,
            seus_deveres=deveres,
            beneficios_destravados=beneficios,
        )


if __name__ == "__main__":
    tradutor = CitizenForestCodeTranslator()

    # Cenário 1: Agricultura Familiar na Bacia PCJ (Piracicaba/SP - 8.5 ha -> 0.85 MF)
    c1 = tradutor.gerar_cartilha(
        area_imovel_ha=8.5,
        uf="SP",
        municipio="Piracicaba",
        area_app_exigida_ha=1.2,
        area_conflito_app_ha=0.6,
        area_reserva_legal_declarada_ha=0.4,
        possui_uso_consolidado_2008=True,
    )

    # Cenário 2: Sítio em Minas Gerais na cabeceira do PCJ (Extrema/MG - 55 ha -> 2.5 MF)
    c2 = tradutor.gerar_cartilha(
        area_imovel_ha=55.0,
        uf="MG",
        municipio="Extrema",
        area_app_exigida_ha=4.5,
        area_conflito_app_ha=0.0,
        area_reserva_legal_declarada_ha=6.0,
        possui_uso_consolidado_2008=True,
    )

    # Cenário 3: Média Propriedade Paulista (113.887 ha em Piracicaba -> 11.39 MF)
    c3 = tradutor.gerar_cartilha(
        area_imovel_ha=113.887,
        uf="SP",
        municipio="Piracicaba",
        area_app_exigida_ha=8.0,
        area_conflito_app_ha=1.5,
        area_reserva_legal_declarada_ha=12.0,
        possui_uso_consolidado_2008=True,
    )

    print("\n=== Teste do Tradutor Cidadão do Código Florestal (Etapa 3) ===")
    print(f"[Cenário 1 - Sítio Familiar SP] : {c1.area_imovel_ha} ha ({c1.qtd_modulos_fiscais} MF) | Escadinha APP: {c1.faixa_recomposicao_app_m}m | Isento RL Art.67: {c1.isento_recomposicao_rl_art67}")
    print(f"                                  Status: {c1.status_cidadao} | Déficit Ajustado: {c1.deficit_estimado_app_ha} ha")
    print(f"[Cenário 2 - Cabec. PCJ MG]     : {c2.area_imovel_ha} ha ({c2.qtd_modulos_fiscais} MF) | Escadinha APP: {c2.faixa_recomposicao_app_m}m | Isento RL Art.67: {c2.isento_recomposicao_rl_art67}")
    print(f"                                  Status: {c2.status_cidadao}")
    print(f"[Cenário 3 - Média Prop. SP]    : {c3.area_imovel_ha} ha ({c3.qtd_modulos_fiscais} MF) | Escadinha APP: {c3.faixa_recomposicao_app_m}m | Isento RL Art.67: {c3.isento_recomposicao_rl_art67}")
    print(f"                                  Status: {c3.status_cidadao} | Déficit Ajustado: {c3.deficit_estimado_app_ha} ha")
    print("Status                          : Motor jurídico-ambiental e Cartilha Cidadã validados com sucesso!")