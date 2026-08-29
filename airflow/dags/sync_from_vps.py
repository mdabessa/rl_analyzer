"""Coleta periodicamente os replays baixados na VPS e limpa o disco remoto.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.providers.standard.operators.bash import BashOperator
from airflow.providers.ssh.operators.ssh import SSHOperator


# Data dir na VPS: o serviço rl-download roda com --data-dir
# /home/ubuntu/rl_analyzer/data (contém replays/, manifests/ e state.json).
VPS_DATA_DIR = "/home/ubuntu/rl_analyzer/data"
# Diretório local dentro do container: ./data (bind mount /opt/data).
LOCAL_DATA_DIR = "/opt/data"

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
    schedule="0 */6 * * *",
    start_date=datetime(2026, 8, 1),
    catchup=False,
    max_active_runs=1,
    tags=["vps", "download", "rsync"],
) as dag:

    stop_downloader = SSHOperator(
        task_id="stop_downloader",
        ssh_conn_id="vps",
        command=(
            "sudo systemctl stop rl-download"
        ),
    )

    remove_stubs = SSHOperator(
        task_id="remove_stubs",
        ssh_conn_id="vps",
        command=(
            f"python3 /home/ubuntu/vps_sync/remove_fakes.py {VPS_DATA_DIR}"
        ),
    )

    pull = BashOperator(
        task_id="pull_replays",
        bash_command=(
            f"rsync -rvP --ignore-existing vps:{VPS_DATA_DIR}/replays/ {LOCAL_DATA_DIR}/replays/ && "
            f"rsync -rvP vps:{VPS_DATA_DIR}/manifests/ {LOCAL_DATA_DIR}/manifests/ && "
            f"rsync -rvP vps:{VPS_DATA_DIR}/state.json {LOCAL_DATA_DIR}/state.json"
        ),
    )

    cleanup = SSHOperator(
        task_id="cleanup_remote",
        ssh_conn_id="vps",
        command=(
            f"find {VPS_DATA_DIR}/replays -type f -delete"
        ),
    )

    create_stubs = SSHOperator(
        task_id="create_stubs",
        ssh_conn_id="vps",
        command=(
            f"python3 /home/ubuntu/vps_sync/create_fakes.py {VPS_DATA_DIR}"
        ),
    )

    start_downloader = SSHOperator(
        task_id="start_downloader",
        ssh_conn_id="vps",
        command=(
            "sudo systemctl daemon-reload && "
            "sudo systemctl enable --now rl-download"
        ),
    )

    build_silver = BashOperator(
        task_id="build_silver",
        bash_command=(
            f"python3 /opt/airflow/scripts/build_silver.py --data-dir {LOCAL_DATA_DIR}"
        ),
    )

    build_warehouse = BashOperator(
        task_id="build_warehouse",
        bash_command=(
            f"python3 /opt/airflow/scripts/build_warehouse.py --data-dir {LOCAL_DATA_DIR} "
            f"--db {LOCAL_DATA_DIR}/warehouse.duckdb"
        ),
    )

    (
        stop_downloader
        >> remove_stubs
        >> pull
        >> cleanup
        >> create_stubs
        >> start_downloader
        >> build_silver
        >> build_warehouse
    )
