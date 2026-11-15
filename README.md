# Bin Packing Problem
Trabalho realizado para a disciplina de Programação Matemática, resolvendo uma aplicação do problema do empacotamento, relacionado à alocação de máquinas virtuais.

## Início rápido

Requer `make` e [uv](https://docs.astral.sh/uv/) (`make uv` instala o uv em `~/.local/bin` se faltar).

```bash
make setup      # cria .venv com pandas, gurobipy e pyscipopt (uv sync)
make test       # testes rápidos
make solvers    # experimento principal (instâncias de 50 a 2000 VMs, Gurobi e SCIP, 600 s)
make tabela     # tabela LaTeX a partir de resultados/solvers.csv
make help       # todos os alvos e variáveis
```

Qualquer variável do Makefile pode ser trocada na linha de comando:

```bash
make solvers NS="50 100" SOLVERS=scip TEMPO=60
make solvers EXTRA_ARGS="--verbose --semente 3" SAIDA=resultados/meu_teste.csv
```

Para fixar configurações da máquina (caminhos, threads, cluster), copie `config.mk.example` para `config.mk` (ignorado pelo git).

## Dataset

As instâncias reais `data/instancias/instancia_<N>_vms.csv` são as N primeiras VMs do vmtable do *Azure Public Dataset v1* (colunas `vmid`, `vmcorecount`, `vmmemory`).

**Não é preciso baixar nada à mão.** Se uma instância pedida não existe, o arquivo [`trace_data_vmtable_vmtable.csv.gz`](https://github.com/Azure/AzurePublicDataset/releases/download/dataset-v1/trace_data_vmtable_vmtable.csv.gz) (~155 MB) é baixado para `data/raw/` e a instância é gerada. Isso vale para:

```bash
make instancias NS="50 300 5000"                           # só gera as que faltam
uv run bpp-dataset --n 300                                 # o mesmo, direto
uv run bpp-solvers data/instancias/instancia_300_vms.csv   # o runner gera se faltar
```

## Estrutura

| Caminho | Conteúdo |
|---|---|
| `src/bpp/dados/` | `azure.py` (download do dataset e geração das instâncias), `sintetico.py` (instâncias sintéticas) |
| `src/bpp/modelo/` | Leitura da instância, limitantes, classe base `Solver` e os modelos Gurobi/SCIP — ver [`docs/modelo.md`](docs/modelo.md) |
| `src/bpp/experimentos/` | `rodar.py` (roda os solvers e grava CSV/JSON), `tabela.py` (tabelas Markdown/LaTeX), `validador.py` (validação das soluções JSON), `slurm.py` (submissão SLURM e junção dos CSVs) |
| `data/raw/` | Dataset bruto baixado (não versionado) |
| `data/instancias/` | Instâncias reais `instancia_<N>_vms.csv` |
| `data/instancias/teste/` | Instâncias sintéticas, só para testar o código |
| `resultados/` | `solvers.csv` (resultados principais), `reforcos.csv`, `s_ingenuo.csv` e `solucoes/` (JSONs das soluções; `reforcos/` e `s_ingenuo/` em subpastas) |
| `resultados/teste/` | Resultados das instâncias sintéticas |
| `tests/` | Testes (`make test`) |
| `scripts/slurm.sbatch` | Job SLURM genérico usado por `make slurm` e `make slurm-experimentos` |
| `docs/cluster.md` | Execução no cluster: um job por execução, estimativa de tempo/memória |
| `docs/modelo.md` | Modelo, decisões de implementação e formato da saída |

Comandos instalados no ambiente (`uv run <comando> --help`): `bpp-dataset`, `bpp-sintetico`, `bpp-solvers`, `bpp-tabela`, `bpp-validador`, `bpp-slurm`, `bpp-juntar`.

## Alvos do Makefile

| Alvo | O que faz |
|---|---|
| `setup` | `uv sync` |
| `dados` / `instancias` | Baixa o dataset / gera as instâncias de `NS` que faltam |
| `solvers` | Experimento principal (`NS` × `SOLVERS`, `REFORCOS`, `TEMPO`, `THREADS`) |
| `reforcos` | As 4 combinações de reforços R1/R2 em todas as instâncias de `NS` (ou `NS_REFORCOS`) |
| `s-ingenuo` | Comparação com S_k = n em todas as instâncias de `NS` (ou `NS_INGENUO`) — ~3n² variáveis, ver aviso abaixo |
| `experimentos` | `solvers` + `reforcos` + `s-ingenuo` |
| `sinteticas` / `teste-sintetico` | Gera / roda as instâncias sintéticas |
| `tabela` | Tabela a partir de `SAIDA` (`TABELA_ARGS`, padrão `--latex --reforcos nenhum`) |
| `validador` | Valida os JSONs de solução contra as instâncias (`JSONS`, padrão `resultados/solucoes` com subpastas) |
| `test` | pytest |
| `slurm-experimentos` | `experimentos` no SLURM, um job por execução + junção dos CSVs |
| `juntar` | Junta manualmente os CSVs parciais de uma `RODADA` |
| `slurm` | Submete `make $(SLURM_ALVO)` como um único job SLURM |
| `clean` / `clean-dados` | Remove `.venv` e caches / remove `data/raw` |

Cada execução dos solvers **acrescenta** linhas ao CSV de saída (não sobrescreve).

`make experimentos` com os padrões são 60 execuções (10 + 40 + 10), até ~10 h com `TEMPO=600`.
O `s-ingenuo` cria 3n² + 3n variáveis (12 milhões em 2000 VMs): exige muita RAM e tempo só
para montar o modelo. Para limitar: `make s-ingenuo NS_INGENUO="50 100 500"`.

## Cluster (SLURM)

```bash
make slurm-experimentos SLURM_DRY=1        # mostra o plano: 1 job por execução, tempo e memória estimados
make slurm-experimentos SLURM_PARTICAO=cpu # submete tudo do relatório em paralelo e junta os CSVs no fim
make slurm SLURM_ALVO=reforcos             # alternativa: um único job rodando `make reforcos` em sequência
```

`slurm-experimentos` submete cada execução (instância × solver × reforço) como job independente, com `--time` e `--mem` estimados pelo tamanho do modelo, e um job final que junta os CSVs parciais em `resultados/`. Detalhes, estimativas e ressubmissão: [`docs/cluster.md`](docs/cluster.md). Logs em `logs/`. Em clusters com cota pequena na home, aponte `UV_CACHE_DIR` e `UV_PROJECT_ENVIRONMENT` para o scratch no `config.mk`. Sem SLURM, basta rodar `make <alvo>` dentro do job do escalonador.

**Gurobi**: o `gurobipy` instalado traz licença restrita (só instâncias pequenas). Para 100+ VMs é preciso a licença acadêmica (ver [`docs/modelo.md`](docs/modelo.md#instalação)); no cluster, defina `GRB_LICENSE_FILE` se o `gurobi.lic` não estiver na home.

#### Referências

Dataset obtido de *Azure Public Dataset* no GitHub, link:

https://github.com/Azure/AzurePublicDataset/tree/master

Trabalho original:

> E. Cortez, A. Bonde, A. Muzio, M. Russinovich, M. Fontoura, and R. Bianchini, *"Resource Central: Understanding and Predicting Workloads for Improved Resource Management in Large Cloud Platforms,"* in Proceedings of the 26th Symposium on Operating Systems Principles (SOSP '17), 2017.
