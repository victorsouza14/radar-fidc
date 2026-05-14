"""Mapeamento CNAE → seção/setor legível para display no dashboard.

CNAE 2.0 (IBGE) tem 7 dígitos. As 2 primeiras posições (divisão CNAE)
agrupam atividades por seção econômica. Aqui mapeamos para um label
curto e legível, adequado para exibir em cards e tabelas.

Referência oficial: https://concla.ibge.gov.br/classificacoes/por-tema/atividades-economicas/classificacao-nacional-de-atividades-economicas
"""

from __future__ import annotations

# Divisão CNAE (2 dígitos) → label curto. Cobre as seções A-U do IBGE.
_DIV_TO_SETOR: dict[str, str] = {
    # A — Agricultura, pecuária, produção florestal, pesca
    "01": "Agropecuária",
    "02": "Agropecuária",
    "03": "Agropecuária",
    # B — Indústrias extrativas
    "05": "Mineração",
    "06": "Mineração",
    "07": "Mineração",
    "08": "Mineração",
    "09": "Mineração",
    # C — Indústrias de transformação
    "10": "Alimentos",
    "11": "Bebidas",
    "12": "Fumo",
    "13": "Têxteis",
    "14": "Vestuário",
    "15": "Couro/calçados",
    "16": "Madeira",
    "17": "Celulose/papel",
    "18": "Gráfica",
    "19": "Petróleo/biocombustíveis",
    "20": "Química",
    "21": "Farmacêutica",
    "22": "Borracha/plástico",
    "23": "Minerais não-metálicos",
    "24": "Metalurgia",
    "25": "Metal (produtos)",
    "26": "Eletrônicos",
    "27": "Equipamentos elétricos",
    "28": "Máquinas",
    "29": "Veículos",
    "30": "Outros transportes",
    "31": "Móveis",
    "32": "Produtos diversos",
    "33": "Manutenção/reparação",
    # D — Eletricidade e gás
    "35": "Energia",
    # E — Água, esgoto, resíduos
    "36": "Saneamento",
    "37": "Saneamento",
    "38": "Saneamento",
    "39": "Saneamento",
    # F — Construção
    "41": "Construção",
    "42": "Construção",
    "43": "Construção",
    # G — Comércio, reparação de veículos
    "45": "Veículos (comércio)",
    "46": "Comércio atacadista",
    "47": "Comércio varejista",
    # H — Transporte, armazenagem, correio
    "49": "Transporte terrestre",
    "50": "Transporte aquaviário",
    "51": "Transporte aéreo",
    "52": "Armazenagem",
    "53": "Correio",
    # I — Alojamento e alimentação
    "55": "Hotelaria",
    "56": "Alimentação fora",
    # J — Informação e comunicação
    "58": "Edição",
    "59": "Audiovisual",
    "60": "Rádio/TV",
    "61": "Telecomunicações",
    "62": "TI",
    "63": "Serviços de informação",
    # K — Financeiras, seguros
    "64": "Serviços financeiros",
    "65": "Seguros",
    "66": "Auxiliares financeiros",
    # L — Imobiliárias
    "68": "Imobiliárias",
    # M — Profissionais, científicas, técnicas
    "69": "Jurídico/contábil",
    "70": "Consultoria",
    "71": "Arquitetura/engenharia",
    "72": "P&D",
    "73": "Publicidade",
    "74": "Outras profissionais",
    "75": "Veterinária",
    # N — Administrativas, complementares
    "77": "Aluguel",
    "78": "Recursos humanos",
    "79": "Turismo",
    "80": "Vigilância",
    "81": "Serviços p/ edifícios",
    "82": "Apoio administrativo",
    # O — Administração pública
    "84": "Administração pública",
    # P — Educação
    "85": "Educação",
    # Q — Saúde
    "86": "Saúde",
    "87": "Assistência social",
    "88": "Serviços sociais",
    # R — Artes, cultura, esporte
    "90": "Artes",
    "91": "Cultura",
    "92": "Loterias",
    "93": "Esporte/lazer",
    # S — Outros serviços
    "94": "Associações",
    "95": "Reparação/manutenção",
    "96": "Outros serviços pessoais",
    # T — Serviços domésticos
    "97": "Domésticos",
    "98": "Domésticos",
    # U — Organismos internacionais
    "99": "Internacional",
}


def setor_from_cnae(cd_cnae_prin: int | float | str | None) -> str:
    """Devolve o label do setor a partir do código CNAE de 7 dígitos.

    Aceita int/float/str. Devolve ``"Não classificado"`` se ``None``,
    inválido ou divisão não mapeada.
    """
    if cd_cnae_prin is None:
        return "Não classificado"
    try:
        code = int(float(cd_cnae_prin))
    except (TypeError, ValueError):
        return "Não classificado"
    if code <= 0:
        return "Não classificado"
    div = str(code).zfill(7)[:2]
    return _DIV_TO_SETOR.get(div, "Não classificado")
