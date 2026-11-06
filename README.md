# 🌱 Civis Agrícola — Consultoria Ambiental e Cidadania Rural

Plataforma geoespacial **100% Software Livre** para validação topológica, tradução multi-estado de camadas do **Cadastro Ambiental Rural (CAR)** e geração automática da **Cartilha Cidadã do Código Florestal Brasileiro (Lei Federal nº 12.651/2012)**, com recorte territorial nas **Bacias Hidrográficas dos Rios Piracicaba, Capivari e Jundiaí (PCJ)** e suporte nacional (**SP, MG e Padrão Federal**).

## 🎯 Propósito do Projeto

Pequenos produtores rurais e agricultores familiares frequentemente enfrentam barreiras técnicas e financeiras para compreender exigências cartográficas e jurídicas do licenciamento ambiental. O **Civis Agrícola** atua como uma ponte cidadã:

1. **Coleta em Campo 100% Offline:** Permite demarcar o perímetro do sítio usando celulares simples e sem conexão à internet via PWA ultra-leve (< 15 KB).
2. **Interoperabilidade Estadual do CAR:** Traduz automaticamente pacotes de diferentes sistemas estaduais (**SICAR-SP / DataGEO**, **IDE-Sisema / SICAR-MG** e **SICAR Federal**) para um modelo canônico em **SIRGAS 2000 (EPSG:4674)** e cálculo métrico em **UTM (EPSG:31983)**.
3. **Tradução Jurídica Cidadã:** Converte geometrias e passivos de APP/Reserva Legal em orientações claras divididas em **Seus Direitos** (Regra da Escadinha do Art. 61-A e isenção de Reserva Legal do Art. 67), **Seus Deveres** (adesão ao PRA) e **Benefícios Destravados** (Pronaf Floresta, Pronaf ABC+ e Pagamento por Serviços Ambientais — PSA).

## 🏗️ Arquitetura e Módulos (Etapas 1 a 5)

* **Etapa 1 — App Mobile PWA Offline-First (pasta mobile):** Aplicação web progressiva em HTML5, CSS e JavaScript puro (Vanilla JS), sem dependências externas. Inclui renderização vetorial em Canvas 2D sem exigir imagens de satélite, leitura do chip GPS nativo offline, cache via Service Worker e fila de sincronização em LocalStorage.
* **Etapa 2 — Tradutor Unificado de Camadas do CAR (backend/car_translator.py):** Motor de harmonização semântica e reprojeção cartográfica que converte nomenclaturas estaduais distintas (São Paulo, Minas Gerais e União) para camadas padronizadas de imóvel, APP, Reserva Legal, vegetação nativa e uso consolidado.
* **Etapa 3 — Tradutor Cidadão do Código Florestal (backend/citizen_translator.py):** Motor de regras socioambientais que calcula o porte do imóvel em **Módulos Fiscais (INCRA)**, aplica as faixas reduzidas de recomposição ciliar (5m, 8m, 15m ou 20m+) e estrutura a Cartilha Cidadã.
* **Etapa 4 — API Geoespacial Assíncrona (backend/main.py):** Backend em FastAPI que integra validação geométrica, cruzamento espacial com hidrografia e Unidades de Conservação da Bacia PCJ, cálculo de passivos ambientais e emissão de diagnósticos JSON e PDF.
* **Etapa 5 — Painel Interativo de Consultoria (frontend/app.py):** Interface em Streamlit e Folium com mapas multicamadas dos 78 municípios das Bacias PCJ (73 em SP e 5 em MG), seletor multi-estado do CAR, painel da Cartilha Cidadã e geração de laudo técnico em PDF.

## 📂 Estrutura do Repositório

```text
civis-agricola/
├── backend/
│   ├── app_calculator.py       # Cálculo de passivos de APP e Reserva Legal em UTM
│   ├── car_translator.py       # Etapa 2: Tradutor multi-estado de camadas do CAR (SP/MG/BR)
│   ├── citizen_translator.py   # Etapa 3: Motor jurídico-ambiental e Cartilha Cidadã
│   ├── main.py                 # Etapa 4: API FastAPI integrada
│   ├── overlap_detector.py     # Cruzamento espacial com hidrografia e UCs (Bacia PCJ)
│   ├── report_generator.py     # Geração automatizada de Laudo Técnico em PDF
│   ├── spatial_validator.py    # Validação topológica e padronização SIRGAS 2000
│   └── test_backend.py         # Bateria de testes unitários e de integração
├── data/
│   └── processed/              # Camadas vetoriais padronizadas (EPSG:4674) e amostras PCJ
├── frontend/
│   ├── assets/                 # Identidade visual do projeto
│   └── app.py                  # Etapa 5: Painel web interativo (Streamlit + Folium)
├── mobile/
│   ├── index.html              # Etapa 1: Interface PWA leve + Canvas 2D + GPS Offline
│   ├── manifest.json           # Manifesto de instalação na tela inicial do celular
│   └── sw.js                   # Service Worker para operação sem sinal de internet
├── compose.yaml                # Orquestração de containers (API + Web + Mobile PWA)
├── Containerfile               # Imagem base para execução em Podman
└── requirements.txt            # Dependências Python 100% abertas