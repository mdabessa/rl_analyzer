FROM apache/airflow:3.3.1
USER root
RUN apt-get update && apt-get install -y rsync openssh-client && rm -rf /var/lib/apt/lists/*
# DuckDB p/ o rebuild do silver/warehouse dentro do DAG
# (scripts/build_silver.py e scripts/build_warehouse.py rodam no worker).
# A imagem do Airflow bloqueia pip como root ("use airflow user") e o Python é
# um venv em /home/airflow/.local (dono: airflow, user site desativado) → pip
# install como airflow, SEM --user, cai no site-packages do venv.
USER airflow
RUN pip install --no-cache-dir duckdb
USER root
# Entrypoint que provisiona SSH (chave montada pelo compose) e repassa ao
# /entrypoint oficial. Container sobe como root apenas para copiar a chave;
# o script derruba para o usuário airflow antes de iniciar o Airflow.
COPY entrypoint.sh /usr/local/bin/airflow-ssh-entrypoint.sh
RUN chmod +x /usr/local/bin/airflow-ssh-entrypoint.sh
ENTRYPOINT ["/usr/local/bin/airflow-ssh-entrypoint.sh"]
USER root
