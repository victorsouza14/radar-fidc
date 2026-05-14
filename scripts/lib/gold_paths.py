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
