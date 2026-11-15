#!/usr/bin/env bash
# Job SLURM genérico: executa o comando recebido. Submetido por `make slurm` e `make slurm-experimentos`.
#SBATCH --job-name=bpp
#SBATCH --cpus-per-task=1
#SBATCH --mem=16G
#SBATCH --time=24:00:00

set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-.}"

# Descomente/ajuste se o cluster usa módulos de ambiente:
# module load python

export PATH="$HOME/.local/bin:$PATH"
command -v uv >/dev/null 2>&1 || make uv

echo "[$(date -Is)] $(hostname) | cpus: ${SLURM_CPUS_PER_TASK:-?} | $*"
status=0
"$@" || status=$?

# Jobs Gurobi: segura a faixa até o token WLS expirar, para não exceder as sessões da licença
if [[ "${BPP_ESPERA_FIM:-0}" -gt 0 ]]; then
    echo "[$(date -Is)] aguardando ${BPP_ESPERA_FIM}s (token Gurobi)"
    sleep "$BPP_ESPERA_FIM"
fi
echo "[$(date -Is)] fim (status $status)"
exit "$status"
