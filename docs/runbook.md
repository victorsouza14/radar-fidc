# Runbook operacional — Radar FIDC

## 0. Introdução

O Radar FIDC é um dashboard estático servido a partir deste repositório. Ele lê `data.json` e `data-quality.json` gerados diariamente pelo workflow `data-refresh.yml`, que consome a camada Gold do data lake `dfdatalakesprint`. Este runbook é o playbook de operação e resposta a incidentes: leia-o quando o workflow falhar, antes de rotacionar credenciais, ou quando precisar evoluir o manifesto de qualidade.

Mantenha este documento atualizado sempre que um novo modo de falha aparecer ou uma heurística for adicionada/removida.

---

## 1. Branch protection esperado em `main`

<!-- branch-protection-checklist -->

Branch protection está **pendente de ativação manual** no GitHub. A ativação não pode ser feita por API — o GitHub não expõe configuração confiável via REST para `Allow specified actors to bypass`, que é necessária para o `github-actions[bot]` continuar commitando `data.json` diariamente sem abrir PR.

Depois que o PR que adiciona `.github/workflows/ci.yml` for mergeado em `main`, ative as regras abaixo em **Settings → Branches → Branch protection rules** para `main`.

### Status checks obrigatórios

Marque **Require status checks to pass before merging** e selecione os 5 checks abaixo (os nomes correspondem exatamente aos `name:` dos jobs em `ci.yml`):

- [ ] `lint-python` — ruff lint
- [ ] `lint-python-format` — ruff format check
- [ ] `type-check` — mypy
- [ ] `unit-tests` — pytest
- [ ] `secret-scan` — gitleaks

Também marque **Require branches to be up to date before merging**.

### Demais regras recomendadas

- [ ] **Require a pull request before merging** — 1 aprovação mínima
- [ ] **Require conversation resolution before merging**
- [ ] **Do not allow bypassing the above settings** — desativado APENAS para permitir o bypass abaixo
- [ ] **Allow specified actors to bypass required pull requests** → adicionar `github-actions[bot]` (necessário para `data-refresh.yml` commitar `data.json` direto em `main` sem abrir PR)
- [ ] **Restrict who can push to matching branches** → manter vazio (qualquer collaborator pode abrir PR; só não pode push direto)
- [ ] **Do not allow force pushes**
- [ ] **Do not allow deletions**

### Como validar

Depois de ativar:

1. Abrir PR de teste em branch `chore/test-branch-protection` com mudança trivial.
2. Conferir que os 5 checks aparecem como **Required** no rodapé do PR.
3. Conferir que merge só fica liberado quando todos passam + 1 approval.
4. Aguardar o próximo run agendado de `data-refresh.yml` (9h UTC) ou disparar `workflow_dispatch` e confirmar que o push do bot em `main` funciona (i.e., o bypass está corretamente configurado).

---

## 2. Fluxo diário

Sequência completa do `data-refresh.yml`, disparado pelo cron 9h UTC (e por `workflow_dispatch` manual):

```
06h UTC ── Databricks roda Bronze→Silver→Gold
           └─ grava gold/final/_quality/expectations-result.json (Fase 3)

09h UTC ── data-refresh.yml acorda
           │
           ├─ 1. Checkout (fetch-depth: 2, para regression check vs HEAD~1)
           ├─ 2. Setup Python 3.11 + cache pip + install requirements.txt
           ├─ 3. Login ADLS via AZURE_CONNECTION_STRING
           ├─ 4. Download expectations-result.json (gold/final/_quality/)
           ├─ 5. Validate GE overall_success (bypassável)
           ├─ 6. Generate data.json (lê ADLS, valida pandera schemas)
           ├─ 7. Regression check vs HEAD~1 (bypassável)
           ├─ 8. Playwright smoke (6 páginas)
           ├─ 9. Update docs/operacao.md (script update_operacao_doc.py)
           ├─ 10. Commit + push se algo mudou
           └─ 11. Em falha → notify-failures.yml abre issue
```

Em sucesso, três artefatos são commitados em `main` pelo `github-actions[bot]`: `data.json`, `data-quality.json` e `docs/operacao.md`. Em falha, um issue com label `data-refresh-failure` é aberto automaticamente e auto-fecha quando o próximo run passar.

---

## 3. Diagnóstico por modo de falha

Cada subseção segue o mesmo padrão: **sintoma**, **o que significa**, **ação**.

### 3.1 `expectations-result.json` ausente

**Sintoma:** step "Download expectations-result.json" emite `::warning::` e segue adiante. Manifesto `data-quality.json` registra `pipeline_quality_check.status: "not_run"`.

**O que significa:** ou a Fase 3 do projeto ainda não habilitou o notebook `06_great_expectations.py` no Databricks, ou a pipeline gravou em `gold/staging/` por falha interna e não promoveu para `gold/final/`.

**Ação:**

1. Este caso **não bloqueia** o run — o manifesto registra `status: "not_run"` mas o dashboard atualiza normalmente.
2. Confirmar no Azure Portal: `dfdatalakesprint → containers → gold → final/_quality/expectations-result.json` existe?
3. Se a ausência for sistemática após a Fase 3 entrar em produção, escalar com o time Databricks (canal `#radar-fidc-pipeline`).

### 3.2 `overall_success: false` da pipeline GE

**Sintoma:** step "Validate GE overall_success" termina com `::error::GE overall_success=false` e o workflow falha.

**O que significa:** a pipeline Databricks rodou mas pelo menos uma expectation falhou. O dado provavelmente foi gravado em `gold/staging/`, não em `gold/final/`, então o `data.json` ficaria com dado velho mesmo se forçássemos a continuação.

**Ação:**

1. Baixar o `expectations-result.json` do staging:
   ```bash
   az storage blob download \
     --account-name dfdatalakesprint \
     --container-name gold \
     --name staging/_quality/expectations-result.json \
     --file /tmp/ge.json
   ```
2. Identificar a suite que falhou (`results[*].success: false`).
3. Coordenar com o time Databricks: foi mudança de schema legítima, drift de dado-fonte, ou bug da pipeline?
4. Aguardar re-run da pipeline. Em geral, esperar o próximo ciclo (24h) resolve.
5. **Bypass emergencial** (use com critério e documente o motivo no comentário do issue):
   ```bash
   gh workflow run data-refresh.yml -f bypass_ge_check=true
   ```

### 3.3 Schema drift (pandera)

**Sintoma:** step "Generate data.json" sai com `SchemaValidationError: Schema <X> falhou em <arquivo>` e lista até 5 violações.

**O que significa:** o Gold mudou de formato — coluna nova, coluna removida, tipo alterado, range estourado. O `scripts/lib/schemas.py` reflete o contrato que o frontend espera; pandera fail-fast antes do dashboard quebrar.

**Ação:**

1. Ler as 5 primeiras causas no log do step para localizar o campo problemático.
2. Confirmar com o time Databricks: a mudança foi intencional?
3. **Se sim:** abrir PR atualizando `scripts/lib/schemas.py` para refletir o novo layout. Adicionar coluna nova como `Optional` durante a transição, depois promover para required em PR posterior.
4. **Se não:** reverter a mudança no pipeline Databricks ou re-rodar a versão anterior do Gold. NÃO altere `schemas.py` para "fazer passar" — é o sinal funcionando como projetado.

### 3.4 Regression check (Δ > 10% fidcs ou > 20% matches)

**Sintoma:** step "Regression check" reporta `result=fail` com razões listadas (ex: `fidcs_delta=-12.3%`, `matches_delta=+27.1%`).

**O que significa:** o número de linhas mudou mais do que o esperado entre runs consecutivos. Pode ser dado novo legítimo (safra trimestral chegou, nova fonte ANBIMA) ou bug (perda de dados no pipeline).

**Ação:**

1. Inspecionar os deltas vs `HEAD~1`: o comportamento é esperado?
2. **Se sim** (ex: pipeline carregou nova safra que dobrou o universo): rodar dispatch com bypass — `gh workflow run data-refresh.yml -f bypass_regression_check=true` — OU adicionar label `data-regression-ok` no PR equivalente.
3. **Se não:** investigar pipeline antes de bypassar. Provável bug de filtro ou join que perdeu linhas. Trate como incidente, não como inconveniente.

### 3.5 Smoke Playwright falhou

**Sintoma:** step "Playwright smoke" falha; artefato `playwright-report/` disponível para download no run.

**O que significa:** uma das 6 páginas do dashboard quebrou no `chromium` headless. Tipicamente erro de JS no console, `NaN`/`undefined` no payload, ou ID de DOM removido sem atualizar o teste.

**Ação:**

1. `gh run download <run-id> --name playwright-report`
2. Abrir `playwright-report/index.html` no navegador e localizar o teste falhado.
3. Inspecionar screenshot + trace.zip — erro de console? elemento ausente?
4. Reproduzir local: `python3 -m http.server 8000` + `npx playwright test`.
5. Corrigir frontend (ou teste, se o teste é que está desatualizado), abrir PR, re-rodar workflow após merge.

---

## 4. Rotação de Account Key

Cadência: **trimestral**. Responsável: maintainer principal do repositório (atualmente `victor.braga@brandlovers.ai`).

A storage account `dfdatalakesprint` expõe duas keys (key1 e key2). O processo é rotação alternada — você sempre tem uma key ativa e válida enquanto a outra é girada.

**Passos (rotação de key2 primeiro, depois key1):**

1. **Portal Azure:** `Storage Accounts → dfdatalakesprint → Security + networking → Access keys → Rotate key2`.
2. Copiar a nova connection string completa (não só a key).
3. **GitHub Secrets:** `Settings → Secrets and variables → Actions → AZURE_CONNECTION_STRING → Update value`. Colar a nova connection string.
4. **Databricks Secret Scope:** atualizar `escopo/AZURECONNSTRING` com a nova connection string:
   ```bash
   databricks secrets put-secret escopo AZURECONNSTRING
   ```
5. **Validar:** `gh workflow run data-refresh.yml`. Aguardar conclusão; deve passar.
6. **Repetir** o processo para key1 (Rotate key1, atualizar Secrets, validar).
7. **Registrar** a rotação na tabela "Rotação de Account Key" em `docs/operacao.md` (data, quem, qual key).

Se um run quebrar imediatamente após a rotação com `AuthorizationFailure`, é quase certo que algum secret não foi atualizado em sincronia. Reverter NÃO é possível (a key antiga já foi invalidada) — o caminho é completar a atualização do secret faltante e re-rodar.

---

## 5. Adicionar uma heurística ao manifesto

Sempre que um novo cálculo aproximado entrar no payload (ex: nova projeção macro derivada de fórmula), registre-o no manifesto para auditoria de qualidade.

**Passo 1:** Editar `scripts/lib/trust_manifest.py`, constante `HEURISTIC_FIELDS`, adicionar:

```python
{
    "field": "secao.campo",                    # path dentro de data.json
    "method": "descrição curta da heurística", # ex: "selic - 0.5"
    "replaced_in_fase_3": True,                # False se for permanente
}
```

**Passo 2:** Atualizar `scripts/lib/schemas.py` se a coluna correspondente passar a aceitar o valor heurístico (geralmente nenhuma mudança — heurísticas vivem em campos já permitidos).

**Passo 3:** O frontend não consome `heuristic_fields` atualmente; o manifesto serve apenas para auditoria server-side. Nenhuma alteração no JS é necessária ao adicionar a heurística.

**Passo 4:** Adicionar a heurística a `docs/limitacoes_atuais.md` na tabela "Heurísticas ativas", indicando a substituição planejada e a fase de eliminação.

---

## 6. Remover uma heurística (Fase 3)

Quando uma heurística for substituída por dado real (ex: projeções Focus do BCB substituindo `selic - 0.5`):

1. Remover a entrada de `HEURISTIC_FIELDS` em `scripts/lib/trust_manifest.py`.
2. Atualizar `scripts/lib/schemas.py` se o novo cálculo introduz campos novos (ex: `proj_source: "bcb_focus_top5"`).
3. Mover a entrada para a seção "Histórico" de `docs/limitacoes_atuais.md`, registrando data, qual heurística saiu e o que a substituiu.
4. Rodar `python scripts/generate_dashboard_data.py` local e validar que o manifesto `data-quality.json` perdeu a entrada em `heuristic_fields` e ganhou correspondente em `replaced_heuristics`.

---

## Próximos passos

- [Limitações atuais](limitacoes_atuais.md) — lista viva das heurísticas conhecidas e plano de eliminação
- [Operação](operacao.md) — histórico auto-atualizado de runs e rotações
- [Arquitetura](arquitetura.md) — visão geral do sistema
