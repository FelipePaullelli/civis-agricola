import sys
from pathlib import Path

# Fix permanente para resolver caminhos independente de como o script é chamado
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

from typing import Union
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm

from backend.app_calculator import calculate_environmental_liability

OUTPUT_DIR = BASE_DIR / "data" / "reports"


def generate_pdf_report(
    file_input: Union[str, Path, bytes],
    filename: str = "",
    output_pdf_path: Path = None,
) -> Path:
    """
    Gera um laudo diagnóstico ambiental em PDF (estilo Sebrae/Embrapa) 
    a partir do polígono da propriedade rural na Bacia PCJ.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if output_pdf_path is None:
        output_pdf_path = OUTPUT_DIR / "laudo_diagnostico_civis_agricola.pdf"

    # Executa o cálculo de passivos ambientais
    diagnostico = calculate_environmental_liability(file_input, filename=filename)
    meta = diagnostico["metadados_espaciais"]
    uso = diagnostico["balanco_uso_solo_ha"]
    bacia = diagnostico["diagnostico_bacia"]

    doc = SimpleDocTemplate(
        str(output_pdf_path),
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    styles = getSampleStyleSheet()

    # Estilos customizados
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=16,
        leading=20,
        textColor=colors.HexColor('#1b5e20'),
        spaceAfter=4,
    )

    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor('#455a64'),
        spaceAfter=12,
    )

    section_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=15,
        textColor=colors.HexColor('#2e7d32'),
        spaceBefore=10,
        spaceAfter=6,
    )

    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.0,
        leading=12.5,
        textColor=colors.HexColor('#263238'),
    )

    bold_normal = ParagraphStyle(
        'CustomBold',
        parent=normal_style,
        fontName='Helvetica-Bold',
    )

    story = []

    # Cabeçalho do Laudo
    story.append(Paragraph("🌱 CIVIS AGRICOLA — LAUDO DIAGNÓSTICO AMBIENTAL", title_style))
    story.append(Paragraph("Sistema de Apoio ao Pequeno Produtor Rural | Bacias Hidrográficas PCJ (SP/MG)", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#2e7d32'), spaceAfter=8))

    # Tabela de Metadados do Imóvel
    meta_data = [
        [Paragraph("<b>Parâmetro Territorial</b>", normal_style), Paragraph("<b>Valor Mapeado / Calculado</b>", normal_style)],
        [Paragraph("Recorte Hidrográfico", normal_style), Paragraph("Bacias PCJ (UGRHI-05)", normal_style)],
        [Paragraph("Sistema Geodésico de Referência", normal_style), Paragraph(f"SIRGAS 2000 ({meta['crs_padronizado']})", normal_style)],
        [Paragraph("Área Total do Imóvel", normal_style), Paragraph(f"<b>{uso['area_total_ha']:.4f} ha</b>", normal_style)],
        [Paragraph("Perímetro Mapeado", normal_style), Paragraph(f"{meta['perimetro_m']:.2f} metros", normal_style)],
        [Paragraph("Centroide (Lat, Lon)", normal_style), Paragraph(f"{meta['centroide'][0]}, {meta['centroide'][1]}", normal_style)],
        [Paragraph("Pertencimento à Bacia PCJ", normal_style), Paragraph("Sim (Dentro do Perímetro Oficial)" if bacia['dentro_da_bacia_pcj'] else "Externo", normal_style)],
    ]
    t_meta = Table(meta_data, colWidths=[7.0 * cm, 11.0 * cm])
    t_meta.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e8f5e9')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#1b5e20')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#c8e6c9')),
    ]))
    story.append(t_meta)
    story.append(Spacer(1, 8))

    # Seção 1: Balanço de Uso do Solo
    story.append(Paragraph("1. Balanço de Uso do Solo e Parâmetros de APP / Reserva Legal", section_style))
    uso_data = [
        [Paragraph("<b>Componente Territorial</b>", normal_style), Paragraph("<b>Área (ha)</b>", normal_style), Paragraph("<b>Observações Técnicas / Legislação</b>", normal_style)],
        [Paragraph("Área Total do Imóvel", normal_style), Paragraph(f"{uso['area_total_ha']:.2f} ha", normal_style), Paragraph("Delimitação declarada no polígono", normal_style)],
        [Paragraph("Área de Preservação Permanente (APP)", normal_style), Paragraph(f"{uso['app_estimada_ha']:.2f} ha", normal_style), Paragraph("Buffer hídrico oficial (Bacia PCJ)", normal_style)],
        [Paragraph("Reserva Legal de Referência (20%)", normal_style), Paragraph(f"{uso['reserva_legal_referencia_ha']:.2f} ha", normal_style), Paragraph("Parâmetro Código Florestal (Bioma SP/MG)", normal_style)],
        [Paragraph("Área Útil / Produtiva Estimada", normal_style), Paragraph(f"{uso['area_util_produtiva_ha']:.2f} ha", normal_style), Paragraph("Potencial para uso agropecuário sustentável", normal_style)],
    ]
    t_uso = Table(uso_data, colWidths=[6.5 * cm, 3.0 * cm, 8.5 * cm])
    t_uso.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e8f5e9')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#1b5e20')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#c8e6c9')),
    ]))
    story.append(t_uso)
    story.append(Spacer(1, 8))

    # Seção 2: Diagnóstico e Conclusão
    story.append(Paragraph("2. Diagnóstico de Conformidade e Conclusão Técnica", section_style))
    status_text = f"<b>Status Geral do Imóvel:</b> {diagnostico['status_geral']}"
    story.append(Paragraph(status_text, bold_normal))
    story.append(Spacer(1, 3))
    story.append(Paragraph(diagnostico['conclusao_tecnica'], normal_style))
    story.append(Spacer(1, 8))

    # Seção 3: Recomendações Práticas
    story.append(Paragraph("3. Recomendações Práticas para Regularização (Sebrae/Embrapa)", section_style))
    for rec in diagnostico['recomendacoes_tecnicas']:
        story.append(Paragraph(f"• {rec}", normal_style))
        story.append(Spacer(1, 2))

    story.append(Spacer(1, 10))

    # Rodapé institucional
    footer_text = (
        "<i>Laudo gerado automaticamente pelo aplicativo Civis Agricola — Ferramenta de apoio técnico "
        "ao produtor rural. Este documento possui caráter preliminar e orientativo, não substituindo "
        "as análises oficiais do SICAR / CAR ou órgãos ambientais competentes.</i>"
    )
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#b0bec5'), spaceAfter=4))
    story.append(Paragraph(footer_text, ParagraphStyle('Footer', parent=normal_style, fontSize=7.0, leading=9.5, textColor=colors.HexColor('#78909c'))))

    doc.build(story)
    return output_pdf_path


if __name__ == "__main__":
    sample_path = BASE_DIR / "data" / "processed" / "samples_pcj" / "piracicaba_uc_app.geojson"
    if not sample_path.exists():
        sample_path = BASE_DIR / "data" / "processed" / "amostra_propriedade_pcj.geojson"

    pdf_gerado = generate_pdf_report(sample_path)
    print("\n=== Teste do Gerador de PDF (Dia 11) ===")
    print(f"PDF salvo em        : {pdf_gerado}")
    print(f"Tamanho do arquivo  : {pdf_gerado.stat().st_size} bytes")
    print("Status              : Laudo PDF gerado com sucesso!")