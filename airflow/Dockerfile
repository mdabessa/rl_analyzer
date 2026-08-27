FROM apache/airflow:3.3.1
USER root
RUN apt-get update && apt-get install -y rsync openssh-client && rm -rf /var/lib/apt/lists/*
# Entrypoint que provisiona SSH (chave montada pelo compose) e repassa ao
# /entrypoint oficial. Container sobe como root apenas para copiar a chave;
# o script derruba para o usuário airflow antes de iniciar o Airflow.
COPY entrypoint.sh /usr/local/bin/airflow-ssh-entrypoint.sh
RUN chmod +x /usr/local/bin/airflow-ssh-entrypoint.sh
ENTRYPOINT ["/usr/local/bin/airflow-ssh-entrypoint.sh"]
USER root
