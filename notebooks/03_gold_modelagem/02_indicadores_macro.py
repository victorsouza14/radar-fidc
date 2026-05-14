# Notebook: 02_indicadores_macro
# Camada: Gold — Radar FIDC
#
# Consolida indicadores macroeconômicos atuais (SELIC, IPCA, CDI) e projeções 12m
# em uma única tabela `gold/indicadores_macro/indicadores.parquet`.
#
# Não altera o score por FIDC — o ajuste macro é responsabilidade do 01_score_fidc.

import io
import os
import sys
from datetime import date, datetime

import pandas as pd
from azure.storage.blob import BlobServiceClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import azure_connection_string  # noqa: E402


CONNECTION_STRING = azure_connection_string()
blob_svc = BlobServiceClient.from_connection_string(CONNECTION_STRING)
silver = blob_svc.get_container_client("silver")
gold = blob_svc.get_container_client("gold")

# Janela máxima de "frescor" da pesquisa Focus que aceitamos como fonte primária.
# Acima disso, caímos para heurística (mais transparente que projeção velha).
FOCUS_FRESHNESS_MAX_DAYS = 14
FOCUS_SILVER_PATH = "focus/projecoes_anuais.parquet"

# Fallback usado APENAS se a Silver estiver indisponível (não para mascarar erro).
FALLBACK = {
    "selic_atual": None,
    "ipca_12m": None,
    "cdi_atual": None,
    "selic_projetada_12m": None,
    "ipca_projetado_12m": None,
}

# COMMAND ----------

df_macro = pd.DataFrame()
blobs = [
    b for b in silver.list_blobs(name_starts_with="dados_macroeconomicos/")
    if b.name.endswith(".parquet")
]
print(f"Arquivos macro encontrados: {len(blobs)}")
for b in blobs:
    try:
        d = silver.get_blob_client(b.name).download_blob().readall()
        df_tmp = pd.read_parquet(io.BytesIO(d))
        df_macro = pd.concat([df_macro, df_tmp], ignore_index=True)
        print(f"  {b.name}: {len(df_tmp)} linhas")
    except Exception as e:
        print(f"  Erro lendo {b.name}: {e}")


# COMMAND ----------

def ultimo_valor(df, keywords):
    """Pega último valor numérico não-nulo de qualquer coluna cujo nome bata."""
    for col in df.columns:
        if any(k in col.lower() for k in keywords):
            v = pd.to_numeric(df[col], errors="coerce").dropna()
            if not v.empty:
                return float(v.iloc[-1])
    return None


def soma_ultimos_12(df, keywords):
    """Soma das últimas 12 observações (para acumulado IPCA)."""
    for col in df.columns:
        if any(k in col.lower() for k in keywords):
            v = pd.to_numeric(df[col], errors="coerce").dropna()
            if not v.empty:
                return round(float(v.tail(12).sum()), 4)
    return None


def carregar_focus_silver(silver_client, caminho: str) -> pd.DataFrame:
    """Lê silver/focus/projecoes_anuais.parquet; devolve DataFrame vazio se ausente."""
    try:
        data = silver_client.get_blob_client(caminho).download_blob().readall()
        df = pd.read_parquet(io.BytesIO(data))
        print(f"Focus Silver lido: {len(df)} projecoes")
        return df
    except Exception as e:
        print(f"Focus Silver ausente/erro ({e}). Fallback para heurística.")
        return pd.DataFrame()


def focus_para_indicadores(
    df_focus: pd.DataFrame,
    anos_alvo: tuple[int, int],
    max_age_days: int = FOCUS_FRESHNESS_MAX_DAYS,
) -> dict | None:
    """Extrai (selic_proj, ipca_proj, data_pesquisa) do parquet Silver.

    Retorna None se: vazio, sem cobertura mínima dos anos alvo, ou stale.
    Critério de stale: a pesquisa mais antiga entre as usadas tem >max_age_days.
    """
    if df_focus.empty:
        return None
    requeridos = {"Indicador", "DataReferencia", "Mediana", "DataPesquisa"}
    if not requeridos.issubset(df_focus.columns):
        print(f"Focus Silver com schema inesperado: {set(df_focus.columns)}")
        return None
    df = df_focus.copy()
    df["DataReferencia"] = df["DataReferencia"].astype(int)
    df["DataPesquisa"] = pd.to_datetime(df["DataPesquisa"], errors="coerce").dt.date

    out: dict = {"proj_source": "bcb_focus_top5"}
    datas_pesquisa = []
    ano_atual, ano_proximo = anos_alvo

    for indicador, key_atual, key_prox in (
        ("Selic", "selic_proj_atual", "selic_proj_proximo"),
        ("IPCA", "ipca_proj_atual", "ipca_proj_proximo"),
    ):
        sub = df[df["Indicador"] == indicador]
        if sub.empty:
            print(f"Focus sem indicador {indicador}; cai para heurística.")
            return None
        for ano, k in ((ano_atual, key_atual), (ano_proximo, key_prox)):
            linha = sub[sub["DataReferencia"] == ano]
            if linha.empty:
                print(f"Focus sem projecao {indicador}/{ano}; cai para heurística.")
                return None
            out[k] = round(float(linha["Mediana"].iloc[0]), 2)
            datas_pesquisa.append(linha["DataPesquisa"].iloc[0])

    pesquisa_mais_antiga = min(datas_pesquisa)
    idade = (date.today() - pesquisa_mais_antiga).days
    if idade > max_age_days:
        print(
            f"Focus stale: pesquisa mais antiga {pesquisa_mais_antiga} "
            f"({idade}d > {max_age_days}d). Cai para heurística."
        )
        return None

    out["proj_date"] = max(datas_pesquisa).isoformat()
    out["proj_pesquisa_mais_antiga"] = pesquisa_mais_antiga.isoformat()
    return out


# COMMAND ----------

ind = dict(FALLBACK)
ind["is_proj_heuristica"] = True
ind["proj_source"] = "heuristica_local"

if not df_macro.empty:
    # SELIC: alinhar com o frontend (`scripts/lib/payload.build_macro`), que
    # prefere `selic_efetiva` (SGS 1178 — taxa efetiva anualizada base 252,
    # ~14,4% em maio/26) com fallback para `selic_meta` (SGS 432 — meta Copom,
    # ~13,75%). Antes o notebook usava só `selic_meta`, então o cenário do
    # parquet dizia "SELIC 13,75%" enquanto o dashboard exibia 14,4%.
    ind["selic_atual"] = ultimo_valor(df_macro, ["selic_efetiva"])
    if ind["selic_atual"] is None:
        ind["selic_atual"] = ultimo_valor(df_macro, ["selic_meta", "selic"])
    ind["cdi_atual"] = ultimo_valor(df_macro, ["cdi"])
    ind["ipca_12m"] = soma_ultimos_12(df_macro, ["ipca"])
    # Heurística (default) — substituída adiante por Focus se disponível e fresh.
    if ind["selic_atual"] is not None:
        ind["selic_projetada_12m"] = round(ind["selic_atual"] - 0.5, 2)
    if ind["ipca_12m"] is not None:
        ind["ipca_projetado_12m"] = round(ind["ipca_12m"] * 0.9, 2)

# Tenta substituir as projeções heurísticas pelas oficiais do BCB Focus.
df_focus = carregar_focus_silver(silver, FOCUS_SILVER_PATH)
ano_atual = date.today().year
anos_alvo = (ano_atual, ano_atual + 1)
focus = focus_para_indicadores(df_focus, anos_alvo)
if focus is not None:
    # Override: ano corrente fica em `selic_projetada_12m`/`ipca_projetado_12m` (compat com Gold antigo);
    # próximo ano vai em campos extras para o frontend exibir o cenário 2027.
    ind["selic_projetada_12m"] = focus["selic_proj_atual"]
    ind["ipca_projetado_12m"] = focus["ipca_proj_atual"]
    ind[f"selic_proj_{ano_atual}"] = focus["selic_proj_atual"]
    ind[f"selic_proj_{ano_atual + 1}"] = focus["selic_proj_proximo"]
    ind[f"ipca_proj_{ano_atual}"] = focus["ipca_proj_atual"]
    ind[f"ipca_proj_{ano_atual + 1}"] = focus["ipca_proj_proximo"]
    ind["proj_source"] = focus["proj_source"]
    ind["proj_date"] = focus["proj_date"]
    ind["is_proj_heuristica"] = False
    print(
        f"Projecoes substituidas por BCB Focus (pesquisa {focus['proj_date']}); "
        "is_proj_heuristica=False."
    )
else:
    # Fallback explícito — útil pra auditar quando heurística ainda está em uso.
    fallback_age = "n/a"
    if df_focus is not None and not df_focus.empty:
        try:
            ultimas = pd.to_datetime(df_focus["DataPesquisa"], errors="coerce").dropna()
            if not ultimas.empty:
                fallback_age = f"{(datetime.now() - ultimas.max()).days}d"
        except Exception:
            pass
    print(f"Usando projecoes heurísticas (Focus indisponivel/stale; idade={fallback_age}).")


# Cenário macroeconômico
def classificar_cenario(selic):
    if selic is None:
        return "indisponivel", "Sem dados macro suficientes."
    if selic >= 13:
        return (
            "favoravel_posfixado",
            f"SELIC {selic:.2f}% favorece FIDCs pós-fixados (CDI+). "
            "Alta remuneração relativa frente à renda fixa tradicional.",
        )
    if selic >= 10:
        return (
            "neutro",
            f"SELIC {selic:.2f}% em patamar neutro. Diversificação recomendada.",
        )
    return (
        "favoravel_prefixado",
        f"SELIC {selic:.2f}% baixa favorece FIDCs pré-fixados, "
        "que travam taxa antes de novas quedas.",
    )


cenario, descricao = classificar_cenario(ind["selic_atual"])
ind["cenario_macro"] = cenario
ind["descricao_cenario"] = descricao
ind["data_ref"] = datetime.today().strftime("%Y-%m-%d")

print("Indicadores macro:")
for k, v in ind.items():
    print(f"  {k}: {v}")

# COMMAND ----------

try:
    gold.create_container()
except Exception:
    pass

buf = io.BytesIO()
pd.DataFrame([ind]).to_parquet(buf, index=False, engine="pyarrow")
gold.get_blob_client("indicadores_macro/indicadores.parquet").upload_blob(buf.getvalue(), overwrite=True)
print("\nSalvo: gold/indicadores_macro/indicadores.parquet")
