
# AI News Intelligence Pipeline

> Automated AI news aggregation, summarization, classification and scheduled publishing.
> Um pipeline completo, determinístico e pronto para produção para coleta, curadoria e distribuição de notícias sobre Inteligência Artificial.


## Visão Geral

Este projeto implementa um **pipeline end-to-end de inteligência de notícias de IA**, capaz de:

- Coletar notícias diariamente de múltiplas fontes confiáveis (RSS e HTML)
- Normalizar, resumir e classificar conteúdos automaticamente
- Deduplicar informações redundantes
- Gerar um **digest editorial** em Markdown e JSON
- Atualizar e sobrescrever o conteúdo diariamente
- Publicar notícias de forma **escalonada ao longo do dia** (drip publishing)
- Integrar com Google Drive, cron Linux e n8n

O foco do projeto é **robustez, previsibilidade e baixo acoplamento**, evitando dependência excessiva de LLMs para o core do sistema.

---

## Objetivos do Estudo

Este projeto foi desenvolvido como um **estudo prático de engenharia de dados e automação**, com os seguintes objetivos:

- Criar um agregador de notícias **realmente utilizável em produção**
- Evitar scraping agressivo ou práticas frágeis
- Priorizar RSS sempre que possível
- Tratar bloqueios reais (ex.: HTTP 403)
- Construir um pipeline determinístico (ideal para cron)
- Separar claramente:

  - coleta
  - enriquecimento
  - classificação
  - publicação

---

## Arquitetura Geral

```
[Fontes de Notícias]
        │
        ▼
ai_news_scraper.py
(Coleta RSS + HTML)
        │
        ▼
ai_news.json
        │
        ▼
run_pipeline.py
 ├─ Passo 2: Resumo
 ├─ Passo 3: Classificação
 ├─ Passo 1: Deduplicação
 └─ Passo 4: Digest
        │
        ▼
ai_digest.md / ai_digest.json
        │
        ▼
Google Drive (Update File)
        │
        ▼
n8n (Drip Publishing)
```

---

## Fontes de Dados

### RSS (prioritário)

- OpenAI News
- arXiv (cs.AI)
- VentureBeat

### HTML (best-effort)

- TechCrunch (AI)
- The Verge (AI)
- Google DeepMind Blog

> O projeto **não tenta contornar bloqueios**. Quando uma fonte bloqueia scraping (ex.: OpenAI com 403), o sistema usa **fallback limpo via RSS**.

---

## Componentes do Projeto

### `ai_news_scraper.py`

Responsável pela **coleta bruta** das notícias.

- RSS-first
- HTML apenas quando necessário
- Timeouts, limites e logs estruturados
- Saída única: `ai_news.json`

---

### `run_pipeline.py` (orquestrador)

Executa todo o fluxo de forma sequencial:

#### Passo 2 — Resumo

- Resumo curto e factual
- Estratégias:

  - RSS summary (OpenAI)
  - Abstract (arXiv)
  - Meta description / OG / primeiro parágrafo (HTML)

- Correção automática de encoding (`â`, etc.)

#### Passo 3 — Classificação

Classificação rule-based, sem LLM:

- `product_updates`
- `security_safety`
- `llm_agents_reasoning`
- `research_papers`
- `business_market`
- `policy_society`
- `general_ai_news`

#### Passo 1 — Deduplicação

- Normalização de URL
- Priorização por fonte
- Preferência por itens com resumo

#### Passo 4 — Digest

- Geração de:

  - `ai_digest.md` (humano)
  - `ai_digest.json` (automação)

- Ordenação por data quando disponível

---

## Estrutura de Arquivos

```
ai_news/
├── ai_news_scraper.py
├── run_pipeline.py
├── ai_news.json
├── ai_news_step2_with_summary.json
├── ai_news_step3_classified.json
├── ai_news_step1_deduped.json
├── ai_digest.md
├── ai_digest.json
└── cron.log
```

---

## Automação Diária

### Installation

Esta seção descreve como configurar e executar o projeto localmente de forma segura e reprodutível.

Requisitos:

- Python 3.10+
- Git
- Ambiente Linux ou macOS (recomendado para uso com cron)
- Acesso à internet para coleta das fontes

1. Clone do repositório
   git clone git@github.com:DiogoBispo/ai-news-intelligence-pipeline.git
   cd ai-news-intelligence-pipeline

2. Criação do ambiente virtual
   python3 -m venv .venv
   source .venv/bin/activate

3. Instalação das dependências
   pip install --upgrade pip
   pip install -r requirements.txt

4. Execução manual (teste local)

- Execute primeiro o coletor:

python3 ai_news_scraper.py

- Em seguida, execute o pipeline completo:

python3 run_pipeline.py \
 --timeout-s 15 \
 --sleep-s 0.8 \
 --max-summary-chars 280

- Ao final, os seguintes arquivos serão gerados/atualizados:

ai_digest.md

ai_digest.json

5. Execução automatizada via Bash (recomendado)

- Crie o script daily_run.sh:

```bash
#!/usr/bin/env bash
set -euo pipefail

cd /home/caminho_do_codigo/ai_news

source .venv/bin/activate

python3 ai_news_scraper.py
python3 run_pipeline.py --timeout-s 15 --sleep-s 0.8 --max-summary-chars 280
```

- Torne o script executável:

chmod +x daily_run.sh

\*Esse script pode ser utilizado tanto por cron Linux quanto por n8n (Execute Command).

### Integração com n8n

- Upload diário do `ai_digest.md` para Google Drive (Update File)
- Reset diário da fila de publicação
- Publicação escalonada durante o dia (ex.: a cada 30 min)

---

## Google Drive

- O arquivo é **sobrescrito diariamente**
- Utiliza sempre o mesmo **File ID**
- Mantém o Drive como “fonte viva” do digest atual

---

## Publicação Escalonada (Drip Feed)

- Cada notícia é publicada individualmente
- Intervalos configuráveis
- Canais suportados:

  - Telegram
  - Slack
  - WhatsApp (API)

- Evita flood
- Mantém presença contínua ao longo do dia

---

## Princípios de Engenharia

- Nada de scraping agressivo
- Nada de bypass de segurança
- RSS sempre que possível
- Fallbacks explícitos
- Logs claros
- Código legível
- Pipeline determinístico

---

## Possíveis Extensões

- Google Drive + n8n (Automação e Publicação Programada)
- Upload diário do ai_digest.md para Google Drive via Update File (sobrescrita pelo mesmo File ID).
- Reset diário de uma fila queue_today.json baseada no ai_digest.json.
- Workflow “Drip Publisher” no n8n para publicar notícias (em redes sociais) em intervalos ao longo do dia (ex.: a cada 30 minutos), marcando cada item como postado e garantindo cadência contínua sem flood.
- Score de relevância (“Top AI Today”)
- Digest semanal
- Dashboard
- API pública
- Empacotamento como CLI
- Produto SaaS / newsletter

---

## Conclusão

Este projeto demonstra como construir um **sistema real de inteligência de informação**, indo além de scripts experimentais.

Ele é:

- confiável
- extensível
- pronto para produção leve
- adequado tanto para uso pessoal quanto corporativo

---
