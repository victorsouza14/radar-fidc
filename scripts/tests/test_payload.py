"""Testes dos builders de payload — ``scripts/lib/payload.py``.

Cobertura dos builders centrais usados por ``generate_dashboard_data.py``:

- ``build_macro``: preferências (selic_efetiva > selic_meta, ipca_12m_acumulado >
  composição mensal), Focus vs heurística, guard de CDI patológico, cenário.
- ``build_fidcs``: filtro ``MIN_MESES_HISTORICO``, distribuições estatísticas, dedup.
- ``build_clientes``: PII mascarado, total consistente, distribuição.
- ``build_matches``: top-N e estrutura vazia.
- ``build_credit``: top-N por score, gating por ``dados_suficientes``, médias.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from lib.payload import (
    MAX_CREDIT,
    MAX_FIDC_DETALHE,
    MIN_BOLETOS_SCORE_CONFIAVEL,
    MIN_MESES_HISTORICO,
    build_clientes,
    build_credit,
    build_fidcs,
    build_macro,
    build_matches,
)


# ─── BUILD_MACRO ─────────────────────────────────────────────────────────
def _macro_row(**overrides: Any) -> dict[str, Any]:
    """Linha padrão (todos campos preenchidos), com overrides pontuais."""
    base: dict[str, Any] = {
        "data_processamento": pd.Timestamp("2026-05-14"),
        "selic_meta": 13.75,
        "selic_efetiva": 13.65,
        "cdi_diario": 0.05,
        "ipca_mensal": 0.4,
        "ipca_12m_acumulado": 4.39,
    }
    base.update(overrides)
    return base


class TestBuildMacroEmpty:
    """DataFrame vazio devolve estrutura de payload com campos None."""

    def test_empty_df_retorna_todos_campos_none(self) -> None:
        payload = build_macro(pd.DataFrame())
        assert payload["selic"] is None
        assert payload["cdi"] is None
        assert payload["ipca"] is None
        assert payload["selic_proj"] is None
        assert payload["ipca_proj"] is None

    def test_empty_df_cenario_eh_indisponivel(self) -> None:
        payload = build_macro(pd.DataFrame())
        assert payload["cenario"] == "indisponivel"

    def test_empty_df_data_ref_eh_fallback_hoje(self) -> None:
        """Sem registros, ``data_ref`` ainda é uma string YYYY-MM-DD válida."""
        payload = build_macro(pd.DataFrame())
        assert isinstance(payload["data_ref"], str)
        assert len(payload["data_ref"]) == 10
        assert payload["data_ref"][4] == "-"
        assert payload["data_ref"][7] == "-"


class TestBuildMacroSelicPrecedence:
    """Preferência SGS 1178 (selic_efetiva) sobre SGS 432 (selic_meta)."""

    def test_efetiva_presente_eh_usada(self) -> None:
        df = pd.DataFrame([_macro_row(selic_meta=13.75, selic_efetiva=13.65)])
        payload = build_macro(df)
        assert payload["selic"] == 13.65

    def test_efetiva_ausente_fallback_para_meta(self) -> None:
        df = pd.DataFrame([_macro_row(selic_efetiva=None)])
        payload = build_macro(df)
        assert payload["selic"] == 13.75

    def test_ambas_ausentes_selic_eh_none(self) -> None:
        df = pd.DataFrame([_macro_row(selic_meta=None, selic_efetiva=None)])
        payload = build_macro(df)
        assert payload["selic"] is None
        assert payload["cenario"] == "indisponivel"


class TestBuildMacroCDI:
    """Anualização do CDI (base 252) e guard de valor patológico."""

    def test_cdi_diario_005_anualiza_em_ate_2_decimais(self) -> None:
        """0.05% a.d. ≈ 13.42% a.a. (base 252)."""
        df = pd.DataFrame([_macro_row(cdi_diario=0.05)])
        payload = build_macro(df)
        assert payload["cdi"] == 13.42

    def test_cdi_diario_zero_resulta_em_zero(self) -> None:
        df = pd.DataFrame([_macro_row(cdi_diario=0.0)])
        payload = build_macro(df)
        assert payload["cdi"] == 0.0

    def test_cdi_patologico_menos_100_protegido_por_guard(self) -> None:
        df = pd.DataFrame([_macro_row(cdi_diario=-100.0)])
        payload = build_macro(df)
        assert payload["cdi"] is None

    def test_cdi_ausente_eh_none(self) -> None:
        df = pd.DataFrame([_macro_row(cdi_diario=None)])
        payload = build_macro(df)
        assert payload["cdi"] is None


class TestBuildMacroIPCA:
    """Preferência SGS 13522 (oficial) sobre composição interna mensal."""

    def test_ipca_12m_oficial_eh_usado(self) -> None:
        df = pd.DataFrame([_macro_row(ipca_12m_acumulado=4.39)])
        payload = build_macro(df)
        assert payload["ipca"] == 4.39

    def test_sem_12m_oficial_compoe_da_serie_mensal(self) -> None:
        rows = [_macro_row(ipca_12m_acumulado=None, ipca_mensal=0.4) for _ in range(12)]
        df = pd.DataFrame(rows)
        payload = build_macro(df)
        assert payload["ipca"] is not None
        assert 4.5 < payload["ipca"] < 5.5

    def test_sem_12m_oficial_e_sem_serie_mensal_ipca_eh_none(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "data_processamento": pd.Timestamp("2026-05-14"),
                    "selic_efetiva": 13.5,
                    "selic_meta": 13.75,
                    "cdi_diario": 0.05,
                    "ipca_12m_acumulado": None,
                }
            ]
        )
        payload = build_macro(df)
        assert payload["ipca"] is None


class TestBuildMacroFocusVsHeuristica:
    """Projeções: Focus oficial > heurística simples."""

    def test_focus_disponivel_usa_focus(self) -> None:
        df = pd.DataFrame([_macro_row()])
        focus = {
            "selic_projetada_12m": 12.5,
            "ipca_projetado_12m": 3.5,
            "is_proj_heuristica": False,
        }
        payload = build_macro(df, focus_indicators=focus)
        assert payload["selic_proj"] == 12.5
        assert payload["ipca_proj"] == 3.5

    def test_focus_none_usa_heuristica(self) -> None:
        df = pd.DataFrame([_macro_row(selic_efetiva=13.65, ipca_12m_acumulado=4.39)])
        payload = build_macro(df, focus_indicators=None)
        # Heurística documentada: selic_proj = selic - 0.5
        assert payload["selic_proj"] == 13.15
        # ipca_proj = ipca * 0.9 quando positivo
        assert payload["ipca_proj"] == round(4.39 * 0.9, 2)

    def test_focus_com_is_heuristica_true_ainda_cai_no_fallback(self) -> None:
        """Focus marcado como heurística (stale) NÃO deve substituir o cálculo."""
        df = pd.DataFrame([_macro_row(selic_efetiva=10.0, ipca_12m_acumulado=2.0)])
        focus = {"is_proj_heuristica": True, "selic_projetada_12m": 99.0, "ipca_projetado_12m": 99.0}
        payload = build_macro(df, focus_indicators=focus)
        assert payload["selic_proj"] != 99.0


class TestBuildMacroCenario:
    """Cenário derivado da SELIC."""

    def test_selic_alta_marca_cenario_posfixado(self) -> None:
        df = pd.DataFrame([_macro_row(selic_efetiva=14.0)])
        payload = build_macro(df)
        assert payload["cenario"] == "favoravel_posfixado"


# ─── BUILD_FIDCS ─────────────────────────────────────────────────────────
def _geral_row(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "CNPJ": "12345678000190",
        "FUNDO": "FIDC ABC",
        "TIPO_COTA": "UNICA",
        "SEGMENTO": None,
        "RISCO": "BAIXO",
        "SCORE_RISCO": 42.5,
        "PERFIL_SUGERIDO": "CONSERVADOR",
        "RETORNO_ANUAL": 12.3,
        "VOLATILIDADE": 3.0,
        "RETORNO_AJ_RISCO": 4.1,
        "TAXA_INADIMPLENCIA": 1.2,
        "SCR_NORMALIZADO": 0.5,
        "CONC_MAIOR_CEDENTE": 0.0,
        "CONC_TOP3": 0.0,
        "MESES_HISTORICO": 12,
    }
    base.update(overrides)
    return base


class TestBuildFidcsEmpty:
    def test_empty_geral_retorna_estrutura_vazia(self) -> None:
        out = build_fidcs(pd.DataFrame())
        assert out["stats"]["total_classes"] == 0
        assert out["stats"]["total_fundos"] == 0
        assert out["detalhe"] == []


class TestBuildFidcsMinHistorico:
    """Filtro ``MIN_MESES_HISTORICO`` — fundos curtos saem das listagens."""

    def test_fundo_com_historico_curto_nao_aparece_em_detalhe(self) -> None:
        geral = pd.DataFrame(
            [
                _geral_row(CNPJ="11111111000111", FUNDO="FIDC LONGO", MESES_HISTORICO=24),
                _geral_row(CNPJ="22222222000222", FUNDO="FIDC CURTO", MESES_HISTORICO=3),
            ]
        )
        out = build_fidcs(geral)
        nomes = [d["fundo"] for d in out["detalhe"]]
        assert "FIDC LONGO" in nomes
        assert "FIDC CURTO" not in nomes

    def test_meses_historico_no_limite_aparece(self) -> None:
        geral = pd.DataFrame([_geral_row(MESES_HISTORICO=MIN_MESES_HISTORICO)])
        out = build_fidcs(geral)
        assert len(out["detalhe"]) == 1

    def test_fundo_curto_ainda_conta_em_stats(self) -> None:
        geral = pd.DataFrame(
            [
                _geral_row(CNPJ="11111111000111", FUNDO="A", MESES_HISTORICO=24),
                _geral_row(CNPJ="22222222000222", FUNDO="B", MESES_HISTORICO=3),
            ]
        )
        out = build_fidcs(geral)
        assert out["stats"]["total_classes"] == 2
        assert out["stats"]["total_fundos"] == 2


class TestBuildFidcsDistribuicoes:
    def test_distribuicao_por_risco_agregada(self) -> None:
        geral = pd.DataFrame(
            [
                _geral_row(CNPJ="A0000000000001", FUNDO="A", RISCO="BAIXO"),
                _geral_row(CNPJ="B0000000000002", FUNDO="B", RISCO="ALTO"),
                _geral_row(CNPJ="C0000000000003", FUNDO="C", RISCO="ALTO"),
            ]
        )
        out = build_fidcs(geral)
        dist = out["stats"]["distribuicao"]["por_risco"]
        assert dist["ALTO"] == 2
        assert dist["BAIXO"] == 1

    def test_distribuicao_por_perfil_agregada(self) -> None:
        geral = pd.DataFrame(
            [
                _geral_row(CNPJ="A0000000000001", FUNDO="A", PERFIL_SUGERIDO="CONSERVADOR"),
                _geral_row(CNPJ="B0000000000002", FUNDO="B", PERFIL_SUGERIDO="ARROJADO"),
            ]
        )
        out = build_fidcs(geral)
        dist = out["stats"]["distribuicao"]["por_perfil"]
        assert dist["CONSERVADOR"] == 1
        assert dist["ARROJADO"] == 1


class TestBuildFidcsDetalheCap:
    def test_detalhe_limitado_por_max_detalhe(self) -> None:
        geral = pd.DataFrame(
            [_geral_row(CNPJ=f"{i:014d}", FUNDO=f"F{i}", SCORE_RISCO=float(i), MESES_HISTORICO=24) for i in range(20)]
        )
        out = build_fidcs(geral)
        assert len(out["detalhe"]) <= MAX_FIDC_DETALHE
        assert len(out["detalhe"]) == 20


# ─── BUILD_CLIENTES ──────────────────────────────────────────────────────
def _cliente_row(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "cpf": "12345678901",
        "nome": "Ana Lima",
        "email": "ana@exemplo.com",
        "idade": 30,
        "perfil": "MODERADO",
        "score_perfil": 65.0,
    }
    base.update(overrides)
    return base


class TestBuildClientes:
    def test_empty_df_retorna_estrutura_vazia(self) -> None:
        out = build_clientes(pd.DataFrame())
        assert out["total"] == 0
        assert out["distribuicao_perfil"] == {}
        assert out["lista"] == []

    def test_total_consistente_com_len_df(self) -> None:
        df = pd.DataFrame([_cliente_row(cpf=f"1234567890{i}") for i in range(7)])
        out = build_clientes(df)
        assert out["total"] == 7
        assert len(out["lista"]) == 7

    def test_pii_mascarada_smoke(self) -> None:
        """Smoke: cpf/nome/email NÃO saem do builder em claro."""
        df = pd.DataFrame([_cliente_row()])
        out = build_clientes(df)
        cliente = out["lista"][0]
        assert "12345678901" not in cliente["cpf"]
        assert cliente["cpf"].startswith("***")
        assert cliente["nome"] != "Ana Lima"
        assert "Ana" in cliente["nome"]
        assert "ana@exemplo.com" not in cliente["email"]
        assert "@" in cliente["email"]

    def test_distribuicao_perfil(self) -> None:
        df = pd.DataFrame(
            [
                _cliente_row(cpf="12345678901", perfil="MODERADO"),
                _cliente_row(cpf="12345678902", perfil="MODERADO"),
                _cliente_row(cpf="12345678903", perfil="ARROJADO"),
            ]
        )
        out = build_clientes(df)
        assert out["distribuicao_perfil"]["MODERADO"] == 2
        assert out["distribuicao_perfil"]["ARROJADO"] == 1


# ─── BUILD_MATCHES ───────────────────────────────────────────────────────
def _match_row_dict(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "CPF": "12345678901",
        "CLIENTE": "Ana Lima",
        "PERFIL_CLIENTE": "MODERADO",
        "FUNDO": "FIDC ABC",
        "TIPO_COTA": "UNICA",
        "RISCO_FUNDO": "BAIXO",
        "RETORNO_ANUAL": 12.3,
        "VOLATILIDADE": 3.0,
        "TAXA_INAD": 1.2,
        "MESES_HISTORICO": 12,
        "MATCH_SCORE": 85.0,
        "MOTIVO": "Bom alinhamento",
        "RANK": 1,
    }
    base.update(overrides)
    return base


def _ranking_row_dict(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "FUNDO": "FIDC ABC",
        "TIPO_COTA": "UNICA",
        "RISCO_FUNDO": "BAIXO",
        "RETORNO_ANUAL": 12.3,
        "VEZES_RECOMENDADO": 42,
        "MATCH_MEDIO": 78.0,
    }
    base.update(overrides)
    return base


class TestBuildMatches:
    def test_empty_inputs_retorna_estrutura_valida(self) -> None:
        out = build_matches(pd.DataFrame(), pd.DataFrame())
        assert out["total"] == 0
        assert out["lista"] == []
        assert out["ranking_fundos"] == []

    def test_total_eh_len_todos(self) -> None:
        todos = pd.DataFrame([_match_row_dict(CPF=f"1234567890{i}") for i in range(5)])
        out = build_matches(todos, pd.DataFrame())
        assert out["total"] == 5
        assert len(out["lista"]) == 5

    def test_ranking_preservado(self) -> None:
        ranking = pd.DataFrame(
            [
                _ranking_row_dict(FUNDO="FIDC A", VEZES_RECOMENDADO=100),
                _ranking_row_dict(FUNDO="FIDC B", VEZES_RECOMENDADO=50),
            ]
        )
        out = build_matches(pd.DataFrame(), ranking)
        assert len(out["ranking_fundos"]) == 2
        nomes = [r["fundo"] for r in out["ranking_fundos"]]
        assert "FIDC A" in nomes
        assert "FIDC B" in nomes

    def test_match_pii_mascarada(self) -> None:
        todos = pd.DataFrame([_match_row_dict()])
        out = build_matches(todos, pd.DataFrame())
        m = out["lista"][0]
        assert "12345678901" not in m["cpf"]
        assert m["cliente"] != "Ana Lima"


# ─── BUILD_CREDIT ────────────────────────────────────────────────────────
def _credit_row(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id_cnpj": "abcdef123456",
        "score_credito": 75.0,
        "prob_default": 0.12,
        "risco_credito": "BAIXO",
        "total_boletos": 25,  # >= MIN_BOLETOS_SCORE_CONFIAVEL
        "n_default": 0,
        "pct_default": 0.0,
        "defaultou": 0,
    }
    base.update(overrides)
    return base


class TestBuildCredit:
    def test_empty_retorna_estrutura_vazia(self) -> None:
        out = build_credit(pd.DataFrame())
        assert out["empresas"] == []
        assert out["stats"]["total"] == 0
        assert out["stats"]["por_risco"] == {}
        assert out["stats"]["media_score"] == 0.0

    def test_stats_total_consistente(self) -> None:
        df = pd.DataFrame([_credit_row(id_cnpj=f"emp{i:05d}", score_credito=float(i)) for i in range(50)])
        out = build_credit(df)
        assert out["stats"]["total"] == 50

    def test_stats_por_risco_agregado(self) -> None:
        df = pd.DataFrame(
            [
                _credit_row(id_cnpj="emp1", risco_credito="BAIXO"),
                _credit_row(id_cnpj="emp2", risco_credito="ALTO"),
                _credit_row(id_cnpj="emp3", risco_credito="ALTO"),
            ]
        )
        out = build_credit(df)
        assert out["stats"]["por_risco"]["ALTO"] == 2
        assert out["stats"]["por_risco"]["BAIXO"] == 1

    def test_empresas_sem_duplicatas(self) -> None:
        df = pd.DataFrame([_credit_row(id_cnpj=f"emp{i:05d}", score_credito=float(i)) for i in range(20)])
        out = build_credit(df)
        nomes = [e["nome"] for e in out["empresas"]]
        assert len(nomes) == len(set(nomes))

    def test_empresas_limitadas_por_max_credit(self) -> None:
        df = pd.DataFrame([_credit_row(id_cnpj=f"emp{i:05d}", score_credito=float(i)) for i in range(MAX_CREDIT * 2)])
        out = build_credit(df)
        assert len(out["empresas"]) <= MAX_CREDIT

    def test_top_n_ordenado_por_score(self) -> None:
        df = pd.DataFrame(
            [
                _credit_row(id_cnpj="emp_low", score_credito=10.0, total_boletos=25),
                _credit_row(id_cnpj="emp_high", score_credito=90.0, total_boletos=25),
                _credit_row(id_cnpj="emp_mid", score_credito=50.0, total_boletos=25),
            ]
        )
        out = build_credit(df)
        scores = [e["score"] for e in out["empresas"]]
        assert scores == sorted(scores, reverse=True)

    def test_media_prob_default_calculada_quando_coluna_existe(self) -> None:
        df = pd.DataFrame(
            [
                _credit_row(id_cnpj="emp1", prob_default=0.10, total_boletos=25),
                _credit_row(id_cnpj="emp2", prob_default=0.30, total_boletos=25),
            ]
        )
        out = build_credit(df)
        assert out["stats"]["media_prob_default"] == 0.2

    def test_score_e_prob_anulados_quando_dados_insuficientes(self) -> None:
        """``total_boletos`` abaixo do limiar zera score/prob/pct para evitar
        leitura ruidosa no front (que mostra "Dados insuficientes" no lugar)."""
        df = pd.DataFrame([_credit_row(id_cnpj="emp_noisy", total_boletos=5)])
        out = build_credit(df)
        empresa = out["empresas"][0]
        assert empresa["dados_suficientes"] is False
        assert empresa["score"] is None
        assert empresa["prob_default"] is None
        assert empresa["pct_default"] is None

    def test_empresa_acima_do_limiar_mantem_score(self) -> None:
        df = pd.DataFrame(
            [_credit_row(id_cnpj="emp_ok", score_credito=72.5, total_boletos=MIN_BOLETOS_SCORE_CONFIAVEL)]
        )
        out = build_credit(df)
        empresa = out["empresas"][0]
        assert empresa["dados_suficientes"] is True
        assert empresa["score"] == 72.5
