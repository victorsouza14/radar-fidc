# Conectar Power BI ao Radar FIDC

Os notebooks Gold exportam CSVs prontos para o Power BI em `gold/powerbi/` dentro do
ADLS Gen2 (conta `dfdatalakesprint`). Este guia mostra como conectar o Power BI Desktop
nesses arquivos.

> **Atenção:** Os caminhos no Power BI continuam apontando para `gold/powerbi/`
> (sufixo legado dos notebooks de exportação CSV). O dashboard HTML consome
> `gold/final/` (sufixo da pipeline analítica unificada). Os dois prefixos
> coexistem no Lake — mantenha o `powerbi/` enquanto o Power BI estiver em uso.

## Pré-requisitos

- Power BI Desktop (Windows).
- Acesso de leitura ao ADLS Gen2 do projeto. Você precisa de **um** dos dois:
  - **Conta de Storage + chave de acesso** (mais simples).
  - **Conta organizacional Azure AD** com permissão `Storage Blob Data Reader` no container `gold`.

## CSVs disponíveis

| Caminho | Conteúdo |
|---------|----------|
| `gold/powerbi/score_fidc.csv` | Score por FIDC (todos os 2k+ fundos) |
| `gold/powerbi/ranking_fidcs.csv` | Score + `rank_geral` |
| `gold/powerbi/recomendacao_pme.csv` | Top-3 FIDCs por segmento de PME |
| `gold/powerbi/indicadores_macro.csv` | SELIC, IPCA, CDI e projeções |
| `gold/powerbi/dashboard_master.csv` | Tabela mestre (rec + score + macro) |

## Passo a passo — Power BI Desktop

1. **Home → Get Data → More… → Azure → Azure Data Lake Storage Gen2**.
2. Informe a URL no formato:
   ```
   https://dfdatalakesprint.dfs.core.windows.net/gold/
   ```
3. Selecione **CDM Folder View** (Combine).
4. Autenticação:
   - **Account key**: Cole a chave primária da conta de Storage.
   - **Organizational account**: Faça login com a conta Azure AD com permissão.
5. Em **Navigator**, expanda `gold/powerbi/` e selecione os CSVs desejados.
6. Clique em **Transform Data** (não em Load).
7. No Power Query Editor, para cada query:
   - Confirme o **separador** (vírgula) e **encoding** (`65001 = UTF-8`).
   - Aplique tipagem em colunas numéricas (`score_final`, `retorno_medio`, `volatilidade`).
   - **Date locale**: defina `pt-BR` antes de converter colunas de data.
8. **Close & Apply**.

## Modelo de dados sugerido

```
dashboard_master  ←→  score_fidc         (via cnpj_fundo, 1:1)
dashboard_master  ←→  indicadores_macro  (relação implícita, sem join)
recomendacao_pme  →   score_fidc         (via cnpj_fundo, *:1)
```

## Refresh automático

- **Opção 1 — Manual**: clique em *Refresh* no Power BI Desktop.
- **Opção 2 — Service**: publique no Power BI Service, configure um **Gateway** com
  as credenciais do ADLS, e agende refresh diário às **9h Brasília** (após a pipeline
  ADF executar às 6h UTC + Gold).

## Solução de problemas

| Erro | Causa provável | Como resolver |
|------|----------------|---------------|
| `AuthorizationPermissionMismatch` | Conta sem role no container | Atribuir `Storage Blob Data Reader` |
| Caracteres errados (ç, ã) | Encoding diferente | Trocar para `65001 = UTF-8` no Power Query |
| `Could not save modifications` | Token expirado | Re-autenticar (File → Options → Data source settings) |
| Colunas com tipo `Any` | Detect type falhou | Aplicar tipagem manual em Transform Data |
