#!/usr/bin/env python3
"""Modelo de crédito — XGBoost / Random Forest para probabilidade de default por pagador.

Treina sobre `bases/base_boletos_fiap.csv` + `bases/base_auxiliar_fiap.csv`, faz
5-fold CV estratificado, escolhe o melhor por AUC e salva `credit_model.pkl` +
`scores_credito.csv` em `data_real/`.
"""
from __future__ import annotations

import os
import pathlib
import pickle
import sys
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.preprocessing import LabelEncoder

ROOT   = pathlib.Path(__file__).resolve().parent.parent
BASES  = os.environ.get("RADAR_BASES",  str(ROOT / "data_real" / "bases"))
OUTPUT = os.environ.get("RADAR_OUTPUT", str(ROOT / "data_real"))

# ─── Constantes do modelo ──────────────────────────────────────────────
CARENCIA_DIAS = 30
TIPOS_DEFAULT = {
    "6 - Baixa integral por envio para protesto",
    "7 - Baixa integral por decurso de prazo",
}
FEAT_AUX = [
    "sacado_indice_liquidez_1m",
    "score_materialidade_evolucao",
    "media_atraso_dias",
    "indicador_liquidez_quantitativo_3m",
    "share_vl_inad_pag_bol_6_a_15d",
    "score_quantidade_v2",
    "score_materialidade_v2",
    "uf_enc",
    "cnae_enc",
]
FEAT_BOL = ["total_boletos", "vlr_medio", "pct_atraso_1_30", "atraso_medio"]
FEATURES = FEAT_BOL + FEAT_AUX
TARGET   = "defaultou"

THRESHOLD_RISCO_BAIXO = 0.15
THRESHOLD_RISCO_MEDIO = 0.40

CV_FOLDS = 5
RANDOM_STATE = 42


# ─── Preparação ────────────────────────────────────────────────────────

def preparar_boletos(path: str) -> pd.DataFrame:
    """Lê boletos brutos e adiciona colunas derivadas (datas, atraso, flag_default)."""
    df = pd.read_csv(path)
    df["dt_emissao"]    = pd.to_datetime(df["dt_emissao"], errors="coerce")
    df["dt_vencimento"] = pd.to_datetime(df["dt_vencimento"], errors="coerce")
    df["dt_pagamento"]  = pd.to_datetime(df["dt_pagamento"], errors="coerce")
    df["atraso_dias"]   = (df["dt_pagamento"] - df["dt_vencimento"]).dt.days

    data_ref = df["dt_emissao"].max()
    if pd.isna(data_ref):
        data_ref = df["dt_vencimento"].max()
    limite_carencia = data_ref - pd.Timedelta(days=CARENCIA_DIAS)
    print(f"  Data ref: {data_ref.date() if pd.notna(data_ref) else 'N/A'} | "
          f"carência: {CARENCIA_DIAS}d")

    df["flag_default"] = (
        df["tipo_baixa"].isin(TIPOS_DEFAULT) |
        (df["dt_pagamento"].isna() & (df["dt_vencimento"] < limite_carencia)) |
        (df["atraso_dias"] > CARENCIA_DIAS)
    ).astype(int)
    return df


def agregar_pagador(df_bol: pd.DataFrame) -> pd.DataFrame:
    """Reduz boletos para 1 linha por pagador com features comportamentais."""
    agg = df_bol.groupby("id_pagador").agg(
        total_boletos   = ("id_boleto",    "count"),
        total_vlr       = ("vlr_nominal",  "sum"),
        vlr_medio       = ("vlr_nominal",  "mean"),
        n_default       = ("flag_default", "sum"),
        atraso_medio    = ("atraso_dias",  lambda x: x[x > 0].mean()),
        pct_atraso_1_30 = ("atraso_dias",  lambda x: ((x > 0) & (x <= 30)).mean()),
        pct_default     = ("flag_default", "mean"),
        defaultou       = ("flag_default", "max"),  # TARGET
    ).reset_index().rename(columns={"id_pagador": "id_cnpj"})
    agg["atraso_medio"] = agg["atraso_medio"].fillna(0)
    return agg


def carregar_auxiliar(path: str) -> tuple[pd.DataFrame, LabelEncoder, LabelEncoder]:
    """Lê base auxiliar e codifica UF/CNAE."""
    df = pd.read_csv(path)
    le_uf, le_cnae = LabelEncoder(), LabelEncoder()
    df["uf_enc"]   = le_uf.fit_transform(df["uf"].fillna("DESCONHECIDO"))
    df["cnae_enc"] = le_cnae.fit_transform(df["cd_cnae_prin"].fillna(0).astype(str))
    return df, le_uf, le_cnae


def montar_dataset(agg_pagador: pd.DataFrame, df_aux: pd.DataFrame) -> pd.DataFrame:
    return agg_pagador.merge(df_aux[["id_cnpj"] + FEAT_AUX], on="id_cnpj", how="left")


# ─── Treino ────────────────────────────────────────────────────────────

@dataclass
class CrossValResult:
    auc_mean: float
    auc_std: float
    acc_mean: float
    f1_mean: float


def _modelos(n_tot: int, n_def: int) -> dict:
    return {
        "Random Forest": RandomForestClassifier(
            n_estimators=300, max_depth=6, class_weight="balanced",
            random_state=RANDOM_STATE, n_jobs=-1,
        ),
        "XGBoost": xgb.XGBClassifier(
            n_estimators=300, max_depth=4, learning_rate=0.05,
            scale_pos_weight=(n_tot - n_def) / max(n_def, 1),
            eval_metric="logloss", random_state=RANDOM_STATE, verbosity=0,
        ),
    }


def avaliar_modelos(X: np.ndarray, y: np.ndarray, n_tot: int, n_def: int) -> tuple[str, dict[str, CrossValResult]]:
    """Roda CV em cada modelo, retorna nome do melhor e os scores."""
    cv = StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_STATE)
    resultados: dict[str, CrossValResult] = {}
    modelos = _modelos(n_tot, n_def)

    for nome, modelo in modelos.items():
        auc = cross_val_score(modelo, X, y, cv=cv, scoring="roc_auc")
        acc = cross_val_score(modelo, X, y, cv=cv, scoring="accuracy")
        f1  = cross_val_score(modelo, X, y, cv=cv, scoring="f1")
        resultados[nome] = CrossValResult(auc.mean(), auc.std(), acc.mean(), f1.mean())
        print(f"  {nome}: AUC {auc.mean():.4f}±{auc.std():.4f}  "
              f"Acc {acc.mean()*100:.1f}%  F1 {f1.mean():.4f}")

    melhor = max(resultados, key=lambda k: resultados[k].auc_mean)
    print(f"\n  Melhor: {melhor} (AUC {resultados[melhor].auc_mean:.4f})\n")
    return melhor, resultados


def categorizar_risco(prob: float) -> str:
    if prob <= THRESHOLD_RISCO_BAIXO:
        return "BAIXO"
    if prob <= THRESHOLD_RISCO_MEDIO:
        return "MEDIO"
    return "ALTO"


# ─── IO de saída ───────────────────────────────────────────────────────

def salvar_modelo(model, imputer: SimpleImputer, le_uf: LabelEncoder, le_cnae: LabelEncoder, path: str) -> None:
    pipeline = {
        "modelo": model, "imputer": imputer, "features": FEATURES,
        "le_uf": le_uf, "le_cnae": le_cnae,
    }
    with open(path, "wb") as f:
        pickle.dump(pipeline, f)
    print(f"  Modelo salvo: {path}")


def salvar_scores(df: pd.DataFrame, path: str) -> None:
    cols = ["id_cnpj", "prob_default", "score_credito", "risco_credito",
            "total_boletos", "n_default", "pct_default", "defaultou"]
    df[cols].to_csv(path, index=False)
    print(f"  Scores salvos: {path}")


# ─── Main ──────────────────────────────────────────────────────────────

def main() -> int:
    print("=" * 60)
    print("  MODELO DE CRÉDITO — SCORING DE INADIMPLÊNCIA")
    print("=" * 60)
    print(f"  Início: {datetime.now().strftime('%H:%M:%S')}\n")

    print("[1/5] Preparando labels de default...")
    df_bol = preparar_boletos(os.path.join(BASES, "base_boletos_fiap.csv"))
    agg = agregar_pagador(df_bol)
    n_def, n_tot = agg["defaultou"].sum(), len(agg)
    print(f"  Pagadores: {n_tot:,} | inadimplentes: {n_def:,} ({n_def/n_tot*100:.1f}%)\n")

    print("[2/5] Carregando auxiliar e codificando UF/CNAE...")
    df_aux, le_uf, le_cnae = carregar_auxiliar(os.path.join(BASES, "base_auxiliar_fiap.csv"))

    print("[3/5] Montando dataset final...")
    df = montar_dataset(agg, df_aux)
    X = df[FEATURES].copy()
    y = df[TARGET].values
    print(f"  {len(X):,} linhas × {len(FEATURES)} features\n")

    print("[4/5] Avaliando modelos com 5-fold CV...")
    imputer = SimpleImputer(strategy="median")
    X_imp = imputer.fit_transform(X)
    melhor_nome, resultados = avaliar_modelos(X_imp, y, n_tot, n_def)
    melhor_modelo = _modelos(n_tot, n_def)[melhor_nome]

    print("[5/5] Treinando modelo final + scoring...")
    melhor_modelo.fit(X_imp, y)

    if hasattr(melhor_modelo, "feature_importances_"):
        imp = pd.Series(melhor_modelo.feature_importances_, index=FEATURES).sort_values(ascending=False)
        print("  Importância das features:")
        for feat, val in imp.items():
            print(f"    {feat:<40}: {val:.4f}")
        print()

    df["prob_default"]  = melhor_modelo.predict_proba(X_imp)[:, 1]
    df["score_credito"] = (1.0 - df["prob_default"]) * 100.0
    df["risco_credito"] = df["prob_default"].apply(categorizar_risco)

    print("  Distribuição de risco:")
    print(df["risco_credito"].value_counts().to_string())
    print()

    salvar_modelo(melhor_modelo, imputer, le_uf, le_cnae, os.path.join(OUTPUT, "credit_model.pkl"))
    salvar_scores(df, os.path.join(OUTPUT, "scores_credito.csv"))

    print("\n" + "=" * 60)
    print("  RESUMO FINAL")
    print("=" * 60)
    for nome, r in resultados.items():
        print(f"  {nome:<20}: AUC {r.auc_mean:.4f} | Acc {r.acc_mean*100:.1f}% | F1 {r.f1_mean:.4f}")
    print(f"\n  Fim: {datetime.now().strftime('%H:%M:%S')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
