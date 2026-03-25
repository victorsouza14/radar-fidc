# Notebook: orquestrador_gold
# Camada: Gold — Radar FIDC
# Executar via: Databricks Workspace

# Databricks notebook source
# RADAR FIDC — Orquestrador Gold (roda todos em sequência)
import datetime

BASE = "/Users/rm566652@fiap.com.br/03_gold_modelagem"

def run_nb(name, timeout=600):
    t0 = datetime.datetime.now()
    print(f"[{t0.strftime('%H:%M:%S')}] Iniciando: {name}...")
    try:
        result = dbutils.notebook.run(f"{BASE}/{name}", timeout_seconds=timeout)
        elapsed = (datetime.datetime.now() - t0).seconds
        print(f"  OK em {elapsed}s | resultado: {result[:50] if result else 'OK'}")
        return True
    except Exception as e:
        print(f"  ERRO: {e}")
        return False

# COMMAND ----------

print("=" * 60)
print("  RADAR FIDC — Pipeline Gold")
print(f"  {datetime.datetime.now()}")
print("=" * 60)

steps = [
    "00_schema_report",
    "01_score_fidc",
    "02_indicadores_macro",
    "03_recomendacao_pme",
    "04_dashboard_master",
    "05_export_csv",
]

results = {}
for step in steps:
    results[step] = run_nb(step)

# COMMAND ----------

print("\n=== RESULTADO FINAL ===")
for step, ok in results.items():
    status = "OK" if ok else "FALHOU"
    print(f"  {status}  {step}")

all_ok = all(results.values())
if all_ok:
    print("\nPipeline Gold concluido com sucesso!")
    print("Dados disponiveis em gold/powerbi/ para o Power BI")
else:
    raise Exception("Alguns steps falharam. Verifique os logs acima.")
