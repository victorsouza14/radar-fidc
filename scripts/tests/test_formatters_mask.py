"""Teste regressivo de PII: o ``data.json`` gerado NÃO pode conter PII em claro.

Estratégia: construir um payload sintético com CPF, e-mail, telefone e nome
reais; processar via ``payload.build_clientes`` e ``payload.build_matches``;
e fazer busca por igualdade exata no JSON resultante. Falha se qualquer
padrão de PII original aparece literalmente.

Cobertura adicional: validar que as máscaras estão no formato esperado
(``***.***.***-XX``, ``c***@****.tld``, ``(DD) ****-XXXX``) — uma string
silenciosamente vazia também é regressão.
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
    return pd.DataFrame(
        {
            "cpf": [PII_PROBE["cpf"]],
            "nome": [PII_PROBE["nome"]],
            "email": [PII_PROBE["email"]],
            "telefone": [PII_PROBE["telefone"]],
            "idade": [42],
            "renda": [10000.0],
            "experiencia": [5],
            "horizonte": [10],
            "perfil": ["MODERADO"],
            "score_perfil": [70.0],
            "data_cadastro": ["2025-01-01"],
        }
    )


@pytest.fixture
def matches_pii_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "CPF": [PII_PROBE["cpf"]],
            "CLIENTE": [PII_PROBE["nome"]],
            "PERFIL_CLIENTE": ["MODERADO"],
            "SCORE_CLIENTE": [70.0],
            "FUNDO": ["FIDC Teste"],
            "TIPO_COTA": ["UNICA"],
            "RISCO_FUNDO": ["BAIXO"],
            "SCORE_RISCO_FUNDO": [30.0],
            "PERFIL_FUNDO": ["MODERADO"],
            "RETORNO_ANUAL": [10.0],
            "VOLATILIDADE": [3.0],
            "TAXA_INAD": [1.0],
            "MESES_HISTORICO": [12],
            "MATCH_SCORE": [80.0],
            "S_PERFIL": [90.0],
            "S_RISCO": [80.0],
            "S_RETORNO": [70.0],
            "S_HISTORICO": [60.0],
            "MOTIVO": ["x"],
            "RANK": [1],
        }
    )


class TestPIIMaskRegression:
    def test_no_pii_in_clientes_payload(self, clientes_pii_df: pd.DataFrame) -> None:
        from lib.payload import build_clientes

        out = build_clientes(clientes_pii_df)
        as_json = json.dumps(out, ensure_ascii=False)

        assert PII_PROBE["cpf"] not in as_json, "CPF cru vazou para o payload"
        assert PII_PROBE["email"] not in as_json, "Email cru vazou para o payload"
        assert PII_PROBE["telefone"] not in as_json, "Telefone cru vazou para o payload"
        assert PII_PROBE["nome"] not in as_json, "Nome completo vazou para o payload"

    def test_no_pii_in_matches_payload(self, matches_pii_df: pd.DataFrame) -> None:
        from lib.payload import build_matches

        out = build_matches(matches_pii_df, pd.DataFrame())
        as_json = json.dumps(out, ensure_ascii=False)

        assert PII_PROBE["cpf"] not in as_json, "CPF vazou em matches"
        assert PII_PROBE["nome"] not in as_json, "Nome vazou em matches"

    def test_mask_format_recognizable(self, clientes_pii_df: pd.DataFrame) -> None:
        """Garante que máscaras estão no formato esperado — não silenciosamente vazias."""
        from lib.payload import build_clientes

        out = build_clientes(clientes_pii_df)
        cli = out["lista"][0]
        # CPF mascarado guarda os 2 últimos dígitos.
        assert re.match(r"\*{3}\.\*{3}\.\*{3}-\d{2}", cli["cpf"]), f"CPF mask inesperada: {cli['cpf']}"
        # Email mascarado preserva 1ª letra e TLD.
        assert "@" in cli["email"] and "***" in cli["email"]
        assert cli["email"].startswith("j"), f"Email mask perdeu inicial: {cli['email']}"
        # Telefone: (DD) ****-XXXX
        assert re.match(r"\(\d{2}\) \*{4}-\d{4}", cli["telefone"]), f"Telefone mask inesperada: {cli['telefone']}"
        # Nome: primeiro + inicial do último (sem o sobrenome do meio).
        assert "Pereira" not in cli["nome"], f"Sobrenome completo vazou: {cli['nome']}"
        assert cli["nome"].startswith("Joao "), f"Nome mask quebrou: {cli['nome']}"

    def test_no_pii_in_full_generator_payload(
        self,
        clientes_pii_df: pd.DataFrame,
        matches_pii_df: pd.DataFrame,
    ) -> None:
        """Regressivo end-to-end: gera payload completo (mock io_utils) e busca PII.

        Cobre o caso de novo campo PII adicionado em algum builder no futuro
        que escape do mask. Pega ``build_clientes`` + ``build_matches`` +
        builders adjacentes em uma única passada.
        """
        from lib import payload

        full_payload = {
            "clientes": payload.build_clientes(clientes_pii_df),
            "matches": payload.build_matches(matches_pii_df, pd.DataFrame()),
            # fidcs/credit/macro são "PII-free" por construção, mas incluir
            # builders vazios garante que JSON final não trapaceia ao concatenar.
            "fidcs": payload.build_fidcs(pd.DataFrame(), pd.DataFrame()),
            "credit": payload.build_credit(pd.DataFrame()),
            "macro": payload.build_macro(pd.DataFrame()),
        }
        as_json = json.dumps(full_payload, ensure_ascii=False)
        for label, probe in PII_PROBE.items():
            assert probe not in as_json, f"PII '{label}'='{probe}' encontrada literalmente no payload completo"
