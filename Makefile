# Bin Packing — `make help` lista alvos e variáveis.
# Toda variável abaixo pode ser trocada na linha de comando (make solvers TEMPO=60),
# no ambiente ou num config.mk local (ver config.mk.example).

-include config.mk

# --- ambiente ---------------------------------------------------------------
UV          ?= uv
UV_SYNC_ARGS ?=
RUN         ?= $(UV) run

# --- caminhos ---------------------------------------------------------------
DATA_DIR    ?= data
RAW_DIR     ?= $(DATA_DIR)/raw
INST_DIR    ?= $(DATA_DIR)/instancias
TESTE_DIR   ?= $(INST_DIR)/teste
RESULT_DIR  ?= resultados

# --- experimento principal --------------------------------------------------
NS          ?= 50 100 500 1000 2000
SOLVERS     ?= gurobi scip
TEMPO       ?= 600
THREADS     ?= 1
REFORCOS    ?= nenhum
SAIDA       ?= $(RESULT_DIR)/solvers.csv
SOLUCOES    ?= $(RESULT_DIR)/solucoes
EXTRA_ARGS  ?=

# --- experimentos secundários (docs/modelo.md) ------------------------------
NS_REFORCOS   ?= $(NS)
NS_INGENUO    ?= $(NS)
NS_SINTETICAS ?= 50 100 500
TEMPO_TESTE   ?= 60
TABELA_ARGS   ?= --latex --reforcos nenhum
JSONS         ?= $(SOLUCOES)

# --- SLURM ------------------------------------------------------------------
SLURM_ALVO     ?= solvers
SLURM_CPUS     ?= $(THREADS)
SLURM_MEM      ?= 16G
SLURM_TEMPO    ?= 24:00:00
SLURM_PARTICAO ?=
SLURM_LOG_DIR  ?= logs
SLURM_ARGS     ?=
# slurm-experimentos: tempo/memória estimados por job (docs/cluster.md)
SLURM_FOLGA     ?= 1.5
SLURM_MARGEM    ?= 300
SLURM_FATOR_MEM ?= 2
SLURM_MEM_MIN   ?= 2
SLURM_DRY       ?=
RODADA          ?=
GUROBI_SIMULT   ?= 2
GUROBI_ESPERA   ?= 300

# subpasta de SOLUCOES por experimento; vazio se SOLUCOES="" (não grava JSON)
sol_dir = $(if $(SOLUCOES),$(SOLUCOES)/$(1))
instancias_de = $(foreach n,$(1),$(INST_DIR)/instancia_$(n)_vms.csv)
INSTANCIAS     = $(call instancias_de,$(NS))
COMUM          = --solver $(SOLVERS) --tempo $(TEMPO) --threads $(THREADS) $(EXTRA_ARGS)

.DEFAULT_GOAL := help
.PHONY: help uv setup dados instancias sinteticas solvers reforcos s-ingenuo \
        experimentos teste-sintetico tabela validador test slurm slurm-experimentos juntar \
        clean clean-dados

help: ## Mostra esta ajuda
	@echo "Uso: make <alvo> [VAR=valor ...]"
	@echo
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'
	@echo
	@echo "Variáveis (valor atual):"
	@printf "  %-14s %s\n" NS "$(NS)" SOLVERS "$(SOLVERS)" TEMPO "$(TEMPO)" \
		THREADS "$(THREADS)" REFORCOS "$(REFORCOS)" SAIDA "$(SAIDA)" \
		SOLUCOES "$(SOLUCOES)" EXTRA_ARGS "$(EXTRA_ARGS)" DATA_DIR "$(DATA_DIR)" \
		RESULT_DIR "$(RESULT_DIR)" SLURM_ALVO "$(SLURM_ALVO)" SLURM_CPUS "$(SLURM_CPUS)" \
		SLURM_MEM "$(SLURM_MEM)" SLURM_TEMPO "$(SLURM_TEMPO)" SLURM_PARTICAO "$(SLURM_PARTICAO)" \
		SLURM_FOLGA "$(SLURM_FOLGA)" SLURM_MARGEM "$(SLURM_MARGEM)" \
		SLURM_FATOR_MEM "$(SLURM_FATOR_MEM)" SLURM_MEM_MIN "$(SLURM_MEM_MIN)" RODADA "$(RODADA)"

uv: ## Instala o uv em ~/.local/bin se não existir
	@command -v $(UV) >/dev/null 2>&1 && echo "uv já instalado: $$(command -v $(UV))" || \
		curl -LsSf https://astral.sh/uv/install.sh | sh

setup: ## Cria o .venv com as dependências (uv sync)
	$(UV) sync $(UV_SYNC_ARGS)

dados: ## Baixa o vmtable do Azure para data/raw (se faltar)
	$(RUN) bpp-dataset --raw-dir $(RAW_DIR)

instancias: ## Gera as instâncias reais de NS que faltam (baixa o dataset se preciso)
	$(RUN) bpp-dataset --n $(NS) --raw-dir $(RAW_DIR) --inst-dir $(INST_DIR)

sinteticas: ## Gera instâncias sintéticas (NS_SINTETICAS) em data/instancias/teste
	$(RUN) bpp-sintetico --n $(NS_SINTETICAS) --pasta $(TESTE_DIR)

solvers: instancias ## Experimento principal: NS x SOLVERS, grava SAIDA e SOLUCOES
	$(RUN) bpp-solvers $(INSTANCIAS) $(COMUM) --reforcos $(REFORCOS) \
		--saida $(SAIDA) --solucoes "$(SOLUCOES)"

reforcos: ## As 4 combinações de reforços (R1/R2) em NS_REFORCOS (padrão: NS)
	$(RUN) bpp-solvers $(call instancias_de,$(NS_REFORCOS)) $(COMUM) --reforcos todos \
		--saida $(RESULT_DIR)/reforcos.csv --solucoes "$(call sol_dir,reforcos)"

s-ingenuo: ## Comparação com S_k = n em NS_INGENUO (padrão: NS; ~3n² variáveis)
	$(RUN) bpp-solvers $(call instancias_de,$(NS_INGENUO)) $(COMUM) --s-ingenuo \
		--saida $(RESULT_DIR)/s_ingenuo.csv --solucoes "$(call sol_dir,s_ingenuo)"

experimentos: solvers reforcos s-ingenuo ## Roda tudo do relatório

teste-sintetico: ## Roda os solvers nas instâncias sintéticas (TEMPO_TESTE s)
	$(RUN) bpp-solvers "$(TESTE_DIR)/*.csv" --solver $(SOLVERS) --tempo $(TEMPO_TESTE) \
		--threads $(THREADS) $(EXTRA_ARGS) \
		--saida $(RESULT_DIR)/teste/teste_sintetico.csv --solucoes $(RESULT_DIR)/teste/solucoes

tabela: ## Tabela de resultados a partir de SAIDA (TABELA_ARGS)
	@$(RUN) bpp-tabela $(SAIDA) $(TABELA_ARGS)

validador: ## Valida os JSONs de solução contra os CSVs (JSONS: arquivos, pastas ou curingas)
	$(RUN) bpp-validador $(JSONS) --inst-dir $(INST_DIR) $(TESTE_DIR) --raw-dir $(RAW_DIR)

test: ## Testes automatizados (pytest)
	$(RUN) pytest -q

slurm-experimentos: setup instancias ## experimentos no SLURM: 1 job por execução + job que junta os CSVs
	$(RUN) bpp-slurm --ns $(NS) --ns-reforcos $(NS_REFORCOS) --ns-ingenuo $(NS_INGENUO) \
		--solvers $(SOLVERS) --reforcos $(REFORCOS) --tempo $(TEMPO) --threads $(THREADS) \
		--extra-args="$(EXTRA_ARGS)" --inst-dir $(INST_DIR) --raw-dir $(RAW_DIR) \
		--resultados $(RESULT_DIR) --solucoes="$(SOLUCOES)" --uv $(UV) \
		--folga $(SLURM_FOLGA) --margem $(SLURM_MARGEM) --fator-mem $(SLURM_FATOR_MEM) \
		--mem-min $(SLURM_MEM_MIN) --log-dir $(SLURM_LOG_DIR) --sbatch-args="$(SLURM_ARGS)" \
		--gurobi-simult $(GUROBI_SIMULT) --gurobi-espera $(GUROBI_ESPERA) \
		$(if $(SLURM_PARTICAO),--particao $(SLURM_PARTICAO)) \
		$(if $(RODADA),--rodada $(RODADA)) $(if $(SLURM_DRY),--dry-run)

juntar: ## Junta os CSVs parciais de RODADA em RESULT_DIR (se o job de junção falhou)
	$(RUN) bpp-juntar $(RESULT_DIR)/parcial/$(RODADA) --resultados $(RESULT_DIR)

slurm: setup ## Submete `make SLURM_ALVO` como um único job SLURM (repassa as variáveis)
	@mkdir -p $(SLURM_LOG_DIR)
	sbatch --job-name=bpp-$(SLURM_ALVO) --cpus-per-task=$(SLURM_CPUS) \
		--mem=$(SLURM_MEM) --time=$(SLURM_TEMPO) \
		$(if $(SLURM_PARTICAO),--partition=$(SLURM_PARTICAO)) \
		--output=$(SLURM_LOG_DIR)/%x-%j.out $(SLURM_ARGS) \
		scripts/slurm.sbatch make $(SLURM_ALVO) \
		NS="$(NS)" SOLVERS="$(SOLVERS)" TEMPO=$(TEMPO) THREADS=$(THREADS) \
		REFORCOS=$(REFORCOS) SAIDA=$(SAIDA) SOLUCOES="$(SOLUCOES)" \
		DATA_DIR=$(DATA_DIR) RESULT_DIR=$(RESULT_DIR) EXTRA_ARGS="$(EXTRA_ARGS)"

clean: ## Remove .venv e caches
	rm -rf .venv .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

clean-dados: ## Remove o dataset baixado (data/raw)
	rm -rf $(RAW_DIR)
