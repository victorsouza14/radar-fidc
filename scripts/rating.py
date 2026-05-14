import ast
import os
import pathlib
import re
import sys
from datetime import datetime

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE = os.environ.get("RADAR_ARQUIVOS", str(ROOT / "data_real" / "arquivos"))
OUTPUT = os.environ.get("RADAR_OUTPUT", str(ROOT / "data_real"))

# ─── Constantes versionadas ─────────────────────────────────────────────
# Mediana histórica fixa (2020-2025) da inadimplência PJ — fixar para estabilidade
# temporal do rating. Antes era recalculada a cada execução como mediana móvel
# (`inad_pj_serie.median()`), o que fazia o `fator_macro` mudar conforme o BCB
# publicava nova observação. Isso reescalava `f_inad` e deslocava as fronteiras
# de cluster, gerando instabilidade na classe (BAIXO/MEDIO/ALTO) de FIDCs entre
# runs consecutivos sem que o fundo tivesse mudado.
#
# Valor: 4,20% (mediana das observações mensais BCB SGS 21084 entre 2020-2025).
# Se atualizar este valor, documentar em `docs/limitacoes_atuais.md` no
# histórico de heurísticas substituídas.
INAD_PJ_MEDIANA_HISTORICA = 4.20


def main() -> int:
    print("=" * 60)
    print("  RATING FIDC - RISCO / RETORNO / PERFIL DE INVESTIDOR")
    print("=" * 60)
    print(f"Início: {datetime.now().strftime('%H:%M:%S')}\n")

    def limpar_cnpj(v):
        """Remove máscara e zero-pad para 14 dígitos."""
        return re.sub(r"\D", "", str(v)).zfill(14)

    # ============================================================
    # 1. MAPA DE SUBCLASSES  (codigo_subclasse -> tipo_cota + CNPJ)
    #    Usa fundos_v2 (5794 fundos históricos) para máxima cobertura
    # ============================================================
    print("[1/7] Mapeando tipos de cota (ANBIMA fundos_v2)...")

    df_v2 = pd.read_csv(os.path.join(BASE, "anbima", "fundos_v2_fidc.csv"), sep=";")

    def classificar_tipo(nome):
        n = str(nome).upper()
        # Regex com word-boundary evita falsos positivos do tipo "SUPERSR" e pega "SR1", "SR.", "SR-".
        if re.search(r"\b(SENIOR|SEN|SR)\b", n) or re.search(r"\bSR\d", n):
            return "SENIOR"
        if re.search(r"\b(MEZANINO|MEZZANINE|MEZ)\b", n):
            return "MEZANINO"
        if re.search(r"\b(JUNIOR|JR|SUBORDIN|SUBORD)\b", n):
            return "JUNIOR"
        return "UNICA"

    registros = []
    for _, row in df_v2.iterrows():
        cnpj_fundo = limpar_cnpj(row["identificador_fundo"])
        nome_fundo = row.get("razao_social_fundo", "")
        try:
            classes = ast.literal_eval(row["classes"])
            if not isinstance(classes, list):
                classes = [classes]
        except Exception:
            continue
        for cls in classes:
            if not isinstance(cls, dict):
                continue
            cod_classe = cls.get("codigo_classe")
            subs = cls.get("subclasses", [])
            if not isinstance(subs, list) or len(subs) == 0:
                # Fundo sem subclasses: mapeia a classe diretamente
                registros.append(
                    {
                        "codigo_subclasse": cod_classe,
                        "codigo_classe": cod_classe,
                        "CNPJ_FUNDO": cnpj_fundo,
                        "NOME_FUNDO": nome_fundo,
                        "TIPO_COTA": "UNICA",
                        "FOCO_ATUACAO": "",
                    }
                )
            else:
                for sub in subs:
                    if not isinstance(sub, dict):
                        continue
                    registros.append(
                        {
                            "codigo_subclasse": sub.get("codigo"),
                            "codigo_classe": cod_classe,
                            "CNPJ_FUNDO": cnpj_fundo,
                            "NOME_FUNDO": nome_fundo,
                            "TIPO_COTA": classificar_tipo(sub.get("nome_comercial", "")),
                            "FOCO_ATUACAO": "",
                        }
                    )

    df_classes = pd.DataFrame(registros).dropna(subset=["codigo_subclasse"])
    print(f"  {len(df_classes)} subclasses mapeadas | tipos: {df_classes['TIPO_COTA'].value_counts().to_dict()}")

    # CNPJs com data de encerramento = fundos cancelados/em liquidacao.
    # Ambos os lados (ANBIMA e Tab V do CVM) passam por `limpar_cnpj` → 14 dígitos zero-padded.
    cnpjs_encerrados = set(df_v2[df_v2["data_encerramento_fundo"].notna()]["identificador_fundo"].apply(limpar_cnpj))
    print(f"  {len(cnpjs_encerrados)} fundos encerrados/cancelados identificados (excluidos do rating)\n")
    # Sanity check: contar quantos encerrados aparecem na base mensal (descobre desalinhamento
    # de identificador entre fontes antes de o filtro virar no-op).
    # Esse print fica visível na execução; se a interseção for << len(cnpjs_encerrados),
    # logamos uma divergência clara.

    # ============================================================
    # 2. INADIMPLÊNCIA E AGING  (Tab V)
    # ============================================================
    print("[2/7] Carregando inadimplência e aging (Tab V)...")

    cols_v = [
        "CNPJ_FUNDO",
        "DT_COMPTC",
        "TAB_V_A_VL_DIRCRED_PRAZO",
        "TAB_V_B_VL_DIRCRED_INAD",
        "TAB_V_B1_VL_INAD_30",
        "TAB_V_B2_VL_INAD_60",
        "TAB_V_B3_VL_INAD_90",
        "TAB_V_B4_VL_INAD_120",
        "TAB_V_B5_VL_INAD_150",
        "TAB_V_B6_VL_INAD_180",
        "TAB_V_B7_VL_INAD_360",
        "TAB_V_B8_VL_INAD_720",
        "TAB_V_B9_VL_INAD_1080",
        "TAB_V_B10_VL_INAD_MAIOR_1080",
    ]

    df_v = pd.read_csv(
        os.path.join(BASE, "info_mensal", "inf_mensal_fidc_tab_V_.csv"), sep=";", usecols=cols_v, low_memory=False
    )

    for c in cols_v[2:]:
        df_v[c] = pd.to_numeric(df_v[c], errors="coerce").fillna(0)

    df_v["DT_COMPTC"] = pd.to_datetime(df_v["DT_COMPTC"], errors="coerce")
    df_v = df_v.sort_values("DT_COMPTC").groupby("CNPJ_FUNDO").last().reset_index()
    df_v["CNPJ_FUNDO"] = df_v["CNPJ_FUNDO"].apply(limpar_cnpj)

    df_v["TAXA_INAD"] = np.where(
        df_v["TAB_V_A_VL_DIRCRED_PRAZO"] > 0, df_v["TAB_V_B_VL_DIRCRED_INAD"] / df_v["TAB_V_A_VL_DIRCRED_PRAZO"], np.nan
    )

    # Aging ponderado: inadimplência concentrada em prazos mais longos = pior
    pesos_aging = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    cols_aging = [
        f"TAB_V_B{i}_VL_INAD_{p}"
        for i, p in zip(range(1, 11), [30, 60, 90, 120, 150, 180, 360, 720, 1080, "MAIOR_1080"], strict=False)
    ]
    total_inad = df_v["TAB_V_B_VL_DIRCRED_INAD"].replace(0, np.nan)
    aging_pond = sum(df_v[c] * p for c, p in zip(cols_aging, pesos_aging, strict=False))
    df_v["AGING_SCORE"] = (aging_pond / (total_inad * sum(pesos_aging))).fillna(0)

    inad_df = df_v[["CNPJ_FUNDO", "TAXA_INAD", "AGING_SCORE"]].copy()
    print(f"  {len(inad_df)} fundos carregados\n")

    # ============================================================
    # 3. RATING SCR DOS DEVEDORES  (Tab X)
    # ============================================================
    print("[3/7] Carregando SCR dos devedores (Tab X)...")

    ratings = ["AA", "A", "B", "C", "D", "E", "F", "G", "H"]
    cols_x = ["CNPJ_FUNDO", "DT_COMPTC"] + [f"TAB_X_SCR_RISCO_DEVEDOR_{r}" for r in ratings]

    df_x = pd.read_csv(
        os.path.join(BASE, "info_mensal", "inf_mensal_fidc_tab_X_.csv"), sep=";", usecols=cols_x, low_memory=False
    )

    for c in cols_x[2:]:
        df_x[c] = pd.to_numeric(df_x[c], errors="coerce").fillna(0)

    df_x["DT_COMPTC"] = pd.to_datetime(df_x["DT_COMPTC"], errors="coerce")
    df_x = df_x.sort_values("DT_COMPTC").groupby("CNPJ_FUNDO").last().reset_index()
    df_x["CNPJ_FUNDO"] = df_x["CNPJ_FUNDO"].apply(limpar_cnpj)

    # Peso: AA=0 (risco zero) → H=8 (perda provável)
    pesos_scr = {r: i for i, r in enumerate(ratings)}
    total_scr = df_x[[f"TAB_X_SCR_RISCO_DEVEDOR_{r}" for r in ratings]].sum(axis=1).replace(0, np.nan)
    scr_pond = sum(df_x[f"TAB_X_SCR_RISCO_DEVEDOR_{r}"] * p for r, p in pesos_scr.items())
    # 0=melhor, 1=pior. Fundos sem dados ficam como NaN e são EXCLUÍDOS no `mask_completo`
    # (antes preenchíamos com 0.5, o que mascarava ausência como "neutro" — bug corrigido).
    df_x["SCR_SCORE"] = scr_pond / (total_scr * 8)

    scr_df = df_x[["CNPJ_FUNDO", "SCR_SCORE"]].copy()
    print(f"  {len(scr_df)} fundos carregados\n")

    # ============================================================
    # 4. CONCENTRAÇÃO DE CEDENTES  (Tab I)
    # ============================================================
    print("[4/7] Carregando concentração de cedentes (Tab I)...")

    cols_i = ["CNPJ_FUNDO", "DENOM_SOCIAL", "DT_COMPTC", "TAB_I2A_VL_DIRCRED_RISCO"] + [
        f"TAB_I2B1_PR_CEDENTE_{i}" for i in range(1, 6)
    ]

    df_i = pd.read_csv(
        os.path.join(BASE, "info_mensal", "inf_mensal_fidc_tab_I_.csv"), sep=";", usecols=cols_i, low_memory=False
    )

    for c in cols_i[3:]:
        df_i[c] = pd.to_numeric(df_i[c], errors="coerce").fillna(0)

    df_i["DT_COMPTC"] = pd.to_datetime(df_i["DT_COMPTC"], errors="coerce")
    df_i = df_i.sort_values("DT_COMPTC").groupby("CNPJ_FUNDO").last().reset_index()
    df_i["CNPJ_FUNDO"] = df_i["CNPJ_FUNDO"].apply(limpar_cnpj)

    ced_cols = [f"TAB_I2B1_PR_CEDENTE_{i}" for i in range(1, 6)]
    df_i["CONC_MAIOR_CEDENTE"] = df_i[ced_cols].max(axis=1) / 100  # 0-1
    df_i["CONC_TOP3_CEDENTES"] = df_i[ced_cols[:3]].sum(axis=1) / 100

    conc_df = df_i[["CNPJ_FUNDO", "DENOM_SOCIAL", "CONC_MAIOR_CEDENTE", "CONC_TOP3_CEDENTES"]].copy()
    print(f"  {len(conc_df)} fundos carregados\n")

    # ============================================================
    # 5. RENTABILIDADE E VOLATILIDADE  (Série Histórica ANBIMA)
    # ============================================================
    print("[5/7] Calculando rentabilidade e volatilidade (ANBIMA série histórica)...")

    df_hist = pd.read_csv(os.path.join(BASE, "anbima", "serie_historica_fidc.csv"), sep=";")
    df_hist["valor_cota"] = pd.to_numeric(df_hist["valor_cota"], errors="coerce")
    df_hist["data_competencia"] = pd.to_datetime(df_hist["data_competencia"], errors="coerce")
    df_hist = df_hist.sort_values(["codigo_fundo", "codigo_classe", "data_competencia"])

    df_hist["retorno_mensal"] = df_hist.groupby(["codigo_fundo", "codigo_subclasse"])["valor_cota"].pct_change()

    # Últimos 24 meses para capturar ciclo recente
    data_corte = df_hist["data_competencia"].max() - pd.DateOffset(months=24)
    df_rec = df_hist[df_hist["data_competencia"] >= data_corte].copy()

    # Winsoriza retornos mensais (clip em ±50%) em vez de descartar.
    # Antes filtrávamos com `between(-0.5, 0.5)` — descartar valores legítimos > 50%
    # subestimava retorno e volatilidade de fundos voláteis. Clip preserva o sinal.
    CLIP = 0.5
    MIN_N = 3

    def _annual_return(serie: pd.Series) -> float:
        s = serie.clip(-CLIP, CLIP).dropna()
        if len(s) < MIN_N:
            return np.nan
        annual = (1.0 + s.mean()) ** 12 - 1.0
        return max(-1.0, min(annual, 10.0))  # mantém em faixa plotável

    def _annual_vol(serie: pd.Series) -> float:
        s = serie.clip(-CLIP, CLIP).dropna()
        if len(s) < MIN_N:
            return np.nan
        return float(s.std() * np.sqrt(12))

    ret_agg = (
        df_rec.groupby(["codigo_fundo", "codigo_subclasse"])
        .agg(
            RETORNO_ANUAL=("retorno_mensal", _annual_return),
            VOLATILIDADE=("retorno_mensal", _annual_vol),
            MESES_HISTORICO=("retorno_mensal", "count"),
        )
        .reset_index()
    )

    # Junta com mapa de subclasses para obter CNPJ e tipo de cota
    ret_agg = ret_agg.merge(df_classes, on="codigo_subclasse", how="left")
    matched = ret_agg["CNPJ_FUNDO"].notna().sum()
    print(f"  {len(ret_agg)} combinacoes | {matched} com CNPJ linkado ({matched / len(ret_agg) * 100:.0f}%)\n")

    # ============================================================
    # 6. CONTEXTO MACROECONÔMICO
    # ============================================================
    print("[6/7] Carregando contexto macroeconômico...")

    df_macro = pd.read_csv(os.path.join(BASE, "macroeconomicos", "consolidade.csv"), sep=";")
    df_macro["data_processamento"] = pd.to_datetime(df_macro["data_processamento"], errors="coerce")
    df_macro = df_macro.sort_values("data_processamento")

    inad_pj_serie = pd.to_numeric(df_macro["inadimplencia_pj"], errors="coerce").dropna()
    inad_pj_atual = inad_pj_serie.iloc[-1]
    # Usa mediana histórica fixa (constante versionada) em vez de mediana móvel —
    # ver `INAD_PJ_MEDIANA_HISTORICA` no topo do módulo para racional completo.
    fator_macro = inad_pj_atual / INAD_PJ_MEDIANA_HISTORICA if INAD_PJ_MEDIANA_HISTORICA > 0 else 1.0
    selic_atual = pd.to_numeric(df_macro["selic_meta"], errors="coerce").dropna().iloc[-1]

    print(
        f"  Inadimplência PJ atual: {inad_pj_atual:.2f}% | mediana histórica fixa: {INAD_PJ_MEDIANA_HISTORICA:.2f}% | fator macro: {fator_macro:.3f}"
    )
    print(f"  SELIC atual: {selic_atual:.1f}%\n")

    # ============================================================
    # 7. SCORE DE RISCO ML  (StandardScaler + PCA + tercis do SCORE_RISCO)
    # ============================================================
    print("[7/7] Calculando score de risco com ML (StandardScaler + PCA + tercis)...")

    df_risk = conc_df.merge(inad_df, on="CNPJ_FUNDO", how="outer")
    df_risk = df_risk.merge(scr_df, on="CNPJ_FUNDO", how="outer")

    df_risk["TAXA_INAD"].median()
    df_risk["CONC_MAIOR_CEDENTE"].median()

    # Sanity check da chave (descobre divergência entre fontes antes do filtro virar no-op).
    intersec_encerrados = len(set(df_risk["CNPJ_FUNDO"]) & cnpjs_encerrados)
    print(f"  Interseção encerrados∩base_mensal: {intersec_encerrados} / {len(cnpjs_encerrados)}")
    if cnpjs_encerrados and intersec_encerrados == 0:
        print("  AVISO: nenhum encerrado bate na base mensal — verificar formato do CNPJ entre fontes.")

    # Features normalizadas; inadimplência ajustada pelo ambiente macro atual.
    # Apenas fundos com dados reais, ativos e sem artefatos de liquidação entram no modelo.
    # Nota: NÃO preencher SCR_SCORE com sintético antes desta máscara (era bug — 0.5 mascarava
    # fundos sem dados como "neutros").
    mask_completo = (
        df_risk["TAXA_INAD"].notna()
        & (df_risk["TAXA_INAD"] <= 1.0)
        & df_risk["SCR_SCORE"].notna()
        & df_risk["CONC_MAIOR_CEDENTE"].notna()
        & ~df_risk["CNPJ_FUNDO"].isin(cnpjs_encerrados)
    )
    df_risk["SCORE_RISCO"] = np.nan
    df_risk["CATEGORIA_RISCO"] = "SEM DADOS"

    df_ml = df_risk[mask_completo].copy()
    df_ml["f_inad"] = df_ml["TAXA_INAD"] * fator_macro
    df_ml["f_aging"] = df_ml["AGING_SCORE"].fillna(0)
    df_ml["f_scr"] = df_ml["SCR_SCORE"]
    df_ml["f_conc"] = df_ml["CONC_MAIOR_CEDENTE"]

    FEAT_COLS = ["f_inad", "f_aging", "f_scr", "f_conc"]
    FEAT_NAMES = ["Inadimplencia", "Aging", "SCR Devedor", "Concentracao"]

    X = df_ml[FEAT_COLS].values
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # PCA: score contínuo pelo primeiro componente principal
    pca = PCA(n_components=4, random_state=42)
    X_pca = pca.fit_transform(X_scaled)

    if pca.components_[0, 0] < 0:
        X_pca[:, 0] *= -1

    score_raw = X_pca[:, 0]
    scores_norm = (score_raw - score_raw.min()) / (score_raw.max() - score_raw.min()) * 100
    df_ml["SCORE_RISCO"] = scores_norm

    # CATEGORIA via tercis do SCORE_RISCO (determinístico, monotônico, auditável).
    # Substituiu K-Means (Fase 3) para eliminar instabilidade entre runs causada
    # por re-clusterização sobre features rescaled pelo fator macro. Combinado com
    # `INAD_PJ_MEDIANA_HISTORICA` fixa, o rating é totalmente reproduzível.
    q33, q67 = df_ml["SCORE_RISCO"].quantile([0.33, 0.67])
    df_ml["CATEGORIA_RISCO"] = pd.cut(
        df_ml["SCORE_RISCO"],
        bins=[-np.inf, q33, q67, np.inf],
        labels=["BAIXO", "MEDIO", "ALTO"],
    )

    # Devolve os resultados para df_risk
    df_risk.loc[mask_completo, "SCORE_RISCO"] = df_ml["SCORE_RISCO"].values
    df_risk.loc[mask_completo, "CATEGORIA_RISCO"] = df_ml["CATEGORIA_RISCO"].values
    df_risk = df_risk.drop(columns=[c for c in df_risk.columns if c.startswith("f_")], errors="ignore")

    # Diagnóstico
    var_exp = pca.explained_variance_ratio_
    loadings = dict(zip(FEAT_NAMES, pca.components_[0], strict=False))
    print(f"  Fundos classificados (dados completos): {mask_completo.sum()} / {len(df_risk)}")
    print(
        f"  Variancia explicada -> PC1: {var_exp[0] * 100:.1f}%  PC2: {var_exp[1] * 100:.1f}%  PC3: {var_exp[2] * 100:.1f}%  PC4: {var_exp[3] * 100:.1f}%"
    )
    print("  Pesos aprendidos (loadings PC1):")
    for nome, peso in sorted(loadings.items(), key=lambda x: abs(x[1]), reverse=True):
        print(f"    {nome:<20}: {peso:+.4f}")
    print(f"  Cortes tercis SCORE_RISCO -> q33: {q33:.2f}  q67: {q67:.2f}")
    print(f"  Distribuicao por categoria: {df_risk['CATEGORIA_RISCO'].value_counts().to_dict()}")
    print()

    # Junta risco com retorno por classe
    df_final = ret_agg.merge(
        df_risk[
            [
                "CNPJ_FUNDO",
                "SCORE_RISCO",
                "CATEGORIA_RISCO",
                "TAXA_INAD",
                "SCR_SCORE",
                "CONC_MAIOR_CEDENTE",
                "CONC_TOP3_CEDENTES",
            ]
        ],
        on="CNPJ_FUNDO",
        how="left",
    )

    # Perfil de investidor: cruza tipo de cota x categoria de risco
    perfil_map = {
        # (TIPO_COTA, CATEGORIA_RISCO) -> PERFIL
        ("UNICA", "BAIXO"): "CONSERVADOR",
        ("UNICA", "MEDIO"): "MODERADO",
        ("UNICA", "ALTO"): "ARROJADO",
        ("SENIOR", "BAIXO"): "CONSERVADOR",
        ("SENIOR", "MEDIO"): "MODERADO",
        ("SENIOR", "ALTO"): "MODERADO",
        ("MEZANINO", "BAIXO"): "MODERADO",
        ("MEZANINO", "MEDIO"): "MODERADO",
        ("MEZANINO", "ALTO"): "ARROJADO",
        ("JUNIOR", "BAIXO"): "MODERADO",
        ("JUNIOR", "MEDIO"): "ARROJADO",
        ("JUNIOR", "ALTO"): "ARROJADO",
    }

    df_final["PERFIL_SUGERIDO"] = df_final.apply(
        lambda r: perfil_map.get((r["TIPO_COTA"], r["CATEGORIA_RISCO"]), "SEM DADOS"), axis=1
    )

    # Retorno ajustado ao risco (quanto retorno por ponto de risco).
    # Nota: RETORNO_ANUAL aqui ainda é DECIMAL (não foi multiplicado por 100).
    # Recalcularemos abaixo após a conversão para percentual, para manter coerência de escala.
    df_final["RETORNO_AJ_RISCO"] = df_final["RETORNO_ANUAL"] / ((df_final["SCORE_RISCO"] / 100.0) + 0.01)

    df_final = df_final.sort_values("RETORNO_AJ_RISCO", ascending=False)

    # ============================================================
    # OUTPUT — Excel com abas por perfil
    # ============================================================
    cols_out = {
        "CNPJ_FUNDO": "CNPJ",
        "NOME_FUNDO": "FUNDO",
        "TIPO_COTA": "TIPO_COTA",
        "FOCO_ATUACAO": "SEGMENTO",
        "CATEGORIA_RISCO": "RISCO",
        "SCORE_RISCO": "SCORE_RISCO",
        "PERFIL_SUGERIDO": "PERFIL_SUGERIDO",
        "RETORNO_ANUAL": "RETORNO_ANUAL",
        "VOLATILIDADE": "VOLATILIDADE",
        "RETORNO_AJ_RISCO": "RETORNO_AJ_RISCO",
        "TAXA_INAD": "TAXA_INADIMPLENCIA",
        "SCR_SCORE": "SCR_NORMALIZADO",
        "CONC_MAIOR_CEDENTE": "CONC_MAIOR_CEDENTE",
        "CONC_TOP3_CEDENTES": "CONC_TOP3",
        "MESES_HISTORICO": "MESES_HISTORICO",
    }

    df_out = df_final.rename(columns=cols_out)[
        [c for c in cols_out.values() if c in df_final.rename(columns=cols_out).columns]
    ]

    # Formatar percentuais
    for col in ["RETORNO_ANUAL", "VOLATILIDADE", "TAXA_INADIMPLENCIA", "CONC_MAIOR_CEDENTE", "CONC_TOP3"]:
        if col in df_out.columns:
            df_out[col] = (df_out[col] * 100).round(2)

    # Recalcula RETORNO_AJ_RISCO em escala percentual (RETORNO_ANUAL já está em %).
    # Antes, era calculado com decimal x score_risco/100 — escala misturada no payload.
    df_out["RETORNO_AJ_RISCO"] = (df_out["RETORNO_ANUAL"] / ((df_out["SCORE_RISCO"] / 100.0) + 0.01)).round(2)

    df_out["SCORE_RISCO"] = df_out["SCORE_RISCO"].round(1)
    df_out["SCR_NORMALIZADO"] = df_out["SCR_NORMALIZADO"].round(4)

    output_path = os.path.join(OUTPUT, "rating_fidc.xlsx")

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        # Aba geral
        df_out.to_excel(writer, sheet_name="GERAL", index=False)

        # Aba por perfil
        for perfil in ["CONSERVADOR", "MODERADO", "ARROJADO"]:
            sub = df_out[df_out["PERFIL_SUGERIDO"] == perfil]
            if not sub.empty:
                sub.to_excel(writer, sheet_name=perfil, index=False)

        # Aba resumo por fundo
        resumo = (
            df_out.groupby("CNPJ")
            .agg(
                FUNDO=("FUNDO", "first"),
                SCORE_RISCO=("SCORE_RISCO", "first"),
                RISCO=("RISCO", "first"),
                RETORNO_MEDIO=("RETORNO_ANUAL", "mean"),
                MELHOR_COTA=("TIPO_COTA", lambda x: x.iloc[0] if len(x) > 0 else ""),
                PERFIL_PREDOMINANTE=("PERFIL_SUGERIDO", lambda x: x.mode()[0] if len(x) > 0 else ""),
            )
            .reset_index()
            .sort_values("SCORE_RISCO")
        )
        resumo.to_excel(writer, sheet_name="RESUMO_POR_FUNDO", index=False)

    print(f"\nSalvo: {output_path}")
    print(f"  Total de combinações fundo/classe: {len(df_out)}")
    print("\n  Distribuição de risco:")
    print(df_out["RISCO"].value_counts().to_string())
    print("\n  Distribuição por perfil sugerido:")
    print(df_out["PERFIL_SUGERIDO"].value_counts().to_string())
    print("\n  Top 5 melhor relação retorno/risco:")
    print(df_out[["FUNDO", "TIPO_COTA", "RISCO", "RETORNO_ANUAL", "PERFIL_SUGERIDO"]].head().to_string(index=False))
    print(f"\nFim: {datetime.now().strftime('%H:%M:%S')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
