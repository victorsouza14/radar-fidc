# Helpers compartilhados pelos notebooks Radar FIDC.
# Resolve segredos tanto no Databricks (via dbutils.secrets) quanto local
# (via variáveis de ambiente / .env).

import os


def _databricks_dbutils():
    try:
        from pyspark.dbutils import DBUtils  # type: ignore
        from pyspark.sql import SparkSession  # type: ignore

        spark = SparkSession.builder.getOrCreate()
        return DBUtils(spark)
    except Exception:
        return None


_DBUTILS = _databricks_dbutils()


def get_secret(env_name: str, scope: str = "escopo", key: str | None = None) -> str:
    """Resolve um segredo procurando primeiro em os.environ, depois no Databricks.

    Args:
        env_name: nome da variável de ambiente (ex: "AZURE_CONNECTION_STRING").
        scope: scope do Databricks Secret Scope.
        key: chave dentro do scope. Default = env_name.

    Raises:
        RuntimeError quando o segredo não é encontrado em nenhuma fonte.
    """
    val = os.environ.get(env_name)
    if val:
        return val

    if _DBUTILS is not None:
        try:
            return _DBUTILS.secrets.get(scope=scope, key=key or env_name)
        except Exception as e:
            raise RuntimeError(
                f"Segredo '{env_name}' não encontrado em os.environ "
                f"nem no Databricks scope '{scope}'/key '{key or env_name}': {e}"
            ) from e

    raise RuntimeError(
        f"Variável obrigatória '{env_name}' ausente. "
        "Configure no .env local ou no Databricks Secret Scope."
    )


def azure_connection_string() -> str:
    return get_secret("AZURE_CONNECTION_STRING", key="AZURECONNSTRING")
