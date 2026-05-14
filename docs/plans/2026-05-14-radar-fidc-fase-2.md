# Radar FIDC — Fase 2 (Trust Layer) — Plano de Implementação

> **Para agentes:** SUB-SKILL OBRIGATÓRIA: use `ring:executing-plans` para executar este plano tarefa por tarefa.

**Objetivo:** Implementar a Trust Layer (Seções 4, 6, 7 e 8 da spec) — validação pandera por DataFrame, manifesto `data-quality.json`, regression check entre runs, smoke tests Playwright, CI hardenizado e indicadores de confiança no frontend — mantendo `data.json` schema-compatível e arquitetura estática (GitHub Pages).

**Arquitetura:** Camada de validação em 3 linhas de defesa (GE no Databricks — quando disponível, defensivo —, pandera no CI, regression check vs HEAD~1). Manifesto `data-quality.json` publicado lado-a-lado com `data.json` e consumido pelo frontend (trust bar sticky + heuristic markers inline). Workflows separados em `ci.yml` (PR/push), `data-refresh.yml` (cron diário) e `notify-failures.yml` (reaction).

**Stack:** Python 3.11 (pandera, pytest, mypy, ruff, responses), HTML+JS vanilla (sem framework), Playwright (Node 20, TypeScript), GitHub Actions, Azure Data Lake Gen2 (`dfdatalakesprint/gold/final/`).

**Pré-requisitos globais:**
- Ambiente: macOS/Linux, Python 3.11, Node 20, Git
- Ferramentas: `python --version`, `node --version`, `npm --version`, `git --version`, `gh --version`
- Acesso: `.env` com `AZURE_CONNECTION_STRING` válida (apenas para validação local opcional; CI usa o GitHub Secret)
- Estado: branch `main` checkout, working tree limpo, Fase 0+1 mergeada (commits até `873273e`)

**Verificação antes de começar:**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
python --version       # Esperado: Python 3.11.x
node --version         # Esperado: v20.x
npm --version          # Esperado: 10.x
git status             # Esperado: working tree clean, branch main
ls scripts/lib/        # Esperado: azure_io.py, gold_paths.py, io_utils.py, logger.py presentes
cat data.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(list(d.keys()))"
# Esperado: ['generated_at', 'config', 'macro', 'fidcs', 'clientes', 'matches', 'credit']
```

**Princípios de execução:**
- DRY, YAGNI, TDD (vermelho → verde → refactor → commit)
- Tarefas de 2-5 minutos com paths absolutos e código completo
- Cada arquivo novo tem teste antes da implementação (quando aplicável)
- Sem TODO órfão; toda dívida tem owner e data
- Idempotência: rodar uma tarefa 2x não muda o estado final

---

## Resumo das fases internas

| Bloco | Tarefas | O que entrega |
|-------|---------|---------------|
| A. Bootstrap de tooling | T01–T04 | `pyproject.toml`, `requirements-dev.txt`, estrutura `scripts/tests/` |
| B. Schemas pandera | T05–T11 | `lib/schemas.py` + integração em `io_utils.py` |
| C. Regression check | T12–T14 | `lib/regression_check.py` + testes |
| D. Trust manifest | T15–T18 | `lib/trust_manifest.py` + integração no generator |
| E. PII regressivo | T19 | `test_formatters_mask.py` end-to-end |
| **F. Code review checkpoint** | **T20** | 7 reviewers paralelos |
| G. CI workflow | T21–T23 | `.github/workflows/ci.yml` |
| H. Notify failures | T24 | `.github/workflows/notify-failures.yml` |
| I. Playwright smoke | T25–T29 | `package.json`, `playwright.config.ts`, specs |
| J. Refresh workflow hardening | T30–T33 | `data-refresh.yml` atualizado |
| **K. Code review checkpoint** | **T34** | 7 reviewers paralelos |
| L. Frontend trust components | T35–T41 | CSS, JS componentes, integração |
| M. Frontend heuristic & empty state | T42–T44 | Markers em macro.js + empty state em match.js |
| N. Acessibilidade | T45 | ARIA + cores não-só-cor |
| O. Documentação operacional | T46–T49 | `runbook.md`, `limitacoes_atuais.md`, `operacao.md`, `update_operacao_doc.py` |
| **P. Code review final** | **T50** | 7 reviewers + smoke E2E manual |

Total: 50 tarefas.

---

## Bloco A — Bootstrap de tooling

### Tarefa T01 — Criar `requirements-dev.txt`

**Arquivos:**
- Criar: `/Users/victorbraga/Downloads/radar-fidc/requirements-dev.txt`

**Pré-requisitos:**
- `requirements.txt` existente com `pandera>=0.18.0`

**Passo 1: Criar arquivo com dependências de dev**

Conteúdo exato:

```
# Radar FIDC — Dependências de desenvolvimento (CI + local)
# Instalar com: pip install -r requirements-dev.txt
# Não usado em runtime — só em PR/push checks e testes locais.

-r requirements.txt

# Testes
pytest>=8.0.0
pytest-mock>=3.12.0
responses>=0.25.0           # mock de requests HTTP (azure SDK usa requests)

# Lint + format + types
ruff>=0.4.10
mypy>=1.10.0
types-requests>=2.31.0
pandas-stubs>=2.0.0
```

**Passo 2: Verificar instalação**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
python -m venv .venv-fase2
source .venv-fase2/bin/activate
pip install --upgrade pip
pip install -r requirements-dev.txt
```

**Saída esperada:** `Successfully installed ... pytest-8.x pytest-mock-3.x responses-0.25.x ruff-0.4.x mypy-1.x ...`

**Passo 3: Commit**

```bash
git add requirements-dev.txt
git commit -m "chore: Add requirements-dev.txt with pytest, ruff, mypy"
```

**Se falhar:**
- `pip install` falha por conflito de versões → checar `requirements.txt`, alinhar versões; rollback `git checkout -- requirements-dev.txt`
- venv não cria → checar `python --version` (precisa 3.11)

---

### Tarefa T02 — Criar `pyproject.toml` com ruff/mypy/pytest

**Arquivos:**
- Criar: `/Users/victorbraga/Downloads/radar-fidc/pyproject.toml`

**Pré-requisitos:**
- T01 concluída

**Passo 1: Criar `pyproject.toml`**

Conteúdo exato:

```toml
# Radar FIDC — Configuração de tooling Python.
# Fonte única para ruff (lint+format), mypy (types) e pytest (test runner).

[project]
name = "radar-fidc"
version = "0.0.0"
description = "Radar FIDC — geração do data.json a partir do ADLS Gen2"
requires-python = ">=3.11"

[tool.ruff]
line-length = 120
target-version = "py311"
src = ["scripts"]
extend-exclude = [".cache", ".venv*", "notebooks", "tests/e2e"]

[tool.ruff.lint]
select = [
  "E",   # pycodestyle
  "F",   # pyflakes
  "I",   # isort
  "UP",  # pyupgrade
  "B",   # flake8-bugbear
  "SIM", # flake8-simplify
  "RUF", # ruff-specific
]
ignore = [
  "E501",   # line-too-long — controlado por formatter
  "B008",   # function call in default arg — comum em Click/FastAPI
]

[tool.ruff.lint.per-file-ignores]
"scripts/tests/*" = ["S101"]  # assert é permitido em testes

[tool.mypy]
python_version = "3.11"
strict = true
warn_unused_ignores = true
warn_redundant_casts = true
disallow_untyped_decorators = false
files = ["scripts/lib"]
exclude = ["scripts/tests/", "notebooks/", ".cache/", ".venv.*"]

[[tool.mypy.overrides]]
module = [
  "pandera.*",
  "pandas.*",
  "azure.*",
  "openpyxl.*",
  "dotenv",
]
ignore_missing_imports = true

[tool.pytest.ini_options]
minversion = "8.0"
testpaths = ["scripts/tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = [
  "-ra",
  "--strict-markers",
  "--strict-config",
  "-q",
]
filterwarnings = [
  "error",
  "ignore::DeprecationWarning:pandera.*",
  "ignore::DeprecationWarning:pandas.*",
]
```

**Passo 2: Verificar ruff e mypy reconhecem a config**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
ruff check scripts/lib/
mypy --version
```

**Saída esperada:**
```
All checks passed!
mypy 1.x.x (compiled: yes)
```

**Passo 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: Configure ruff, mypy and pytest via pyproject.toml"
```

**Se falhar:**
- `ruff check` reporta erros existentes → não bloqueia, anotar em T20; mas verificar se T05+ não introduz novos
- mypy reclama de imports → garantir `ignore_missing_imports = true` para as libs sem stubs

---

### Tarefa T03 — Criar diretório de testes

**Arquivos:**
- Criar: `/Users/victorbraga/Downloads/radar-fidc/scripts/tests/__init__.py` (vazio)
- Criar: `/Users/victorbraga/Downloads/radar-fidc/scripts/tests/conftest.py`

**Pré-requisitos:**
- T02 concluída

**Passo 1: Criar `__init__.py` vazio**

Conteúdo: arquivo vazio (zero bytes).

**Passo 2: Criar `conftest.py`**

Conteúdo exato:

```python
"""Fixtures compartilhadas entre testes.

- `monkey_env`: limpa env vars sensíveis antes de cada teste
- `disable_azure_real`: garante que nenhum teste bate em ADLS de verdade
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Permite `from lib.* import ...` dentro dos testes sem instalar o pacote.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture(autouse=True)
def _isolate_azure_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove credenciais reais do ambiente do teste por segurança."""
    for key in ("AZURE_CONNECTION_STRING", "AZURE_STORAGE_KEY"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def fake_etag() -> str:
    return '"0x8DB000000000000"'
```

**Passo 3: Rodar pytest vazio para validar config**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
source .venv-fase2/bin/activate
pytest -q
```

**Saída esperada:**
```
no tests ran in 0.0xs
```

**Passo 4: Commit**

```bash
git add scripts/tests/__init__.py scripts/tests/conftest.py
git commit -m "test: Bootstrap pytest with conftest and sys.path fixture"
```

**Se falhar:**
- `ModuleNotFoundError: pytest` → instalar `requirements-dev.txt` (T01)
- pytest reclama de `filterwarnings = error` → garantir versão pandera>=0.18

---

### Tarefa T04 — Atualizar `.gitignore` para artefatos de teste

**Arquivos:**
- Modificar: `/Users/victorbraga/Downloads/radar-fidc/.gitignore`

**Pré-requisitos:**
- T03 concluída

**Passo 1: Adicionar entradas ao final do `.gitignore`**

Inserir após a linha 50 (`logs/`), antes do EOF:

```
# Test / coverage / type-check artifacts
.pytest_cache/
.mypy_cache/
.ruff_cache/
htmlcov/
.coverage
coverage.xml

# Node (Playwright)
node_modules/
playwright-report/
test-results/

# Trust manifest output (gerado pelo pipeline; commitado lado-a-lado com data.json)
# (NÃO ignorar data-quality.json — entra no git como artefato do build)
```

**Passo 2: Verificar**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
grep -E "pytest_cache|node_modules" .gitignore
```

**Saída esperada:** ambas as entradas listadas.

**Passo 3: Commit**

```bash
git add .gitignore
git commit -m "chore: Ignore pytest, mypy, ruff and Playwright artifacts"
```

**Se falhar:**
- Conflito com regra existente → revisar manualmente o `.gitignore` e remover duplicatas

---

## Bloco B — Schemas pandera

### Tarefa T05 — Inspecionar colunas reais dos artefatos do Gold

**Arquivos:**
- Nenhum (somente leitura)

**Pré-requisitos:**
- Fase 1 mergeada; `.cache/` populado OU `AZURE_CONNECTION_STRING` no `.env`

**Passo 1: Listar colunas dos DataFrames atuais**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
source .venv-fase2/bin/activate
python - <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, str(Path("scripts").resolve()))
from lib import io_utils
geral, resumo = io_utils.read_rating()
todos, ranking = io_utils.read_matches()
print("rating.GERAL:", list(geral.columns))
print("rating.RESUMO:", list(resumo.columns))
print("matches.TODOS:", list(todos.columns))
print("matches.RANKING:", list(ranking.columns))
print("clientes:", list(io_utils.read_clientes().columns))
print("credit:", list(io_utils.read_credit_scores().columns))
print("macro:", list(io_utils.read_macro().columns))
PY
```

**Saída esperada:** listas com colunas esperadas (CNPJ, FUNDO, SCORE_RISCO, ..., para rating; cpf, nome, perfil para clientes; selic_meta, cdi_diario, ipca_mensal para macro; id_cnpj, score_credito para credit).

**Passo 2: Anotar exatamente as colunas em `/tmp/cols-fase2.txt`** (referência para T06).

**Passo 3: Sem commit** (passo investigativo).

**Se falhar:**
- `AzureMissingConnectionString` → rodar `cp .env.example .env` e preencher; ou usar `.cache/` populado pela Fase 1
- DataFrames vazios → checar se Databricks rodou hoje; consultar `gold/final/` no portal Azure

---

### Tarefa T06 — Escrever testes vermelhos para `RatingGeralSchema` e `RatingResumoSchema`

**Arquivos:**
- Criar: `/Users/victorbraga/Downloads/radar-fidc/scripts/tests/test_schemas.py`

**Pré-requisitos:**
- T03, T05 concluídas

**Passo 1: Escrever teste falhando**

Conteúdo inicial (será expandido em T07/T08/T09):

```python
"""Testes dos schemas pandera de `lib.schemas`.

TDD: cada schema tem (a) DataFrame válido que passa, (b) DataFrame inválido
em pelo menos 2 dimensões que falha com mensagem identificável.

Para isolar schema drift, esses testes NÃO batem no ADLS — usam fixtures
sintéticas que replicam a forma do Gold.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pandera as pa
import pytest


@pytest.fixture
def rating_geral_valid() -> pd.DataFrame:
    return pd.DataFrame({
        "CNPJ": ["12.345.678/0001-90", "98.765.432/0001-10"],
        "FUNDO": ["FIDC ABC", "FIDC XYZ"],
        "TIPO_COTA": ["UNICA", "JUNIOR"],
        "SCORE_RISCO": [42.5, 78.0],
        "RISCO": ["BAIXO", "MEDIO"],
        "CATEGORIA_RISCO": ["BAIXO", "MEDIO"],
        "PERFIL_SUGERIDO": ["CONSERVADOR", "MODERADO"],
        "RETORNO_ANUAL": [12.3, 18.5],
        "VOLATILIDADE": [3.0, 7.0],
        "RETORNO_AJ_RISCO": [4.1, 2.6],
        "TAXA_INADIMPLENCIA": [1.2, 4.5],
        "SCR_NORMALIZADO": [0.5, 0.7],
        "CONC_MAIOR_CEDENTE": [25.0, 40.0],
        "CONC_TOP3": [55.0, 70.0],
        "MESES_HISTORICO": [12, 24],
    })


@pytest.fixture
def rating_resumo_valid() -> pd.DataFrame:
    return pd.DataFrame({
        "CNPJ": ["12.345.678/0001-90"],
        "FUNDO": ["FIDC ABC"],
        "SCORE_RISCO": [42.5],
        "RISCO": ["BAIXO"],
        "RETORNO_MEDIO": [12.3],
        "MELHOR_COTA": ["UNICA"],
        "PERFIL_PREDOMINANTE": ["CONSERVADOR"],
    })


class TestRatingGeralSchema:
    def test_valid_df_passes(self, rating_geral_valid: pd.DataFrame) -> None:
        from lib.schemas import RatingGeralSchema
        RatingGeralSchema.validate(rating_geral_valid, lazy=True)

    def test_score_above_100_fails(self, rating_geral_valid: pd.DataFrame) -> None:
        from lib.schemas import RatingGeralSchema
        bad = rating_geral_valid.copy()
        bad.loc[0, "SCORE_RISCO"] = 150.0
        with pytest.raises(pa.errors.SchemaErrors):
            RatingGeralSchema.validate(bad, lazy=True)

    def test_invalid_categoria_risco_fails(self, rating_geral_valid: pd.DataFrame) -> None:
        from lib.schemas import RatingGeralSchema
        bad = rating_geral_valid.copy()
        bad.loc[0, "CATEGORIA_RISCO"] = "FOOBAR"
        with pytest.raises(pa.errors.SchemaErrors):
            RatingGeralSchema.validate(bad, lazy=True)

    def test_sem_dados_categoria_aceita(self, rating_geral_valid: pd.DataFrame) -> None:
        from lib.schemas import RatingGeralSchema
        df = rating_geral_valid.copy()
        df.loc[0, "CATEGORIA_RISCO"] = "SEM DADOS"
        RatingGeralSchema.validate(df, lazy=True)


class TestRatingResumoSchema:
    def test_valid_df_passes(self, rating_resumo_valid: pd.DataFrame) -> None:
        from lib.schemas import RatingResumoSchema
        RatingResumoSchema.validate(rating_resumo_valid, lazy=True)

    def test_score_negative_fails(self, rating_resumo_valid: pd.DataFrame) -> None:
        from lib.schemas import RatingResumoSchema
        bad = rating_resumo_valid.copy()
        bad.loc[0, "SCORE_RISCO"] = -1.0
        with pytest.raises(pa.errors.SchemaErrors):
            RatingResumoSchema.validate(bad, lazy=True)
```

**Passo 2: Rodar pytest e ver falhar**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
pytest scripts/tests/test_schemas.py -v
```

**Saída esperada:**
```
FAILED ... ModuleNotFoundError: No module named 'lib.schemas'
```

**Passo 3: Sem commit** (cobre em T07).

**Se falhar (de forma diferente):**
- Outro erro de import → checar `conftest.py` (T03)
- Pandera não importa → reinstalar `pip install pandera>=0.18`

---

### Tarefa T07 — Implementar `lib/schemas.py` com Rating + Macro + Credit

**Arquivos:**
- Criar: `/Users/victorbraga/Downloads/radar-fidc/scripts/lib/schemas.py`

**Pré-requisitos:**
- T06 (teste vermelho rodando)

**Passo 1: Criar `schemas.py`**

Conteúdo exato:

```python
"""Pandera DataFrameModels — Linha 2 de defesa (consumer-side).

Cada schema corresponde a UM DataFrame lido pelo `io_utils`. A validação é
chamada dentro de cada `read_*()` em modo `lazy=True` para que TODAS as
violações apareçam em um único erro, não a primeira.

Schema drift = pipeline mudou layout sem coordenação → CI vermelho imediato.

Convenções:
- Strings nullable explícitas via `nullable=True`
- Ranges via `ge`/`le` (inclusive); strings categóricas via `isin`
- Coerção opcional via `coerce=True` quando o CSV vem como str e a coluna é numérica
"""
from __future__ import annotations

import pandera as pa
from pandera.typing import Series


RISCO_VALUES = ("BAIXO", "MEDIO", "ALTO", "SEM DADOS")
CATEGORIA_RISCO_VALUES = ("BAIXO", "MEDIO", "ALTO", "SEM DADOS")
PERFIL_VALUES = ("CONSERVADOR", "MODERADO", "AGRESSIVO", "SEM DADOS")
TIPO_COTA_VALUES = ("UNICA", "SENIOR", "MEZANINO", "JUNIOR", "SUBORDINADA")


class RatingGeralSchema(pa.DataFrameModel):
    """`gold/final/rating_fidc.xlsx` — aba GERAL."""

    CNPJ: Series[str] = pa.Field(nullable=False)
    FUNDO: Series[str] = pa.Field(nullable=False)
    TIPO_COTA: Series[str] = pa.Field(isin=TIPO_COTA_VALUES, nullable=False)
    SCORE_RISCO: Series[float] = pa.Field(ge=0.0, le=100.0, nullable=False, coerce=True)
    RISCO: Series[str] = pa.Field(isin=RISCO_VALUES, nullable=False)
    CATEGORIA_RISCO: Series[str] = pa.Field(isin=CATEGORIA_RISCO_VALUES, nullable=False)
    PERFIL_SUGERIDO: Series[str] = pa.Field(isin=PERFIL_VALUES, nullable=False)
    RETORNO_ANUAL: Series[float] = pa.Field(nullable=True, coerce=True)
    VOLATILIDADE: Series[float] = pa.Field(ge=0.0, nullable=True, coerce=True)
    RETORNO_AJ_RISCO: Series[float] = pa.Field(nullable=True, coerce=True)
    TAXA_INADIMPLENCIA: Series[float] = pa.Field(ge=0.0, le=100.0, nullable=True, coerce=True)
    SCR_NORMALIZADO: Series[float] = pa.Field(nullable=True, coerce=True)
    CONC_MAIOR_CEDENTE: Series[float] = pa.Field(ge=0.0, le=100.0, nullable=True, coerce=True)
    CONC_TOP3: Series[float] = pa.Field(ge=0.0, le=100.0, nullable=True, coerce=True)
    MESES_HISTORICO: Series[int] = pa.Field(ge=0, nullable=True, coerce=True)

    class Config:
        strict = False  # aceita colunas extras (pipeline pode acrescentar sem quebrar)
        coerce = True


class RatingResumoSchema(pa.DataFrameModel):
    """`gold/final/rating_fidc.xlsx` — aba RESUMO_POR_FUNDO."""

    CNPJ: Series[str] = pa.Field(nullable=False)
    FUNDO: Series[str] = pa.Field(nullable=False)
    SCORE_RISCO: Series[float] = pa.Field(ge=0.0, le=100.0, nullable=False, coerce=True)
    RISCO: Series[str] = pa.Field(isin=RISCO_VALUES, nullable=False)
    RETORNO_MEDIO: Series[float] = pa.Field(nullable=True, coerce=True)
    MELHOR_COTA: Series[str] = pa.Field(isin=TIPO_COTA_VALUES, nullable=False)
    PERFIL_PREDOMINANTE: Series[str] = pa.Field(isin=PERFIL_VALUES, nullable=False)

    class Config:
        strict = False
        coerce = True


class MacroSchema(pa.DataFrameModel):
    """`gold/final/macroeconomicos/consolidade.csv`."""

    data_processamento: Series[pa.DateTime] = pa.Field(nullable=False, coerce=True)
    selic_meta: Series[float] = pa.Field(ge=0.0, le=50.0, nullable=True, coerce=True)
    cdi_diario: Series[float] = pa.Field(ge=-1.0, le=5.0, nullable=True, coerce=True)
    ipca_mensal: Series[float] = pa.Field(ge=-5.0, le=30.0, nullable=True, coerce=True)
    inadimplencia_pj: Series[float] = pa.Field(ge=0.0, le=100.0, nullable=True, coerce=True)
    inadimplencia_pf: Series[float] = pa.Field(ge=0.0, le=100.0, nullable=True, coerce=True)
    ibc_br: Series[float] = pa.Field(nullable=True, coerce=True)
    dolar_venda: Series[float] = pa.Field(ge=0.0, nullable=True, coerce=True)

    class Config:
        strict = False
        coerce = True


class CreditSchema(pa.DataFrameModel):
    """`gold/final/scores_credito.csv`."""

    id_cnpj: Series[str] = pa.Field(nullable=False)
    score_credito: Series[float] = pa.Field(ge=0.0, le=1000.0, nullable=False, coerce=True)
    prob_default: Series[float] = pa.Field(ge=0.0, le=1.0, nullable=True, coerce=True)
    risco_credito: Series[str] = pa.Field(isin=RISCO_VALUES, nullable=True)
    total_boletos: Series[int] = pa.Field(ge=0, nullable=True, coerce=True)
    n_default: Series[int] = pa.Field(ge=0, nullable=True, coerce=True)
    pct_default: Series[float] = pa.Field(ge=0.0, le=100.0, nullable=True, coerce=True)
    defaultou: Series[int] = pa.Field(isin=(0, 1), nullable=True, coerce=True)

    class Config:
        strict = False
        coerce = True
```

**Passo 2: Rodar pytest e ver verde**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
pytest scripts/tests/test_schemas.py -v
```

**Saída esperada:**
```
TestRatingGeralSchema::test_valid_df_passes PASSED
TestRatingGeralSchema::test_score_above_100_fails PASSED
TestRatingGeralSchema::test_invalid_categoria_risco_fails PASSED
TestRatingGeralSchema::test_sem_dados_categoria_aceita PASSED
TestRatingResumoSchema::test_valid_df_passes PASSED
TestRatingResumoSchema::test_score_negative_fails PASSED
6 passed in 0.xx s
```

**Passo 3: Commit**

```bash
git add scripts/lib/schemas.py scripts/tests/test_schemas.py
git commit -m "feat: Add pandera schemas for rating/macro/credit DataFrames"
```

**Se falhar:**
- `pa.errors.SchemaErrors` em vez de `SchemaError` → ok, mantemos `lazy=True`
- Coerção quebra um teste válido → relaxar `coerce=True` na coluna específica

---

### Tarefa T08 — Adicionar `MatchesTodosSchema` e `MatchesRankingSchema` (teste vermelho)

**Arquivos:**
- Modificar: `/Users/victorbraga/Downloads/radar-fidc/scripts/tests/test_schemas.py`

**Pré-requisitos:**
- T07 verde

**Passo 1: Adicionar fixtures e testes ao final do arquivo**

Inserir antes do EOF:

```python


@pytest.fixture
def matches_todos_valid() -> pd.DataFrame:
    return pd.DataFrame({
        "CPF": ["12345678901", "98765432100"],
        "CLIENTE": ["Ana L.", "Bruno S."],
        "PERFIL_CLIENTE": ["MODERADO", "AGRESSIVO"],
        "SCORE_CLIENTE": [0.65, 0.82],
        "FUNDO": ["FIDC ABC", "FIDC XYZ"],
        "TIPO_COTA": ["UNICA", "SENIOR"],
        "RISCO_FUNDO": ["BAIXO", "MEDIO"],
        "SCORE_RISCO_FUNDO": [42.5, 78.0],
        "PERFIL_FUNDO": ["CONSERVADOR", "AGRESSIVO"],
        "RETORNO_ANUAL": [12.3, 18.5],
        "VOLATILIDADE": [3.0, 7.0],
        "TAXA_INAD": [1.2, 4.5],
        "MESES_HISTORICO": [12, 24],
        "MATCH_SCORE": [0.85, 0.72],
        "S_PERFIL": [0.9, 0.7],
        "S_RISCO": [0.8, 0.7],
        "S_RETORNO": [0.6, 0.9],
        "S_HISTORICO": [0.5, 0.8],
        "MOTIVO": ["Bom alinhamento", "Histórico curto"],
        "RANK": [1, 2],
    })


@pytest.fixture
def matches_ranking_valid() -> pd.DataFrame:
    return pd.DataFrame({
        "FUNDO": ["FIDC ABC"],
        "TIPO_COTA": ["UNICA"],
        "RISCO_FUNDO": ["BAIXO"],
        "RETORNO_ANUAL": [12.3],
        "VEZES_RECOMENDADO": [42],
        "MATCH_MEDIO": [0.78],
    })


class TestMatchesTodosSchema:
    def test_valid_df_passes(self, matches_todos_valid: pd.DataFrame) -> None:
        from lib.schemas import MatchesTodosSchema
        MatchesTodosSchema.validate(matches_todos_valid, lazy=True)

    def test_match_score_above_1_fails(self, matches_todos_valid: pd.DataFrame) -> None:
        from lib.schemas import MatchesTodosSchema
        bad = matches_todos_valid.copy()
        bad.loc[0, "MATCH_SCORE"] = 1.5
        with pytest.raises(pa.errors.SchemaErrors):
            MatchesTodosSchema.validate(bad, lazy=True)

    def test_rank_negative_fails(self, matches_todos_valid: pd.DataFrame) -> None:
        from lib.schemas import MatchesTodosSchema
        bad = matches_todos_valid.copy()
        bad.loc[0, "RANK"] = -1
        with pytest.raises(pa.errors.SchemaErrors):
            MatchesTodosSchema.validate(bad, lazy=True)


class TestMatchesRankingSchema:
    def test_valid_df_passes(self, matches_ranking_valid: pd.DataFrame) -> None:
        from lib.schemas import MatchesRankingSchema
        MatchesRankingSchema.validate(matches_ranking_valid, lazy=True)

    def test_vezes_recomendado_negative_fails(self, matches_ranking_valid: pd.DataFrame) -> None:
        from lib.schemas import MatchesRankingSchema
        bad = matches_ranking_valid.copy()
        bad.loc[0, "VEZES_RECOMENDADO"] = -5
        with pytest.raises(pa.errors.SchemaErrors):
            MatchesRankingSchema.validate(bad, lazy=True)
```

**Passo 2: Rodar e ver falhar (verde nos antigos, falha nos novos)**

```bash
pytest scripts/tests/test_schemas.py -v
```

**Saída esperada:** 6 PASSED (antigos) + 5 FAILED (novos por ModuleNotFoundError em `MatchesTodosSchema`/`MatchesRankingSchema`).

**Passo 3: Sem commit** (vai com T09).

---

### Tarefa T09 — Implementar `MatchesTodosSchema` e `MatchesRankingSchema` + `ClientesSchema`

**Arquivos:**
- Modificar: `/Users/victorbraga/Downloads/radar-fidc/scripts/lib/schemas.py`

**Pré-requisitos:**
- T08 (teste vermelho)

**Passo 1: Adicionar ao final de `schemas.py`**

```python


class MatchesTodosSchema(pa.DataFrameModel):
    """`gold/final/matches.xlsx` — aba TODOS_OS_MATCHES."""

    CPF: Series[str] = pa.Field(nullable=False)
    CLIENTE: Series[str] = pa.Field(nullable=False)
    PERFIL_CLIENTE: Series[str] = pa.Field(isin=PERFIL_VALUES, nullable=False)
    SCORE_CLIENTE: Series[float] = pa.Field(ge=0.0, le=1.0, nullable=False, coerce=True)
    FUNDO: Series[str] = pa.Field(nullable=False)
    TIPO_COTA: Series[str] = pa.Field(isin=TIPO_COTA_VALUES, nullable=False)
    RISCO_FUNDO: Series[str] = pa.Field(isin=RISCO_VALUES, nullable=False)
    SCORE_RISCO_FUNDO: Series[float] = pa.Field(ge=0.0, le=100.0, nullable=False, coerce=True)
    PERFIL_FUNDO: Series[str] = pa.Field(isin=PERFIL_VALUES, nullable=False)
    RETORNO_ANUAL: Series[float] = pa.Field(nullable=True, coerce=True)
    VOLATILIDADE: Series[float] = pa.Field(ge=0.0, nullable=True, coerce=True)
    TAXA_INAD: Series[float] = pa.Field(ge=0.0, le=100.0, nullable=True, coerce=True)
    MESES_HISTORICO: Series[int] = pa.Field(ge=0, nullable=True, coerce=True)
    MATCH_SCORE: Series[float] = pa.Field(ge=0.0, le=1.0, nullable=False, coerce=True)
    S_PERFIL: Series[float] = pa.Field(ge=0.0, le=1.0, nullable=True, coerce=True)
    S_RISCO: Series[float] = pa.Field(ge=0.0, le=1.0, nullable=True, coerce=True)
    S_RETORNO: Series[float] = pa.Field(ge=0.0, le=1.0, nullable=True, coerce=True)
    S_HISTORICO: Series[float] = pa.Field(ge=0.0, le=1.0, nullable=True, coerce=True)
    MOTIVO: Series[str] = pa.Field(nullable=True)
    RANK: Series[int] = pa.Field(ge=0, nullable=False, coerce=True)

    class Config:
        strict = False
        coerce = True


class MatchesRankingSchema(pa.DataFrameModel):
    """`gold/final/matches.xlsx` — aba RANKING_FUNDOS."""

    FUNDO: Series[str] = pa.Field(nullable=False)
    TIPO_COTA: Series[str] = pa.Field(isin=TIPO_COTA_VALUES, nullable=False)
    RISCO_FUNDO: Series[str] = pa.Field(isin=RISCO_VALUES, nullable=False)
    RETORNO_ANUAL: Series[float] = pa.Field(nullable=True, coerce=True)
    VEZES_RECOMENDADO: Series[int] = pa.Field(ge=0, nullable=False, coerce=True)
    MATCH_MEDIO: Series[float] = pa.Field(ge=0.0, le=1.0, nullable=False, coerce=True)

    class Config:
        strict = False
        coerce = True


class ClientesSchema(pa.DataFrameModel):
    """`gold/final/clientes.csv` — pré-mascaramento (PII em claro).

    IMPORTANTE: validar ANTES do mascaramento. O regex `^\d{11}$` falha de propósito
    se vier algo já mascarado — sinaliza pipeline com regressão de privacidade.
    """

    cpf: Series[str] = pa.Field(str_matches=r"^\d{11}$", nullable=False)
    nome: Series[str] = pa.Field(nullable=False)
    email: Series[str] = pa.Field(str_contains="@", nullable=True)
    telefone: Series[str] = pa.Field(nullable=True)
    idade: Series[int] = pa.Field(ge=18, le=120, nullable=True, coerce=True)
    renda: Series[float] = pa.Field(ge=0.0, nullable=True, coerce=True)
    experiencia: Series[int] = pa.Field(ge=0, nullable=True, coerce=True)
    horizonte: Series[int] = pa.Field(ge=0, nullable=True, coerce=True)
    perfil: Series[str] = pa.Field(isin=PERFIL_VALUES, nullable=False)
    score_perfil: Series[float] = pa.Field(ge=0.0, le=1.0, nullable=True, coerce=True)
    data_cadastro: Series[str] = pa.Field(nullable=True)

    class Config:
        strict = False
        coerce = True
```

**Passo 2: Adicionar testes para `ClientesSchema` em `test_schemas.py`** (final do arquivo):

```python


@pytest.fixture
def clientes_valid() -> pd.DataFrame:
    return pd.DataFrame({
        "cpf": ["12345678901", "98765432100"],
        "nome": ["Ana Lima", "Bruno Souza"],
        "email": ["ana@exemplo.com", "bruno@exemplo.com"],
        "telefone": ["11999990000", "21988880000"],
        "idade": [30, 45],
        "renda": [5000.0, 12000.0],
        "experiencia": [3, 10],
        "horizonte": [5, 10],
        "perfil": ["MODERADO", "AGRESSIVO"],
        "score_perfil": [0.65, 0.82],
        "data_cadastro": ["2025-01-15", "2024-06-22"],
    })


class TestClientesSchema:
    def test_valid_df_passes(self, clientes_valid: pd.DataFrame) -> None:
        from lib.schemas import ClientesSchema
        ClientesSchema.validate(clientes_valid, lazy=True)

    def test_cpf_already_masked_fails(self, clientes_valid: pd.DataFrame) -> None:
        """Sinaliza regressão de privacidade: pipeline NÃO pode entregar PII mascarada."""
        from lib.schemas import ClientesSchema
        bad = clientes_valid.copy()
        bad.loc[0, "cpf"] = "***.***.***-01"
        with pytest.raises(pa.errors.SchemaErrors):
            ClientesSchema.validate(bad, lazy=True)

    def test_invalid_perfil_fails(self, clientes_valid: pd.DataFrame) -> None:
        from lib.schemas import ClientesSchema
        bad = clientes_valid.copy()
        bad.loc[0, "perfil"] = "DESCONHECIDO"
        with pytest.raises(pa.errors.SchemaErrors):
            ClientesSchema.validate(bad, lazy=True)
```

**Passo 3: Rodar todos os testes verdes**

```bash
pytest scripts/tests/test_schemas.py -v
```

**Saída esperada:** 14 PASSED.

**Passo 4: Commit**

```bash
git add scripts/lib/schemas.py scripts/tests/test_schemas.py
git commit -m "feat: Add Matches and Clientes pandera schemas with PII regression guard"
```

---

### Tarefa T10 — Integrar pandera em `lib/io_utils.py`

**Arquivos:**
- Modificar: `/Users/victorbraga/Downloads/radar-fidc/scripts/lib/io_utils.py`

**Pré-requisitos:**
- T09 (schemas implementados)

**Passo 1: Reescrever `io_utils.py`** (substituição completa)

Substituir todo o conteúdo do arquivo por:

```python
"""IO defensivo — leitura dos arquivos do pipeline no Gold (ADLS) + validação pandera.

Substitui a leitura de `data_real/` local pela leitura direta do ADLS,
mantendo o contrato de retorno (tuplas e DataFrames) idêntico ao código
anterior para preservar `payload.build_*` sem mudança.

Cada `read_*()` valida o DataFrame contra o schema pandera correspondente
em modo `lazy=True` (acumula todos os erros) ANTES de devolver. Schema drift
quebra o pipeline com erro descritivo em vez de produzir `data.json` corrompido.
"""
from __future__ import annotations

import pandas as pd
import pandera as pa

from . import azure_io
from .gold_paths import PATHS
from .logger import get_logger
from .schemas import (
    ClientesSchema,
    CreditSchema,
    MacroSchema,
    MatchesRankingSchema,
    MatchesTodosSchema,
    RatingGeralSchema,
    RatingResumoSchema,
)

log = get_logger(__name__)


class SchemaValidationError(RuntimeError):
    """Falha de schema validation. Não retentável — pipeline precisa intervir."""


def _validate(df: pd.DataFrame, schema: type[pa.DataFrameModel], source: str) -> pd.DataFrame:
    """Roda pandera em modo lazy. Devolve o DataFrame (coercido) ou explode."""
    if df.empty:
        log.warn("schema_validation_skipped_empty", source=source)
        return df
    try:
        validated = schema.validate(df, lazy=True)
    except pa.errors.SchemaErrors as e:
        log.error(
            "schema_validation_failed",
            source=source,
            schema=schema.__name__,
            failures=len(e.failure_cases) if hasattr(e, "failure_cases") else None,
            sample=str(e)[:2000],
        )
        raise SchemaValidationError(
            f"Schema {schema.__name__} falhou em {source}. "
            f"Causas (até 5 primeiras):\n{e.failure_cases.head(5) if hasattr(e, 'failure_cases') else e}"
        ) from e
    log.info("schema_validation_ok", source=source, schema=schema.__name__, rows=len(validated))
    return validated


def _empty_on_404(fn, *args, **kwargs):
    """Wrapper: devolve DataFrame vazio se o arquivo não existe no Gold."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:  # noqa: BLE001
        from azure.core.exceptions import ResourceNotFoundError

        if isinstance(e, ResourceNotFoundError):
            log.warn("file_not_found", path=str(args[0]) if args else "?")
            return pd.DataFrame()
        raise


def read_clientes() -> pd.DataFrame:
    df = _empty_on_404(azure_io.read_csv, PATHS["clientes"], encoding="utf-8-sig", dtype={"cpf": str, "telefone": str})
    return _validate(df, ClientesSchema, "clientes.csv")


def read_credit_scores() -> pd.DataFrame:
    df = _empty_on_404(azure_io.read_csv, PATHS["credit"])
    if df.empty:
        return df
    for col in ("score_credito", "prob_default", "pct_default", "defaultou"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return _validate(df, CreditSchema, "scores_credito.csv")


def read_macro() -> pd.DataFrame:
    df = _empty_on_404(azure_io.read_csv, PATHS["macro"], sep=";", dtype=str)
    if df.empty:
        return df
    df["data_processamento"] = pd.to_datetime(df["data_processamento"], errors="coerce")
    for col in df.columns:
        if col != "data_processamento":
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.sort_values("data_processamento").reset_index(drop=True)
    return _validate(df, MacroSchema, "macroeconomicos/consolidade.csv")


def read_rating() -> tuple[pd.DataFrame, pd.DataFrame]:
    try:
        sheets = azure_io.read_excel_sheets(PATHS["rating"], ["GERAL", "RESUMO_POR_FUNDO"])
    except Exception as e:  # noqa: BLE001
        from azure.core.exceptions import ResourceNotFoundError
        if isinstance(e, ResourceNotFoundError):
            log.warn("file_not_found", path=PATHS["rating"])
            return pd.DataFrame(), pd.DataFrame()
        raise
    geral = _validate(sheets.get("GERAL", pd.DataFrame()), RatingGeralSchema, "rating_fidc.xlsx::GERAL")
    resumo = _validate(sheets.get("RESUMO_POR_FUNDO", pd.DataFrame()), RatingResumoSchema, "rating_fidc.xlsx::RESUMO_POR_FUNDO")
    return geral, resumo


def read_matches() -> tuple[pd.DataFrame, pd.DataFrame]:
    try:
        sheets = azure_io.read_excel_sheets(PATHS["matches"], ["TODOS_OS_MATCHES", "RANKING_FUNDOS"])
    except Exception as e:  # noqa: BLE001
        from azure.core.exceptions import ResourceNotFoundError
        if isinstance(e, ResourceNotFoundError):
            log.warn("file_not_found", path=PATHS["matches"])
            return pd.DataFrame(), pd.DataFrame()
        raise
    todos = _validate(sheets.get("TODOS_OS_MATCHES", pd.DataFrame()), MatchesTodosSchema, "matches.xlsx::TODOS_OS_MATCHES")
    ranking = _validate(sheets.get("RANKING_FUNDOS", pd.DataFrame()), MatchesRankingSchema, "matches.xlsx::RANKING_FUNDOS")
    return todos, ranking
```

**Passo 2: Rodar testes existentes para confirmar que não quebrou nada**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
pytest scripts/tests/ -v
```

**Saída esperada:** 14 PASSED (mesmos de antes).

**Passo 3: Commit**

```bash
git add scripts/lib/io_utils.py
git commit -m "feat: Validate every DataFrame with pandera inside io_utils readers"
```

**Se falhar:**
- `SchemaValidationError` ao rodar `generate_dashboard_data.py` local → schema está mais estrito que dados reais; ajustar `nullable=True` ou relaxar `isin` para incluir valor real

---

### Tarefa T11 — Smoke test do generator com pandera ativo

**Arquivos:**
- Nenhum (smoke)

**Pré-requisitos:**
- T10, `.env` populado OU `.cache/` válido

**Passo 1: Rodar generator localmente**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
source .venv-fase2/bin/activate
python scripts/generate_dashboard_data.py --output /tmp/data-fase2-smoke.json
```

**Saída esperada:** logs JSON com `schema_validation_ok` para cada source, `pipeline_end` ao final, sem `schema_validation_failed`.

**Passo 2: Comparar tamanho com `data.json` da Fase 1**

```bash
ls -la /tmp/data-fase2-smoke.json /Users/victorbraga/Downloads/radar-fidc/data.json
```

**Saída esperada:** tamanhos similares (±5%).

**Passo 3: Sem commit** (smoke).

**Se falhar:**
- Schema falha em coluna real → ajustar `lib/schemas.py` (afrouxar a regra que está estourando) + re-rodar
- Documentar qualquer ajuste pós-amostra real como commit de fix antes de avançar

---

## Bloco C — Regression check

### Tarefa T12 — Teste vermelho de `regression_check.py`

**Arquivos:**
- Criar: `/Users/victorbraga/Downloads/radar-fidc/scripts/tests/test_regression_check.py`

**Pré-requisitos:**
- T03

**Passo 1: Criar testes**

Conteúdo exato:

```python
"""Testes do regression check entre `data.json` candidato e HEAD~1."""
from __future__ import annotations

import pytest


@pytest.fixture
def base_data() -> dict:
    return {
        "macro": {"data_ref": "2026-05-13"},
        "fidcs": {"stats": {"total_classes": 2400}},
        "matches": {"total": 12000},
    }


def _with(d: dict, **overrides) -> dict:
    out = {k: dict(v) if isinstance(v, dict) else v for k, v in d.items()}
    for key, val in overrides.items():
        section, _, field = key.partition(".")
        if field:
            out[section] = dict(out[section])
            if "." in field:
                sub, _, inner = field.partition(".")
                out[section][sub] = dict(out[section][sub])
                out[section][sub][inner] = val
            else:
                out[section][field] = val
        else:
            out[section] = val
    return out


class TestCheckRegression:
    def test_no_changes_passes(self, base_data: dict) -> None:
        from lib.regression_check import check_regression
        ok, reasons = check_regression(base_data, base_data, bypass=False)
        assert ok is True
        assert reasons == []

    def test_small_fidc_change_passes(self, base_data: dict) -> None:
        from lib.regression_check import check_regression
        current = _with(base_data, **{"fidcs.stats.total_classes": 2450})  # +2%
        ok, reasons = check_regression(current, base_data, bypass=False)
        assert ok is True
        assert reasons == []

    def test_large_fidc_drop_fails(self, base_data: dict) -> None:
        from lib.regression_check import check_regression
        current = _with(base_data, **{"fidcs.stats.total_classes": 2000})  # -16.7%
        ok, reasons = check_regression(current, base_data, bypass=False)
        assert ok is False
        assert any("fidcs" in r.lower() for r in reasons)

    def test_large_matches_drop_fails(self, base_data: dict) -> None:
        from lib.regression_check import check_regression
        current = _with(base_data, **{"matches.total": 8000})  # -33%
        ok, reasons = check_regression(current, base_data, bypass=False)
        assert ok is False
        assert any("matches" in r.lower() for r in reasons)

    def test_macro_date_regression_fails(self, base_data: dict) -> None:
        from lib.regression_check import check_regression
        current = _with(base_data, **{"macro.data_ref": "2026-05-10"})  # mais antigo que base
        ok, reasons = check_regression(current, base_data, bypass=False)
        assert ok is False
        assert any("macro" in r.lower() or "data_ref" in r.lower() for r in reasons)

    def test_bypass_returns_pass_with_note(self, base_data: dict) -> None:
        from lib.regression_check import check_regression
        current = _with(base_data, **{"fidcs.stats.total_classes": 1})  # absurdo
        ok, reasons = check_regression(current, base_data, bypass=True)
        assert ok is True
        assert any("bypass" in r.lower() for r in reasons)

    def test_missing_previous_data_passes_with_note(self, base_data: dict) -> None:
        """Primeiro run da história não tem HEAD~1 → não bloqueia."""
        from lib.regression_check import check_regression
        ok, reasons = check_regression(base_data, None, bypass=False)
        assert ok is True
        assert any("anterior" in r.lower() or "previous" in r.lower() for r in reasons)
```

**Passo 2: Rodar e ver falhar**

```bash
pytest scripts/tests/test_regression_check.py -v
```

**Saída esperada:** 7 FAILED com `ModuleNotFoundError: No module named 'lib.regression_check'`.

**Passo 3: Sem commit.**

---

### Tarefa T13 — Implementar `lib/regression_check.py`

**Arquivos:**
- Criar: `/Users/victorbraga/Downloads/radar-fidc/scripts/lib/regression_check.py`

**Pré-requisitos:**
- T12 (vermelho)

**Passo 1: Criar módulo**

```python
"""Regression check — Linha 3 de defesa.

Compara `data.json` candidato contra a versão de HEAD~1. Bloqueia o commit
se qualquer das regras dispara, exceto se `bypass=True` (label `data-regression-ok`
no PR ou input `bypass_regression_check` no `workflow_dispatch`).

Regras:
1. |Δ fidcs.stats.total_classes| < 10%
2. |Δ matches.total| < 20%
3. macro.data_ref >= macro.data_ref anterior

Cada violação vira uma string em `reasons` para diagnóstico humano.
"""
from __future__ import annotations

from typing import Any


FIDC_THRESHOLD = 0.10
MATCHES_THRESHOLD = 0.20


def _get(d: dict, dotted: str) -> Any:
    """Acessa `d['a']['b']['c']` por `'a.b.c'` — None se faltar qualquer nível."""
    cur: Any = d
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _abs_delta_ratio(curr: float | int | None, prev: float | int | None) -> float | None:
    """|curr-prev|/prev. None se prev é 0 ou faltando."""
    if curr is None or prev is None or prev == 0:
        return None
    return abs(curr - prev) / abs(prev)


def check_regression(
    current_data: dict,
    previous_data: dict | None,
    *,
    bypass: bool,
) -> tuple[bool, list[str]]:
    """Compara `current_data` contra `previous_data`.

    Args:
        current_data: payload novo (gerado pelo run atual)
        previous_data: payload de HEAD~1. None = sem histórico ainda.
        bypass: ignora todas as regras (mantém auditoria nas `reasons`).

    Returns:
        (ok, reasons). `ok=True` permite seguir. `reasons` é a lista de mensagens
        de auditoria, mesmo no caminho feliz quando bypass está ligado.
    """
    if bypass:
        return True, ["regression_check: bypass=True (label/input override aplicado)"]

    if previous_data is None:
        return True, ["regression_check: sem data.json anterior (primeiro run; previous_data=None)"]

    reasons: list[str] = []

    # Regra 1 — FIDCs
    curr_fidcs = _get(current_data, "fidcs.stats.total_classes")
    prev_fidcs = _get(previous_data, "fidcs.stats.total_classes")
    ratio = _abs_delta_ratio(curr_fidcs, prev_fidcs)
    if ratio is not None and ratio >= FIDC_THRESHOLD:
        reasons.append(
            f"fidcs.stats.total_classes mudou {ratio:.1%} "
            f"(anterior={prev_fidcs}, atual={curr_fidcs}, limite={FIDC_THRESHOLD:.0%})"
        )

    # Regra 2 — Matches
    curr_matches = _get(current_data, "matches.total")
    prev_matches = _get(previous_data, "matches.total")
    ratio_m = _abs_delta_ratio(curr_matches, prev_matches)
    if ratio_m is not None and ratio_m >= MATCHES_THRESHOLD:
        reasons.append(
            f"matches.total mudou {ratio_m:.1%} "
            f"(anterior={prev_matches}, atual={curr_matches}, limite={MATCHES_THRESHOLD:.0%})"
        )

    # Regra 3 — macro.data_ref não pode regredir
    curr_ref = _get(current_data, "macro.data_ref")
    prev_ref = _get(previous_data, "macro.data_ref")
    if curr_ref and prev_ref and str(curr_ref) < str(prev_ref):
        reasons.append(
            f"macro.data_ref regrediu (anterior={prev_ref}, atual={curr_ref})"
        )

    return (len(reasons) == 0, reasons)
```

**Passo 2: Rodar testes**

```bash
pytest scripts/tests/test_regression_check.py -v
```

**Saída esperada:** 7 PASSED.

**Passo 3: Commit**

```bash
git add scripts/lib/regression_check.py scripts/tests/test_regression_check.py
git commit -m "feat: Add regression check comparing data.json against HEAD~1"
```

---

### Tarefa T14 — CLI wrapper para regression check (consumível pelo workflow)

**Arquivos:**
- Criar: `/Users/victorbraga/Downloads/radar-fidc/scripts/run_regression_check.py`

**Pré-requisitos:**
- T13

**Passo 1: Criar script**

```python
#!/usr/bin/env python3
"""Wrapper CLI para `lib.regression_check.check_regression`.

Uso (em `.github/workflows/data-refresh.yml`):
    python scripts/run_regression_check.py \
        --current data.json \
        --previous /tmp/data-previous.json \
        --bypass "${{ github.event.inputs.bypass_regression_check }}"

Exit codes:
    0 = OK
    1 = Regressão detectada
    2 = Erro de I/O (arquivos ausentes)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.logger import get_logger  # noqa: E402
from lib.regression_check import check_regression  # noqa: E402

log = get_logger(__name__)


def _load(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        log.error("regression_load_failed", path=str(path), error=str(e))
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current", required=True, type=Path)
    parser.add_argument("--previous", required=True, type=Path)
    parser.add_argument("--bypass", default="false")
    args = parser.parse_args()

    current = _load(args.current)
    if current is None:
        log.error("regression_current_missing", path=str(args.current))
        return 2

    previous = _load(args.previous)
    bypass = str(args.bypass).strip().lower() in ("1", "true", "yes")

    ok, reasons = check_regression(current, previous, bypass=bypass)
    for r in reasons:
        log.info("regression_reason", reason=r)
    if ok:
        log.info("regression_ok", bypass=bypass, n_notes=len(reasons))
        return 0
    log.error("regression_failed", n_reasons=len(reasons))
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

**Passo 2: Validar execução manual**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
python scripts/run_regression_check.py --current data.json --previous data.json --bypass false
echo "exit=$?"
```

**Saída esperada:** logs JSON com `regression_ok`, `exit=0`.

**Passo 3: Commit**

```bash
git add scripts/run_regression_check.py
git commit -m "feat: Add CLI wrapper for regression_check used by data-refresh workflow"
```

---

## Bloco D — Trust manifest

### Tarefa T15 — Teste vermelho de `trust_manifest.build_manifest`

**Arquivos:**
- Criar: `/Users/victorbraga/Downloads/radar-fidc/scripts/tests/test_trust_manifest.py`

**Pré-requisitos:**
- T03

**Passo 1: Criar testes**

```python
"""Testes do `data-quality.json` builder."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest


@pytest.fixture
def macro_df_today() -> pd.DataFrame:
    return pd.DataFrame({
        "data_processamento": [pd.Timestamp.utcnow().normalize().tz_localize(None)],
        "selic_meta": [13.75],
    })


@pytest.fixture
def macro_df_stale() -> pd.DataFrame:
    old = (pd.Timestamp.utcnow().normalize().tz_localize(None) - pd.Timedelta(days=10))
    return pd.DataFrame({"data_processamento": [old], "selic_meta": [13.75]})


@pytest.fixture
def empty_df() -> pd.DataFrame:
    return pd.DataFrame()


class TestBuildManifest:
    def test_minimal_fresh_run(self, macro_df_today: pd.DataFrame, empty_df: pd.DataFrame) -> None:
        from lib.trust_manifest import build_manifest
        manifest = build_manifest(
            macro_df=macro_df_today,
            geral_df=pd.DataFrame({"CNPJ": ["a"]}),
            matches_df=empty_df,
            clientes_df=empty_df,
            credit_df=empty_df,
            pipeline_quality_result=None,  # blob ainda não existe (Fase 3)
            schema_validation_ok=True,
            regression_check_result="pass",
            smoke_tests_result="pass",
        )
        assert "generated_at" in manifest
        assert manifest["pipeline_quality_check"]["status"] == "not_run"
        assert manifest["ci_quality_check"]["schema_validation"] == "pass"
        assert manifest["data_freshness"]["macro"]["status"] == "fresh"
        assert manifest["row_counts"]["fidcs"] == 1
        assert len(manifest["heuristic_fields"]) >= 1
        assert manifest["source"]["storage_account"] == "dfdatalakesprint"

    def test_stale_macro_marks_warn(self, macro_df_stale: pd.DataFrame, empty_df: pd.DataFrame) -> None:
        from lib.trust_manifest import build_manifest
        manifest = build_manifest(
            macro_df=macro_df_stale,
            geral_df=empty_df, matches_df=empty_df, clientes_df=empty_df, credit_df=empty_df,
            pipeline_quality_result=None,
            schema_validation_ok=True,
            regression_check_result="pass",
            smoke_tests_result="pass",
        )
        assert manifest["data_freshness"]["macro"]["status"] in ("warn", "error")

    def test_pipeline_result_passed_through(self, macro_df_today: pd.DataFrame, empty_df: pd.DataFrame) -> None:
        from lib.trust_manifest import build_manifest
        manifest = build_manifest(
            macro_df=macro_df_today,
            geral_df=empty_df, matches_df=empty_df, clientes_df=empty_df, credit_df=empty_df,
            pipeline_quality_result={
                "ts": "2026-05-14T07:00:00Z",
                "overall_success": True,
                "suites_passed": 5,
                "suites_failed": 0,
            },
            schema_validation_ok=True,
            regression_check_result="pass",
            smoke_tests_result="pass",
        )
        assert manifest["pipeline_quality_check"]["overall_success"] is True
        assert manifest["pipeline_quality_check"]["suites_passed"] == 5
        assert manifest["pipeline_quality_check"]["status"] == "ok"

    def test_heuristic_fields_present(self, macro_df_today: pd.DataFrame, empty_df: pd.DataFrame) -> None:
        from lib.trust_manifest import build_manifest
        manifest = build_manifest(
            macro_df=macro_df_today,
            geral_df=empty_df, matches_df=empty_df, clientes_df=empty_df, credit_df=empty_df,
            pipeline_quality_result=None,
            schema_validation_ok=True,
            regression_check_result="pass",
            smoke_tests_result="pass",
        )
        keys = {h["field"] for h in manifest["heuristic_fields"]}
        # Heurísticas conhecidas na Fase 2 (vão sumir na Fase 3).
        assert "macro.selic_proj" in keys
        assert "macro.ipca_proj" in keys
        assert "credit.scoring" in keys
        assert "matches.engine" in keys
        assert "rating.algorithm" in keys

    def test_schema_validation_failed_propagates(self, macro_df_today: pd.DataFrame, empty_df: pd.DataFrame) -> None:
        from lib.trust_manifest import build_manifest
        manifest = build_manifest(
            macro_df=macro_df_today,
            geral_df=empty_df, matches_df=empty_df, clientes_df=empty_df, credit_df=empty_df,
            pipeline_quality_result=None,
            schema_validation_ok=False,
            regression_check_result="fail",
            smoke_tests_result="pass",
        )
        assert manifest["ci_quality_check"]["schema_validation"] == "fail"
        assert manifest["ci_quality_check"]["regression_check"] == "fail"
```

**Passo 2: Rodar e ver falhar**

```bash
pytest scripts/tests/test_trust_manifest.py -v
```

**Saída esperada:** 5 FAILED por `ModuleNotFoundError`.

**Passo 3: Sem commit.**

---

### Tarefa T16 — Implementar `lib/trust_manifest.py`

**Arquivos:**
- Criar: `/Users/victorbraga/Downloads/radar-fidc/scripts/lib/trust_manifest.py`

**Pré-requisitos:**
- T15 (vermelho)

**Passo 1: Criar módulo**

```python
"""Builder do `data-quality.json` — manifesto de confiança consumido pelo frontend.

Estrutura (Seção 4 da spec):
{
  "generated_at": ISO-UTC,
  "pipeline_quality_check": {...} | {"status": "not_run"},
  "ci_quality_check": {schema_validation, regression_check, smoke_tests},
  "data_freshness": {<fonte>: {data_ref, age_days, status}},
  "row_counts": {...},
  "heuristic_fields": [{field, method, replaced_in_fase_3}],
  "source": {storage_account, container, path}
}

`pipeline_quality_check` é defensivo: se `gold/final/_quality/expectations-result.json`
não existir (Fase 3 ainda não rodou GE pela primeira vez), marca `status: "not_run"`
em vez de quebrar.

Heurísticas: lista fixa atual (Fase 2). Esvazia automaticamente conforme a Fase 3
elimina cada heurística (basta remover do dict abaixo).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import pandas as pd


# Thresholds por fonte (em dias) — Seção 4 da spec.
FRESHNESS_THRESHOLDS: dict[str, tuple[int, int]] = {
    # source: (warn_days, error_days)
    "macro": (2, 7),       # BCB/SGS — diário
    "anbima": (2, 7),      # ANBIMA — diário
    "cda": (40, 60),       # CVM CDA — mensal
    "credit_model": (100, 180),  # retrain trimestral
}


# Heurísticas vivas na Fase 2. Remover entrada conforme Fase 3 substitui.
HEURISTIC_FIELDS: list[dict[str, Any]] = [
    {
        "field": "macro.selic_proj",
        "method": "selic - 0.5 (heurística simples; substituir por Focus/BCB)",
        "replaced_in_fase_3": True,
    },
    {
        "field": "macro.ipca_proj",
        "method": "ipca_12m * 0.9 (heurística simples; substituir por Focus/BCB)",
        "replaced_in_fase_3": True,
    },
    {
        "field": "credit.scoring",
        "method": "single-cohort sem features macro (substituir por multi-cohort)",
        "replaced_in_fase_3": True,
    },
    {
        "field": "matches.engine",
        "method": "scoring sem filtro CVM 555 e sem peso por segmento",
        "replaced_in_fase_3": True,
    },
    {
        "field": "rating.algorithm",
        "method": "K-Means com fator_macro de mediana móvel (substituir por quantis)",
        "replaced_in_fase_3": True,
    },
]


def _now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _classify_age(age_days: int, source_key: str) -> str:
    """Classifica freshness: fresh / warn / error.

    Sem threshold configurada (`source_key` não está em `FRESHNESS_THRESHOLDS`)
    cai para o padrão diário (2/7).
    """
    warn, err = FRESHNESS_THRESHOLDS.get(source_key, (2, 7))
    if age_days >= err:
        return "error"
    if age_days >= warn:
        return "warn"
    return "fresh"


def _freshness_from_df(df: pd.DataFrame, source_key: str, date_col: str = "data_processamento") -> dict[str, Any]:
    """Calcula freshness de um DataFrame baseado na última `data_processamento`."""
    if df is None or df.empty or date_col not in df.columns:
        return {"data_ref": None, "age_days": None, "status": "error", "reason": "no_data"}
    last = pd.to_datetime(df[date_col], errors="coerce").max()
    if pd.isna(last):
        return {"data_ref": None, "age_days": None, "status": "error", "reason": "invalid_date"}
    today = pd.Timestamp.utcnow().normalize().tz_localize(None)
    age = int((today - last.normalize()).days)
    return {
        "data_ref": last.date().isoformat(),
        "age_days": max(0, age),
        "status": _classify_age(max(0, age), source_key),
    }


def _normalize_pipeline_result(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Lida com o blob `expectations-result.json` ausente ou presente."""
    if raw is None:
        return {
            "status": "not_run",
            "source": "great_expectations",
            "overall_success": None,
            "suites_passed": None,
            "suites_failed": None,
        }
    return {
        "status": "ok" if raw.get("overall_success") else "fail",
        "source": "great_expectations",
        "ts": raw.get("ts"),
        "overall_success": bool(raw.get("overall_success", False)),
        "suites_passed": int(raw.get("suites_passed", 0)),
        "suites_failed": int(raw.get("suites_failed", 0)),
    }


def build_manifest(
    *,
    macro_df: pd.DataFrame,
    geral_df: pd.DataFrame,
    matches_df: pd.DataFrame,
    clientes_df: pd.DataFrame,
    credit_df: pd.DataFrame,
    pipeline_quality_result: dict[str, Any] | None,
    schema_validation_ok: bool,
    regression_check_result: str,  # "pass" | "fail" | "bypassed"
    smoke_tests_result: str,        # "pass" | "fail" | "not_run"
) -> dict[str, Any]:
    """Monta o dict do `data-quality.json`."""
    return {
        "generated_at": _now_iso_utc(),
        "pipeline_quality_check": _normalize_pipeline_result(pipeline_quality_result),
        "ci_quality_check": {
            "schema_validation": "pass" if schema_validation_ok else "fail",
            "regression_check": regression_check_result,
            "smoke_tests": smoke_tests_result,
        },
        "data_freshness": {
            "macro": _freshness_from_df(macro_df, "macro"),
        },
        "row_counts": {
            "fidcs": int(len(geral_df)),
            "matches": int(len(matches_df)),
            "clientes": int(len(clientes_df)),
            "credit_empresas": int(len(credit_df)),
            "macro_observations": int(len(macro_df)),
        },
        "heuristic_fields": [dict(h) for h in HEURISTIC_FIELDS],
        "source": {
            "storage_account": os.environ.get("AZURE_STORAGE_ACCOUNT", "dfdatalakesprint"),
            "container": os.environ.get("AZURE_FILESYSTEM", "gold"),
            "path": f"{os.environ.get('AZURE_GOLD_PREFIX', 'final')}/",
        },
    }


def load_pipeline_quality_result_safely(local_path: str | None) -> dict[str, Any] | None:
    """Lê `expectations-result.json` se baixado; None se ausente ou inválido.

    Defensivo: blob criado pela Fase 3 do Databricks. Enquanto não existe,
    devolvemos None e o manifesto marca `pipeline_quality_check.status: "not_run"`.
    """
    import json
    from pathlib import Path

    if not local_path:
        return None
    p = Path(local_path)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        return data
    except (OSError, json.JSONDecodeError):
        return None
```

**Passo 2: Rodar testes**

```bash
pytest scripts/tests/test_trust_manifest.py -v
```

**Saída esperada:** 5 PASSED.

**Passo 3: Commit**

```bash
git add scripts/lib/trust_manifest.py scripts/tests/test_trust_manifest.py
git commit -m "feat: Add trust_manifest builder with defensive pipeline_quality_check"
```

---

### Tarefa T17 — Integrar trust manifest em `generate_dashboard_data.py`

**Arquivos:**
- Modificar: `/Users/victorbraga/Downloads/radar-fidc/scripts/generate_dashboard_data.py`

**Pré-requisitos:**
- T16

**Passo 1: Reescrever o arquivo**

Substituição completa:

```python
#!/usr/bin/env python3
"""Gera `data.json` e `data-quality.json` consumidos pelo dashboard Radar FIDC.

`data.json` — payload do dashboard (Bronze→Silver→Gold materializado).
`data-quality.json` — trust manifest (Fase 2). Lado-a-lado, mesmo diretório.

Uso:
    python scripts/generate_dashboard_data.py
    python scripts/generate_dashboard_data.py --output data.json --quality data-quality.json
    python scripts/generate_dashboard_data.py --ge-result /tmp/expectations-result.json
    python scripts/generate_dashboard_data.py --regression-result pass --smoke-result pass

Pré-requisitos:
    - AZURE_CONNECTION_STRING no .env (local) ou no GitHub Secret (CI)
    - pandera valida cada DataFrame; se falhar, NÃO escreve data.json (fail fast)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from lib import io_utils, payload  # noqa: E402
from lib.logger import get_logger  # noqa: E402
from lib.trust_manifest import build_manifest, load_pipeline_quality_result_safely  # noqa: E402

log = get_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = REPO_ROOT / "data.json"
DEFAULT_QUALITY = REPO_ROOT / "data-quality.json"


def now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_all() -> tuple[dict, dict, dict]:
    """Devolve (dataframes_dict, payload_dict, raw_dataframes_for_manifest)."""
    log.info("pipeline_start", source="adls", filesystem="gold", prefix="final")

    log.info("reading", source="rating_fidc.xlsx")
    geral, resumo = io_utils.read_rating()
    if geral.empty:
        raise SystemExit("ERRO: gold/final/rating_fidc.xlsx ausente ou vazio. Pipeline Databricks deve gerar antes.")

    log.info("reading", source="matches.xlsx")
    todos, ranking = io_utils.read_matches()

    log.info("reading", source="clientes.csv")
    df_clientes = io_utils.read_clientes()

    log.info("reading", source="scores_credito.csv")
    df_credit = io_utils.read_credit_scores()

    log.info("reading", source="macroeconomicos/consolidade.csv")
    df_macro = io_utils.read_macro()

    payload_dict = {
        "generated_at": now_iso_utc(),
        "config": {
            "min_meses_historico": payload.MIN_MESES_HISTORICO,
            "retorno_outlier_pct": payload.RETORNO_OUTLIER_PCT,
        },
        "macro":    payload.build_macro(df_macro),
        "fidcs":    payload.build_fidcs(geral, resumo),
        "clientes": payload.build_clientes(df_clientes),
        "matches":  payload.build_matches(todos, ranking),
        "credit":   payload.build_credit(df_credit),
    }

    raw_dfs = {
        "geral": geral,
        "matches": todos,
        "clientes": df_clientes,
        "credit": df_credit,
        "macro": df_macro,
    }

    return payload_dict, raw_dfs, {}  # 3º slot reservado para evolução


def write_json(out: Path, data: dict) -> None:
    out.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False),
        encoding="utf-8",
    )


def emit_summary(out: Path, data: dict) -> None:
    size_kb = out.stat().st_size // 1024
    log.info(
        "pipeline_end",
        output=str(out),
        size_kb=size_kb,
        fidcs_resumo=len(data["fidcs"]["resumo"]),
        fidcs_detalhe=len(data["fidcs"]["detalhe"]),
        scatter=len(data["fidcs"]["scatter"]),
        clientes=data["clientes"]["total"],
        matches=data["matches"]["total"],
        credit=len(data["credit"]["empresas"]),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=None)
    parser.add_argument("--quality", default=None)
    parser.add_argument("--ge-result", default=None,
                        help="Path local para expectations-result.json (opcional; defensivo se ausente)")
    parser.add_argument("--regression-result", default="not_run",
                        choices=["pass", "fail", "bypassed", "not_run"])
    parser.add_argument("--smoke-result", default="not_run",
                        choices=["pass", "fail", "not_run"])
    args = parser.parse_args()

    out = Path(args.output) if args.output else DEFAULT_OUTPUT
    quality_out = Path(args.quality) if args.quality else DEFAULT_QUALITY

    # Importante: build_all() já valida via pandera; se algum schema falhar
    # ele LEVANTA SchemaValidationError e a função para aqui (não escreve nada).
    data, raw_dfs, _ = build_all()

    write_json(out, data)
    emit_summary(out, data)

    # Trust manifest (sempre depois do data.json escrito com sucesso).
    pipeline_result = load_pipeline_quality_result_safely(args.ge_result)
    manifest = build_manifest(
        macro_df=raw_dfs["macro"],
        geral_df=raw_dfs["geral"],
        matches_df=raw_dfs["matches"],
        clientes_df=raw_dfs["clientes"],
        credit_df=raw_dfs["credit"],
        pipeline_quality_result=pipeline_result,
        schema_validation_ok=True,  # se chegou aqui, todos os schemas passaram
        regression_check_result=args.regression_result,
        smoke_tests_result=args.smoke_result,
    )
    write_json(quality_out, manifest)
    log.info("manifest_written", path=str(quality_out), size_kb=quality_out.stat().st_size // 1024)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Passo 2: Smoke local**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
source .venv-fase2/bin/activate
python scripts/generate_dashboard_data.py --output /tmp/data-fase2.json --quality /tmp/dq-fase2.json --regression-result pass --smoke-result pass
cat /tmp/dq-fase2.json | python3 -m json.tool | head -40
```

**Saída esperada:** JSON formatado com chaves `generated_at`, `pipeline_quality_check.status: "not_run"`, `ci_quality_check.schema_validation: "pass"`, `data_freshness.macro.status`, `heuristic_fields` (lista com 5 entradas), `source.storage_account: "dfdatalakesprint"`.

**Passo 3: Commit**

```bash
git add scripts/generate_dashboard_data.py
git commit -m "feat: Emit data-quality.json alongside data.json from generator"
```

---

### Tarefa T18 — Teste de integração com mock do azure_io

**Arquivos:**
- Criar: `/Users/victorbraga/Downloads/radar-fidc/scripts/tests/test_azure_io.py`

**Pré-requisitos:**
- T03

**Passo 1: Criar testes com mocks (sem rede)**

```python
"""Testes de `lib.azure_io` — usa pytest-mock para nunca bater no ADLS real."""
from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest


@pytest.fixture
def fake_props(fake_etag: str) -> MagicMock:
    m = MagicMock()
    m.etag = fake_etag
    return m


class TestAzureIO:
    def test_missing_connection_string_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from lib.azure_io import AzureMissingConnectionString, _service_client
        _service_client.cache_clear()
        with pytest.raises(AzureMissingConnectionString):
            _service_client()

    def test_blob_etag_returns_string(self, monkeypatch: pytest.MonkeyPatch, fake_props: MagicMock) -> None:
        from lib import azure_io

        fake_file_client = MagicMock()
        fake_file_client.get_file_properties.return_value = fake_props
        fake_fs = MagicMock()
        fake_fs.get_file_client.return_value = fake_file_client

        azure_io._filesystem_client.cache_clear()
        monkeypatch.setattr(azure_io, "_filesystem_client", lambda: fake_fs)

        etag = azure_io.blob_etag("final/rating_fidc.xlsx")
        assert etag == fake_props.etag
        fake_fs.get_file_client.assert_called_once_with("final/rating_fidc.xlsx")

    def test_download_uses_cache_when_etag_matches(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch, fake_etag: str
    ) -> None:
        from lib import azure_io

        # Redirecionar root de cache para tmp_path do teste.
        monkeypatch.setattr(azure_io, "_CACHE_ROOT", tmp_path)
        path = "final/sample.csv"
        body = b"a,b\n1,2\n"

        # Plantar cache local + etag.
        (tmp_path / "final").mkdir(parents=True)
        (tmp_path / "final" / "sample.csv").write_bytes(body)
        (tmp_path / "final" / "sample.csv.etag").write_text(fake_etag, encoding="utf-8")

        # Mockar etag remoto = etag local → cache hit.
        monkeypatch.setattr(azure_io, "blob_etag", lambda p: fake_etag)

        data = azure_io.download_to_bytes(path)
        assert data == body

    def test_read_csv_parses_dataframe(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch, fake_etag: str
    ) -> None:
        from lib import azure_io

        monkeypatch.setattr(azure_io, "_CACHE_ROOT", tmp_path)
        path = "final/scores.csv"
        body = b"id_cnpj,score\nA1,500\nA2,750\n"

        (tmp_path / "final").mkdir(parents=True)
        (tmp_path / "final" / "scores.csv").write_bytes(body)
        (tmp_path / "final" / "scores.csv.etag").write_text(fake_etag, encoding="utf-8")
        monkeypatch.setattr(azure_io, "blob_etag", lambda p: fake_etag)

        df = azure_io.read_csv(path)
        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == ["id_cnpj", "score"]
        assert len(df) == 2
```

**Passo 2: Rodar**

```bash
pytest scripts/tests/test_azure_io.py -v
```

**Saída esperada:** 4 PASSED.

**Passo 3: Commit**

```bash
git add scripts/tests/test_azure_io.py
git commit -m "test: Add mock-based tests for azure_io (no network)"
```

---

## Bloco E — PII regressivo

### Tarefa T19 — Teste regressivo end-to-end de PII masking

**Arquivos:**
- Criar: `/Users/victorbraga/Downloads/radar-fidc/scripts/tests/test_formatters_mask.py`

**Pré-requisitos:**
- T18

**Passo 1: Criar teste**

```python
"""Teste regressivo de PII: o `data.json` gerado NÃO pode conter PII em claro.

Estratégia: construir um payload sintético com CPF, e-mail e telefone reais,
processar via `payload.build_clientes` e `payload.build_matches`, e fazer
busca por regex no JSON resultante. Falha se qualquer padrão de PII original
aparece literalmente.
"""
from __future__ import annotations

import json
import re

import pandas as pd
import pytest


PII_PROBE = {
    "cpf": "12345678901",
    "nome": "Joao da Silva Pereira",
    "email": "joao.silva@dominioreal.com.br",
    "telefone": "11987654321",
}


@pytest.fixture
def clientes_pii_df() -> pd.DataFrame:
    return pd.DataFrame({
        "cpf": [PII_PROBE["cpf"]],
        "nome": [PII_PROBE["nome"]],
        "email": [PII_PROBE["email"]],
        "telefone": [PII_PROBE["telefone"]],
        "idade": [42],
        "renda": [10000.0],
        "experiencia": [5],
        "horizonte": [10],
        "perfil": ["MODERADO"],
        "score_perfil": [0.7],
        "data_cadastro": ["2025-01-01"],
    })


@pytest.fixture
def matches_pii_df() -> pd.DataFrame:
    return pd.DataFrame({
        "CPF": [PII_PROBE["cpf"]],
        "CLIENTE": [PII_PROBE["nome"]],
        "PERFIL_CLIENTE": ["MODERADO"],
        "SCORE_CLIENTE": [0.7],
        "FUNDO": ["FIDC Teste"],
        "TIPO_COTA": ["UNICA"],
        "RISCO_FUNDO": ["BAIXO"],
        "SCORE_RISCO_FUNDO": [30.0],
        "PERFIL_FUNDO": ["MODERADO"],
        "RETORNO_ANUAL": [10.0],
        "VOLATILIDADE": [3.0],
        "TAXA_INAD": [1.0],
        "MESES_HISTORICO": [12],
        "MATCH_SCORE": [0.8],
        "S_PERFIL": [0.9],
        "S_RISCO": [0.8],
        "S_RETORNO": [0.7],
        "S_HISTORICO": [0.6],
        "MOTIVO": ["x"],
        "RANK": [1],
    })


class TestPIIMaskRegression:
    def test_no_pii_in_clientes_payload(self, clientes_pii_df: pd.DataFrame) -> None:
        from lib.payload import build_clientes

        out = build_clientes(clientes_pii_df)
        as_json = json.dumps(out, ensure_ascii=False)

        assert PII_PROBE["cpf"] not in as_json, "CPF cru vazou para o payload"
        assert PII_PROBE["email"] not in as_json, "Email cru vazou para o payload"
        assert PII_PROBE["telefone"] not in as_json, "Telefone cru vazou para o payload"
        # Nome completo NÃO pode aparecer literal; só "primeiro último-inicial".
        assert PII_PROBE["nome"] not in as_json, "Nome completo vazou para o payload"

    def test_no_pii_in_matches_payload(self, matches_pii_df: pd.DataFrame) -> None:
        from lib.payload import build_matches

        out = build_matches(matches_pii_df, pd.DataFrame())
        as_json = json.dumps(out, ensure_ascii=False)

        assert PII_PROBE["cpf"] not in as_json
        assert PII_PROBE["nome"] not in as_json

    def test_mask_format_recognizable(self, clientes_pii_df: pd.DataFrame) -> None:
        """Garante que máscaras estão no formato esperado (não silenciosamente vazias)."""
        from lib.payload import build_clientes
        out = build_clientes(clientes_pii_df)
        cli = out["lista"][0]
        # CPF mascarado guarda os 2 últimos dígitos.
        assert re.match(r"\*{3}\.\*{3}\.\*{3}-\d{2}", cli["cpf"]), f"CPF mask inesperada: {cli['cpf']}"
        assert "@" in cli["email"] and "***" in cli["email"]
        assert re.match(r"\(\d{2}\) \*{4}-\d{4}", cli["telefone"]), f"Telefone mask inesperada: {cli['telefone']}"
```

**Passo 2: Rodar**

```bash
pytest scripts/tests/test_formatters_mask.py -v
```

**Saída esperada:** 3 PASSED.

**Passo 3: Commit**

```bash
git add scripts/tests/test_formatters_mask.py
git commit -m "test: Add PII leak regression covering clientes and matches payloads"
```

**Se falhar:**
- Algum campo está vazando → corrigir o builder em `lib/payload.py` (não relaxar o teste)

---

## Bloco F — Code Review checkpoint #1

### Tarefa T20 — Code review do Bloco A-E

**Pré-requisitos:**
- Tarefas T01-T19 commitadas

**Passo 1: Dispatch dos 7 reviewers em paralelo**

- SUB-SKILL OBRIGATÓRIA: usar `ring:requesting-code-review`
- Reviewers: `ring:code-reviewer`, `ring:business-logic-reviewer`, `ring:security-reviewer`, `ring:test-reviewer`, `ring:nil-safety-reviewer`, `ring:consequences-reviewer`, `ring:dead-code-reviewer`
- Escopo: diff de `T01..T19` (todos os arquivos novos/modificados em `scripts/`, `pyproject.toml`, `.gitignore`, `requirements-dev.txt`)

**Passo 2: Tratar findings por severidade**

- **Critical/High/Medium:** corrigir imediatamente, re-rodar reviewers, repetir até zero.
- **Low:** adicionar `TODO(review): <descrição> (reportado por <reviewer> em 2026-05-14, severity: Low)` no código.
- **Cosmetic/Nitpick:** adicionar `FIXME(nitpick): <descrição> (reportado por <reviewer> em 2026-05-14, severity: Cosmetic)`.

**Passo 3: Prosseguir somente quando**

- Zero Critical/High/Medium pendentes
- TODOs e FIXMEs marcados onde aplicável

**Se falhar:**
- Reviewer não disponível → ainda assim rodar `pytest` + `ruff check` + `mypy scripts/lib/` como mínimo e documentar; voltar para review quando disponível

---

## Bloco G — CI workflow (`ci.yml`)

### Tarefa T21 — Criar `.github/workflows/ci.yml` (jobs base)

**Arquivos:**
- Criar: `/Users/victorbraga/Downloads/radar-fidc/.github/workflows/ci.yml`

**Pré-requisitos:**
- T20

**Passo 1: Criar workflow**

```yaml
name: CI (PR + push)

# Roda em qualquer PR contra main e em push para main.
# Target <2min total. Falha => PR bloqueado (branch protection cuida).

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

permissions:
  contents: read

jobs:
  lint-python:
    name: Lint Python (ruff)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11   # v4.1.1
      - uses: actions/setup-python@0a5c61591373683505ea898e09a3ea4f39ef2b9c   # v5.0.0
        with:
          python-version: "3.11"
          cache: "pip"
          cache-dependency-path: requirements-dev.txt
      - run: pip install -r requirements-dev.txt
      - run: ruff check scripts/
      - run: ruff format --check scripts/

  type-check:
    name: Type-check (mypy)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11   # v4.1.1
      - uses: actions/setup-python@0a5c61591373683505ea898e09a3ea4f39ef2b9c   # v5.0.0
        with:
          python-version: "3.11"
          cache: "pip"
          cache-dependency-path: requirements-dev.txt
      - run: pip install -r requirements-dev.txt
      - run: mypy scripts/lib

  unit-tests:
    name: Unit tests (pytest)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11   # v4.1.1
      - uses: actions/setup-python@0a5c61591373683505ea898e09a3ea4f39ef2b9c   # v5.0.0
        with:
          python-version: "3.11"
          cache: "pip"
          cache-dependency-path: requirements-dev.txt
      - run: pip install -r requirements-dev.txt
      - run: pytest -q

  secret-scan:
    name: Secret scan (gitleaks)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11   # v4.1.1
        with:
          fetch-depth: 0
      - uses: gitleaks/gitleaks-action@cb7149a9b57195b609c63e8518d2c37118d80de2   # v2.3.4
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITLEAKS_ENABLE_UPLOAD_ARTIFACT: "false"
          GITLEAKS_ENABLE_SUMMARY: "true"
```

**Passo 2: Validar sintaxe YAML local**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"
echo "OK"
```

**Saída esperada:** `OK`.

**Passo 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: Add ci.yml with ruff, mypy, pytest and gitleaks in parallel"
```

---

### Tarefa T22 — Validar CI roda local via `act` (opcional) ou simular

**Arquivos:**
- Nenhum (sanity)

**Pré-requisitos:**
- T21

**Passo 1: Rodar localmente as mesmas checagens do CI**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
source .venv-fase2/bin/activate
ruff check scripts/
ruff format --check scripts/
mypy scripts/lib
pytest -q
```

**Saída esperada:** todos verdes; pytest reporta `N passed`.

**Passo 2: Se algo falha, corrigir antes de seguir.**

**Passo 3: Sem commit.**

---

### Tarefa T23 — Documentar requisitos de branch protection no `runbook.md` (placeholder)

**Arquivos:**
- Criar (placeholder, será preenchido em T46): `/Users/victorbraga/Downloads/radar-fidc/docs/runbook.md`

**Pré-requisitos:**
- T22

**Passo 1: Criar arquivo com header mínimo**

```markdown
# Runbook operacional — Radar FIDC

> Status: stub. Preenchido em detalhe na tarefa T46.

## Branch protection esperado em `main`

- Require PR + 1 approval
- Require status checks: `lint-python`, `type-check`, `unit-tests`, `secret-scan`
- Require conversation resolution
- No force-push, no deletion
- Bypass: `github-actions[bot]` para commit do `data-refresh`
```

**Passo 2: Commit**

```bash
git add docs/runbook.md
git commit -m "docs: Stub runbook.md with branch protection requirements"
```

---

## Bloco H — Notify failures

### Tarefa T24 — Criar `.github/workflows/notify-failures.yml`

**Arquivos:**
- Criar: `/Users/victorbraga/Downloads/radar-fidc/.github/workflows/notify-failures.yml`

**Pré-requisitos:**
- T21

**Passo 1: Criar workflow**

```yaml
name: Notify failures

# Reaction workflow: dispara quando `data-refresh.yml` termina com falha.
# Cria issue com label `data-refresh-failure`. Quando o próximo run passa,
# fecha automaticamente os issues abertos com essa label.

on:
  workflow_run:
    workflows: ["Data refresh (ADLS → data.json)"]
    types: [completed]

permissions:
  contents: read
  issues: write

jobs:
  on-failure:
    if: ${{ github.event.workflow_run.conclusion == 'failure' }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/github-script@60a0d83039c74a4aee543508d2ffcb1c3799cdea   # v7.0.1
        with:
          script: |
            const run = context.payload.workflow_run;
            const title = `data-refresh falhou — run ${run.id}`;
            const body = [
              `**Workflow:** ${run.name}`,
              `**Conclusão:** ${run.conclusion}`,
              `**Branch:** ${run.head_branch}`,
              `**Commit:** ${run.head_sha}`,
              `**URL:** ${run.html_url}`,
              ``,
              `Consulte o runbook em \`docs/runbook.md\` para diagnóstico.`,
            ].join("\n");
            await github.rest.issues.create({
              owner: context.repo.owner,
              repo: context.repo.repo,
              title,
              body,
              labels: ["data-refresh-failure"],
            });

  on-success:
    if: ${{ github.event.workflow_run.conclusion == 'success' }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/github-script@60a0d83039c74a4aee543508d2ffcb1c3799cdea   # v7.0.1
        with:
          script: |
            const issues = await github.rest.issues.listForRepo({
              owner: context.repo.owner,
              repo: context.repo.repo,
              labels: "data-refresh-failure",
              state: "open",
              per_page: 100,
            });
            for (const issue of issues.data) {
              await github.rest.issues.createComment({
                owner: context.repo.owner,
                repo: context.repo.repo,
                issue_number: issue.number,
                body: `Auto-fechado: próximo run de data-refresh passou (${context.payload.workflow_run.html_url}).`,
              });
              await github.rest.issues.update({
                owner: context.repo.owner,
                repo: context.repo.repo,
                issue_number: issue.number,
                state: "closed",
              });
            }
```

**Passo 2: Validar YAML**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/notify-failures.yml'))"
```

**Saída esperada:** sem erro.

**Passo 3: Garantir label `data-refresh-failure` existe**

```bash
gh label create data-refresh-failure --description "Auto-criado por notify-failures.yml" --color "B60205" || echo "já existe"
```

**Passo 4: Commit**

```bash
git add .github/workflows/notify-failures.yml
git commit -m "ci: Add notify-failures workflow that opens/closes issues on data-refresh"
```

---

## Bloco I — Playwright smoke tests

### Tarefa T25 — Criar `package.json` mínimo para Playwright

**Arquivos:**
- Criar: `/Users/victorbraga/Downloads/radar-fidc/package.json`

**Pré-requisitos:**
- T20

**Passo 1: Criar `package.json`**

```json
{
  "name": "radar-fidc-e2e",
  "version": "0.0.0",
  "private": true,
  "description": "Playwright smoke tests do dashboard estático Radar FIDC.",
  "scripts": {
    "test:e2e": "playwright test",
    "test:e2e:ci": "playwright test --reporter=line",
    "serve": "python3 -m http.server 8000 --bind 127.0.0.1"
  },
  "devDependencies": {
    "@playwright/test": "1.45.0",
    "typescript": "5.4.5"
  }
}
```

**Passo 2: Instalar local**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
npm install
npx playwright install --with-deps chromium
```

**Saída esperada:** `added N packages`, browsers chromium baixados.

**Passo 3: Commit**

```bash
git add package.json package-lock.json
git commit -m "chore: Add package.json for Playwright smoke tests"
```

**Se falhar:**
- `npm install` falha → checar `node --version` (precisa >=18)
- `npx playwright install` falha em CI → no workflow precisa `--with-deps`

---

### Tarefa T26 — Criar `playwright.config.ts`

**Arquivos:**
- Criar: `/Users/victorbraga/Downloads/radar-fidc/playwright.config.ts`
- Criar: `/Users/victorbraga/Downloads/radar-fidc/tsconfig.json`

**Pré-requisitos:**
- T25

**Passo 1: Criar `tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "types": ["node"]
  },
  "include": ["tests/e2e/**/*.ts", "playwright.config.ts"]
}
```

**Passo 2: Criar `playwright.config.ts`**

```ts
// Playwright config — smoke do dashboard estático.
// Serve `index.html` via http.server local na porta 8000; checa renderização
// das 6 páginas. Retry x2 cobre flakiness ocasional do `defer` do Chart.js.

import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? "line" : "list",
  timeout: 30_000,
  expect: { timeout: 5_000 },
  use: {
    baseURL: "http://127.0.0.1:8000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } },
    },
  ],
  webServer: {
    command: "python3 -m http.server 8000 --bind 127.0.0.1",
    url: "http://127.0.0.1:8000",
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
```

**Passo 3: Commit**

```bash
git add tsconfig.json playwright.config.ts
git commit -m "chore: Configure Playwright (chromium headless, retries x2, http.server)"
```

---

### Tarefa T27 — Criar `tests/e2e/dashboard.spec.ts` com 6 cenários

**Arquivos:**
- Criar: `/Users/victorbraga/Downloads/radar-fidc/tests/e2e/dashboard.spec.ts`

**Pré-requisitos:**
- T26

**Passo 1: Criar diretório e arquivo**

```bash
mkdir -p /Users/victorbraga/Downloads/radar-fidc/tests/e2e
```

**Passo 2: Criar spec**

```ts
// Smoke test: 6 cenários cobrindo cada página do dashboard. Cada teste
// garante (1) que a página renderiza sem erro JS, (2) que campos críticos
// não são "NaN"/"undefined", (3) que pelo menos uma estrutura de dados
// (gráfico/tabela/lista) tem conteúdo OU mostra empty state.
//
// Roda sobre o `data.json` atualmente commitado — não bate no ADLS.

import { test, expect, type Page } from "@playwright/test";

async function gotoTab(page: Page, hash: string) {
  await page.goto(`/#${hash}`);
  await page.waitForLoadState("networkidle");
}

function expectNoNaN(text: string | null) {
  expect(text ?? "", `Esperado texto sem NaN, recebido "${text}"`).not.toMatch(/NaN|undefined/i);
}

test.beforeEach(async ({ page }) => {
  // Falha o teste se o JS lançar uncaught error.
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  expect(errors, `Erros JS na boot: ${errors.join(" | ")}`).toEqual([]);
});

test("01 Visão Geral renderiza KPIs sem NaN", async ({ page }) => {
  await gotoTab(page, "overview");
  const kpis = page.locator(".kpi-value");
  await expect(kpis.first()).toBeVisible();
  const count = await kpis.count();
  expect(count).toBeGreaterThanOrEqual(3);
  for (let i = 0; i < count; i++) {
    expectNoNaN(await kpis.nth(i).textContent());
  }
});

test("02 Score & Risco mostra distribuição (FIDCs)", async ({ page }) => {
  await gotoTab(page, "fidcs");
  await expect(page.locator("canvas").first()).toBeVisible();
  // Pelo menos uma linha na tabela ou empty state explícito.
  const rows = page.locator("tbody tr");
  expect(await rows.count()).toBeGreaterThanOrEqual(1);
});

test("03 Macro mostra SELIC numérica", async ({ page }) => {
  await gotoTab(page, "macro");
  const selic = page.locator("#m-selic");
  await expect(selic).toBeVisible();
  const text = (await selic.textContent()) ?? "";
  expectNoNaN(text);
  // Precisa ter um número (pode ter %).
  expect(text).toMatch(/\d/);
});

test("04 Clientes tem ao menos uma linha ou empty state", async ({ page }) => {
  await gotoTab(page, "clientes");
  const rows = page.locator("tbody tr");
  const empty = page.locator('[data-empty-state="true"]');
  const hasRows = (await rows.count()) > 0;
  const hasEmpty = (await empty.count()) > 0;
  expect(hasRows || hasEmpty, "Esperado linhas ou empty state na página Clientes").toBeTruthy();
});

test("05 Match tem top-3 OU empty state amigável", async ({ page }) => {
  await gotoTab(page, "match");
  // Sem cliente selecionado, cards podem estar vazios — checar empty state OU tabela.
  const cards = page.locator(".pme-card");
  const tableRows = page.locator("tbody tr");
  const empty = page.locator('[data-empty-state="true"]');
  const ok = (await cards.count()) >= 0 && ((await tableRows.count()) > 0 || (await empty.count()) > 0);
  expect(ok, "Esperado tabela com linhas OU empty state na página Match").toBeTruthy();
});

test("06 Credit tem dados de empresas", async ({ page }) => {
  await gotoTab(page, "credit");
  const rows = page.locator("tbody tr");
  expect(await rows.count()).toBeGreaterThanOrEqual(1);
  // Stat principal não pode ser NaN.
  const stat = page.locator(".kpi-value").first();
  expectNoNaN(await stat.textContent());
});
```

**Passo 3: Rodar local**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
npx playwright test --reporter=line
```

**Saída esperada:** `6 passed`.

**Passo 4: Commit**

```bash
git add tests/e2e/dashboard.spec.ts
git commit -m "test: Add Playwright smoke covering 6 dashboard pages"
```

**Se falhar:**
- Algum seletor errado → ajustar; NÃO afrouxar para "always pass"
- Empty state ainda não implementado em Clientes/Match → o teste aceita ambos (linhas OU empty state)

---

### Tarefa T28 — Smoke result CLI script (consumível pelo workflow)

**Arquivos:**
- Criar: `/Users/victorbraga/Downloads/radar-fidc/scripts/run_smoke.sh`

**Pré-requisitos:**
- T27

**Passo 1: Criar script**

```bash
#!/usr/bin/env bash
# Wrapper para Playwright no workflow. Captura exit code e emite arquivo
# de status que o step seguinte consome para preencher `smoke_tests` no manifesto.
set -euo pipefail

OUT_STATUS="${1:-/tmp/smoke-status.txt}"

if npx playwright test --reporter=line; then
  echo "pass" > "$OUT_STATUS"
  exit 0
else
  echo "fail" > "$OUT_STATUS"
  exit 1
fi
```

**Passo 2: Marcar executável**

```bash
chmod +x /Users/victorbraga/Downloads/radar-fidc/scripts/run_smoke.sh
```

**Passo 3: Commit**

```bash
git add scripts/run_smoke.sh
git update-index --chmod=+x scripts/run_smoke.sh
git commit -m "ci: Add run_smoke.sh wrapper exposing pass/fail to data-refresh"
```

---

### Tarefa T29 — Atualizar `.gitignore` para Playwright e validar

**Arquivos:**
- Verificar: `/Users/victorbraga/Downloads/radar-fidc/.gitignore` (T04 já adicionou)

**Pré-requisitos:**
- T28

**Passo 1: Confirmar entradas**

```bash
grep -E "node_modules|playwright-report|test-results" /Users/victorbraga/Downloads/radar-fidc/.gitignore
```

**Saída esperada:** 3 linhas listadas.

**Passo 2: Sem commit se já presente.**

---

## Bloco J — Refresh workflow hardening

### Tarefa T30 — Atualizar `data-refresh.yml` com inputs de bypass

**Arquivos:**
- Modificar: `/Users/victorbraga/Downloads/radar-fidc/.github/workflows/data-refresh.yml`

**Pré-requisitos:**
- T29

**Passo 1: Reescrever o workflow inteiro**

Substituir todo o conteúdo por:

```yaml
name: Data refresh (ADLS → data.json)

# Regenera data.json + data-quality.json lendo o Gold do ADLS Gen2
# (dfdatalakesprint/gold/final). Cron diário 9h UTC + dispatch manual com bypasses.

on:
  schedule:
    - cron: "0 9 * * *"
  workflow_dispatch:
    inputs:
      bypass_ge_check:
        description: "Ignorar overall_success do expectations-result.json"
        required: false
        default: "false"
      bypass_regression_check:
        description: "Ignorar regression check vs HEAD~1"
        required: false
        default: "false"

concurrency:
  group: data-refresh
  cancel-in-progress: false   # NÃO cancelar runs em andamento (risco de commit pela metade)

permissions:
  contents: read

jobs:
  refresh:
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    permissions:
      contents: write
    steps:
      - name: Checkout
        uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11   # v4.1.1
        with:
          fetch-depth: 2
          persist-credentials: true

      - name: Set up Python
        uses: actions/setup-python@0a5c61591373683505ea898e09a3ea4f39ef2b9c   # v5.0.0
        with:
          python-version: "3.11"
          cache: "pip"
          cache-dependency-path: requirements-dev.txt

      - name: Set up Node (Playwright)
        uses: actions/setup-node@1a4442cacd436585916779262731d5b162bc6ec7   # v3.8.2
        with:
          node-version: "20"
          cache: "npm"

      - name: Validar secret AZURE_CONNECTION_STRING
        env:
          AZURE_CONNECTION_STRING: ${{ secrets.AZURE_CONNECTION_STRING }}
        run: |
          if [ -z "$AZURE_CONNECTION_STRING" ]; then
            echo "::error::AZURE_CONNECTION_STRING não configurada"
            exit 1
          fi
          case "$AZURE_CONNECTION_STRING" in
            *"AccountName=dfdatalakesprint"*"AccountKey="*"EndpointSuffix=core.windows.net"*)
              echo "OK formato connection string"
              ;;
            *)
              echo "::error::AZURE_CONNECTION_STRING não tem formato esperado"
              exit 1
              ;;
          esac

      - name: Install Python deps
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements-dev.txt

      - name: Install Node deps + Playwright browser
        run: |
          npm ci
          npx playwright install --with-deps chromium

      - name: Backup previous data.json (HEAD~1 para regression check)
        run: |
          if git rev-parse HEAD~1 >/dev/null 2>&1; then
            git show HEAD~1:data.json > /tmp/data-previous.json || echo "{}" > /tmp/data-previous.json
          else
            echo "{}" > /tmp/data-previous.json
          fi

      - name: Download expectations-result.json (defensivo)
        id: ge
        env:
          AZURE_CONNECTION_STRING: ${{ secrets.AZURE_CONNECTION_STRING }}
        run: |
          set +e
          python - <<'PY'
          import os, sys, json
          from pathlib import Path
          sys.path.insert(0, "scripts")
          from lib import azure_io
          remote = "final/_quality/expectations-result.json"
          out = Path("/tmp/expectations-result.json")
          try:
              data = azure_io.download_to_bytes(remote)
              out.write_bytes(data)
              print(f"::notice::baixou {remote} ({len(data)} bytes)")
          except Exception as e:
              print(f"::warning::expectations-result.json não disponível: {e}")
              # NÃO falhar — Fase 3 cria esse blob; até lá manifesto marca not_run.
              if out.exists():
                  out.unlink()
          PY

      - name: Validate GE overall_success (com bypass)
        env:
          BYPASS_GE: ${{ github.event.inputs.bypass_ge_check }}
        run: |
          if [ ! -f /tmp/expectations-result.json ]; then
            echo "::notice::Sem expectations-result.json — manifesto marcará pipeline_quality_check.status=not_run"
            exit 0
          fi
          OK=$(python -c "import json; d=json.load(open('/tmp/expectations-result.json')); print(d.get('overall_success', False))")
          if [ "$OK" != "True" ] && [ "$BYPASS_GE" != "true" ]; then
            echo "::error::GE overall_success=false. Use bypass_ge_check para forçar."
            exit 1
          fi

      - name: Generate data.json + data-quality.json
        env:
          AZURE_CONNECTION_STRING: ${{ secrets.AZURE_CONNECTION_STRING }}
        run: |
          python scripts/generate_dashboard_data.py \
            --output data.json \
            --quality data-quality.json \
            --ge-result /tmp/expectations-result.json \
            --regression-result not_run \
            --smoke-result not_run

      - name: Regression check
        id: regression
        env:
          BYPASS_REG: ${{ github.event.inputs.bypass_regression_check }}
        run: |
          set +e
          python scripts/run_regression_check.py \
            --current data.json \
            --previous /tmp/data-previous.json \
            --bypass "${BYPASS_REG:-false}"
          CODE=$?
          if [ $CODE -eq 0 ]; then
            echo "result=pass" >> "$GITHUB_OUTPUT"
            [ "$BYPASS_REG" = "true" ] && echo "result=bypassed" >> "$GITHUB_OUTPUT"
            exit 0
          fi
          echo "result=fail" >> "$GITHUB_OUTPUT"
          if [ "$BYPASS_REG" = "true" ]; then
            echo "::warning::regression_check falhou mas bypass_regression_check=true"
            exit 0
          fi
          exit 1

      - name: Playwright smoke (6 páginas)
        id: smoke
        run: |
          set +e
          ./scripts/run_smoke.sh /tmp/smoke-status.txt
          CODE=$?
          STATUS=$(cat /tmp/smoke-status.txt || echo fail)
          echo "result=$STATUS" >> "$GITHUB_OUTPUT"
          exit $CODE

      - name: Re-emit data-quality.json with final statuses
        run: |
          python scripts/generate_dashboard_data.py \
            --output data.json \
            --quality data-quality.json \
            --ge-result /tmp/expectations-result.json \
            --regression-result "${{ steps.regression.outputs.result }}" \
            --smoke-result "${{ steps.smoke.outputs.result }}"

      - name: Commit if changed
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          set -e
          git config user.name  "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          if git diff --quiet data.json data-quality.json; then
            echo "Sem mudanças em data.json/data-quality.json."
            exit 0
          fi
          git add data.json data-quality.json
          git commit -m "chore: Regenerate dashboard data + quality manifest ($(date -u +%Y-%m-%d))"
          git push

      - name: Step summary
        if: always()
        run: |
          {
            echo "## Data refresh run"
            echo "| Etapa | Resultado |"
            echo "|---|---|"
            echo "| Regression check | ${{ steps.regression.outputs.result }} |"
            echo "| Smoke test       | ${{ steps.smoke.outputs.result }} |"
          } >> "$GITHUB_STEP_SUMMARY"
```

**Passo 2: Validar YAML**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/data-refresh.yml'))"
```

**Saída esperada:** sem erro.

**Passo 3: Commit**

```bash
git add .github/workflows/data-refresh.yml
git commit -m "ci: Harden data-refresh with GE/regression/smoke gates and bypass inputs"
```

---

### Tarefa T31 — Smoke `workflow_dispatch` manual com bypasses (após push)

**Pré-requisitos:**
- T30 mergeada em `main`

**Passo 1: Disparar manualmente o workflow**

```bash
gh workflow run data-refresh.yml -f bypass_ge_check=true -f bypass_regression_check=true
```

**Saída esperada:** `✓ Created workflow_dispatch event for data-refresh.yml at main`.

**Passo 2: Aguardar run e validar logs**

```bash
sleep 30 && gh run list --workflow=data-refresh.yml --limit 1
gh run view --log $(gh run list --workflow=data-refresh.yml --limit 1 --json databaseId -q '.[0].databaseId')
```

**Saída esperada:** `success`, mensagens `::notice::` indicando bypass aplicado.

**Passo 3: Sem commit.**

**Se falhar:**
- Workflow não está em `main` ainda → primeiro fazer merge
- Step summary não aparece → checar permissão `contents: write`

---

### Tarefa T32 — Validar que `data-quality.json` foi commitado pelo workflow

**Pré-requisitos:**
- T31

**Passo 1: Atualizar local**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
git fetch origin main
git log --oneline -5
ls -la data-quality.json
```

**Saída esperada:** commit `chore: Regenerate dashboard data...` recente; arquivo `data-quality.json` presente.

**Passo 2: Inspecionar conteúdo**

```bash
cat data-quality.json | python3 -m json.tool | head -30
```

**Saída esperada:** JSON estruturado com todas as chaves esperadas (`pipeline_quality_check`, `ci_quality_check`, `data_freshness`, `row_counts`, `heuristic_fields`, `source`).

**Passo 3: Sem commit.**

---

### Tarefa T33 — Atualizar `README.md` documentando os 3 workflows

**Arquivos:**
- Modificar: `/Users/victorbraga/Downloads/radar-fidc/README.md`

**Pré-requisitos:**
- T32

**Passo 1: Adicionar seção "Workflows" ao README**

Localizar a seção de "Estrutura" ou final do README; adicionar antes do EOF:

```markdown

## Workflows GitHub Actions

| Workflow | Trigger | Função |
|----------|---------|--------|
| `ci.yml` | PR + push para `main` | ruff + mypy + pytest + gitleaks (< 2 min) |
| `data-refresh.yml` | Cron diário 9h UTC + dispatch | Lê ADLS, valida schemas, regression check, smoke Playwright, commita `data.json` + `data-quality.json` |
| `notify-failures.yml` | Reaction (`workflow_run` failure) | Abre issue com label `data-refresh-failure`; auto-fecha quando próximo run passa |

### Bypasses (workflow_dispatch)

- `bypass_ge_check=true` → ignora `overall_success` do `expectations-result.json`
- `bypass_regression_check=true` → ignora deltas > 10% (fidcs) / 20% (matches)
```

**Passo 2: Commit**

```bash
git add README.md
git commit -m "docs: Document the 3 GitHub Actions workflows and bypass inputs"
```

---

## Bloco K — Code Review checkpoint #2

### Tarefa T34 — Code review do Bloco G-J

**Pré-requisitos:**
- T21–T33 commitadas e mergeadas

**Passo 1:** Dispatch dos 7 reviewers via `ring:requesting-code-review` cobrindo `.github/workflows/`, `package.json`, `playwright.config.ts`, `tests/e2e/`, `scripts/run_*`.

**Passo 2:** Tratar Critical/High/Medium imediatamente; Low → `TODO(review):`; Cosmetic → `FIXME(nitpick):`.

**Passo 3:** Prosseguir somente quando zero Critical/High/Medium.

---

## Bloco L — Frontend trust components

### Tarefa T35 — Criar `assets/css/trust.css`

**Arquivos:**
- Criar: `/Users/victorbraga/Downloads/radar-fidc/assets/css/trust.css`
- Modificar: `/Users/victorbraga/Downloads/radar-fidc/assets/css/main.css` (import)

**Pré-requisitos:**
- T34

**Passo 1: Criar `trust.css`**

```css
/* Trust layer — sticky bar + heuristic markers + empty/error states. */

.trust-bar {
  position: sticky;
  top: 0;
  z-index: 50;
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 8px 16px;
  font-size: 0.85rem;
  font-weight: 500;
  border-bottom: 1px solid var(--border-subtle, rgba(0, 0, 0, 0.08));
  background: var(--bg-surface, #f5f5f0);
  color: var(--fg-default, #0b0d0c);
}

.trust-bar[data-state="ok"] {
  background: rgba(46, 160, 67, 0.08);
  color: var(--data-positive, #1a7f37);
}

.trust-bar[data-state="warn"] {
  background: rgba(255, 153, 0, 0.10);
  color: var(--data-warning, #9a6700);
}

.trust-bar[data-state="error"] {
  background: rgba(207, 34, 46, 0.10);
  color: var(--data-negative, #cf222e);
}

.trust-bar__icon {
  font-size: 1.05rem;
  line-height: 1;
}

.trust-bar__details {
  display: flex;
  gap: 12px;
  margin-left: auto;
  font-weight: 400;
  font-size: 0.78rem;
  color: var(--fg-muted, #57606a);
}

/* Heuristic marker — usado inline com o valor heurístico. */
.heuristic-marker {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 0.72rem;
  padding: 2px 6px;
  margin-left: 6px;
  border-radius: 4px;
  background: rgba(255, 153, 0, 0.15);
  color: var(--data-warning, #9a6700);
  cursor: help;
}

.heuristic-marker[aria-label] {
  /* Tooltip nativo basta; mantemos sem hover custom. */
}

/* Empty state reutilizável. */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 32px 16px;
  border: 1px dashed var(--border-subtle, rgba(0, 0, 0, 0.12));
  border-radius: 8px;
  color: var(--fg-muted, #57606a);
}

.empty-state__title {
  font-size: 1rem;
  font-weight: 600;
  color: var(--fg-default, #0b0d0c);
  margin-bottom: 4px;
}

.empty-state__desc {
  font-size: 0.85rem;
  margin-bottom: 12px;
  max-width: 480px;
}

.empty-state__suggestions {
  list-style: disc;
  text-align: left;
  font-size: 0.8rem;
  padding-left: 24px;
}

/* Fetch error banner. */
.fetch-error {
  margin: 12px 16px;
  padding: 12px 16px;
  border-radius: 8px;
  background: rgba(207, 34, 46, 0.08);
  color: var(--data-negative, #cf222e);
  font-size: 0.85rem;
}

.fetch-error__action {
  margin-top: 8px;
  display: inline-block;
  padding: 6px 12px;
  background: var(--data-negative, #cf222e);
  color: #fff;
  border-radius: 6px;
  cursor: pointer;
  border: none;
  font-weight: 600;
}
```

**Passo 2: Importar em `main.css`**

Abrir `assets/css/main.css` e adicionar import no final (após o último `@import`):

```css
@import "trust.css";
```

**Passo 3: Commit**

```bash
git add assets/css/trust.css assets/css/main.css
git commit -m "feat: Add trust.css with bar, markers, empty state and fetch error styles"
```

---

### Tarefa T36 — Criar `assets/js/utils/trust.js` (helper markHeuristic)

**Arquivos:**
- Criar: `/Users/victorbraga/Downloads/radar-fidc/assets/js/utils/trust.js`

**Pré-requisitos:**
- T35

**Passo 1: Criar módulo**

```js
// trust.js — utilidades para consumir `data-quality.json` no frontend.
//
// `loadManifest()` carrega o manifesto uma única vez (cache em memória).
// `markHeuristic(fieldKey)` devolve uma string HTML segura (escapada) com
//   ícone ⚠ + tooltip quando o campo está em `heuristic_fields`.
// Quando a Fase 3 esvazia `heuristic_fields`, todas as marcas somem automaticamente.

let _manifestPromise = null;

export function loadManifest() {
  if (_manifestPromise) return _manifestPromise;
  _manifestPromise = fetch("data-quality.json", { cache: "no-store" })
    .then((r) => {
      if (!r.ok) throw new Error(`data-quality.json: HTTP ${r.status}`);
      return r.json();
    })
    .catch((err) => {
      console.warn("[trust] manifesto indisponível:", err);
      return null;
    });
  return _manifestPromise;
}

function _escape(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

export async function markHeuristic(fieldKey) {
  const m = await loadManifest();
  if (!m || !Array.isArray(m.heuristic_fields)) return "";
  const entry = m.heuristic_fields.find((h) => h.field === fieldKey);
  if (!entry) return "";
  const tooltip = `Heurística: ${entry.method}`;
  return `<span class="heuristic-marker" role="img" aria-label="${_escape(tooltip)}" title="${_escape(tooltip)}">⚠ heurística</span>`;
}

export async function isHeuristic(fieldKey) {
  const m = await loadManifest();
  if (!m || !Array.isArray(m.heuristic_fields)) return false;
  return m.heuristic_fields.some((h) => h.field === fieldKey);
}
```

**Passo 2: Commit**

```bash
git add assets/js/utils/trust.js
git commit -m "feat: Add trust.js with markHeuristic helper consuming data-quality.json"
```

---

### Tarefa T37 — Criar `assets/js/components/trust-bar.js`

**Arquivos:**
- Criar: `/Users/victorbraga/Downloads/radar-fidc/assets/js/components/trust-bar.js`

**Pré-requisitos:**
- T36

**Passo 1: Criar componente**

```js
// trust-bar.js — sticky bar no topo do dashboard.
//
// Lógica de cor (Seção 6 da spec, decisão do usuário):
//   - 🟢 ok    : pipeline_quality_check.overall_success === true E nenhum data_freshness.*.status === "error"
//   - 🔴 error : pipeline_quality_check.overall_success === false OU algum data_freshness.*.status === "error"
//   - 🟡 warn  : caso intermediário (pipeline not_run, ou freshness warn)
//
// Heurísticas NÃO afetam a cor — só aparecem como marker inline (utils/trust.js).
//
// Acessibilidade: role="status" + aria-live="polite". Ícone + texto explícito
// para não depender só de cor.

import { loadManifest } from "../utils/trust.js";

function pickState(manifest) {
  if (!manifest) return { state: "error", icon: "⛔", label: "Manifesto indisponível" };
  const pq = manifest.pipeline_quality_check || {};
  const freshness = manifest.data_freshness || {};
  const hasError =
    pq.overall_success === false ||
    Object.values(freshness).some((f) => f && f.status === "error");
  if (hasError) {
    return { state: "error", icon: "⛔", label: "Dados com falha de qualidade — verificar runbook" };
  }
  const pipelineOk = pq.overall_success === true;
  const allFresh = Object.values(freshness).every((f) => !f || f.status === "fresh");
  if (pipelineOk && allFresh) {
    return { state: "ok", icon: "✓", label: "Pipeline saudável" };
  }
  return { state: "warn", icon: "⚠", label: "Sinal misto — ver detalhes" };
}

function detailsLine(manifest) {
  if (!manifest) return "";
  const ts = manifest.generated_at ? `Gerado em ${manifest.generated_at}` : "";
  const f = manifest.data_freshness?.macro;
  const fresh = f ? `Macro: ${f.data_ref ?? "—"} (${f.status})` : "";
  return [ts, fresh].filter(Boolean).join(" · ");
}

export async function renderTrustBar(rootSelector = "body") {
  const manifest = await loadManifest();
  const { state, icon, label } = pickState(manifest);
  const details = detailsLine(manifest);

  const bar = document.createElement("div");
  bar.className = "trust-bar";
  bar.setAttribute("role", "status");
  bar.setAttribute("aria-live", "polite");
  bar.setAttribute("data-state", state);
  bar.innerHTML = `
    <span class="trust-bar__icon" aria-hidden="true">${icon}</span>
    <span class="trust-bar__label">${label}</span>
    <span class="trust-bar__details">${details}</span>
  `;

  const root = document.querySelector(rootSelector);
  if (!root) return;
  // Inserir no topo do body (antes do main).
  root.insertBefore(bar, root.firstChild);
}
```

**Passo 2: Commit**

```bash
git add assets/js/components/trust-bar.js
git commit -m "feat: Add trust-bar component with state-driven color and a11y"
```

---

### Tarefa T38 — Criar `assets/js/components/empty-state.js`

**Arquivos:**
- Criar: `/Users/victorbraga/Downloads/radar-fidc/assets/js/components/empty-state.js`

**Pré-requisitos:**
- T37

**Passo 1: Criar componente**

```js
// empty-state.js — bloco reutilizável para "sem dados" / "filtro vazio".
//
// Uso:
//   import { renderEmptyState } from "../components/empty-state.js";
//   container.innerHTML = renderEmptyState({
//     title: "Sem matches",
//     description: "Nenhum FIDC compatível com este perfil + filtros.",
//     suggestions: ["Limpar filtros", "Tentar outro cliente"],
//   });

function _escape(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

export function renderEmptyState({ title, description = "", suggestions = [] } = {}) {
  const safeTitle = _escape(title || "Sem dados");
  const safeDesc = description ? `<p class="empty-state__desc">${_escape(description)}</p>` : "";
  const sugList = suggestions.length
    ? `<ul class="empty-state__suggestions">${suggestions.map((s) => `<li>${_escape(s)}</li>`).join("")}</ul>`
    : "";
  return `
    <div class="empty-state" data-empty-state="true" role="status">
      <div class="empty-state__title">${safeTitle}</div>
      ${safeDesc}
      ${sugList}
    </div>
  `;
}
```

**Passo 2: Commit**

```bash
git add assets/js/components/empty-state.js
git commit -m "feat: Add reusable empty-state component"
```

---

### Tarefa T39 — Criar `assets/js/components/fetch-error.js`

**Arquivos:**
- Criar: `/Users/victorbraga/Downloads/radar-fidc/assets/js/components/fetch-error.js`

**Pré-requisitos:**
- T38

**Passo 1: Criar componente**

```js
// fetch-error.js — banner para falha de fetch (data.json indisponível, p.ex.).
// Tenta também restaurar última cópia conhecida do localStorage.

function _escape(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

const STORAGE_KEY = "radar-fidc:data-cache";

export function renderFetchError({ message, onRetry } = {}) {
  const banner = document.createElement("div");
  banner.className = "fetch-error";
  banner.setAttribute("role", "alert");
  banner.innerHTML = `
    <strong>Falha ao carregar dados:</strong> ${_escape(message || "erro desconhecido")}.<br>
    <button class="fetch-error__action" type="button">Recarregar</button>
  `;
  const btn = banner.querySelector("button");
  btn.addEventListener("click", () => {
    if (typeof onRetry === "function") onRetry();
    else window.location.reload();
  });
  return banner;
}

export function cacheData(data) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  } catch {
    /* quota cheia / private mode — silenciar é OK */
  }
}

export function getCachedData() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}
```

**Passo 2: Commit**

```bash
git add assets/js/components/fetch-error.js
git commit -m "feat: Add fetch-error component with localStorage fallback"
```

---

### Tarefa T40 — Integrar trust-bar no `main.js`

**Arquivos:**
- Modificar: `/Users/victorbraga/Downloads/radar-fidc/assets/js/main.js`

**Pré-requisitos:**
- T39

**Passo 1: Editar `main.js`**

Adicionar import e chamada após `boot()`:

```js
import { renderTrustBar } from "./components/trust-bar.js";
```

E dentro de `boot()`, antes do `try { await load() ... }`:

```js
  // Trust bar é independente do load — renderiza com manifest mesmo se data.json falhar.
  renderTrustBar("body").catch((e) => console.warn("[Radar] trust-bar falhou:", e));
```

**Passo 2: Verificação local**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
python3 -m http.server 8000 --bind 127.0.0.1 &
SERVER_PID=$!
sleep 1
curl -s http://127.0.0.1:8000/ | head -10
kill $SERVER_PID 2>/dev/null
```

Abrir `http://127.0.0.1:8000/` no navegador → verificar trust bar no topo com cor + ícone + label.

**Passo 3: Commit**

```bash
git add assets/js/main.js
git commit -m "feat: Mount trust-bar at boot independent of data.json load"
```

---

### Tarefa T41 — Integrar `cacheData` no store

**Arquivos:**
- Modificar: `/Users/victorbraga/Downloads/radar-fidc/assets/js/store.js`

**Pré-requisitos:**
- T40

**Passo 1: Inspecionar `store.js`** (já lido):

```bash
cat /Users/victorbraga/Downloads/radar-fidc/assets/js/store.js | head -30
```

**Passo 2: Adicionar caching opcional**

Onde a função `load()` resolve com `data`, adicionar import e chamada:

```js
import { cacheData } from "./components/fetch-error.js";
```

E após `data = await response.json()` (ou equivalente), antes do return:

```js
cacheData(data);
```

**Passo 3: Commit**

```bash
git add assets/js/store.js
git commit -m "feat: Cache last loaded data.json in localStorage for offline fallback"
```

**Se falhar:**
- Estrutura de `store.js` for diferente do esperado → adaptar mantendo a chamada `cacheData(data)` no caminho de sucesso

---

## Bloco M — Heuristic markers + empty state

### Tarefa T42 — Marcar heurísticas em `pages/macro.js`

**Arquivos:**
- Modificar: `/Users/victorbraga/Downloads/radar-fidc/assets/js/pages/macro.js`

**Pré-requisitos:**
- T41

**Passo 1: Adicionar import e marcação**

Topo do arquivo, junto aos outros imports:

```js
import { markHeuristic } from "../utils/trust.js";
```

Modificar `renderHeader()` para acrescentar marker:

```js
async function renderHeader() {
  const m = Store.macro();
  setText("m-selic",      fmtPct(m.selic));
  setText("m-cdi",        fmtPct(m.cdi));
  setText("m-ipca",       fmtPct(m.ipca, 2));

  // SELIC projetada e IPCA projetada são heurísticas — marcar inline.
  const selicProjMark = await markHeuristic("macro.selic_proj");
  const ipcaProjMark = await markHeuristic("macro.ipca_proj");
  const elSelicProj = document.getElementById("m-selic-proj");
  if (elSelicProj) elSelicProj.innerHTML = `${fmtPct(m.selic_proj)}${selicProjMark}`;
  const elIpcaProj = document.getElementById("m-ipca-proj");
  if (elIpcaProj) elIpcaProj.innerHTML = `${fmtPct(m.ipca_proj)}${ipcaProjMark}`;

  setText("cenario-desc",
    `Cenário atual: ${(m.cenario || "").replace(/_/g, " ").toUpperCase()}. ${m.descricao || ""}`);
}
```

E adicionar `export async function init()` (era sync):

```js
export async function init() { await renderHeader(); }
```

**Passo 2: Verificar local**

Abrir `http://127.0.0.1:8000/#macro` → SELIC* e IPCA* devem ter badge "⚠ heurística".

**Passo 3: Commit**

```bash
git add assets/js/pages/macro.js
git commit -m "feat: Mark selic_proj and ipca_proj as heuristics via inline badge"
```

**Se falhar:**
- `#m-ipca-proj` não existe no HTML → adicionar `<span id="m-ipca-proj"></span>` no `index.html` ao lado de `m-selic-proj`; commit separado

---

### Tarefa T43 — Empty state em `pages/match.js`

**Arquivos:**
- Modificar: `/Users/victorbraga/Downloads/radar-fidc/assets/js/pages/match.js`

**Pré-requisitos:**
- T42

**Passo 1: Adicionar import**

No topo:

```js
import { renderEmptyState } from "../components/empty-state.js";
```

**Passo 2: Substituir o bloco vazio em `renderCards`**

Localizar:

```js
  if (!state.cpf) { wrap.innerHTML = ""; return; }
```

Substituir por:

```js
  if (!state.cpf) {
    wrap.innerHTML = renderEmptyState({
      title: "Selecione um cliente",
      description: "Escolha um cliente no seletor acima para ver as recomendações top-3 personalizadas.",
      suggestions: [
        "Use o seletor de cliente",
        "Ou aplique o filtro por perfil para ver agrupamentos",
      ],
    });
    return;
  }
```

E após `if (!cliente)`:

```js
  if (!cliente) {
    wrap.innerHTML = renderEmptyState({
      title: "Cliente não encontrado",
      description: "O CPF selecionado não retornou nenhum cliente no payload atual.",
      suggestions: ["Limpar filtros", "Selecionar outro cliente"],
    });
    return;
  }
```

**Passo 3: Commit**

```bash
git add assets/js/pages/match.js
git commit -m "feat: Add empty-state messages to match page selectors"
```

---

### Tarefa T44 — Empty state em `pages/clientes.js` (defensivo p/ smoke)

**Arquivos:**
- Modificar: `/Users/victorbraga/Downloads/radar-fidc/assets/js/pages/clientes.js`

**Pré-requisitos:**
- T43

**Passo 1: Ler arquivo**

```bash
head -60 /Users/victorbraga/Downloads/radar-fidc/assets/js/pages/clientes.js
```

**Passo 2: Adicionar bloco condicional onde a tabela é renderizada**

No topo:

```js
import { renderEmptyState } from "../components/empty-state.js";
```

Identificar o ponto em que `Store.clientes.lista()` é usada para popular a tabela. Se vazia, no início do `init()`/`render()`, inserir:

```js
  if (!Store.clientes.lista().length) {
    const wrap = document.getElementById("tbody-clientes")?.closest(".table-wrap") ||
                 document.querySelector("#clientes .card");
    if (wrap) wrap.innerHTML = renderEmptyState({
      title: "Sem clientes cadastrados",
      description: "O pipeline ainda não trouxe dados de clientes para o Gold.",
      suggestions: ["Verificar run mais recente em docs/operacao.md"],
    });
    return;
  }
```

**Passo 3: Commit**

```bash
git add assets/js/pages/clientes.js
git commit -m "feat: Show empty state when clientes payload is empty"
```

---

## Bloco N — Acessibilidade

### Tarefa T45 — Acessibilidade do trust bar e markers

**Arquivos:**
- Já cobertos em T37 (`role="status"`, `aria-live="polite"`)
- Já cobertos em T36 (`role="img"`, `aria-label`)

**Passo 1: Auditoria manual**

Abrir `http://127.0.0.1:8000/` no Chrome DevTools → Lighthouse → Accessibility audit somente.

**Saída esperada:** score ≥ 90 na categoria Accessibility, sem erros críticos de contraste no trust bar (verde, amarelo, vermelho com texto acompanhante).

**Passo 2: Se ajustes forem necessários**

Editar `assets/css/trust.css` para reforçar contraste (cores acima já passam WCAG AA quando texto é em tom escuro sobre fundo claro).

**Passo 3: Commit (se houve ajuste)**

```bash
git add assets/css/trust.css
git commit -m "fix: Increase trust-bar contrast to meet WCAG AA"
```

---

## Bloco O — Documentação operacional

### Tarefa T46 — Escrever `docs/runbook.md` completo

**Arquivos:**
- Modificar: `/Users/victorbraga/Downloads/radar-fidc/docs/runbook.md`

**Pré-requisitos:**
- T45

**Passo 1: Substituir conteúdo**

```markdown
# Runbook operacional — Radar FIDC

## 1. Branch protection esperado em `main`

- Require PR + 1 approval
- Require status checks: `lint-python`, `type-check`, `unit-tests`, `secret-scan`
- Require conversation resolution
- No force-push, no deletion
- Bypass: `github-actions[bot]` para commits do `data-refresh`

## 2. Fluxo diário

1. 06h UTC — Pipeline Databricks roda Bronze→Silver→Gold e (Fase 3) grava `gold/final/_quality/expectations-result.json`
2. 09h UTC — `data-refresh.yml` dispara automaticamente
3. Steps validam: GE → pandera → regression check → smoke Playwright
4. Em sucesso: commit `chore: Regenerate dashboard data ...` + push
5. Em falha: `notify-failures.yml` abre issue com label `data-refresh-failure`

## 3. Diagnóstico por modo de falha

### 3.1 `expectations-result.json` ausente

**Sintoma:** step "Download expectations-result.json" emite `::warning::`.

**O que isso significa:**
- Fase 3 ainda não rodou o notebook `06_great_expectations.py` no Databricks pela primeira vez OU
- Pipeline gravou em `gold/staging/` por falha, não em `gold/final/`

**Ação:**
- Manifesto vai marcar `pipeline_quality_check.status: "not_run"` — NÃO bloqueia o run.
- Confirmar via Azure Portal: `dfdatalakesprint/gold/final/_quality/expectations-result.json`
- Se ausente sistematicamente após Fase 3, escalar com time Databricks.

### 3.2 `overall_success: false` da pipeline GE

**Sintoma:** step "Validate GE overall_success" sai com erro `::error::GE overall_success=false`.

**Ação:**
1. Inspecionar `expectations-result.json` (baixar do ADLS) → identificar suite que falhou
2. Coordenar com time Databricks → re-rodar pipeline OU corrigir source data
3. Bypass emergencial: `gh workflow run data-refresh.yml -f bypass_ge_check=true` (documentar motivo no comentário do issue)

### 3.3 Schema drift (pandera)

**Sintoma:** step "Generate data.json" sai com `SchemaValidationError: Schema <X> falhou em <arquivo>`.

**Ação:**
1. Ler causas (até 5 primeiras) no log do step
2. Confirmar: foi mudança intencional no Gold? (alinhar com time Databricks)
3. Se SIM → abrir PR que atualiza `scripts/lib/schemas.py` para refletir o novo layout
4. Se NÃO → reverter mudança no pipeline OU re-rodar a versão anterior do Gold

### 3.4 Regression check

**Sintoma:** step "Regression check" reporta `result=fail` com razões listadas.

**Ação:**
1. Inspecionar deltas vs HEAD~1 — comportamento esperado?
2. Se SIM (ex: pipeline carregou nova safra que dobrou o universo) → adicionar label `data-regression-ok` no PR OU rodar dispatch com `bypass_regression_check=true`
3. Se NÃO → investigar pipeline; possível bug que perdeu dados

### 3.5 Smoke Playwright

**Sintoma:** step "Playwright smoke" falha com screenshot em `playwright-report/`.

**Ação:**
1. Baixar artefato do run (`gh run download <run-id>`)
2. Abrir screenshot do teste que falhou
3. Diagnosticar: erro JS? `NaN` no payload? regressão de DOM (ID removido)?
4. Fix → commit → re-rodar workflow

## 4. Rotação de Account Key

Trimestralmente:

1. Portal Azure → Storage Accounts → `dfdatalakesprint` → Access keys → Rotate key2
2. Atualizar `AZURE_CONNECTION_STRING` no GitHub Secrets (`Settings → Secrets and variables → Actions`)
3. Atualizar Secret Scope no Databricks (`escopo/AZURECONNSTRING`)
4. Rodar `gh workflow run data-refresh.yml` para validar
5. Após sucesso, rotacionar key1 (mesmo processo)
6. Registrar data da rotação em `docs/operacao.md`

## 5. Adicionar uma heurística ao manifesto

Editar `scripts/lib/trust_manifest.py` → constante `HEURISTIC_FIELDS` → adicionar entrada:

```python
{
  "field": "secao.campo",
  "method": "descrição curta da heurística",
  "replaced_in_fase_3": True,
}
```

E aplicar `markHeuristic("secao.campo")` no JS da página correspondente.

## 6. Remover uma heurística (Fase 3)

Quando a heurística for substituída por dado real:

1. Remover entrada de `HEURISTIC_FIELDS`
2. Remover chamada `markHeuristic(...)` no JS (badge somem automaticamente, mas é melhor limpar)
3. Atualizar `docs/limitacoes_atuais.md`
```

**Passo 2: Commit**

```bash
git add docs/runbook.md
git commit -m "docs: Expand runbook with incident playbooks and rotation procedure"
```

---

### Tarefa T47 — Criar `docs/limitacoes_atuais.md`

**Arquivos:**
- Criar: `/Users/victorbraga/Downloads/radar-fidc/docs/limitacoes_atuais.md`

**Pré-requisitos:**
- T46

**Passo 1: Criar documento**

```markdown
# Limitações atuais — Radar FIDC

> Lista viva. Quando uma heurística é eliminada na Fase 3, mover para a
> seção "Histórico" no final e remover do `data-quality.json` (constante
> `HEURISTIC_FIELDS` em `scripts/lib/trust_manifest.py`).

Referência cruzada com a Seção 5 da spec
(`docs/superpowers/specs/2026-05-14-radar-fidc-polimento-design.md`).

## Heurísticas ativas

| Campo | Localização | Substituição planejada | Esforço |
|-------|-------------|------------------------|---------|
| `macro.selic_proj` | `lib/payload.py:build_macro` (`selic - 0.5`) | Mediana top-5 Focus BCB (notebook `etl_focus.py`) | 2d |
| `macro.ipca_proj`  | `lib/payload.py:build_macro` (`ipca_12m * 0.9`) | Mediana top-5 Focus BCB | (junto com selic) |
| `credit.scoring`   | `scripts/credit_model.py` (single-cohort, sem macro) | Multi-cohort + features macro (cohort_month, selic_at_origination) | 1-2 semanas |
| `matches.engine`   | `scripts/match.py` (sem CVM 555 / segmento) | Filtros hard CVM 555 + status ANBIMA + peso segmento | 3-5d |
| `rating.algorithm` | `scripts/rating.py` (K-Means com `fator_macro` móvel) | Quantis do `SCORE_RISCO` + `INAD_PJ_MEDIANA_HISTORICA` constante | 2d |

## Como ler o trust bar

| Cor | Quando aparece |
|-----|----------------|
| Verde | Última pipeline GE com `overall_success=true` E todas as fontes em `fresh` |
| Amarelo | Pipeline `not_run` OU pelo menos uma fonte em `warn` |
| Vermelho | Pipeline `overall_success=false` OU qualquer fonte em `error` |

Heurísticas **não** afetam a cor do trust bar — aparecem apenas como
markers inline ⚠ ao lado do valor heurístico (decisão de design Fase 2).

## Histórico

(vazio enquanto Fase 3 não inicia)
```

**Passo 2: Commit**

```bash
git add docs/limitacoes_atuais.md
git commit -m "docs: Add limitacoes_atuais.md listing live heuristics and replacements"
```

---

### Tarefa T48 — Criar template inicial `docs/operacao.md`

**Arquivos:**
- Criar: `/Users/victorbraga/Downloads/radar-fidc/docs/operacao.md`

**Pré-requisitos:**
- T47

**Passo 1: Criar documento template**

```markdown
<!-- AUTO-GENERATED. Não editar a mão entre os marcadores BEGIN/END. -->

# Operação — Radar FIDC

> Atualizado automaticamente pelo workflow `data-refresh.yml` ao final de cada
> run com sucesso (via `scripts/update_operacao_doc.py`).

## Último run

<!-- BEGIN:last-run -->
- **Timestamp:** —
- **Duração:** —
- **Bytes:** —
- **Linhas (fidcs/matches/clientes/credit):** —
<!-- END:last-run -->

## Últimos 14 runs

<!-- BEGIN:history -->
| Data (UTC) | Status | Duração | Notas |
|------------|--------|---------|-------|
| — | — | — | — |
<!-- END:history -->

## Issues abertos de `data-refresh-failure`

<!-- BEGIN:open-issues -->
Nenhum.
<!-- END:open-issues -->

## Rotação de Account Key

| Data | Quem | key1/key2 |
|------|------|-----------|
| 2026-05-13 | (Fase 0) | key1 |
```

**Passo 2: Commit**

```bash
git add docs/operacao.md
git commit -m "docs: Add operacao.md template with auto-update markers"
```

---

### Tarefa T49 — Criar `scripts/update_operacao_doc.py`

**Arquivos:**
- Criar: `/Users/victorbraga/Downloads/radar-fidc/scripts/update_operacao_doc.py`

**Pré-requisitos:**
- T48

**Passo 1: Criar script**

```python
#!/usr/bin/env python3
"""Atualiza `docs/operacao.md` no final de runs do `data-refresh.yml`.

Substitui apenas o conteúdo entre marcadores `<!-- BEGIN:last-run -->` e
`<!-- END:last-run -->`. Resto do documento permanece intacto.

Uso (no workflow):
    python scripts/update_operacao_doc.py \
        --data data.json \
        --quality data-quality.json \
        --duration-seconds 142
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.logger import get_logger  # noqa: E402

log = get_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
OPERACAO_PATH = REPO_ROOT / "docs" / "operacao.md"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _replace_block(content: str, marker: str, replacement: str) -> str:
    pattern = re.compile(
        rf"(<!-- BEGIN:{re.escape(marker)} -->)(.*?)(<!-- END:{re.escape(marker)} -->)",
        re.DOTALL,
    )
    return pattern.sub(rf"\1\n{replacement}\n\3", content)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--quality", required=True, type=Path)
    parser.add_argument("--duration-seconds", type=int, default=0)
    args = parser.parse_args()

    if not OPERACAO_PATH.exists():
        log.warn("operacao_missing", path=str(OPERACAO_PATH))
        return 0

    data = json.loads(args.data.read_text(encoding="utf-8"))
    manifest = json.loads(args.quality.read_text(encoding="utf-8"))

    size = args.data.stat().st_size
    row_counts = manifest.get("row_counts", {})

    last_run = (
        f"- **Timestamp:** {_now_iso()}\n"
        f"- **Duração:** {args.duration_seconds}s\n"
        f"- **Bytes:** {size:,}\n"
        f"- **Linhas (fidcs/matches/clientes/credit):** "
        f"{row_counts.get('fidcs', '?')}/{row_counts.get('matches', '?')}/"
        f"{row_counts.get('clientes', '?')}/{row_counts.get('credit_empresas', '?')}"
    )

    content = OPERACAO_PATH.read_text(encoding="utf-8")
    new_content = _replace_block(content, "last-run", last_run)
    if new_content != content:
        OPERACAO_PATH.write_text(new_content, encoding="utf-8")
        log.info("operacao_updated", section="last-run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Passo 2: Adicionar step ao `data-refresh.yml`** (modificação)

Em `.github/workflows/data-refresh.yml`, antes do step "Commit if changed", adicionar:

```yaml
      - name: Update operacao.md
        run: |
          python scripts/update_operacao_doc.py \
            --data data.json \
            --quality data-quality.json \
            --duration-seconds ${SECONDS:-0}
```

E no step "Commit if changed", incluir `docs/operacao.md`:

```bash
git add data.json data-quality.json docs/operacao.md
```

**Passo 3: Validar local**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
python scripts/update_operacao_doc.py --data data.json --quality data-quality.json --duration-seconds 100
head -20 docs/operacao.md
```

**Saída esperada:** bloco `BEGIN:last-run` preenchido com timestamp atual.

**Passo 4: Commit**

```bash
git add scripts/update_operacao_doc.py .github/workflows/data-refresh.yml docs/operacao.md
git commit -m "feat: Auto-update docs/operacao.md after each successful data-refresh"
```

---

## Bloco P — Code Review final

### Tarefa T50 — Code review final + smoke E2E manual

**Pré-requisitos:**
- T35–T49 commitadas

**Passo 1:** Dispatch dos 7 reviewers via `ring:requesting-code-review` cobrindo Blocos L, M, N, O (`assets/`, `docs/runbook.md`, `docs/limitacoes_atuais.md`, `docs/operacao.md`, `scripts/update_operacao_doc.py`).

**Passo 2:** Tratar findings por severidade conforme padrão.

**Passo 3: Smoke E2E manual**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
source .venv-fase2/bin/activate
# 1. Regerar localmente
python scripts/generate_dashboard_data.py --regression-result pass --smoke-result pass
# 2. Servir
python3 -m http.server 8000 --bind 127.0.0.1 &
sleep 1
# 3. Rodar Playwright
npx playwright test --reporter=line
# 4. Inspecionar manifesto
cat data-quality.json | python3 -m json.tool
# Cleanup
kill %1 2>/dev/null
```

**Saída esperada:**
- Generator emite logs `schema_validation_ok` para cada source
- `data-quality.json` válido com `pipeline_quality_check.status: "not_run"` e 5 heurísticas
- Playwright: 6 PASSED

**Passo 4:** Dispatch manual do `data-refresh.yml` real (após merge para `main`):

```bash
gh workflow run data-refresh.yml
sleep 60
gh run watch
```

**Saída esperada:** run com `success`, `data.json` e `data-quality.json` atualizados em `main`, `docs/operacao.md` com bloco `last-run` preenchido.

**Passo 5: Validar dashboard em produção**

Abrir `https://victorsouza14.github.io/radar-fidc/` → confirmar:
- Trust bar visível no topo, cor adequada
- Aba Macro: SELIC* / IPCA* com badge ⚠
- Aba Match: empty state amigável quando nenhum cliente selecionado
- Lighthouse: Accessibility ≥ 90

**Passo 6:** Se tudo OK, encerrar Fase 2. Não commitar (validação final).

**Se falhar:**
- Lighthouse < 90 → ajustar contraste/ARIA, novo commit
- Workflow falha por permissões → checar `permissions: contents: write` no `data-refresh.yml`
- Trust bar não aparece → checar `cache: no-store` no fetch e cache do GitHub Pages

---

## Critérios de "Fase 2 completa"

- [ ] Todos os 50 tasks commitados em `main`
- [ ] CI verde em todos os 4 jobs (`ci.yml`)
- [ ] `data-refresh.yml` rodou com sucesso pelo menos 1x em produção
- [ ] `data-quality.json` presente na raiz e válido
- [ ] Trust bar renderiza no GitHub Pages com cor correta
- [ ] Markers ⚠ aparecem em SELIC* e IPCA*
- [ ] Empty state aparece na página Match quando nenhum cliente selecionado
- [ ] Playwright smoke: 6 PASSED no CI
- [ ] `docs/runbook.md`, `docs/limitacoes_atuais.md`, `docs/operacao.md` presentes
- [ ] Lighthouse Accessibility ≥ 90 nas 6 páginas
- [ ] Zero Critical/High/Medium dos 3 code reviews
- [ ] `notify-failures.yml` testado (criar PR sintético com falha controlada — opcional)

---

## Notas para o executor

- **Idempotência:** rodar `python scripts/generate_dashboard_data.py` 2x não muda o estado final (cache ETag faz cache hit). `update_operacao_doc.py` sobrescreve apenas o bloco delimitado.
- **Defensividade GE:** o blob `expectations-result.json` será criado pela Fase 3. Até lá, manifesto marca `pipeline_quality_check.status: "not_run"` — comportamento esperado, não é bug.
- **Smoke timeout:** se Playwright falhar com timeout intermitente, o `retries: 2` cobre; se persistir, aumentar `timeout: 30_000` ou granularizar `await page.waitForSelector(...)` em vez de `networkidle`.
- **Branch protection:** após Fase 2, ativar manualmente em `Settings → Branches → Add rule` para `main` exigindo os 4 status checks do `ci.yml`. Não está automatizado.
- **Renovação de Account Key:** próxima rotação trimestral cai em 2026-08-13 (registrar em `docs/operacao.md`).
- **TODOs/FIXMEs gerados pelos reviewers:** ficam como dívida técnica explícita; criar issue agregadora ao final ("Fase 2 — Low/Cosmetic findings to address") referenciando linhas.

---

## Resumo das mudanças por arquivo

**Novos:**
- `requirements-dev.txt`, `pyproject.toml`, `package.json`, `tsconfig.json`, `playwright.config.ts`
- `scripts/lib/{schemas,trust_manifest,regression_check}.py`
- `scripts/{run_regression_check.py,run_smoke.sh,update_operacao_doc.py}`
- `scripts/tests/{__init__,conftest,test_schemas,test_regression_check,test_trust_manifest,test_azure_io,test_formatters_mask}.py`
- `tests/e2e/dashboard.spec.ts`
- `.github/workflows/{ci,notify-failures}.yml`
- `assets/css/trust.css`
- `assets/js/components/{trust-bar,empty-state,fetch-error}.js`
- `assets/js/utils/trust.js`
- `docs/{runbook,limitacoes_atuais,operacao}.md`
- `data-quality.json` (commitado pelo workflow)

**Modificados:**
- `scripts/lib/io_utils.py` (integra pandera)
- `scripts/generate_dashboard_data.py` (emite manifesto)
- `.github/workflows/data-refresh.yml` (hardening)
- `.gitignore` (artefatos de teste/node)
- `README.md` (workflows + bypasses)
- `assets/css/main.css` (import trust.css)
- `assets/js/main.js` (mount trust bar)
- `assets/js/store.js` (cache localStorage)
- `assets/js/pages/{macro,match,clientes}.js` (markers + empty state)
