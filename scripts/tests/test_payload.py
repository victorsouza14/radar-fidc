"""Testes dos builders de payload — ``scripts/lib/payload.py``.

Cobertura dos builders centrais usados por ``generate_dashboard_data.py``:

- ``build_macro``: preferências (selic_efetiva > selic_meta, ipca_12m_acumulado >
  composição mensal), Focus vs heurística, guard de CDI patológico, cenário.
- ``build_fidcs``: filtro ``MIN_MESES_HISTORICO``, sampling ``MAX_SCATTER``,
  distribuições estatísticas, dedup.
- ``build_clientes``: PII mascarado, total consistente, distribuição.
- ``build_matches``: top-N e estrutura vazia.
- ``build_credit``: concat head+tail+sample sem duplicatas, empty handling.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from lib.payload import (
    MAX_CREDIT,
    MAX_FIDC_DETALHE,
    MAX_SCATTER,
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
        "dolar_venda": 5.10,
        "ipca_mensal": 0.4,
        "ipca_12m_acumulado": 4.39,
        "inadimplencia_pj": 3.5,
        "inadimplencia_pf": 5.4,
        "ibc_br": 142.7,
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
        assert "Sem dados" in payload["descricao"]

    def test_empty_df_data_ref_eh_fallback_hoje(self) -> None:
        """Sem registros, ``data_ref`` ainda é uma string YYYY-MM-DD válida."""
        payload = build_macro(pd.DataFrame())
        # Formato yyyy-mm-dd (10 chars)
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
        # Sem selic, cenário fica indisponível.
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
        """``cdi_diario <= -100%`` produziria NaN ou negativo absurdo.

        Guard documentado na fonte: payload precisa devolver None (não Infinity).
        """
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
        """Sem coluna oficial, payload deve compor pela série de 12 ipca_mensal."""
        rows = []
        for _ in range(12):
            rows.append(_macro_row(ipca_12m_acumulado=None, ipca_mensal=0.4))
        df = pd.DataFrame(rows)
        payload = build_macro(df)
        # 12 meses de 0.4% compostos ≈ 4.91%
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
                    # ipca_mensal column ausente totalmente
                    "inadimplencia_pj": None,
                    "inadimplencia_pf": None,
                    "ibc_br": None,
                    "dolar_venda": None,
                }
            ]
        )
        payload = build_macro(df)
        assert payload["ipca"] is None


class TestBuildMacroFocusVsHeuristica:
    """Projeções: Focus oficial > heurística simples."""

    def test_focus_disponivel_usa_focus_e_marca_nao_heuristica(self) -> None:
        df = pd.DataFrame([_macro_row()])
        focus = {
            "selic_projetada_12m": 12.5,
            "ipca_projetado_12m": 3.5,
            "is_proj_heuristica": False,
            "proj_source": "bcb_focus_top5",
            "proj_date": "2026-05-01",
            "selic_proj_2026": 12.0,
            "selic_proj_2027": 10.0,
            "ipca_proj_2026": 3.5,
            "ipca_proj_2027": 3.2,
        }
        payload = build_macro(df, focus_indicators=focus)
        assert payload["selic_proj"] == 12.5
        assert payload["ipca_proj"] == 3.5
        assert payload["is_proj_heuristica"] is False
        assert payload["proj_source"] == "bcb_focus_top5"
        assert payload["proj_date"] == "2026-05-01"
        assert payload["selic_proj_2026"] == 12.0

    def test_focus_none_usa_heuristica(self) -> None:
        """Sem Focus → fallback heurístico simples e ``is_proj_heuristica=True``."""
        df = pd.DataFrame([_macro_row(selic_efetiva=13.65, ipca_12m_acumulado=4.39)])
        payload = build_macro(df, focus_indicators=None)
        assert payload["is_proj_heuristica"] is True
        # Heurística documentada: selic_proj = selic - 0.5
        assert payload["selic_proj"] == 13.15
        # ipca_proj = ipca * 0.9 quando positivo
        assert payload["ipca_proj"] == round(4.39 * 0.9, 2)
        # Quando não vem Focus, proj_source e proj_date ficam None.
        assert payload["proj_source"] is None
        assert payload["proj_date"] is None

    def test_focus_com_is_heuristica_true_ainda_cai_no_fallback(self) -> None:
        """Focus marcado como heurística (stale) NÃO deve substituir o cálculo."""
        df = pd.DataFrame([_macro_row(selic_efetiva=10.0, ipca_12m_acumulado=2.0)])
        focus = {"is_proj_heuristica": True, "selic_projetada_12m": 99.0, "ipca_projetado_12m": 99.0}
        payload = build_macro(df, focus_indicators=focus)
        assert payload["is_proj_heuristica"] is True
        # NÃO usou os 99.0 do focus stale.
        assert payload["selic_proj"] != 99.0


class TestBuildMacroCenario:
    """Cenário derivado da SELIC + descrição."""

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


def _resumo_row(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "CNPJ": "12345678000190",
        "FUNDO": "FIDC ABC",
        "SCORE_RISCO": 42.5,
        "RISCO": "BAIXO",
        "RETORNO_MEDIO": 12.3,
        "MELHOR_COTA": "UNICA",
        "PERFIL_PREDOMINANTE": "CONSERVADOR",
    }
    base.update(overrides)
    return base


class TestBuildFidcsEmpty:
    def test_empty_geral_retorna_estrutura_vazia(self) -> None:
        out = build_fidcs(pd.DataFrame(), pd.DataFrame())
        assert out["stats"]["total_classes"] == 0
        assert out["stats"]["total_fundos"] == 0
        assert out["resumo"] == []
        assert out["detalhe"] == []
        assert out["scatter"] == []


class TestBuildFidcsMinHistorico:
    """Filtro ``MIN_MESES_HISTORICO`` — fundos curtos saem das listagens."""

    def test_fundo_com_historico_curto_nao_aparece_em_detalhe(self) -> None:
        geral = pd.DataFrame(
            [
                _geral_row(CNPJ="11111111000111", FUNDO="FIDC LONGO", MESES_HISTORICO=24),
                _geral_row(CNPJ="22222222000222", FUNDO="FIDC CURTO", MESES_HISTORICO=3),
            ]
        )
        out = build_fidcs(geral, pd.DataFrame())
        nomes = [d["fundo"] for d in out["detalhe"]]
        assert "FIDC LONGO" in nomes
        assert "FIDC CURTO" not in nomes

    def test_meses_historico_no_limite_aparece(self) -> None:
        """``MESES_HISTORICO == MIN_MESES_HISTORICO`` é inclusivo."""
        geral = pd.DataFrame([_geral_row(MESES_HISTORICO=MIN_MESES_HISTORICO)])
        out = build_fidcs(geral, pd.DataFrame())
        assert len(out["detalhe"]) == 1

    def test_fundo_curto_ainda_conta_em_stats(self) -> None:
        """Stats globais incluem fundos curtos — só listagens ordenadas filtram."""
        geral = pd.DataFrame(
            [
                _geral_row(CNPJ="11111111000111", FUNDO="A", MESES_HISTORICO=24),
                _geral_row(CNPJ="22222222000222", FUNDO="B", MESES_HISTORICO=3),
            ]
        )
        out = build_fidcs(geral, pd.DataFrame())
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
        out = build_fidcs(geral, pd.DataFrame())
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
        out = build_fidcs(geral, pd.DataFrame())
        dist = out["stats"]["distribuicao"]["por_perfil"]
        assert dist["CONSERVADOR"] == 1
        assert dist["ARROJADO"] == 1


class TestBuildFidcsScatter:
    def test_scatter_respeita_max(self) -> None:
        """População > MAX_SCATTER → sampling determinístico (seed=42)."""
        rows = [
            _geral_row(
                CNPJ=f"{i:014d}",
                FUNDO=f"FIDC {i}",
                RETORNO_ANUAL=10.0 + i * 0.01,
                SCORE_RISCO=50.0,
                MESES_HISTORICO=24,
            )
            for i in range(MAX_SCATTER + 50)
        ]
        out = build_fidcs(pd.DataFrame(rows), pd.DataFrame())
        assert len(out["scatter"]) <= MAX_SCATTER

    def test_scatter_descarta_retorno_outlier_acima_de_200(self) -> None:
        geral = pd.DataFrame(
            [
                _geral_row(CNPJ="11111111000111", FUNDO="A", RETORNO_ANUAL=15.0),
                _geral_row(CNPJ="22222222000222", FUNDO="B", RETORNO_ANUAL=500.0),  # outlier
            ]
        )
        out = build_fidcs(geral, pd.DataFrame())
        retornos = [s["retorno"] for s in out["scatter"]]
        assert 15.0 in retornos
        assert 500.0 not in retornos


class TestBuildFidcsResumo:
    def test_resumo_filtrado_pelos_cnpjs_confiaveis(self) -> None:
        geral = pd.DataFrame(
            [
                _geral_row(CNPJ="11111111000111", FUNDO="LONGO", MESES_HISTORICO=24),
                _geral_row(CNPJ="22222222000222", FUNDO="CURTO", MESES_HISTORICO=3),
            ]
        )
        resumo = pd.DataFrame(
            [
                _resumo_row(CNPJ="11111111000111", FUNDO="LONGO"),
                _resumo_row(CNPJ="22222222000222", FUNDO="CURTO"),
            ]
        )
        out = build_fidcs(geral, resumo)
        cnpjs_resumo = [r["cnpj"] for r in out["resumo"]]
        # CNPJ formatado: 11.111.111/0001-11
        assert any("11.111.111" in c for c in cnpjs_resumo)
        assert not any("22.222.222" in c for c in cnpjs_resumo)

    def test_detalhe_limitado_por_max_detalhe(self) -> None:
        # Cria mais classes que MAX_FIDC_DETALHE não é prático (1500),
        # mas confirmamos só que o pipeline aplica .head(MAX_FIDC_DETALHE).
        geral = pd.DataFrame(
            [_geral_row(CNPJ=f"{i:014d}", FUNDO=f"F{i}", SCORE_RISCO=float(i), MESES_HISTORICO=24) for i in range(20)]
        )
        out = build_fidcs(geral, pd.DataFrame())
        assert len(out["detalhe"]) <= MAX_FIDC_DETALHE
        assert len(out["detalhe"]) == 20


# ─── BUILD_CLIENTES ──────────────────────────────────────────────────────
def _cliente_row(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "cpf": "12345678901",
        "nome": "Ana Lima",
        "email": "ana@exemplo.com",
        "telefone": "11999990000",
        "idade": 30,
        "renda": 2,
        "experiencia": 3,
        "horizonte": 5,
        "perfil": "MODERADO",
        "score_perfil": 65.0,
        "data_cadastro": "2025-01-15",
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
        """Smoke: cpf/nome/email/telefone NÃO saem do builder em claro."""
        df = pd.DataFrame([_cliente_row()])
        out = build_clientes(df)
        cliente = out["lista"][0]
        # CPF não pode aparecer em claro.
        assert "12345678901" not in cliente["cpf"]
        assert cliente["cpf"].startswith("***")
        # Nome completo não pode aparecer; só primeiro nome + inicial.
        assert cliente["nome"] != "Ana Lima"
        assert "Ana" in cliente["nome"]
        # Email mascarado preserva apenas 1 char do local + TLD.
        assert "ana@exemplo.com" not in cliente["email"]
        assert "@" in cliente["email"]
        # Telefone mascarado (DDD + últimos 4).
        assert "11999990000" not in cliente["telefone"]

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
        "SCORE_CLIENTE": 65.0,
        "FUNDO": "FIDC ABC",
        "TIPO_COTA": "UNICA",
        "RISCO_FUNDO": "BAIXO",
        "SCORE_RISCO_FUNDO": 42.5,
        "PERFIL_FUNDO": "CONSERVADOR",
        "RETORNO_ANUAL": 12.3,
        "VOLATILIDADE": 3.0,
        "TAXA_INAD": 1.2,
        "MESES_HISTORICO": 12,
        "MATCH_SCORE": 85.0,
        "S_PERFIL": 100.0,
        "S_RISCO": 80.0,
        "S_RETORNO": 60.0,
        "S_HISTORICO": 50.0,
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
        """Match também mascara CPF e nome do cliente."""
        todos = pd.DataFrame([_match_row_dict()])
        out = build_matches(todos, pd.DataFrame())
        m = out["lista"][0]
        assert "12345678901" not in m["cpf"]
        assert m["cliente"] != "Ana Lima"


# ─── BUILD_CREDIT ────────────────────────────────────────────────────────
def _credit_row(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id_cnpj": "abcdef12",
        "score_credito": 75.0,
        "prob_default": 0.12,
        "risco_credito": "BAIXO",
        "total_boletos": 10,
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

    def test_empresas_sem_duplicatas_apos_concat_head_tail_sample(self) -> None:
        """Concat de head+tail+sample pode produzir duplicatas; payload precisa deduplicar."""
        df = pd.DataFrame([_credit_row(id_cnpj=f"emp{i:05d}", score_credito=float(i)) for i in range(20)])
        out = build_credit(df)
        # `nome` substitui `id_cnpj` no payload (LGPD: hash anônimo viralizado
        # como label legível). A unicidade segue garantida pelos primeiros 8
        # caracteres do hash, que são determinísticos.
        nomes = [e["nome"] for e in out["empresas"]]
        assert len(nomes) == len(set(nomes)), "Empresas duplicadas no output do build_credit"

    def test_empresas_limitadas_por_max_credit(self) -> None:
        df = pd.DataFrame([_credit_row(id_cnpj=f"emp{i:05d}", score_credito=float(i)) for i in range(MAX_CREDIT * 2)])
        out = build_credit(df)
        assert len(out["empresas"]) <= MAX_CREDIT

    def test_media_prob_default_calculada_quando_coluna_existe(self) -> None:
        # A média de prob_default agora é restrita a empresas com
        # `total_boletos >= MIN_BOLETOS_SCORE_CONFIAVEL` (== 20). Empresas
        # abaixo do limiar têm prob ruidosa e enviesariam a média —
        # decisão deliberada do schema novo de credit. As fixtures usam
        # 25 boletos pra ficarem no universo "confiável".
        df = pd.DataFrame(
            [
                _credit_row(id_cnpj="emp1", prob_default=0.10, total_boletos=25),
                _credit_row(id_cnpj="emp2", prob_default=0.30, total_boletos=25),
            ]
        )
        out = build_credit(df)
        assert out["stats"]["media_prob_default"] == 0.2
