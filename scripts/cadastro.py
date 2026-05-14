import csv
import os
import pathlib
import sys
from datetime import datetime

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data_real"
RATING_PATH = os.environ.get("RADAR_RATING", str(DATA / "rating_fidc.xlsx"))
CADASTRO_CSV = os.environ.get("RADAR_CLIENTES", str(DATA / "clientes.csv"))

# ============================================================
# HELPERS
# ============================================================


def separador(char="=", n=60):
    print(char * n)


def titulo(txt):
    separador()
    print(f"  {txt}")
    separador()


def pergunta_opcao(texto, opcoes):
    """Exibe pergunta com opções numeradas e retorna a escolha (1-based)."""
    print(f"\n{texto}")
    for i, op in enumerate(opcoes, 1):
        print(f"  {i}) {op}")
    while True:
        try:
            r = int(input("  Resposta: ").strip())
            if 1 <= r <= len(opcoes):
                return r
        except ValueError:
            pass
        print(f"  Digite um numero entre 1 e {len(opcoes)}.")


def pergunta_texto(texto, obrigatorio=True):
    while True:
        r = input(f"{texto}: ").strip()
        if r or not obrigatorio:
            return r
        print("  Campo obrigatorio.")


def pergunta_cpf():
    import re

    while True:
        cpf = input("  CPF (somente numeros): ").strip()
        cpf = re.sub(r"\D", "", cpf)
        if len(cpf) == 11:
            return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
        print("  CPF invalido. Digite 11 digitos.")


# ============================================================
# QUESTIONÁRIO DE PERFIL  (API - Adequação ao Perfil)
# ============================================================

PERGUNTAS = [
    {
        "id": "objetivo",
        "peso": 0.20,
        "texto": "1. Qual é o seu principal objetivo com este investimento?",
        "opcoes": [
            "Preservar meu capital — segurança em primeiro lugar",
            "Crescimento equilibrado — aceito algum risco por melhor retorno",
            "Maximizar retorno — aceito riscos maiores em busca de ganhos altos",
        ],
    },
    {
        "id": "horizonte",
        "peso": 0.15,
        "texto": "2. Por quanto tempo você pretende manter o investimento?",
        "opcoes": [
            "Menos de 1 ano",
            "Entre 1 e 3 anos",
            "Mais de 3 anos",
        ],
    },
    {
        "id": "reacao_queda",
        "peso": 0.25,
        "texto": "3. Se seu investimento caísse 15% em um mês, você...",
        "opcoes": [
            "Resgataria tudo imediatamente para evitar mais perdas",
            "Resgataria parte para reduzir a exposição",
            "Aguardaria a recuperação sem resgatar",
            "Aproveitaria para investir mais, já que o preço caiu",
        ],
    },
    {
        "id": "experiencia",
        "peso": 0.15,
        "texto": "4. Como você descreveria sua experiência com investimentos?",
        "opcoes": [
            "Iniciante — conheço poupança e CDB",
            "Intermediário — já investi em fundos, Tesouro Direto, LCI/LCA",
            "Avançado — conheço ações, FIDCs, crédito privado ou derivativos",
        ],
    },
    {
        "id": "renda",
        "peso": 0.10,
        "texto": "5. Qual é a sua renda mensal aproximada?",
        "opcoes": [
            "Até R$ 5.000",
            "Entre R$ 5.000 e R$ 20.000",
            "Acima de R$ 20.000",
        ],
    },
    {
        "id": "percentual_patrimonio",
        "peso": 0.10,
        "texto": "6. Qual percentual do seu patrimônio você pretende alocar neste investimento?",
        "opcoes": [
            "Menos de 10% — é uma parte pequena",
            "Entre 10% e 30%",
            "Mais de 30% — é uma parcela relevante",
        ],
    },
    {
        "id": "reserva_emergencia",
        "peso": 0.05,
        "texto": "7. Você possui reserva de emergência (pelo menos 6 meses de despesas)?",
        "opcoes": [
            "Não",
            "Sim",
        ],
    },
]

# Mapa de resposta → pontuação
PONTOS = {
    "objetivo": {1: 1, 2: 2, 3: 3},
    "horizonte": {1: 1, 2: 2, 3: 3},
    "reacao_queda": {1: 1, 2: 2, 3: 3, 4: 4},
    "experiencia": {1: 1, 2: 2, 3: 3},
    "renda": {1: 1, 2: 2, 3: 3},
    "percentual_patrimonio": {1: 1, 2: 2, 3: 3},
    "reserva_emergencia": {1: 1, 2: 3},
}

# Pontuação máxima possível ponderada
SCORE_MAX = sum(max(PONTOS[p["id"]].values()) * p["peso"] for p in PERGUNTAS)
SCORE_MIN = sum(min(PONTOS[p["id"]].values()) * p["peso"] for p in PERGUNTAS)


def calcular_perfil(respostas: dict) -> tuple[str, float]:
    """Retorna (perfil, score_0_100)."""
    score_pond = sum(PONTOS[p["id"]][respostas[p["id"]]] * p["peso"] for p in PERGUNTAS)
    score_norm = (score_pond - SCORE_MIN) / (SCORE_MAX - SCORE_MIN) * 100

    if score_norm <= 33:
        perfil = "CONSERVADOR"
    elif score_norm <= 66:
        perfil = "MODERADO"
    else:
        perfil = "ARROJADO"

    return perfil, round(score_norm, 1)


# ============================================================
# RECOMENDAÇÃO DE FIDCs
# ============================================================


def carregar_rating():
    if not os.path.exists(RATING_PATH):
        print(f"\n  [AVISO] Arquivo de rating nao encontrado: {RATING_PATH}")
        print("  Execute rating.py primeiro para gerar as recomendacoes.")
        return None
    return pd.read_excel(RATING_PATH, sheet_name="GERAL")


def recomendar(perfil: str, df_rating: pd.DataFrame, top_n: int = 5) -> pd.DataFrame:
    """Retorna top N FIDCs adequados ao perfil, priorizando retorno ajustado ao risco."""
    df = df_rating.copy()

    # Perfis aceitos por perfil do cliente
    perfis_aceitos = {
        "CONSERVADOR": ["CONSERVADOR"],
        "MODERADO": ["CONSERVADOR", "MODERADO"],
        "ARROJADO": ["CONSERVADOR", "MODERADO", "ARROJADO"],
    }

    df = df[df["PERFIL_SUGERIDO"].isin(perfis_aceitos[perfil])]
    df = df[df["MESES_HISTORICO"] >= 6]
    df = df[df["RETORNO_ANUAL"].notna() & (df["RETORNO_ANUAL"] > 0)]
    df = df.sort_values("RETORNO_AJ_RISCO", ascending=False)

    cols = [
        "FUNDO",
        "TIPO_COTA",
        "RISCO",
        "RETORNO_ANUAL",
        "VOLATILIDADE",
        "TAXA_INADIMPLENCIA",
        "SCORE_RISCO",
        "PERFIL_SUGERIDO",
    ]
    cols_existentes = [c for c in cols if c in df.columns]
    return df[cols_existentes].drop_duplicates(subset=["FUNDO", "TIPO_COTA"]).head(top_n)


def imprimir_recomendacoes(perfil: str, nome_cliente: str, df_rec: pd.DataFrame):
    separador("-")
    print(f"\n  RECOMENDACOES DE FIDC PARA {nome_cliente.upper()} | Perfil: {perfil}\n")
    separador("-")

    descricao_perfil = {
        "CONSERVADOR": "Fundos senoir com baixo risco de inadimplencia e carteiras bem diversificadas.",
        "MODERADO": "Fundos com equilibrio entre seguranca e rentabilidade, risco controlado.",
        "ARROJADO": "Fundos com maior potencial de retorno, aceitando exposicao a maior risco de credito.",
    }
    print(f"  {descricao_perfil[perfil]}\n")

    if df_rec.empty:
        print("  Nenhum FIDC disponivel para o perfil no momento.")
        return

    for i, (_, row) in enumerate(df_rec.iterrows(), 1):
        retorno = f"{row['RETORNO_ANUAL']:.1f}%" if pd.notna(row.get("RETORNO_ANUAL")) else "N/D"
        volat = f"{row['VOLATILIDADE']:.1f}%" if pd.notna(row.get("VOLATILIDADE")) else "N/D"
        inad = f"{row['TAXA_INADIMPLENCIA']:.1f}%" if pd.notna(row.get("TAXA_INADIMPLENCIA")) else "N/D"
        score = f"{row['SCORE_RISCO']:.0f}/100" if pd.notna(row.get("SCORE_RISCO")) else "N/D"

        print(f"  [{i}] {row['FUNDO']}")
        print(f"      Cota: {row['TIPO_COTA']} | Risco: {row['RISCO']} | Score: {score}")
        print(f"      Retorno anual: {retorno}  |  Volatilidade: {volat}  |  Inadimplencia: {inad}")
        print()


# ============================================================
# SALVAR CLIENTE
# ============================================================

CABECALHO = [
    "data_cadastro",
    "nome",
    "cpf",
    "email",
    "telefone",
    "idade",
    "objetivo",
    "horizonte",
    "reacao_queda",
    "experiencia",
    "renda",
    "percentual_patrimonio",
    "reserva_emergencia",
    "perfil",
    "score_perfil",
]


def salvar_cliente(dados: dict):
    novo = not os.path.exists(CADASTRO_CSV)
    with open(CADASTRO_CSV, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=CABECALHO, extrasaction="ignore")
        if novo:
            w.writeheader()
        w.writerow(dados)
    print(f"\n  Cliente salvo em: {CADASTRO_CSV}")


# ============================================================
# MODO SIMULAÇÃO — gera N clientes aleatórios
# ============================================================

NOMES_SIMULADOS = [
    "Ana Lima",
    "Bruno Souza",
    "Carla Mendes",
    "Diego Ferreira",
    "Elena Costa",
    "Felipe Rocha",
    "Gabriela Nunes",
    "Hugo Alves",
    "Isabela Moura",
    "João Pinto",
    "Karen Vieira",
    "Lucas Barros",
    "Marina Gomes",
    "Nelson Reis",
    "Olivia Campos",
    "Paulo Martins",
    "Renata Farias",
    "Samuel Lopes",
    "Tânia Borges",
    "Victor Cunha",
]


def simular_clientes(n: int = 20, seed: int = 42):
    rng = np.random.default_rng(seed)
    clientes = []

    for i in range(n):
        respostas = {p["id"]: int(rng.choice(list(PONTOS[p["id"]].keys()))) for p in PERGUNTAS}
        perfil, score = calcular_perfil(respostas)

        cliente = {
            "data_cadastro": datetime.now().strftime("%Y-%m-%d"),
            "nome": NOMES_SIMULADOS[i % len(NOMES_SIMULADOS)]
            + (f" {i // len(NOMES_SIMULADOS) + 1}" if i >= len(NOMES_SIMULADOS) else ""),
            "cpf": f"{''.join([str(rng.integers(0, 9)) for _ in range(11)][:11])}",
            "email": f"cliente{i + 1}@email.com",
            "telefone": f"11{''.join([str(rng.integers(0, 9)) for _ in range(9)])}",
            "idade": int(rng.integers(22, 70)),
            "perfil": perfil,
            "score_perfil": score,
            **respostas,
        }
        clientes.append(cliente)

    df = pd.DataFrame(clientes)[CABECALHO]
    df.to_csv(CADASTRO_CSV, index=False, encoding="utf-8-sig")
    print(f"\n  {n} clientes simulados salvos em: {CADASTRO_CSV}")
    print("  Distribuicao de perfis:")
    print(df["perfil"].value_counts().to_string())
    return df


# ============================================================
# FLUXO PRINCIPAL
# ============================================================


def modo_cadastro():
    titulo("CADASTRO DE CLIENTE — PERFIL DE INVESTIDOR")

    print("\n[ DADOS PESSOAIS ]\n")
    nome = pergunta_texto("  Nome completo")
    cpf = pergunta_cpf()
    email = pergunta_texto("  E-mail")
    telefone = pergunta_texto("  Telefone")
    idade = pergunta_texto("  Idade")

    print("\n\n[ QUESTIONARIO DE PERFIL ]\n")
    print("  Responda com honestidade — as recomendacoes dependem disso.\n")

    respostas = {}
    for p in PERGUNTAS:
        respostas[p["id"]] = pergunta_opcao(p["texto"], p["opcoes"])

    perfil, score = calcular_perfil(respostas)

    separador("-")
    print(f"\n  Perfil identificado: {perfil}  (score {score}/100)\n")
    separador("-")

    dados = {
        "data_cadastro": datetime.now().strftime("%Y-%m-%d"),
        "nome": nome,
        "cpf": cpf,
        "email": email,
        "telefone": telefone,
        "idade": idade,
        "perfil": perfil,
        "score_perfil": score,
        **respostas,
    }
    salvar_cliente(dados)

    df_rating = carregar_rating()
    if df_rating is not None:
        df_rec = recomendar(perfil, df_rating)
        imprimir_recomendacoes(perfil, nome, df_rec)

        # Salva recomendações do cliente
        rec_path = CADASTRO_CSV.replace("clientes.csv", f"rec_{cpf.replace('.', '').replace('-', '')}.xlsx")
        if not df_rec.empty:
            df_rec.to_excel(rec_path, index=False)
            print(f"  Recomendacoes salvas em: {rec_path}")


def menu():
    titulo("SISTEMA DE CADASTRO E RECOMENDACAO DE FIDCs")
    print("\n  1) Cadastrar novo cliente")
    print("  2) Gerar base simulada de clientes")
    print("  3) Consultar recomendacoes para perfil especifico")
    print("  0) Sair")

    while True:
        try:
            op = int(input("\n  Opcao: ").strip())
            if op in (0, 1, 2, 3):
                return op
        except ValueError:
            pass
        print("  Opcao invalida.")


if __name__ == "__main__":
    df_rating = carregar_rating()

    op = menu()

    if op == 1:
        modo_cadastro()

    elif op == 2:
        n = input("\n  Quantos clientes simular? [20]: ").strip()
        n = int(n) if n.isdigit() else 20
        simular_clientes(n)

    elif op == 3:
        perfil = pergunta_opcao("Qual perfil consultar?", ["CONSERVADOR", "MODERADO", "ARROJADO"])
        perfil_str = ["CONSERVADOR", "MODERADO", "ARROJADO"][perfil - 1]
        if df_rating is not None:
            df_rec = recomendar(perfil_str, df_rating)
            imprimir_recomendacoes(perfil_str, "CONSULTA DIRETA", df_rec)

    elif op == 0:
        print("\n  Ate logo!")
        sys.exit(0)
