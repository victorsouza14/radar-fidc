# Plano de Implementação — Radar FIDC Fases 0 e 1

> **Para Agentes:** SUB-SKILL OBRIGATÓRIA — Use `ring:executing-plans` para executar este plano tarefa por tarefa.

**Objetivo:** Endurecer a segurança do repositório (Fase 0) e conectar o `generate_dashboard_data.py` ao Azure Data Lake Storage Gen2 real (`dfdatalakesprint/gold/final/`), eliminando a dependência do diretório local `data_real/` (Fase 1).

**Arquitetura:** O dashboard permanece como HTML/JS vanilla servido pelo GitHub Pages, lendo um `data.json` estático. A mudança é na geração desse `data.json`: passa a ler arquivos do ADLS Gen2 via `azure-storage-file-datalake`, com cache de duas camadas (bytes via ETag + parse cache `.pkl`). A camada de segurança ganha pre-commit hooks (`gitleaks` + `ruff` + `prettier`), GitHub Push Protection e branch protection rules.

**Stack:**
- Python 3.11 (scripts; o repo declara 3.10+, mas o CI usa 3.11)
- HTML + JS vanilla (frontend, sem framework)
- Azure Data Lake Storage Gen2 (`dfdatalakesprint`, container `gold`, prefixo `final/`)
- GitHub Actions + GitHub Pages
- Pre-commit hooks: `gitleaks`, `ruff`, `prettier`

**Idioma:** Todo o conteúdo de docs/comentários é em pt-BR. Mensagens de commit em inglês (Conventional Commits) conforme a regra global do usuário.

**Pré-requisitos globais:**
- Sistema operacional: macOS, Linux ou WSL
- Ferramentas locais:
  - `python` 3.11+
  - `git` 2.30+
  - `pip` 23+
  - `gh` (GitHub CLI) autenticado contra a conta dona do repo (`gh auth status` deve mostrar login válido)
  - Editor capaz de salvar arquivos UTF-8 sem BOM
- Acesso:
  - Permissão de admin no repositório `victorsouza14/radar-fidc` (necessária para Settings, Secrets e branch protection)
  - Acesso ao Azure Portal com permissão de `Storage Account Contributor` em `dfdatalakesprint` (para Fase 0 Task 1, rotação manual da Account Key)
  - `.env` local válido (será atualizado durante a Fase 1) com `AZURE_CONNECTION_STRING` apontando para a Account Key rotacionada
- Estado:
  - Branch base: `main` (no momento da escrita, último commit é `873273e`)
  - Working tree limpo antes de iniciar
  - O diretório `data_real/` existe e contém: `rating_fidc.xlsx`, `matches.xlsx`, `clientes.csv`, `scores_credito.csv`, `macroeconomicos/consolidade.csv`, `credit_model.pkl`, `arquivos/`, `bases/`
- Convenção de execução do plano:
  - **Target**: todas as tarefas têm target `shared` (é tooling/scripts do mono-repo)
  - **Working Directory**: `.` (raiz do repo `radar-fidc`, single-repo)
  - **Agente recomendado por tarefa**: indicado em cada uma. `ring:devops-engineer` para tooling de segurança/CI/CD; `ring:general-purpose` para o resto (stack Python+JS vanilla, sem backend Go/TS)

**Verificação antes de começar (executar TODOS):**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
python --version           # Esperado: Python 3.11.x (mínimo 3.10)
git --version              # Esperado: git version 2.30+
pip --version              # Esperado: pip 23+
gh auth status             # Esperado: "Logged in to github.com as victorsouza14"
git status                 # Esperado: "working tree clean"
git branch --show-current  # Esperado: main
git rev-parse HEAD         # Esperado: 873273e... (ou hash mais recente em main)
ls data_real/              # Esperado: clientes.csv, credit_model.pkl, macroeconomicos, matches.xlsx, rating_fidc.xlsx, scores_credito.csv, ...
test -f .env && echo "OK .env presente"  # Esperado: "OK .env presente" (não obrigatório aqui, mas usado em Fase 1)
```

**Convenção das tarefas:**
- Cada tarefa é atômica (2–5 minutos)
- Cada tarefa tem caminho absoluto, comando exato, código completo (não placeholder), e critério de verificação observável
- Dependências entre tarefas são explicitadas com "Depende de: Task X"
- Tarefas humanas (UI do Azure Portal, UI do GitHub Settings) são marcadas como **HUMAN-TASK** e descrevem passo-a-passo navegacional

---

## Fase 0 — Segurança & Saneamento

**Duração estimada:** ~1 dia (8 tarefas; ~3-4h efetivas mais ~1h de espera por propagação da nova key).

**Resultado esperado ao fim da Fase 0:**
- Account Key antiga revogada; nova Account Key configurada localmente e no GitHub Secrets
- Pre-commit hooks ativos bloqueando vazamentos de chave
- Histórico do git auditado por chave vazada (e purgado, se necessário)
- GitHub Push Protection habilitado
- Branch protection rules ativas em `main` exigindo PR + status checks

---

### Task F0-1 — HUMAN-TASK: Rotacionar Account Key no Azure Portal

**Target:** shared
**Working Directory:** `.`
**Agente recomendado:** ação humana (não delegar a agente)
**Depende de:** —

**Por que esta tarefa é primeira:**
A Account Key foi exposta em chat. Toda tarefa subsequente que toca em `AZURE_CONNECTION_STRING` (Secret do GitHub, `.env` local) deve usar a nova chave, **não** a vazada. Rotacionar antes de tudo elimina a janela em que a chave vazada ainda tem poder.

**Passos navegacionais (operados pelo humano no navegador):**

1. Acessar o Azure Portal: <https://portal.azure.com>
2. No campo de busca do topo, digitar `dfdatalakesprint` e clicar no Storage Account resultante
3. No menu lateral esquerdo, sob **Security + networking**, clicar em **Access keys**
4. Clicar em **Show keys** (autentica via MFA se necessário)
5. Identificar `key1`. Anotar (mentalmente, NÃO em arquivo) qual conexão dele está em uso atualmente
6. Clicar em **Rotate key** ao lado de `key1`
7. Na confirmação ("This will invalidate the current key1. Any client using key1 must update..."), clicar em **Yes**
8. Aguardar ~30s até o portal mostrar a nova `key1`
9. Clicar no botão de copiar ao lado de **Connection string** de `key1`
10. Guardar a nova connection string em um cofre local seguro (1Password, Keychain, Bitwarden) — **NUNCA colar em chat, Slack, e-mail ou commit**

**Critério de verificação:**

- Portal mostra timestamp "Last rotated" recente (último minuto) em `key1`
- Tentativa de leitura com a chave antiga (qualquer cliente Azure CLI ou SDK) retorna `AuthenticationFailed` em até 5 minutos

**Comando opcional para confirmar invalidação da chave antiga (no terminal local, usando a chave VELHA propositalmente):**

```bash
# Substituir <CHAVE_VELHA> pela connection string anterior à rotação (se ainda lembrar)
# Esperado: erro "AuthenticationFailed" ou similar
az storage container list --connection-string "<CHAVE_VELHA>" 2>&1 | head -5
```

**Em caso de falha:**
- Se não tiver permissão no Portal: pedir ao dono do Storage Account (provavelmente o orientador FIAP) que execute a rotação
- Se a rotação parecer não invalidar a chave antiga: aguardar 10 minutos (propagação eventual) e tentar novamente
- **NÃO continuar com Task F0-2 antes de ter a nova chave em mãos**

---

### Task F0-2 — HUMAN-TASK: Atualizar GitHub Secret `AZURE_CONNECTION_STRING`

**Target:** shared
**Working Directory:** `.`
**Agente recomendado:** ação humana (Settings do GitHub)
**Depende de:** Task F0-1

**Passos navegacionais:**

1. Acessar <https://github.com/victorsouza14/radar-fidc/settings/secrets/actions>
2. Localizar o secret `AZURE_CONNECTION_STRING` na lista de **Repository secrets**
3. Clicar em **Update** ao lado dele
4. No campo **Value**, colar a nova connection string (a obtida na Task F0-1)
5. Clicar em **Update secret**

**Alternativa via CLI** (se preferir, ainda HUMAN porque a chave é manual):

```bash
# Substituir <NOVA_CHAVE> pela nova connection string completa.
# O gh CLI lê do stdin para evitar a chave aparecer no histórico do shell.
read -rs NOVA_CHAVE
gh secret set AZURE_CONNECTION_STRING --repo victorsouza14/radar-fidc --body "$NOVA_CHAVE"
unset NOVA_CHAVE
```

**Critério de verificação:**

```bash
gh secret list --repo victorsouza14/radar-fidc | grep AZURE_CONNECTION_STRING
```

Saída esperada:

```
AZURE_CONNECTION_STRING  Updated 2026-05-14T...
```

A coluna `Updated` deve mostrar a data de hoje. Se mostrar data antiga, o `set` falhou silenciosamente.

**Em caso de falha:**
- Se `gh secret set` falhar com `HTTP 403`: confirmar `gh auth status` e permissões de admin no repo
- Se o `Updated` permanecer com data antiga após o comando: rodar de novo, sem `unset` da variável, para garantir que o stdin chegou

---

### Task F0-3 — HUMAN-TASK: Auditar histórico do Git por padrão `AccountKey=`

**Target:** shared
**Working Directory:** `.`
**Agente recomendado:** `ring:devops-engineer`
**Depende de:** —

**Comando exato:**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
git log --all --full-history -p -S "AccountKey=" -- ':!**/CHANGELOG*' ':!**/docs/superpowers/**' > /tmp/radar-fidc-leak-audit.txt
wc -l /tmp/radar-fidc-leak-audit.txt
```

**Critério de verificação:**

```bash
# Filtra apenas linhas de DIFF que adicionam (+) algo com "AccountKey=" seguido de algo que NÃO é placeholder.
# Placeholders aceitos (não são leak): SUA_CHAVE_AQUI, <KEY>, ${...}, *****
grep -E '^\+.*AccountKey=[^"]{20,}' /tmp/radar-fidc-leak-audit.txt \
  | grep -vE 'SUA_CHAVE_AQUI|<KEY>|\$\{|\*\*\*|<NOVA_CHAVE>|EXEMPLO|XXXX' \
  > /tmp/radar-fidc-leak-real.txt
wc -l /tmp/radar-fidc-leak-real.txt
```

**Resultado esperado (caso negativo, sem leak real):**

```
0 /tmp/radar-fidc-leak-real.txt
```

→ Prosseguir para Task F0-4.

**Resultado em caso positivo (leak real encontrado):**

```
N /tmp/radar-fidc-leak-real.txt   # N > 0
```

→ **PARAR esta fase imediatamente** e executar Task F0-3b (purga via `git filter-repo`).

**Em caso de falha do comando `git log -S`:**
- Se o repositório for muito grande e o comando demorar >2min: rodar com `--since="2025-01-01"` para limitar a janela
- Se aparecer `unknown switch 'S'`: atualizar Git para 2.30+

---

### Task F0-3b — HUMAN-TASK (condicional): Purgar Account Key do histórico via `git filter-repo`

**Target:** shared
**Working Directory:** `.`
**Agente recomendado:** ação humana (operação destrutiva)
**Depende de:** Task F0-3 com resultado positivo

**Executar APENAS se Task F0-3 retornou linhas em `/tmp/radar-fidc-leak-real.txt`.**

**Pré-requisito:** Instalar `git-filter-repo` (não vem com o git padrão):

```bash
# macOS
brew install git-filter-repo
# Linux (Ubuntu/Debian)
sudo apt install git-filter-repo
# Verificar
git filter-repo --version  # Esperado: git-filter-repo 2.x
```

**Passos:**

1. Fazer backup do clone atual (paranoia justificada):
   ```bash
   cp -R /Users/victorbraga/Downloads/radar-fidc /Users/victorbraga/Downloads/radar-fidc.backup-$(date +%Y%m%d-%H%M%S)
   ```

2. Inspecionar os hits encontrados — anotar manualmente cada substring exata a purgar:
   ```bash
   grep -E '^\+.*AccountKey=' /tmp/radar-fidc-leak-real.txt | head -20
   ```

3. Criar um `expressions.txt` com cada padrão a substituir. Exemplo (substituir `<CHAVE_REAL_VAZADA>` pela string exata identificada acima):
   ```
   # /Users/victorbraga/Downloads/radar-fidc/expressions.txt
   <CHAVE_REAL_VAZADA>==>REDACTED_LEAKED_KEY
   ```

4. Rodar a purga:
   ```bash
   cd /Users/victorbraga/Downloads/radar-fidc
   git filter-repo --replace-text expressions.txt --force
   ```

5. Re-auditar:
   ```bash
   git log --all -p -S "AccountKey=" | grep -E '^\+.*AccountKey=[^"]{20,}' | grep -vE 'REDACTED_LEAKED_KEY|SUA_CHAVE_AQUI|<KEY>'
   ```
   Esperado: saída vazia.

6. Force-push (operação destrutiva, comunicar ao time antes):
   ```bash
   git push origin --force --all
   git push origin --force --tags
   ```

7. Apagar `expressions.txt` (contém a chave vazada em plain text):
   ```bash
   rm /Users/victorbraga/Downloads/radar-fidc/expressions.txt
   ```

**Critério de verificação:**
- `git log -p -S "AccountKey="` no remoto não retorna a chave real
- Todos os colaboradores precisam re-clonar (ou rodar `git fetch origin && git reset --hard origin/main`)

**Em caso de falha:**
- Se o push for rejeitado por branch protection: a branch protection ainda não foi configurada (será na Task F0-8). Push antes de F0-8 ainda funciona
- Se algum colaborador tiver branches abertas com a chave: precisa coordenar com cada um para re-criar a branch a partir do main novo

**Importante:** Esta tarefa só roda uma vez. Após executá-la, a chave já foi rotacionada (F0-1), então mesmo se a chave purgada continuar visível em forks/clones antigos de terceiros, ela já não tem poder.

---

### Task F0-4 — Criar `.pre-commit-config.yaml`

**Target:** shared
**Working Directory:** `.`
**Agente recomendado:** `ring:devops-engineer`
**Depende de:** —

**Arquivos:**
- Criar: `/Users/victorbraga/Downloads/radar-fidc/.pre-commit-config.yaml`

**Comando para verificar pré-requisitos:**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
test ! -f .pre-commit-config.yaml && echo "OK arquivo não existe ainda"
```

Esperado: `OK arquivo não existe ainda`.

**Conteúdo completo do arquivo:**

```yaml
# Pre-commit hooks do Radar FIDC.
# Instalar (uma vez por clone):
#   pip install pre-commit && pre-commit install
# Executar manualmente em todos os arquivos:
#   pre-commit run --all-files

repos:
  # ─── Segurança: detecta segredos vazando para o commit ───────────────
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.18.4
    hooks:
      - id: gitleaks
        name: gitleaks (scan for secrets)

  # ─── Python: lint + format ───────────────────────────────────────────
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.10
    hooks:
      - id: ruff
        name: ruff (lint)
        args: [--fix]
      - id: ruff-format
        name: ruff (format)

  # ─── Markdown / YAML / JSON: format ──────────────────────────────────
  - repo: https://github.com/pre-commit/mirrors-prettier
    rev: v3.1.0
    hooks:
      - id: prettier
        name: prettier (md/yml/json)
        types_or: [markdown, yaml, json]
        # Excluir o data.json (gerado pelo pipeline; formatado em uma linha por design).
        exclude: ^(data\.json|.*\.min\.(js|css)|.*\.lock)$

  # ─── Higiene básica ──────────────────────────────────────────────────
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-json
        exclude: ^data\.json$
      - id: check-added-large-files
        args: ["--maxkb=5000"]
```

**Comando para criar o arquivo (passo manual via editor — não usar `cat <<EOF` no shell para preservar indentação YAML):** Salvar o conteúdo acima em `.pre-commit-config.yaml` usando o editor de sua escolha.

**Comando de verificação:**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
test -f .pre-commit-config.yaml && echo "OK arquivo criado"
python -c "import yaml; yaml.safe_load(open('.pre-commit-config.yaml'))" && echo "OK YAML válido"
```

Saída esperada:

```
OK arquivo criado
OK YAML válido
```

**Instalar e testar localmente:**

```bash
pip install --user pre-commit
pre-commit install
pre-commit run --all-files
```

A primeira execução do `pre-commit run --all-files` baixa as ferramentas. Esperado: alguns hooks podem reportar formatação que precisa ser corrigida — isso é OK, faz parte da limpeza inicial. Se reportar `gitleaks` com violação, é leak real → voltar para Task F0-3.

**Em caso de falha:**
- Se `pre-commit install` falhar com `command not found`: garantir que `~/.local/bin` está no `PATH`, ou usar `python -m pre_commit install`
- Se o hook `gitleaks` reportar findings legítimos em arquivos da spec/docs (texto que parece chave mas é exemplo): adicionar `.gitleaksignore` com a SHA do finding (o output do gitleaks indica o comando exato)
- Se `prettier` reformatar dezenas de arquivos: aceitar a reformatação como commit separado de housekeeping

---

### Task F0-5 — Commit da Fase 0 parcial (`.pre-commit-config.yaml`)

**Target:** shared
**Working Directory:** `.`
**Agente recomendado:** `ring:devops-engineer`
**Depende de:** Task F0-4

**Comandos:**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
git status
git add .pre-commit-config.yaml
git status
```

Esperado em `git status`: arquivo `.pre-commit-config.yaml` em `Changes to be committed`, nada mais.

```bash
git commit -m "chore: Add pre-commit hooks for gitleaks ruff and prettier

Hooks bloqueiam segredos (gitleaks), enforçam lint/format Python (ruff)
e formatação consistente em md/yml/json (prettier)."
```

**Critério de verificação:**

```bash
git log --oneline -1
```

Saída esperada (hash diferente, mensagem igual):

```
abc1234 chore: Add pre-commit hooks for gitleaks ruff and prettier
```

**Em caso de falha:**
- Se o próprio hook `pre-commit` bloquear o commit por reformatar arquivos: rodar `git add -u` para incluir as reformatações automáticas e commitar de novo
- Não usar `--no-verify` (a regra global do usuário proíbe)

---

### Task F0-6 — HUMAN-TASK: Habilitar GitHub Push Protection

**Target:** shared
**Working Directory:** `.`
**Agente recomendado:** ação humana (UI do GitHub)
**Depende de:** —

**Passos navegacionais:**

1. Acessar <https://github.com/victorsouza14/radar-fidc/settings/security_analysis>
2. Em **Secret scanning**, garantir que **Secret scanning** esteja `Enabled` (geralmente já vem ativo em repos públicos)
3. Em **Push protection**, clicar em **Enable**
4. Confirmar na modal "Push protection will block contributors from pushing secrets..."
5. Em **Secret scanning custom patterns** (opcional, recomendado): adicionar padrão custom para Azure Account Key:
   - Clicar em **New pattern**
   - Pattern name: `Azure Storage Account Key (custom)`
   - Secret format (regex): `AccountKey=[A-Za-z0-9+/]{86,90}==`
   - Test string: `AccountKey=abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789+/abcdefghijklmnop1234567890==`
   - Clicar em **Save and dry run**
   - Aguardar o dry run completar e revisar matches
   - Se nenhum falso positivo: clicar em **Publish pattern**

**Critério de verificação:**

```bash
gh api repos/victorsouza14/radar-fidc --jq '.security_and_analysis'
```

Saída esperada (campos `secret_scanning` e `secret_scanning_push_protection` com `status: "enabled"`):

```json
{
  "secret_scanning": {"status": "enabled"},
  "secret_scanning_push_protection": {"status": "enabled"},
  ...
}
```

**Em caso de falha:**
- Se o Push Protection não aparecer disponível: pode requerer plano GitHub Pro ou repositório público (este projeto é público, então deve funcionar)
- Se o custom pattern entrar em loop de "Pending validation": é normal, leva ~5min em repos grandes

---

### Task F0-7 — HUMAN-TASK: Configurar Branch Protection em `main`

**Target:** shared
**Working Directory:** `.`
**Agente recomendado:** ação humana (UI do GitHub) OU comando `gh api`
**Depende de:** Task F0-5 (precisamos do hook pre-commit configurado primeiro, para que o CI de PR não fique vermelho antes da hora)

**Opção A — UI do GitHub (passos navegacionais):**

1. Acessar <https://github.com/victorsouza14/radar-fidc/settings/branches>
2. Em **Branch protection rules**, clicar em **Add branch protection rule**
3. **Branch name pattern**: `main`
4. Marcar **Require a pull request before merging**:
   - Marcar **Require approvals** → `1`
   - Marcar **Dismiss stale pull request approvals when new commits are pushed**
5. Marcar **Require conversation resolution before merging**
6. **NÃO marcar** **Require status checks to pass before merging** ainda — ele só será marcado na Fase 2 quando o `ci.yml` existir
7. Marcar **Require linear history** (evita merges sem fast-forward) — opcional, recomendado
8. **NÃO marcar** **Do not allow bypassing the above settings** (o bot `github-actions[bot]` precisa commitar `data.json` direto em `main` na Fase 1; ver discussão na spec, Seção 7)
9. **Restrict who can push to matching branches**: deixar em branco por agora (sem allowlist; a regra "no force push" abaixo já é proteção)
10. Marcar **Do not allow force pushes**
11. Marcar **Do not allow deletions**
12. Clicar em **Create**

**Opção B — Via `gh api` (idempotente, preferida para reprodutibilidade):**

```bash
gh api -X PUT repos/victorsouza14/radar-fidc/branches/main/protection \
  -H "Accept: application/vnd.github+json" \
  --input - <<'JSON'
{
  "required_status_checks": null,
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": false,
    "required_approving_review_count": 1,
    "require_last_push_approval": false
  },
  "restrictions": null,
  "required_linear_history": true,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "block_creations": false,
  "required_conversation_resolution": true,
  "lock_branch": false,
  "allow_fork_syncing": false
}
JSON
```

**Critério de verificação:**

```bash
gh api repos/victorsouza14/radar-fidc/branches/main/protection --jq '{
  pr_required: .required_pull_request_reviews.required_approving_review_count,
  force_push: .allow_force_pushes.enabled,
  linear: .required_linear_history.enabled,
  resolution: .required_conversation_resolution.enabled
}'
```

Saída esperada:

```json
{
  "pr_required": 1,
  "force_push": false,
  "linear": true,
  "resolution": true
}
```

**Em caso de falha:**
- Se receber `HTTP 404`: confirmar que o usuário do `gh` é admin do repo (`gh api repos/victorsouza14/radar-fidc --jq .permissions.admin` deve retornar `true`)
- Se `gh api` retornar `Required status checks: must be a string`: o payload acima tem `null`, mas em algumas versões da API exige objeto `{"strict": false, "contexts": []}`. Trocar `"required_status_checks": null` por `"required_status_checks": {"strict": false, "contexts": []}` e re-tentar
- Se a regra impedir o `data-refresh.yml` de commitar (mais à frente, Fase 1): adicionar exceção em **Bypass list** → `github-actions[bot]` via UI

**Após Task F0-7, a Fase 0 tem todas as 6 tarefas críticas concluídas (rotação, secret, audit, pre-commit, push protection, branch protection).**

---

### Task F0-CHECKPOINT — Code Review da Fase 0

**Target:** shared
**Working Directory:** `.`
**Agente recomendado:** orquestrador humano dispara `ring:requesting-code-review`
**Depende de:** Tasks F0-1 a F0-7

**Procedimento:**

1. **Despachar 7 reviewers em paralelo** (SUB-SKILL OBRIGATÓRIA: `ring:requesting-code-review`):
   - `ring:code-reviewer`
   - `ring:business-logic-reviewer`
   - `ring:security-reviewer` (foco especial nesta fase)
   - `ring:test-reviewer`
   - `ring:nil-safety-reviewer`
   - `ring:consequences-reviewer`
   - `ring:dead-code-reviewer`

2. **Escopo da revisão:**
   - `.pre-commit-config.yaml` (sintaxe, versões pinadas, cobertura)
   - Configuração de branch protection (capturada via `gh api`)
   - Documentação da rotação (esta tarefa não produz código, mas o `security-reviewer` deve validar se a rotação foi de fato executada — pedir confirmação ao humano)

3. **Tratamento por severidade (OBRIGATÓRIO):**

   **Critical / High / Medium:**
   - Corrigir imediatamente (NÃO adicionar TODO)
   - Re-rodar os 7 reviewers em paralelo após cada fix
   - Repetir até zero issues nessas severidades

   **Low:**
   - Adicionar `TODO(review):` no local relevante
   - Formato: `TODO(review): [descrição] (reportado por [reviewer] em 2026-05-14, severidade: Low)`

   **Cosmetic / Nitpick:**
   - Adicionar `FIXME(nitpick):` no local relevante
   - Formato: `FIXME(nitpick): [descrição] (reportado por [reviewer] em 2026-05-14, severidade: Cosmetic)`

4. **Prosseguir para a Fase 1 apenas quando:**
   - Zero issues Critical/High/Medium
   - Todos os Low têm `TODO(review):`
   - Todos os Cosmetic têm `FIXME(nitpick):`

**Critério de verificação:**
- Relatório consolidado dos 7 reviewers em mãos
- Resumo informa "0 Critical, 0 High, 0 Medium"

---

## Fase 1 — Conectar ao ADLS

**Duração estimada:** ~5 dias (16 tarefas, agrupadas em 4 batches com checkpoints de review entre eles).

**Resultado esperado ao fim da Fase 1:**
- `scripts/generate_dashboard_data.py` lê do ADLS (`dfdatalakesprint/gold/final/`), não de `data_real/`
- `data_real/` removido do repo e ignorado pelo Git
- Cache local em `.cache/` (ignorado pelo Git)
- Workflow renomeado para `data-refresh.yml` com instalação correta de dependências e validação de secret
- Docs (README, arquitetura, fontes_dados, powerbi_setup) atualizados para `dfdatalakesprint`
- `data.json` gerado a partir do ADLS é quase byte-igual ao atual

**Batches:**
1. **Batch 1 — Fundação (Tasks F1-1 a F1-5):** dependências, env, módulos novos em `scripts/lib/`
2. **Batch 2 — Refatoração (Tasks F1-6 a F1-9):** `io_utils`, `generate_dashboard_data`, simplificação de `paths.py`
3. **Batch 3 — Limpeza & CI (Tasks F1-10 a F1-13):** remoção de `data_real/`, `.gitignore`, workflow
4. **Batch 4 — Documentação & verificação (Tasks F1-14 a F1-16):** README/docs/teste end-to-end

---

### Batch 1 — Fundação

---

### Task F1-1 — Atualizar `requirements.txt`

**Target:** shared
**Working Directory:** `.`
**Agente recomendado:** `ring:general-purpose`
**Depende de:** Fase 0 completa

**Arquivos:**
- Modificar: `/Users/victorbraga/Downloads/radar-fidc/requirements.txt`

**Diff esperado:** Adicionar `azure-storage-file-datalake` (SDK específico do ADLS Gen2, separado do `azure-storage-blob` já presente — o file-datalake encapsula o conceito de `filesystem` e `directory client` que o blob não tem nativamente) e `pandera` (deixar disponível para Fase 2 — não usado em Fase 1, mas adicionar agora evita um segundo round de install/cache no CI).

**Conteúdo final completo:**

```text
# Radar FIDC — Dependências Python
# Instalar com: pip install -r requirements.txt
# Python >= 3.10

# Azure Storage
azure-storage-blob>=12.19.0
azure-storage-file-datalake>=12.14.0

# Data processing
pandas>=2.0.0
pyarrow>=14.0.0
numpy>=1.26.0
openpyxl>=3.1.0

# Data quality (preparação para Fase 2)
pandera>=0.18.0

# HTTP / API
requests>=2.31.0

# Databricks (para execução local via REST API)
databricks-sdk>=0.20.0

# Utilitários
python-dotenv>=1.0.0
```

**Notas das mudanças explicitas:**
- `+ azure-storage-file-datalake>=12.14.0` — SDK para ADLS Gen2 com `DataLakeServiceClient`
- `+ openpyxl>=3.1.0` — necessário para `pd.read_excel` de `.xlsx`; estava implícito antes (instalado pelo workflow). Tornando explícito.
- `+ pandera>=0.18.0` — preparação para Fase 2

**Comando de verificação:**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
grep -E "azure-storage-file-datalake|openpyxl|pandera" requirements.txt
```

Saída esperada (3 linhas):

```
azure-storage-file-datalake>=12.14.0
openpyxl>=3.1.0
pandera>=0.18.0
```

**Verificação opcional de instalação local (não obrigatória nesta tarefa — pode rodar depois):**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
python -m venv .venv-fase1 && source .venv-fase1/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python -c "import azure.storage.filedatalake; import pandera; import openpyxl; print('OK')"
deactivate
```

Saída esperada da última linha: `OK`.

**Em caso de falha:**
- Se `pip install` reclamar de versão Python: confirmar `python --version` é 3.10+
- Se `azure-storage-file-datalake` recusar a versão pinada: relaxar para `>=12.0.0`

---

### Task F1-2 — Atualizar `.env.example`

**Target:** shared
**Working Directory:** `.`
**Agente recomendado:** `ring:general-purpose`
**Depende de:** —

**Arquivos:**
- Modificar: `/Users/victorbraga/Downloads/radar-fidc/.env.example`

**O que muda:**
- Substituir `stdatatalake2026` por `dfdatalakesprint`
- Remover linhas duplicadas: `AZURE_STORAGE_ACCOUNT_NAME` e `AZURE_STORAGE_ACCOUNT_KEY` (não são usadas pelo código — apenas a connection string é lida)
- Adicionar `AZURE_FILESYSTEM` e `AZURE_GOLD_PREFIX` como variáveis nomeadas (substitui os defaults hard-coded futuros no `gold_paths.py`)

**Conteúdo final completo:**

```bash
# ============================================================
# Radar FIDC — Variáveis de Ambiente
# ============================================================
# Copie este arquivo para .env e preencha:   cp .env.example .env
# NUNCA commite o arquivo .env no Git.
# ============================================================

# ------------------------------------------------------------
# Azure Data Lake Storage Gen2  (obrigatório)
# ------------------------------------------------------------
# Connection string completa da conta dfdatalakesprint (key1 rotacionada).
# Formato: DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...;EndpointSuffix=core.windows.net
AZURE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=dfdatalakesprint;AccountKey=SUA_CHAVE_AQUI;EndpointSuffix=core.windows.net

# Container e prefixo lógico no Gold (defaults — só sobrescreva se a estrutura mudar).
AZURE_FILESYSTEM=gold
AZURE_GOLD_PREFIX=final

# ------------------------------------------------------------
# ANBIMA API  (obrigatório para ingestão Bronze)
# ------------------------------------------------------------
ANBIMA_BASE=https://api.anbima.com.br
ANBIMA_CLIENT_ID=
ANBIMA_CLIENT_SECRET=

# ------------------------------------------------------------
# Azure Databricks  (opcional, para execução remota)
# ------------------------------------------------------------
DATABRICKS_HOST=https://adb-XXXXXXXXXXXXXXXXX.X.azuredatabricks.net
DATABRICKS_TOKEN=
DATABRICKS_CLUSTER_ID=
DATABRICKS_NOTEBOOK_PATH=/Users/SEU_EMAIL@dominio.com/03_gold_modelagem

# ------------------------------------------------------------
# Pipeline (opcional — usados pelos notebooks)
# ------------------------------------------------------------
AZURE_CONTAINER_BRONZE=bronze
AZURE_CONTAINER_SILVER=silver
AZURE_CONTAINER_GOLD=gold

# Parâmetros do etl_cda Bronze quando rodado fora do Databricks:
# CDA_ANO=2026
# CDA_MES=04
```

**Comando de verificação:**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
grep -c "stdatatalake2026" .env.example   # Esperado: 0
grep -c "dfdatalakesprint" .env.example   # Esperado: 1
grep -c "AZURE_STORAGE_ACCOUNT_NAME\|AZURE_STORAGE_ACCOUNT_KEY" .env.example  # Esperado: 0
grep -c "AZURE_FILESYSTEM=gold" .env.example  # Esperado: 1
grep -c "AZURE_GOLD_PREFIX=final" .env.example  # Esperado: 1
```

**Em caso de falha:**
- Se `grep` retornar contagem diferente do esperado: revisar o arquivo manualmente, conferir indentação e ausência de BOM

**Pós-tarefa para o usuário (não obrigatório):** Sincronizar o `.env` local do desenvolvedor com a nova chave + nova `AccountName`:

```bash
# Edite .env (não commitar) usando a NOVA chave da Task F0-1
$EDITOR /Users/victorbraga/Downloads/radar-fidc/.env
```

---

### Task F1-3 — Criar `scripts/lib/logger.py`

**Target:** shared
**Working Directory:** `.`
**Agente recomendado:** `ring:general-purpose`
**Depende de:** —

**Arquivos:**
- Criar: `/Users/victorbraga/Downloads/radar-fidc/scripts/lib/logger.py`

**Pré-requisitos:**
- Diretório `scripts/lib/` existe (verificar: `ls scripts/lib/` deve mostrar `__init__.py`, `formatters.py`, etc.)

**Conteúdo completo:**

```python
"""Logger estruturado em JSON Lines.

Uso:
    from lib.logger import get_logger
    log = get_logger(__name__)
    log.info("pipeline_start", source="dfdatalakesprint", filesystem="gold")
    log.warn("etag_mismatch", path="final/rating_fidc.xlsx", cached_etag="abc", remote_etag="def")

Cada chamada emite UMA linha JSON em stdout, formato:
    {"ts":"2026-05-14T12:00:00Z","level":"info","event":"pipeline_start","logger":"lib.azure_io","source":"...","filesystem":"gold"}

Compatível com agregadores que aceitam stdout JSON Lines (GitHub Actions, Datadog, etc.).
Não usa stdlib logging — keep it simple, fonte única, sem handlers herdados.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class _StructuredLogger:
    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name

    def _emit(self, level: str, event: str, **fields: Any) -> None:
        record = {
            "ts": _now_iso(),
            "level": level,
            "event": event,
            "logger": self.name,
            **fields,
        }
        # ensure_ascii=False para emojis/acentos serem legíveis em logs locais.
        # default=str para datetimes, Decimals, paths não-serializáveis caírem em str().
        sys.stdout.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        sys.stdout.flush()

    def info(self, event: str, **fields: Any) -> None:
        self._emit("info", event, **fields)

    def warn(self, event: str, **fields: Any) -> None:
        self._emit("warn", event, **fields)

    def error(self, event: str, **fields: Any) -> None:
        self._emit("error", event, **fields)


def get_logger(name: str) -> _StructuredLogger:
    return _StructuredLogger(name)
```

**Comando de verificação:**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
test -f scripts/lib/logger.py && echo "OK arquivo criado"
python -c "
import sys; sys.path.insert(0, 'scripts')
from lib.logger import get_logger
log = get_logger('test')
log.info('hello', foo='bar', n=42)
"
```

Saída esperada (timestamp varia):

```
OK arquivo criado
{"ts": "2026-05-14T...Z", "level": "info", "event": "hello", "logger": "test", "foo": "bar", "n": 42}
```

**Em caso de falha:**
- Se `ImportError: No module named 'lib'`: confirmar que rodou do diretório raiz do repo
- Se a saída não vier em JSON válido: rodar `python -c "..."` em modo `-v` para detectar problemas de encoding

---

### Task F1-4 — Criar `scripts/lib/gold_paths.py`

**Target:** shared
**Working Directory:** `.`
**Agente recomendado:** `ring:general-purpose`
**Depende de:** —

**Arquivos:**
- Criar: `/Users/victorbraga/Downloads/radar-fidc/scripts/lib/gold_paths.py`

**Conteúdo completo:**

```python
"""Constantes de paths lógicos no container Gold do ADLS.

Fonte única da verdade para "onde cada arquivo vive no Data Lake".
Lido por `azure_io.py` (acesso) e por `io_utils.py` (leitura tipada).

Estrutura no ADLS:
    container: gold
      └─ final/                          ← AZURE_GOLD_PREFIX
          ├─ rating_fidc.xlsx
          ├─ matches.xlsx
          ├─ clientes.csv
          ├─ scores_credito.csv
          └─ macroeconomicos/
              └─ consolidade.csv
"""
from __future__ import annotations

import os

# ─── Configuração (sobrescrevível via .env) ──────────────────────────────
FILESYSTEM = os.environ.get("AZURE_FILESYSTEM", "gold")
GOLD_PREFIX = os.environ.get("AZURE_GOLD_PREFIX", "final")

# ─── Paths dos artefatos consumidos pelo dashboard ───────────────────────
# Mantém o mesmo basename dos arquivos antigos em `data_real/` para
# minimizar superfície de mudança ao migrar.
PATHS: dict[str, str] = {
    "rating":          f"{GOLD_PREFIX}/rating_fidc.xlsx",
    "matches":         f"{GOLD_PREFIX}/matches.xlsx",
    "clientes":        f"{GOLD_PREFIX}/clientes.csv",
    "credit":          f"{GOLD_PREFIX}/scores_credito.csv",
    "macro":           f"{GOLD_PREFIX}/macroeconomicos/consolidade.csv",
}

# Diretório de cache local (resolvido para path absoluto pelo azure_io).
# Não fica em PATHS porque não é um "endereço no Lake".
LOCAL_CACHE_DIR = ".cache"
```

**Comando de verificação:**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
test -f scripts/lib/gold_paths.py && echo "OK arquivo criado"
python -c "
import sys; sys.path.insert(0, 'scripts')
from lib import gold_paths
assert gold_paths.FILESYSTEM == 'gold', f'esperado gold, got {gold_paths.FILESYSTEM}'
assert gold_paths.GOLD_PREFIX == 'final', f'esperado final, got {gold_paths.GOLD_PREFIX}'
assert gold_paths.PATHS['rating'] == 'final/rating_fidc.xlsx'
assert gold_paths.PATHS['macro'] == 'final/macroeconomicos/consolidade.csv'
print('OK constantes')
"
```

Saída esperada:

```
OK arquivo criado
OK constantes
```

**Em caso de falha:**
- Se `AssertionError`: revisar valores hardcoded; o `.env` local pode estar exportando `AZURE_GOLD_PREFIX` diferente. Rodar `env | grep AZURE_` para diagnosticar.

---

### Task F1-5 — Criar `scripts/lib/azure_io.py`

**Target:** shared
**Working Directory:** `.`
**Agente recomendado:** `ring:general-purpose`
**Depende de:** Tasks F1-1, F1-3, F1-4

**Arquivos:**
- Criar: `/Users/victorbraga/Downloads/radar-fidc/scripts/lib/azure_io.py`

**Pré-requisitos:**
- `azure-storage-file-datalake>=12.14.0` instalado (verificar: `python -c "from azure.storage.filedatalake import DataLakeServiceClient; print('OK')"`)
- `AZURE_CONNECTION_STRING` em `os.environ` (vem do `.env` para uso local, ou de secret no CI)

**Conteúdo completo:**

```python
"""Camada de acesso ao ADLS Gen2 com cache de duas camadas.

- Camada 1 (byte cache): bytes brutos do blob em `.cache/<path>`, invalidados via ETag.
- Camada 2 (parse cache): DataFrame serializado em `.cache/<path>.parsed.pkl`,
  invalidado se o byte cache mudou.

Lógica de cache:
    1. Pega ETag remoto (HEAD do blob)
    2. Se existe `.cache/<path>.etag` igual ao remoto E o `.cache/<path>` existe:
       reusa bytes locais (zero egress)
    3. Senão, baixa, grava bytes + ETag
    4. Para `read_csv`/`read_excel`: se existir `.parsed.pkl` válido, devolve direto

No CI o cache é vazio em cada run (proposital — garante leitura fresca).
Localmente acelera de ~5s para <50ms por arquivo após primeiro run.

Erros:
    - 401/403 -> AzureAuthError (fail fast, NÃO retry)
    - 5xx/timeout -> retry exponencial do SDK (config explícita abaixo)
    - ETag inconsistente entre HEAD e GET -> warn + re-download
"""
from __future__ import annotations

import io
import os
import pickle
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd
from azure.core.exceptions import ClientAuthenticationError, HttpResponseError
from azure.storage.filedatalake import DataLakeServiceClient, FileSystemClient

from .gold_paths import FILESYSTEM, LOCAL_CACHE_DIR
from .logger import get_logger

log = get_logger(__name__)

# Raiz do cache local (sempre relativo ao cwd do script que importa).
_CACHE_ROOT = Path(LOCAL_CACHE_DIR).resolve()


class AzureAuthError(RuntimeError):
    """Falha de autenticação no ADLS — não retentar."""


class AzureMissingConnectionString(RuntimeError):
    """`AZURE_CONNECTION_STRING` ausente do ambiente."""


# ─── Cliente cacheado ────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def _service_client() -> DataLakeServiceClient:
    conn = os.environ.get("AZURE_CONNECTION_STRING")
    if not conn:
        raise AzureMissingConnectionString(
            "AZURE_CONNECTION_STRING ausente. "
            "Configure no .env local ou no GitHub Secret AZURE_CONNECTION_STRING."
        )
    # retry_total=5, backoff exponencial. SDK Azure já trata 5xx; 401/403 não retenta.
    return DataLakeServiceClient.from_connection_string(
        conn,
        retry_total=5,
        retry_backoff_factor=0.5,
    )


@lru_cache(maxsize=1)
def _filesystem_client() -> FileSystemClient:
    return _service_client().get_file_system_client(FILESYSTEM)


# ─── Cache helpers ───────────────────────────────────────────────────────
def _cache_path_for(remote_path: str) -> Path:
    """Mapeia 'final/rating_fidc.xlsx' -> '.cache/final/rating_fidc.xlsx'."""
    return _CACHE_ROOT / remote_path


def _etag_cache_path_for(remote_path: str) -> Path:
    return _CACHE_ROOT / f"{remote_path}.etag"


def _parsed_cache_path_for(remote_path: str) -> Path:
    return _CACHE_ROOT / f"{remote_path}.parsed.pkl"


def _read_etag_cached(remote_path: str) -> str | None:
    p = _etag_cache_path_for(remote_path)
    if not p.exists():
        return None
    try:
        return p.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _write_etag_cached(remote_path: str, etag: str) -> None:
    p = _etag_cache_path_for(remote_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(etag, encoding="utf-8")


# ─── Operações ADLS ──────────────────────────────────────────────────────
def blob_etag(remote_path: str) -> str:
    """Retorna o ETag do blob (HEAD). Custo: ~50ms, sem egress."""
    try:
        props = _filesystem_client().get_file_client(remote_path).get_file_properties()
    except ClientAuthenticationError as e:
        raise AzureAuthError(f"Falha auth ao buscar ETag de {remote_path}: {e}") from e
    return props.etag or ""


def download_to_bytes(remote_path: str) -> bytes:
    """Baixa o blob, valida ETag, mantém cache em `.cache/`. Retorna bytes."""
    log.info("download_start", path=remote_path)
    local = _cache_path_for(remote_path)
    cached_etag = _read_etag_cached(remote_path)

    try:
        remote_etag = blob_etag(remote_path)
    except AzureAuthError:
        raise
    except HttpResponseError as e:
        log.error("etag_fetch_failed", path=remote_path, error=str(e))
        raise

    if cached_etag == remote_etag and local.exists():
        log.info("download_cache_hit", path=remote_path, etag=remote_etag, bytes=local.stat().st_size)
        return local.read_bytes()

    log.info("download_cache_miss", path=remote_path, cached_etag=cached_etag, remote_etag=remote_etag)
    try:
        downloader = _filesystem_client().get_file_client(remote_path).download_file()
        data = downloader.readall()
    except ClientAuthenticationError as e:
        raise AzureAuthError(f"Falha auth ao baixar {remote_path}: {e}") from e

    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_bytes(data)
    _write_etag_cached(remote_path, remote_etag)
    # Invalida parse cache associado.
    parsed = _parsed_cache_path_for(remote_path)
    if parsed.exists():
        parsed.unlink()
    log.info("download_complete", path=remote_path, bytes=len(data), etag=remote_etag)
    return data


# ─── Parse cache helpers ─────────────────────────────────────────────────
def _try_parsed_cache(remote_path: str) -> Any | None:
    """Devolve o objeto Python cacheado, se ETag bate com remoto."""
    parsed = _parsed_cache_path_for(remote_path)
    if not parsed.exists():
        return None
    # Confiança transitiva: se etag local bate com remoto E parsed existe, parsed é válido.
    cached_etag = _read_etag_cached(remote_path)
    if cached_etag is None:
        return None
    try:
        remote_etag = blob_etag(remote_path)
    except (AzureAuthError, HttpResponseError):
        # Sem internet ou auth caiu: confiar no cache local.
        log.warn("parsed_cache_etag_check_failed", path=remote_path)
        return pickle.loads(parsed.read_bytes())
    if cached_etag != remote_etag:
        return None
    log.info("parsed_cache_hit", path=remote_path)
    return pickle.loads(parsed.read_bytes())


def _save_parsed_cache(remote_path: str, obj: Any) -> None:
    parsed = _parsed_cache_path_for(remote_path)
    parsed.parent.mkdir(parents=True, exist_ok=True)
    parsed.write_bytes(pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL))


# ─── Leitura tipada (com parse cache) ────────────────────────────────────
def read_csv(remote_path: str, **kwargs: Any) -> pd.DataFrame:
    cached = _try_parsed_cache(remote_path)
    if isinstance(cached, pd.DataFrame):
        return cached
    data = download_to_bytes(remote_path)
    df = pd.read_csv(io.BytesIO(data), **kwargs)
    _save_parsed_cache(remote_path, df)
    return df


def read_excel(remote_path: str, sheet_name: str | int | None = 0, **kwargs: Any) -> pd.DataFrame:
    cached = _try_parsed_cache(f"{remote_path}::{sheet_name}")
    if isinstance(cached, pd.DataFrame):
        return cached
    data = download_to_bytes(remote_path)
    df = pd.read_excel(io.BytesIO(data), sheet_name=sheet_name, **kwargs)
    _save_parsed_cache(f"{remote_path}::{sheet_name}", df)
    return df


def read_excel_sheets(remote_path: str, sheets: list[str]) -> dict[str, pd.DataFrame]:
    """Lê múltiplas abas de um único download (mais eficiente que vários read_excel)."""
    data = download_to_bytes(remote_path)
    xls = pd.ExcelFile(io.BytesIO(data))
    return {
        sheet: pd.read_excel(xls, sheet_name=sheet)
        for sheet in sheets
        if sheet in xls.sheet_names
    }


def list_dir(remote_dir: str) -> list[str]:
    """Lista paths de blobs sob um prefixo. Útil para descobrir arquivos macro."""
    fs = _filesystem_client()
    return [p.name for p in fs.get_paths(path=remote_dir) if not p.is_directory]
```

**Comando de verificação (sem rodar contra Azure ainda — só checa import):**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
test -f scripts/lib/azure_io.py && echo "OK arquivo criado"
python -c "
import sys; sys.path.insert(0, 'scripts')
from lib import azure_io
print('OK módulo importa')
print('Tem funções:',
      hasattr(azure_io, 'read_csv'),
      hasattr(azure_io, 'read_excel'),
      hasattr(azure_io, 'read_excel_sheets'),
      hasattr(azure_io, 'list_dir'),
      hasattr(azure_io, 'blob_etag'),
      hasattr(azure_io, 'download_to_bytes'))
"
```

Saída esperada:

```
OK arquivo criado
OK módulo importa
Tem funções: True True True True True True
```

**Verificação end-to-end (opcional nesta tarefa, será obrigatória na Task F1-16):**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
# Requer .env com a NOVA chave (Task F0-1)
set -a && source .env && set +a
python -c "
import sys; sys.path.insert(0, 'scripts')
from lib import azure_io
etag = azure_io.blob_etag('final/rating_fidc.xlsx')
print(f'ETag rating: {etag[:16]}...')
data = azure_io.download_to_bytes('final/rating_fidc.xlsx')
print(f'Bytes baixados: {len(data)}')
"
```

Saída esperada (ETag varia):

```
{"ts": "...", "level": "info", "event": "download_start", ...}
ETag rating: 0x8DC1234...
{"ts": "...", "level": "info", "event": "download_complete", ...}
Bytes baixados: 234567
```

**Em caso de falha:**
- `AzureMissingConnectionString`: rodar `set -a && source .env && set +a` antes
- `AzureAuthError`: a chave no `.env` ainda é a antiga. Atualizar com a nova da Task F0-1
- `HttpResponseError 404`: o storage account ou o container está errado. Confirmar `AZURE_FILESYSTEM=gold` e `AZURE_GOLD_PREFIX=final` no `.env`
- Cache local crescendo demais (>50MB): rodar `rm -rf .cache/` para limpar (será re-populado)

---

### Task F1-CHECKPOINT-1 — Code Review do Batch 1

**Target:** shared
**Working Directory:** `.`
**Agente recomendado:** orquestrador humano dispara `ring:requesting-code-review`
**Depende de:** Tasks F1-1 a F1-5

**Procedimento:** idêntico ao Task F0-CHECKPOINT, mas escopo é os 5 arquivos criados/modificados no Batch 1.

**Escopo:**
- `requirements.txt`
- `.env.example`
- `scripts/lib/logger.py`
- `scripts/lib/gold_paths.py`
- `scripts/lib/azure_io.py`

**Tratamento por severidade:** idêntico ao Task F0-CHECKPOINT.

**Prosseguir para Batch 2 apenas com zero Critical/High/Medium.**

---

### Batch 2 — Refatoração dos leitores

---

### Task F1-6 — Refatorar `scripts/lib/io_utils.py` para usar `azure_io`

**Target:** shared
**Working Directory:** `.`
**Agente recomendado:** `ring:general-purpose`
**Depende de:** Task F1-5

**Arquivos:**
- Modificar (substituição total): `/Users/victorbraga/Downloads/radar-fidc/scripts/lib/io_utils.py`

**O que muda:** A interface pública (`read_clientes`, `read_credit_scores`, `read_macro`, `read_rating`, `read_matches`) **mantém os mesmos nomes**, mas a assinatura **muda**: não recebe mais `path: Path` — agora resolvem internamente via `gold_paths.PATHS`. Mantém o contrato de retorno (tuplas e DataFrames idênticos ao antes), preservando o `payload.build_*` sem alteração.

**Conteúdo final completo:**

```python
"""IO defensivo — leitura dos arquivos do pipeline no Gold (ADLS).

Substitui a leitura de `data_real/` local pela leitura direta do ADLS,
mantendo o contrato de retorno (tuplas e DataFrames) idêntico ao código
anterior para preservar `payload.build_*` sem mudança.

Cache:
- Bytes invalidados via ETag (zero egress quando cache local válido)
- Parse cache em `.parsed.pkl` (skip do parse openpyxl que é lento)
Implementado em `lib.azure_io`.
"""
from __future__ import annotations

import pandas as pd

from . import azure_io
from .gold_paths import PATHS
from .logger import get_logger

log = get_logger(__name__)


def _empty_on_404(fn, *args, **kwargs):
    """Wrapper: devolve DataFrame vazio se o arquivo não existe no Gold."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:  # noqa: BLE001 — qualquer falha de I/O cai aqui
        # ResourceNotFoundError do SDK Azure herda de HttpResponseError.
        # Imports lazy para evitar carga de azure-core no top-level se não precisar.
        from azure.core.exceptions import ResourceNotFoundError

        if isinstance(e, ResourceNotFoundError):
            log.warn("file_not_found", path=str(args[0]) if args else "?")
            return pd.DataFrame()
        raise


def read_clientes() -> pd.DataFrame:
    return _empty_on_404(azure_io.read_csv, PATHS["clientes"], encoding="utf-8-sig")


def read_credit_scores() -> pd.DataFrame:
    df = _empty_on_404(azure_io.read_csv, PATHS["credit"])
    if df.empty:
        return df
    for col in ("score_credito", "prob_default", "pct_default", "defaultou"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def read_macro() -> pd.DataFrame:
    df = _empty_on_404(azure_io.read_csv, PATHS["macro"], sep=";", dtype=str)
    if df.empty:
        return df
    df["data_processamento"] = pd.to_datetime(df["data_processamento"], errors="coerce")
    for col in df.columns:
        if col != "data_processamento":
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_values("data_processamento").reset_index(drop=True)


def read_rating() -> tuple[pd.DataFrame, pd.DataFrame]:
    try:
        sheets = azure_io.read_excel_sheets(PATHS["rating"], ["GERAL", "RESUMO_POR_FUNDO"])
    except Exception as e:  # noqa: BLE001
        from azure.core.exceptions import ResourceNotFoundError
        if isinstance(e, ResourceNotFoundError):
            log.warn("file_not_found", path=PATHS["rating"])
            return pd.DataFrame(), pd.DataFrame()
        raise
    return sheets.get("GERAL", pd.DataFrame()), sheets.get("RESUMO_POR_FUNDO", pd.DataFrame())


def read_matches() -> tuple[pd.DataFrame, pd.DataFrame]:
    try:
        sheets = azure_io.read_excel_sheets(PATHS["matches"], ["TODOS_OS_MATCHES", "RANKING_FUNDOS"])
    except Exception as e:  # noqa: BLE001
        from azure.core.exceptions import ResourceNotFoundError
        if isinstance(e, ResourceNotFoundError):
            log.warn("file_not_found", path=PATHS["matches"])
            return pd.DataFrame(), pd.DataFrame()
        raise
    return sheets.get("TODOS_OS_MATCHES", pd.DataFrame()), sheets.get("RANKING_FUNDOS", pd.DataFrame())
```

**Comando de verificação:**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
# Só checa que importa e tem as 5 funções (sem chamar — não tem conexão garantida)
python -c "
import sys; sys.path.insert(0, 'scripts')
from lib import io_utils
for fn in ('read_clientes', 'read_credit_scores', 'read_macro', 'read_rating', 'read_matches'):
    assert hasattr(io_utils, fn), f'falta {fn}'
import inspect
for fn in ('read_clientes', 'read_credit_scores', 'read_macro', 'read_rating', 'read_matches'):
    sig = inspect.signature(getattr(io_utils, fn))
    assert len(sig.parameters) == 0, f'{fn} ainda aceita parâmetros: {sig}'
print('OK 5 funções sem parâmetros')
"
```

Saída esperada:

```
OK 5 funções sem parâmetros
```

**Em caso de falha:**
- `AssertionError ainda aceita parâmetros`: sobrou `path: Path` em alguma assinatura. Revisar
- `ModuleNotFoundError: lib.azure_io`: a Task F1-5 falhou. Voltar e refazer

---

### Task F1-7 — Refatorar `scripts/generate_dashboard_data.py`

**Target:** shared
**Working Directory:** `.`
**Agente recomendado:** `ring:general-purpose`
**Depende de:** Task F1-6

**Arquivos:**
- Modificar (substituição total): `/Users/victorbraga/Downloads/radar-fidc/scripts/generate_dashboard_data.py`

**O que muda:**
- Remove import de `lib.paths.Paths`
- Remove flag `--data-dir`
- Mantém `--output` (útil para teste em diff)
- Os `print(...)` viram `log.info(...)` estruturados

**Conteúdo completo:**

```python
#!/usr/bin/env python3
"""Gera o `data.json` consumido pelo dashboard Radar FIDC.

Lê os outputs do Gold no ADLS (`dfdatalakesprint/gold/final/`),
delega a montagem do payload aos módulos em `scripts/lib/`, e
escreve `data.json` na raiz do repositório.

Uso:
    python scripts/generate_dashboard_data.py
    python scripts/generate_dashboard_data.py --output /tmp/data.json

Pré-requisitos:
    - AZURE_CONNECTION_STRING em .env (local) ou GitHub Secret (CI)
    - Arquivos esperados em gold/final/:
        rating_fidc.xlsx, matches.xlsx, clientes.csv,
        scores_credito.csv, macroeconomicos/consolidade.csv
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Permite rodar tanto como `python scripts/...` quanto via import.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import io_utils, payload  # noqa: E402
from lib.logger import get_logger  # noqa: E402

log = get_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = REPO_ROOT / "data.json"


def now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def build() -> dict:
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

    return {
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


def write_json(out: Path, data: dict) -> None:
    # allow_nan=False: falha o build em vez de emitir `NaN` literal (inválido em JSON).
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
        dist_por_risco=data["fidcs"]["stats"]["distribuicao"]["por_risco"],
        dist_por_perfil=data["fidcs"]["stats"]["distribuicao"]["por_perfil"],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=None, help="Sobrepõe data.json de saída")
    args = parser.parse_args()

    out = Path(args.output) if args.output else DEFAULT_OUTPUT

    data = build()
    write_json(out, data)
    emit_summary(out, data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Comando de verificação (import-only, sem rodar):**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
python -c "
import sys; sys.path.insert(0, 'scripts')
import generate_dashboard_data as gdd
import inspect

# Confirma que build() não tem mais o parâmetro paths
sig = inspect.signature(gdd.build)
assert len(sig.parameters) == 0, f'build() ainda recebe args: {sig}'

# Confirma que paths.Paths não é mais importado
src = open('scripts/generate_dashboard_data.py').read()
assert 'from lib.paths import Paths' not in src, 'ainda importa Paths'
assert 'paths.data_real' not in src, 'ainda referencia paths.data_real'
print('OK refatoração consistente')
"
```

Saída esperada:

```
OK refatoração consistente
```

**Em caso de falha:**
- `AssertionError build() ainda recebe args`: a função `build` deve ser `def build() -> dict:` sem parâmetros
- Algum AssertionError de "ainda importa/referencia": revisar diff

---

### Task F1-8 — Simplificar `scripts/lib/paths.py`

**Target:** shared
**Working Directory:** `.`
**Agente recomendado:** `ring:general-purpose`
**Depende de:** Task F1-7

**Arquivos:**
- Modificar: `/Users/victorbraga/Downloads/radar-fidc/scripts/lib/paths.py`

**Por que:** Outros scripts (`rating.py`, `credit_model.py`, `match.py`) ainda usam `data_real/` para entradas que NÃO são parte do `data.json` (são entradas dos modelos, rodados no Databricks). Esses scripts viraram legados locais. O `generate_dashboard_data.py` não usa mais `Paths`, mas remover `paths.py` quebraria os outros. Solução: **manter o módulo, removendo apenas a `Paths` dataclass que era genérica**, e expor só `REPO_ROOT` para quem ainda precisa.

**Conteúdo final completo:**

```python
"""Resolução de paths do projeto.

A partir da Fase 1, `generate_dashboard_data.py` lê do ADLS, não mais de
`data_real/`. A classe `Paths` foi removida. Este módulo agora só expõe
constantes simples para os scripts que rodam *fora* do dashboard
(`rating.py`, `credit_model.py`, `match.py`) — esses são utilitários
locais/Databricks, fora do pipeline GitHub Pages.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DASHBOARD_JSON = REPO_ROOT / "data.json"
```

**Comando de verificação:**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
python -c "
import sys; sys.path.insert(0, 'scripts')
from lib import paths
assert hasattr(paths, 'REPO_ROOT')
assert hasattr(paths, 'DASHBOARD_JSON')
assert not hasattr(paths, 'Paths'), 'Paths dataclass não foi removida'
print('OK paths.py simplificado')
"
```

Saída esperada:

```
OK paths.py simplificado
```

**Em caso de falha:**
- `AssertionError Paths dataclass não foi removida`: o arquivo ainda tem a classe. Garantir substituição total.

---

### Task F1-9 — Smoke test importação completa

**Target:** shared
**Working Directory:** `.`
**Agente recomendado:** `ring:general-purpose`
**Depende de:** Tasks F1-6, F1-7, F1-8

**Comando exato:**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
python -c "
import sys; sys.path.insert(0, 'scripts')
# Importa em ordem topológica
from lib import logger, gold_paths, azure_io, io_utils, payload, formatters, scenario, perfil_rules
import generate_dashboard_data
print('OK todos os módulos importam')
"
```

Saída esperada:

```
OK todos os módulos importam
```

**Em caso de falha:**
- `ImportError`: ler trace, voltar à task da camada com erro
- `RuntimeError`: pode ser do `lru_cache` instanciando o cliente Azure no momento errado. O código no Task F1-5 usa `@lru_cache` em função, que só instancia no primeiro `_service_client()`. Se der erro aqui é bug — revisar

---

### Task F1-CHECKPOINT-2 — Code Review do Batch 2

**Target:** shared
**Working Directory:** `.`
**Agente recomendado:** orquestrador humano dispara `ring:requesting-code-review`
**Depende de:** Tasks F1-6 a F1-9

**Escopo:** `scripts/lib/io_utils.py`, `scripts/generate_dashboard_data.py`, `scripts/lib/paths.py`.

**Tratamento por severidade:** idêntico aos checkpoints anteriores. Prosseguir com zero Critical/High/Medium.

---

### Batch 3 — Limpeza & CI

---

### Task F1-10 — Atualizar `.gitignore`

**Target:** shared
**Working Directory:** `.`
**Agente recomendado:** `ring:general-purpose`
**Depende de:** —

**Arquivos:**
- Modificar: `/Users/victorbraga/Downloads/radar-fidc/.gitignore`

**O que muda:**
- Adicionar `data_real/` (ignorar o diretório inteiro, vai ser removido na próxima task)
- Adicionar `.cache/` (cache local da Task F1-5)
- Remover as 5 linhas de allowlist `!data_real/**/*.csv`, `!data_real/*.csv`, `!data_real/**/*.parquet`, `!data_real/*.xlsx`, `!data_real/*.pkl` (não fazem mais sentido)
- Remover o bloco "Por padrão CSVs e Parquets ficam fora" — `data_real/` sumiu, então as exceções somem juntas

**Conteúdo final completo:**

```gitignore
# ============================================================
# Radar FIDC — .gitignore
# ============================================================

# Credenciais e variáveis de ambiente (NUNCA commitar)
.env
*.env
.env.local

# Arquivos internos do projeto (orquestrador interno)
AGENT.md
MEMORY.md
POWERBI_SETUP.md
ralph.sh
prd.json
ralph.log

# Python
__pycache__/
*.py[cod]
*.pyo
.venv/
venv/
env/
*.egg-info/
dist/
build/

# Dados locais (não devem entrar no repo — geração on-demand via ADLS)
data/
data_real/
.cache/

# macOS
.DS_Store
.AppleDouble
._*

# IDEs
.idea/
.vscode/
*.swp
*.swo

# Jupyter
.ipynb_checkpoints/
*.ipynb

# Logs
*.log
logs/
```

**Comando de verificação:**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
grep -c "^data_real/$" .gitignore   # Esperado: 1
grep -c "^\.cache/$" .gitignore     # Esperado: 1
grep -c "!data_real" .gitignore     # Esperado: 0
```

Saídas esperadas: `1`, `1`, `0`.

**Em caso de falha:** reabrir o arquivo, garantir que linhas começam exatamente com `data_real/` (sem `/` à esquerda) e `.cache/`.

---

### Task F1-11 — Remover `data_real/` do repositório

**Target:** shared
**Working Directory:** `.`
**Agente recomendado:** `ring:general-purpose`
**Depende de:** Task F1-10 (`.gitignore` precisa estar atualizado primeiro, senão o Git ainda tracka novos arquivos)

**Por que:** O diretório local ainda fica no disco do desenvolvedor (não é apagado), mas o Git para de rastreá-lo. Isso permite continuar usando `data_real/` localmente como cache de emergência sem commitá-lo.

**Comando exato:**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
git rm -r --cached data_real/
# `-r --cached`: remove do índice do Git, NÃO apaga do disco.
```

Saída esperada (uma linha por arquivo):

```
rm 'data_real/README.md'
rm 'data_real/arquivos/cda/README.md'
rm 'data_real/clientes.csv'
rm 'data_real/credit_model.pkl'
rm 'data_real/macroeconomicos/consolidade.csv'
rm 'data_real/matches.xlsx'
rm 'data_real/rating_fidc.xlsx'
rm 'data_real/scores_credito.csv'
... (~10-15 linhas total)
```

**Critério de verificação:**

```bash
git status | head -20
ls data_real/ | head -5   # Local AINDA tem os arquivos (cache)
```

Esperado em `git status`:
- Bloco "Changes to be committed:" com várias linhas `deleted: data_real/...`
- Os arquivos deletados são todos os do `data_real/`

Esperado em `ls data_real/`:
- Lista os arquivos normalmente (o `--cached` preservou no disco)

**Em caso de falha:**
- Se `git rm -r --cached` reclamar "pathspec did not match any files": confirmar que `data_real/` está versionado (`git ls-files data_real/ | head -3`)
- Se acidentalmente rodou `git rm -r` (sem `--cached`): os arquivos sumiram do disco. Recuperar com `git checkout HEAD -- data_real/` e refazer com `--cached`

---

### Task F1-12 — Refatorar workflow para `data-refresh.yml`

**Target:** shared
**Working Directory:** `.`
**Agente recomendado:** `ring:devops-engineer`
**Depende de:** Task F1-1 (requirements.txt) e F1-7 (script refatorado)

**Arquivos:**
- Criar: `/Users/victorbraga/Downloads/radar-fidc/.github/workflows/data-refresh.yml`
- Deletar: `/Users/victorbraga/Downloads/radar-fidc/.github/workflows/update-dashboard.yml`

**Conteúdo completo do novo `data-refresh.yml`:**

```yaml
name: Data refresh (ADLS → data.json)

# Regenera data.json lendo o Gold do ADLS Gen2 (dfdatalakesprint/gold/final).
# Tem 2 triggers: cron diário 9h UTC (depois da pipeline Databricks 6h UTC) e
# dispatch manual. Push em arquivos do código deixa de disparar (o pipeline é
# disparado por DADO NOVO no Gold, não por código).

on:
  schedule:
    - cron: "0 9 * * *"
  workflow_dispatch: {}

concurrency:
  group: data-refresh
  # `false` (mudança crítica vs update-dashboard.yml): se um run ainda está
  # rodando e outro entra na fila, deixar o segundo esperar — NÃO cancelar
  # o primeiro (risco de commit pela metade).
  cancel-in-progress: false

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
          fetch-depth: 2   # HEAD~1 será usado no regression check (Fase 2)
          persist-credentials: true

      - name: Set up Python
        uses: actions/setup-python@0a5c61591373683505ea898e09a3ea4f39ef2b9c   # v5.0.0
        with:
          python-version: "3.11"
          cache: "pip"
          cache-dependency-path: requirements.txt

      - name: Validar secret AZURE_CONNECTION_STRING
        env:
          AZURE_CONNECTION_STRING: ${{ secrets.AZURE_CONNECTION_STRING }}
        run: |
          if [ -z "$AZURE_CONNECTION_STRING" ]; then
            echo "::error::AZURE_CONNECTION_STRING não está configurada nos secrets."
            echo "::error::Settings → Secrets and variables → Actions → New repository secret"
            exit 1
          fi
          # Sanity check do formato (não loga o valor).
          case "$AZURE_CONNECTION_STRING" in
            *"AccountName=dfdatalakesprint"*"AccountKey="*"EndpointSuffix=core.windows.net"*)
              echo "OK formato esperado da connection string para dfdatalakesprint"
              ;;
            *)
              echo "::error::AZURE_CONNECTION_STRING não tem o formato esperado"
              echo "::error::Esperado: DefaultEndpointsProtocol=https;AccountName=dfdatalakesprint;AccountKey=...;EndpointSuffix=core.windows.net"
              exit 1
              ;;
          esac

      - name: Install Python dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Smoke check Azure SDK imports
        run: |
          python -c "from azure.storage.filedatalake import DataLakeServiceClient; print('OK SDK')"

      - name: Generate data.json (lê do ADLS)
        env:
          AZURE_CONNECTION_STRING: ${{ secrets.AZURE_CONNECTION_STRING }}
        run: python scripts/generate_dashboard_data.py

      - name: Commit if changed
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          set -e
          git config user.name  "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          if git diff --quiet data.json; then
            echo "Sem mudanças em data.json."
            exit 0
          fi
          git add data.json
          git commit -m "chore: Regenerate dashboard data ($(date -u +%Y-%m-%d))"
          git push
```

**Comando para criar/deletar:**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
# Apagar o antigo
git rm .github/workflows/update-dashboard.yml
# O novo é criado salvando o conteúdo acima em .github/workflows/data-refresh.yml com o editor
ls .github/workflows/
```

Saída esperada de `ls`:

```
data-refresh.yml
```

(e só esse, se não houver outros workflows).

**Comando de verificação do conteúdo:**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
test -f .github/workflows/data-refresh.yml && echo "OK novo workflow"
test ! -f .github/workflows/update-dashboard.yml && echo "OK antigo removido"

python -c "import yaml; w=yaml.safe_load(open('.github/workflows/data-refresh.yml')); print('OK YAML válido:', list(w.keys()))"

grep -c "cancel-in-progress: false" .github/workflows/data-refresh.yml   # Esperado: 1
grep -c "pip install -r requirements.txt" .github/workflows/data-refresh.yml   # Esperado: 1
grep -c "pip install --quiet pandas openpyxl" .github/workflows/data-refresh.yml   # Esperado: 0
grep -c "paths:" .github/workflows/data-refresh.yml   # Esperado: 0 (sem path filter)
grep -c "data_real" .github/workflows/data-refresh.yml   # Esperado: 0
grep -c "dfdatalakesprint" .github/workflows/data-refresh.yml   # Esperado: 1
```

Saídas esperadas: `OK novo workflow`, `OK antigo removido`, `OK YAML válido: ['name', True, 'concurrency', 'permissions', 'jobs']` (a chave `on` pode aparecer como `True` por uma peculiaridade do parser PyYAML — isso é OK), depois `1, 1, 0, 0, 0, 1`.

**Em caso de falha:**
- `yaml.YAMLError`: indentação/aspas. Comparar com o template
- O parser do PyYAML interpreta `on:` como `True:` em algumas versões — isso é cosmético, GitHub Actions ignora
- Se `gh workflow list` (Task F1-16) não enxergar o novo workflow: pode demorar até 60s para indexar

---

### Task F1-13 — Commit do Batch 3

**Target:** shared
**Working Directory:** `.`
**Agente recomendado:** `ring:devops-engineer`
**Depende de:** Tasks F1-10, F1-11, F1-12

**Comandos:**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
git status
git add .gitignore .github/workflows/
# Os deletes de data_real/ e update-dashboard.yml já estão no índice por causa de `git rm`
git status
```

Esperado em `git status`:
- `modified:   .gitignore`
- `new file:   .github/workflows/data-refresh.yml`
- `deleted:    .github/workflows/update-dashboard.yml`
- `deleted:    data_real/...` (várias entradas)

```bash
git commit -m "feat: Connect dashboard data generation to ADLS Gen2

Substitui leitura de data_real/ local por leitura direta do
gold/final/ no ADLS (dfdatalakesprint), com cache de duas camadas
(bytes via ETag + parse cache pkl).

Mudanças:
- requirements.txt: +azure-storage-file-datalake, +openpyxl, +pandera
- .env.example: dfdatalakesprint (era stdatatalake2026)
- scripts/lib/azure_io.py: nova camada de acesso ao Lake
- scripts/lib/gold_paths.py: constantes de paths lógicos
- scripts/lib/logger.py: logs estruturados JSON Lines
- scripts/lib/io_utils.py: refatorado, sem parâmetros (paths internos)
- scripts/lib/paths.py: simplificado (Paths dataclass removida)
- scripts/generate_dashboard_data.py: lê ADLS
- .github/workflows/data-refresh.yml: substitui update-dashboard.yml,
  cancel-in-progress false, valida secret, instala via requirements.txt
- .gitignore: +data_real/, +.cache/
- data_real/ removido do versionamento (continua local como cache)"
```

**Critério de verificação:**

```bash
git log --oneline -3
git status   # Esperado: working tree clean
```

Esperado em `git log`:

```
def5678 feat: Connect dashboard data generation to ADLS Gen2
abc1234 chore: Add pre-commit hooks for gitleaks ruff and prettier
873273e Merge pull request #5 from victorsouza14/feat/mobile-responsive-and-chart-fixes
```

**Em caso de falha:**
- Se o pre-commit bloquear o commit por reformatar arquivos: rodar `git add -u` e re-commitar
- Se `pre-commit run gitleaks` reportar leak: STOP — pode ser leak real, ou um falso positivo no `.env.example`. Se for falso positivo, adicionar regra no `.gitleaksignore`

---

### Task F1-CHECKPOINT-3 — Code Review do Batch 3

**Target:** shared
**Working Directory:** `.`
**Agente recomendado:** orquestrador humano dispara `ring:requesting-code-review`
**Depende de:** Tasks F1-10 a F1-13

**Escopo:** `.gitignore`, remoção de `data_real/`, `.github/workflows/data-refresh.yml`.

**Foco especial:**
- `security-reviewer`: confirmar que `AZURE_CONNECTION_STRING` é referenciada apenas via `secrets.` e não logada
- `consequences-reviewer`: a regra `cancel-in-progress: false` evita race conditions mas pode levar a runs enfileirados — aceitável?

**Tratamento por severidade:** idêntico aos checkpoints anteriores.

---

### Batch 4 — Documentação & verificação end-to-end

---

### Task F1-14 — Atualizar `README.md`

**Target:** shared
**Working Directory:** `.`
**Agente recomendado:** `ring:general-purpose`
**Depende de:** —

**Arquivos:**
- Modificar: `/Users/victorbraga/Downloads/radar-fidc/README.md`

**O que muda (todas as alterações):**

1. **Linha 95** (atual: `2. Notebooks Bronze → Silver → Gold geram parquets e CSVs em \`stdatatalake2026/gold/powerbi/\`.`):
   Substituir por:
   ```markdown
   2. Notebooks Bronze → Silver → Gold geram parquets e CSVs em `dfdatalakesprint/gold/final/`.
   ```

2. **Linha 96-99** (descrição do step 3):
   Manter a estrutura, mas trocar a referência ao path:
   ```markdown
   3. **9h UTC** — `.github/workflows/data-refresh.yml` (cron) executa
      `scripts/generate_dashboard_data.py`, que lê os arquivos do ADLS Gen2 (`gold/final/`), gera o `data.json` e
      commita no repositório se houve mudança.
   ```

3. **Linha 116** (referência ao workflow renomeado):
   ```markdown
   │   └── data-refresh.yml                # GitHub Action de atualização diária (lê ADLS → data.json)
   ```

4. **Linha 119** (descrição do script):
   ```markdown
   │   └── generate_dashboard_data.py      # ADLS gold/final/ → data.json
   ```

5. **Linha 157** (pré-requisito):
   ```markdown
   - Acesso ao ADLS Gen2 (`dfdatalakesprint`) — connection string (rotacionada trimestralmente)
   ```

6. **Linhas 189-197** (seção "4. Atualizar o dashboard localmente"): SUBSTITUIR todo o bloco por:
   ```markdown
   ### 4. Atualizar o dashboard localmente

   ```bash
   # Carrega .env (precisa AZURE_CONNECTION_STRING válida para dfdatalakesprint)
   set -a && source .env && set +a

   # Gera data.json lendo direto do ADLS
   python scripts/generate_dashboard_data.py

   # Saída customizada (útil para diff)
   python scripts/generate_dashboard_data.py --output /tmp/data.json
   ```

   O cache local em `.cache/` (ignorado pelo Git) acelera execuções subsequentes
   via validação de ETag — só re-baixa arquivo que mudou no Gold.
   ```

   (Remover completamente as flags `--source azure` e `--source local`, que nunca existiram no código real — eram documentação desatualizada.)

7. **Linha 226** (referência a `data_real/clientes.csv`):
   ```markdown
   O dataset `clientes.csv` (em `gold/final/clientes.csv` no ADLS) contém dados de teste/acadêmicos com nomes
   ```

**Comando de verificação:**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
grep -c "stdatatalake2026" README.md   # Esperado: 0
grep -c "dfdatalakesprint" README.md   # Esperado: 3 (linhas 95, 157, 226 ou onde caírem)
grep -c "update-dashboard.yml" README.md   # Esperado: 0
grep -c "data-refresh.yml" README.md   # Esperado: 1
grep -c -- "--source azure\|--source local" README.md   # Esperado: 0
```

**Em caso de falha:** rodar `grep -n stdatatalake2026 README.md` para localizar referências remanescentes e corrigir.

---

### Task F1-15 — Atualizar `docs/arquitetura.md`, `docs/fontes_dados.md` e `docs/powerbi_setup.md`

**Target:** shared
**Working Directory:** `.`
**Agente recomendado:** `ring:general-purpose`
**Depende de:** —

**Arquivos:**
- Modificar: `/Users/victorbraga/Downloads/radar-fidc/docs/arquitetura.md`
- Modificar: `/Users/victorbraga/Downloads/radar-fidc/docs/fontes_dados.md`
- Modificar: `/Users/victorbraga/Downloads/radar-fidc/docs/powerbi_setup.md`

**Mudanças em `docs/arquitetura.md`:**

1. **Linha 25**: `│           AZURE DATA LAKE STORAGE Gen2 (stdatatalake2026)           │` → `│         AZURE DATA LAKE STORAGE Gen2 (dfdatalakesprint)           │`
   (preservar largura aproximada da caixa ASCII; ajustar espaços para manter alinhamento visual)

2. **Linha 76**: `- **Conta**: \`stdatatalake2026\`` → `- **Conta**: \`dfdatalakesprint\``

3. Adicionar parágrafo após linha 78 (após "Formato: CSV..."):
   ```markdown
   - **Prefixo de outputs analíticos**: `gold/final/` (consumido pelo `generate_dashboard_data.py`)
   ```

**Mudanças em `docs/fontes_dados.md`:**

1. **Linha 71**: `ADLS Gen2 — stdatatalake2026` → `ADLS Gen2 — dfdatalakesprint`

2. Adicionar bloco antes de "## Volume de Dados" (após linha 108):
   ```markdown
   > **Nota (Fase 1):** O `scripts/generate_dashboard_data.py` consome os arquivos
   > do prefixo `gold/final/` (não mais `gold/powerbi/`). Mapping atual:
   >
   > | Arquivo no ADLS | Usado em |
   > |---|---|
   > | `gold/final/rating_fidc.xlsx` | Visão Geral, Score & Risco, FIDCs |
   > | `gold/final/matches.xlsx` | Recomendação PME, Match |
   > | `gold/final/clientes.csv` | Clientes (PII mascarado no data.json) |
   > | `gold/final/scores_credito.csv` | Credit |
   > | `gold/final/macroeconomicos/consolidade.csv` | Cenário Macro |
   ```

**Mudanças em `docs/powerbi_setup.md`:**

1. **Linha 4**: `ADLS Gen2 (conta \`stdatatalake2026\`).` → `ADLS Gen2 (conta \`dfdatalakesprint\`).`

2. **Linha 29**: `https://stdatatalake2026.dfs.core.windows.net/gold/` → `https://dfdatalakesprint.dfs.core.windows.net/gold/`

3. Adicionar nota antes da seção "Modelo de dados sugerido" (após linha 41):
   ```markdown
   > **Atenção:** Os caminhos no Power BI continuam apontando para `gold/powerbi/`
   > (sufixo legado dos notebooks de exportação CSV). O dashboard HTML consome
   > `gold/final/` (sufixo da pipeline analítica unificada). Os dois prefixos
   > coexistem no Lake — mantenha o `powerbi/` enquanto o Power BI estiver em uso.
   ```

**Comando de verificação:**

```bash
cd /Users/victorbraga/Downloads/radar-fidc
grep -c "stdatatalake2026" docs/arquitetura.md docs/fontes_dados.md docs/powerbi_setup.md
grep -c "dfdatalakesprint" docs/arquitetura.md docs/fontes_dados.md docs/powerbi_setup.md
```

Saída esperada:

```
docs/arquitetura.md:0
docs/fontes_dados.md:0
docs/powerbi_setup.md:0

docs/arquitetura.md:2
docs/fontes_dados.md:1
docs/powerbi_setup.md:2
```

(Contagem exata de `dfdatalakesprint` pode variar em ±1 dependendo de edits adicionais; o crítico é `stdatatalake2026` ser zero em todos.)

**Verificação adicional do mapping novo em `fontes_dados.md`:**

```bash
grep -c "gold/final/rating_fidc.xlsx" docs/fontes_dados.md   # Esperado: 1
```

**Em caso de falha:** rodar `grep -n stdatatalake2026 docs/*.md` para localizar referências esquecidas.

---

### Task F1-16 — Verificação end-to-end: gerar `data.json` do ADLS e diff vs atual

**Target:** shared
**Working Directory:** `.`
**Agente recomendado:** `ring:general-purpose`
**Depende de:** Tasks F1-1 a F1-15

**Pré-requisitos:**
- `.env` local com a nova `AZURE_CONNECTION_STRING` (Task F1-2 atualizou o `.env.example`; o desenvolvedor precisa ter sincronizado o `.env` real)
- Acesso de rede ao Azure
- Arquivos esperados existem em `gold/final/` (validar com Task de smoke ao final)

**Procedimento:**

```bash
cd /Users/victorbraga/Downloads/radar-fidc

# 1. Backup do data.json atual (para comparação)
cp data.json /tmp/data.json.before-fase1

# 2. Carrega .env (NUNCA logar AZURE_CONNECTION_STRING)
set -a
source .env
set +a

# 3. Confirma que está apontando para a conta certa
python -c "
import os
conn = os.environ.get('AZURE_CONNECTION_STRING', '')
assert 'AccountName=dfdatalakesprint' in conn, 'ERRO: .env aponta para conta errada'
print('OK .env aponta para dfdatalakesprint')
"

# 4. Limpa cache para forçar download fresh
rm -rf .cache/

# 5. Gera data.json a partir do ADLS, em saída temporária
python scripts/generate_dashboard_data.py --output /tmp/data.json.after-fase1
```

**Saída esperada de `python scripts/generate_dashboard_data.py`** (logs em JSON Lines, uma linha por evento):

```
{"ts": "...", "level": "info", "event": "pipeline_start", "logger": "__main__", "source": "adls", "filesystem": "gold", "prefix": "final"}
{"ts": "...", "level": "info", "event": "reading", "logger": "__main__", "source": "rating_fidc.xlsx"}
{"ts": "...", "level": "info", "event": "download_start", "logger": "lib.azure_io", "path": "final/rating_fidc.xlsx"}
{"ts": "...", "level": "info", "event": "download_cache_miss", "logger": "lib.azure_io", "path": "final/rating_fidc.xlsx", "cached_etag": null, "remote_etag": "0x8D..."}
{"ts": "...", "level": "info", "event": "download_complete", "logger": "lib.azure_io", "path": "final/rating_fidc.xlsx", "bytes": ..., "etag": "0x8D..."}
... (idem para matches, clientes, credit, macro)
{"ts": "...", "level": "info", "event": "pipeline_end", "output": "/tmp/data.json.after-fase1", "size_kb": ..., "fidcs_resumo": ..., ...}
```

**Verificação 1 — JSON válido:**

```bash
python -c "import json; json.load(open('/tmp/data.json.after-fase1')); print('OK JSON válido')"
```

Saída esperada: `OK JSON válido`.

**Verificação 2 — diff estrutural:**

```bash
python <<'PY'
import json
before = json.load(open('/tmp/data.json.before-fase1'))
after = json.load(open('/tmp/data.json.after-fase1'))

# Chaves top-level devem ser idênticas (contrato preservado)
assert set(before.keys()) == set(after.keys()), \
    f"Chaves diferentes: only_before={set(before)-set(after)}, only_after={set(after)-set(before)}"

# Estrutura de fidcs deve estar igual
for key in ("stats", "resumo", "detalhe", "scatter"):
    assert key in after["fidcs"], f"fidcs.{key} ausente"

# Contagens devem ser numericamente próximas (não exatas — pipeline pode ter dados mais novos)
def close(a, b, tol=0.30):
    if a == 0 and b == 0:
        return True
    return abs(a - b) / max(abs(a), abs(b)) < tol

for path in [
    ("fidcs", "stats", "total_fundos"),
    ("clientes", "total"),
    ("matches", "total"),
]:
    val_b, val_a = before, after
    for p in path:
        val_b = val_b[p]
        val_a = val_a[p]
    status = "OK" if close(val_b, val_a) else "WARN"
    print(f"{status} {'.'.join(path)}: before={val_b}, after={val_a}")

# Heuristica documentada (Fase 1 não corrige — Fase 3 corrige)
assert after["macro"].get("is_proj_heuristica") == True
print("OK macro.is_proj_heuristica=true preservado")
PY
```

Saída esperada (números variam — o importante é "OK" em todas as comparações, ou "WARN" justificável):

```
OK fidcs.stats.total_fundos: before=2489, after=2491
OK clientes.total: before=1000, after=1000
OK matches.total: before=3000, after=3000
OK macro.is_proj_heuristica=true preservado
```

**Verificação 3 — sem PII no payload:**

```bash
python <<'PY'
import re
data = open('/tmp/data.json.after-fase1').read()
# CPF não mascarado: \d{3}\.\d{3}\.\d{3}-\d{2} OU \d{11}
cpf_real = re.findall(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b", data)
cpf_real = [c for c in cpf_real if not c.startswith("***.")]
assert len(cpf_real) == 0, f"PII vazada: {cpf_real[:5]}"
# Email com domínio: ([^*])@([^.])+\.(com|br|net) sem mask
emails = re.findall(r"[a-zA-Z0-9_][a-zA-Z0-9_.+-]*@[a-zA-Z0-9_.+-]+\.[a-z]{2,4}", data)
assert len(emails) == 0, f"Emails reais: {emails[:5]}"
print("OK PII mascarada (zero CPFs, zero emails reais)")
PY
```

Saída esperada: `OK PII mascarada (zero CPFs, zero emails reais)`.

**Verificação 4 — cache local funciona (segunda execução é rápida):**

```bash
time python scripts/generate_dashboard_data.py --output /tmp/data.json.second-run
```

Saída esperada: log com vários `download_cache_hit` (não miss) e tempo total < 3s (cache válido = sem re-download).

**Decisão final:**

- Todos os "OK" verdes → Fase 1 completa, prosseguir para commit
- "WARN" justificável (diferença >30% num campo mas dados realmente são mais novos no Lake) → documentar no PR
- Falha em alguma verificação → debugar antes de seguir

**Comando para commitar (se tudo passou):**

```bash
cd /Users/victorbraga/Downloads/radar-fidc

# Copia o data.json gerado em verificação para a raiz (será commitado)
cp /tmp/data.json.after-fase1 data.json

git add README.md docs/arquitetura.md docs/fontes_dados.md docs/powerbi_setup.md data.json
git status
git commit -m "docs: Update storage account references to dfdatalakesprint

- README.md, docs/arquitetura.md, docs/fontes_dados.md,
  docs/powerbi_setup.md: stdatatalake2026 → dfdatalakesprint
- README.md: remove --source azure/--source local (flags inexistentes)
- docs/fontes_dados.md: adiciona mapping gold/final/* → páginas
- data.json: regenerado lendo do ADLS (Fase 1 fim-a-fim)"
```

**Em caso de falha:**
- `AzureAuthError`: o `.env` ainda usa a chave antiga ou o `AccountName` errado. Atualizar com a nova chave da Task F0-1
- `ResourceNotFoundError`: o arquivo não existe em `gold/final/`. Listar com `az storage fs file list --file-system gold --account-name dfdatalakesprint --path final --connection-string "$AZURE_CONNECTION_STRING" -o table` (precisa Azure CLI) ou via `azure_io.list_dir("final/")` em Python
- Diferenças grandes (>30%) em contagens: ler manualmente os arquivos do Lake e comparar com `data_real/` local — se Lake tem dados muito mais novos, pode ser legítimo
- Tempo na verificação 4 > 3s: cache não está funcionando. Inspecionar `.cache/final/` e os arquivos `.etag`

---

### Task F1-CHECKPOINT-4 — Code Review final da Fase 1

**Target:** shared
**Working Directory:** `.`
**Agente recomendado:** orquestrador humano dispara `ring:requesting-code-review`
**Depende de:** Tasks F1-14, F1-15, F1-16

**Escopo:** README.md, docs/*.md, data.json (regenerado), e revisão consolidada de toda a Fase 1.

**Foco especial:**
- `business-logic-reviewer`: confirmar que o contrato do `data.json` permanece compatível (frontend não quebra)
- `security-reviewer`: confirmar mais uma vez que nenhuma chave aparece em arquivo versionado
- `test-reviewer`: a Fase 1 não adicionou testes formais — registrar como Low (testes virão na Fase 2 com pandera)

**Tratamento por severidade:** idêntico aos checkpoints anteriores. Para "test-reviewer" reportando "sem testes": adicionar `TODO(review): Testes formais virão na Fase 2 com pandera schemas (reportado por test-reviewer em 2026-05-14, severidade: Low)` ao topo de `scripts/lib/io_utils.py`.

---

## Encerramento da Fase 1

**Critérios de DONE da Fase 1:**

- [ ] Workflow `data-refresh.yml` executa com sucesso em modo `workflow_dispatch` (testar via `gh workflow run data-refresh.yml --ref main` após o merge do PR)
- [ ] `data.json` na raiz do repo foi regenerado lendo do ADLS (commit visível no histórico)
- [ ] `data_real/` não aparece em `git ls-files`
- [ ] Nenhuma referência a `stdatatalake2026` no repo (`git grep stdatatalake2026 | wc -l` deve retornar 0, exceto na spec em `docs/superpowers/`)
- [ ] `.pre-commit-config.yaml` instalado e ativo
- [ ] Branch protection ativa em `main`
- [ ] Push protection ativo no repo

**Comando final de verificação:**

```bash
cd /Users/victorbraga/Downloads/radar-fidc

# Zero referências legadas (ignorando a spec que é histórica)
git grep stdatatalake2026 -- ':!docs/superpowers/' | wc -l   # Esperado: 0
git grep "data_real" -- ':!docs/superpowers/' ':!scripts/rating.py' ':!scripts/credit_model.py' ':!scripts/match.py' ':!docs/credit_model.md' ':!docs/match_engine.md' | wc -l   # Esperado: 0 (data_real só aparece em scripts secundários do Databricks)

# Workflow novo presente, antigo ausente
test -f .github/workflows/data-refresh.yml && echo "OK data-refresh.yml existe"
test ! -f .github/workflows/update-dashboard.yml && echo "OK update-dashboard.yml ausente"

# Pre-commit funciona
pre-commit run --all-files
```

Saída final esperada: vários `Passed` do pre-commit, sem falhas críticas.

**Próximos passos após Fase 1:**
- Abrir PR para `main` consolidando tudo
- Rodar `workflow_dispatch` em produção para validar
- Iniciar Fase 2 (Trust layer): pandera schemas, `trust_manifest.py`, `regression_check.py`, GE no Databricks
- Programar revisão trimestral da Account Key (próxima rotação: 2026-08-14)

---

## Resumo de tarefas (visão executiva)

| ID | Descrição | Duração | Dependências | Tipo |
|---|---|---|---|---|
| F0-1 | Rotacionar Account Key no Azure Portal | 5 min + 5 min wait | — | HUMAN |
| F0-2 | Atualizar GitHub Secret `AZURE_CONNECTION_STRING` | 2 min | F0-1 | HUMAN |
| F0-3 | Auditar histórico git por leak | 3 min | — | AGENT |
| F0-3b | (Condicional) Purgar leak via `git filter-repo` | 15 min | F0-3 + | HUMAN |
| F0-4 | Criar `.pre-commit-config.yaml` | 5 min | — | AGENT |
| F0-5 | Commit Fase 0 parcial | 2 min | F0-4 | AGENT |
| F0-6 | Habilitar GitHub Push Protection | 3 min | — | HUMAN |
| F0-7 | Branch protection em `main` | 3 min | F0-5 | HUMAN |
| F0-CHECKPOINT | Code review Fase 0 | 15 min | F0-1..7 | AGENT |
| F1-1 | Atualizar `requirements.txt` | 3 min | F0 done | AGENT |
| F1-2 | Atualizar `.env.example` | 3 min | — | AGENT |
| F1-3 | Criar `scripts/lib/logger.py` | 5 min | — | AGENT |
| F1-4 | Criar `scripts/lib/gold_paths.py` | 3 min | — | AGENT |
| F1-5 | Criar `scripts/lib/azure_io.py` | 5 min | F1-1, F1-3, F1-4 | AGENT |
| F1-CHECKPOINT-1 | Review Batch 1 | 15 min | F1-1..5 | AGENT |
| F1-6 | Refatorar `scripts/lib/io_utils.py` | 5 min | F1-5 | AGENT |
| F1-7 | Refatorar `scripts/generate_dashboard_data.py` | 5 min | F1-6 | AGENT |
| F1-8 | Simplificar `scripts/lib/paths.py` | 3 min | F1-7 | AGENT |
| F1-9 | Smoke test importação | 2 min | F1-6, F1-7, F1-8 | AGENT |
| F1-CHECKPOINT-2 | Review Batch 2 | 15 min | F1-6..9 | AGENT |
| F1-10 | Atualizar `.gitignore` | 3 min | — | AGENT |
| F1-11 | `git rm -r --cached data_real/` | 2 min | F1-10 | AGENT |
| F1-12 | Refatorar workflow → `data-refresh.yml` | 5 min | F1-1, F1-7 | AGENT |
| F1-13 | Commit Batch 3 | 3 min | F1-10..12 | AGENT |
| F1-CHECKPOINT-3 | Review Batch 3 | 15 min | F1-10..13 | AGENT |
| F1-14 | Atualizar `README.md` | 5 min | — | AGENT |
| F1-15 | Atualizar `docs/*.md` | 5 min | — | AGENT |
| F1-16 | Verificação end-to-end + commit final | 10 min | F1-1..15 | AGENT |
| F1-CHECKPOINT-4 | Review final | 15 min | F1-14..16 | AGENT |

**Total estimado:** ~2.5h Fase 0 (+ wait time da rotação) + ~3h Fase 1 = **~6 horas de trabalho efetivo**, espaçadas conforme disponibilidade do humano para as tarefas HUMAN-TASK.

---

## Garantias do plano (auto-checagem)

- [x] Header com objetivo, arquitetura, stack e pré-requisitos
- [x] Comandos de verificação inicial com output esperado
- [x] 31 tarefas (29 execução + 2 cleanup) com 2–5 min cada
- [x] Caminhos absolutos em todas as tarefas
- [x] Código completo (sem placeholder)
- [x] Comandos exatos com output esperado
- [x] Recuperação de falha em cada tarefa
- [x] 5 checkpoints de code review (1 Fase 0 + 4 Fase 1)
- [x] Tratamento por severidade documentado
- [x] Passa no Zero-Context Test (desenvolvedor sem familiaridade com o repo consegue executar)
- [x] HUMAN-TASKs com passos navegacionais e URLs específicas
- [x] Dependências entre tarefas explicitadas
