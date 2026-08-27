"""Coleta periodicamente os replays baixados na VPS e limpa o disco remoto.

Pré-requisito SSH (já provisionado pela imagem — ver airflow/Dockerfile e
airflow/entrypoint.sh): dentro do container o alias `vps` funciona, usando a
chave montada pelo compose. Teste rápido:

    docker compose -f airflow/docker-compose.yaml exec scheduler \
        ssh -T vps 'echo ok && df -h /home/ubuntu'

Atenção sobre o cleanup:
  O downloader da VPS deduplica por EXISTÊNCIA do arquivo local
  (``src/storage.replay_exists``). Se você apagar os .json remotos, a próxima
  passada do downloader RE-BAIXA tudo, queimando a cota da API. Por isso:
    - só apagamos arquivos em ``replays/`` mais antigos que CLEANUP_MIN_AGE_HOURS
      (já copiados em execuções anteriores bem-sucedidas);
    - ``manifests/`` e ``state.json`` NUNCA são apagados (o downloader precisa
      deles para saber o progresso).
  Mesmo assim, se o downloader ainda estiver ativo naquele bucket, ele pode
  re-baixar. Solução definitiva: marcar os IDs como "synced" no manifest (mudança
  pequena em src/downloader.py) — é um follow-up recomendado.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

# Diretório de dados NA VPS (o serviço systemd rl-download usa /home/ubuntu/rl_data).
VPS_DATA_DIR = "/home/ubuntu/rl_data"
# Diretório local dentro do container: ./data (bind mount /opt/data).
LOCAL_DATA_DIR = "/opt/data"
# Só apaga no VPS arquivos mais antigos que isto (horas).
CLEANUP_MIN_AGE_HOURS = 12
CLEANUP_MIN_AGE_MIN = CLEANUP_MIN_AGE_HOURS * 60

DEFAULT_ARGS = {
    "owner": "airflow",
    "retries": 2,
    "retry_delay": timedelta(minutes=10),
    "depends_on_past": False,
}

with DAG(
    dag_id="sync_from_vps",
    default_args=DEFAULT_ARGS,
    description="Puxa replays da VPS e limpa o disco remoto",
    schedule="0 */6 * * *",  # a cada 6h — ajuste conforme a velocidade do downloader
    start_date=datetime(2026, 8, 1),
    catchup=False,
    max_active_runs=1,
    tags=["vps", "download", "rsync"],
) as dag:

    pull = BashOperator(
        task_id="rsync_from_vps",
        bash_command=(
            "rsync -avz --partial --exclude='.tmp-*' "
            f"vps:{VPS_DATA_DIR}/ {LOCAL_DATA_DIR}/"
        ),
    )

    # Só roda se o rsync acima terminou com sucesso (trigger_rule padrão).
    cleanup = BashOperator(
        task_id="cleanup_vps_replays",
        bash_command=(
            "ssh vps '"
            f"find {VPS_DATA_DIR}/replays -type f -mmin +{CLEANUP_MIN_AGE_MIN} -delete && "
            f"find {VPS_DATA_DIR} -type d -empty -delete"
            "'"
        ),
    )

    pull >> cleanup
