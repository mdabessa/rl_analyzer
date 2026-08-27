#!/usr/bin/env bash
# Provisiona SSH para o usuário airflow a partir dos arquivos montados pelo
# compose (read-only) e repassa a execução ao entrypoint oficial do Airflow.
#
# Por que isso existe:
#   - O container roda como airflow (uid 50000), mas a chave no host é 0400 do
#     seu usuário (uid 1000) → o airflow não consegue lê-la via bind mount.
#   - A chave fica FORA de ~/.ssh, então montar só ~/.ssh não basta.
#   - Este script (rodando como root no start) copia a chave para o overlay do
#     container com owner/perms corretos (0600 airflow) e gera ~/.ssh/config.
#
# Montagens esperadas (docker-compose):
#   ~/.ssh                          -> /home/airflow/ssh-conf (config, known_hosts)
#   ${SSH_KEY_PATH} (chave privada) -> /home/airflow/ssh-key/vps.key
#
# Obs.: a chave é montada num caminho SEPARADO do ~/.ssh, porque o Docker não
# cria mountpoint de arquivo dentro de um bind mount de diretório read-only.
#
# Depois de provisionar, faz `su airflow` e executa o /entrypoint oficial, então
# todo o bootstrap normal do Airflow (env, db check, CMD) é preservado.

set -euo pipefail

SSH_CONF_SRC=/home/airflow/ssh-conf
SSH_KEY_SRC=/home/airflow/ssh-key/vps.key

# Se por algum motivo não estiver rodando como root, só repassa para o oficial.
if [[ "$(id -u)" != "0" ]]; then
  exec /usr/bin/dumb-init -- /entrypoint "$@"
fi

provision_ssh() {
  local home="$1" user="$2"
  local ssh_dir="$home/.ssh"

  echo "[ssh-entrypoint] provisionando ~/.ssh de $user"
  install -d -m 0700 -o "$user" -g 0 "$ssh_dir"

  # 1) Chave privada (obrigatória). Montada pelo compose em $SSH_KEY_SRC
  if [[ -f "$SSH_KEY_SRC" ]]; then
    install -m 0600 -o "$user" -g 0 "$SSH_KEY_SRC" "$ssh_dir/vps.key"
  else
    echo "[ssh-entrypoint] AVISO: $SSH_KEY_SRC não montada — ssh/rsync falharão" >&2
  fi

  # 2) known_hosts do host (opcional) — evita revalidar host key
  if [[ -f "$SSH_CONF_SRC/known_hosts" ]]; then
    install -m 0644 -o "$user" -g 0 "$SSH_CONF_SRC/known_hosts" "$ssh_dir/known_hosts"
  fi

  # 3) config: reaproveita o ~/.ssh/config do host corrigindo o IdentityFile;
  #    se não houver config montado, gera um com HostName/User via env
  #    (VPS_HOST/VPS_USER — sem hardcode no repo; vêm do .env).
  if [[ -f "$SSH_CONF_SRC/config" ]]; then
    cp "$SSH_CONF_SRC/config" "$ssh_dir/config"
    sed -E -i \
      -e "s#^([[:space:]]*)IdentityFile[[:space:]].*#\1IdentityFile $ssh_dir/vps.key#" \
      "$ssh_dir/config"
    grep -q '^[[:space:]]*StrictHostKeyChecking' "$ssh_dir/config" \
      || printf '  StrictHostKeyChecking accept-new\n' >> "$ssh_dir/config"
  else
    if [[ -n "${VPS_HOST:-}" && -n "${VPS_USER:-}" ]]; then
      cat > "$ssh_dir/config" <<EOF
Host vps
  HostName ${VPS_HOST}
  User ${VPS_USER}
  IdentityFile $ssh_dir/vps.key
  IdentitiesOnly yes
  StrictHostKeyChecking accept-new
EOF
    else
      echo "[ssh-entrypoint] AVISO: sem ~/.ssh/config montado e VPS_HOST/VPS_USER vazios — alias 'vps' não será criado para $user" >&2
      : > "$ssh_dir/config"
    fi
  fi
  chown "$user":0 "$ssh_dir/config"
  chmod 0600 "$ssh_dir/config"
}

# Provisiona para o airflow (processos do Airflow) e também para root, para que
# `docker compose exec <svc> ssh vps` funcione sem precisar de --user airflow.
provision_ssh /home/airflow airflow
provision_ssh /root root

# Ajusta permissões dos bind mounts p/ o airflow (uid 50000) conseguir escrever:
# logs do dag-processor/tasks, dados do rsync (/opt/data), plugins e scripts.
# (sem isso, o dag-processor falha com FileNotFoundError ao criar os logs e o
#  rsync do DAG falha com permission denied em /opt/data).
for d in /opt/airflow/logs /opt/airflow/plugins /opt/airflow/scripts /opt/airflow/dags /opt/data; do
  if [[ -e "$d" ]]; then
    chmod -R a+rwX "$d" 2>/dev/null || true
  fi
done

# 4) Repassa ao entrypoint oficial do Airflow, já como usuário airflow.
exec su airflow -c 'exec /usr/bin/dumb-init -- /entrypoint "$@"' sh "$@"
