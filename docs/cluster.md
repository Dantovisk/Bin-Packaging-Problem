# Execução no cluster (SLURM)

Dois modos:

| Alvo | Como roda | Quando usar |
|---|---|---|
| `make slurm-experimentos` | **1 job por execução** (60 com os padrões) + 1 job que junta os CSVs | Rodar tudo do relatório em paralelo |
| `make slurm SLURM_ALVO=<alvo>` | 1 job que roda `make <alvo>` em sequência | Um alvo isolado, sem pressa |

## `make slurm-experimentos`

Faz o mesmo que `make experimentos` (`solvers` + `reforcos` + `s-ingenuo`), mas cada
combinação (instância × solver × reforço) vira um job independente:

1. No nó de login: `make setup` e `make instancias` (venv e instâncias prontos antes
   dos jobs, para não haver 60 `uv sync` simultâneos nem downloads concorrentes).
2. `bpp-slurm` calcula o nº de variáveis de cada execução (sem montar o modelo) e
   estima `--time` e `--mem` (abaixo). Submete um `sbatch` por execução.
3. Cada job grava um CSV próprio em `resultados/parcial/<RODADA>/<grupo>__<n>__<solver>__<reforço>.csv`
   (os JSONs do grupo `solvers` vão para `resultados/solucoes/`, um arquivo por execução).
4. Um job final (`--dependency=afterany`) roda `bpp-juntar`: acrescenta os parciais em
   `resultados/solvers.csv`, `reforcos.csv` e `s_ingenuo.csv`, move cada parcial para
   `juntados/` e lista as execuções que não produziram resultado.

```bash
make slurm-experimentos SLURM_DRY=1          # só mostra o plano e os sbatch
make slurm-experimentos SLURM_PARTICAO=cpu SLURM_ARGS="--account=meu_grupo"
```

Logs em `logs/<RODADA>/`, plano (job, tempo, memória, variáveis) em
`resultados/parcial/<RODADA>/plano.tsv`. `RODADA` é a data/hora da submissão se não
for informada.

**Ressubmissão.** Repetir com a mesma rodada só submete o que não tem resultado (job
morto por tempo, memória ou licença), e a nova junção não duplica linhas:

```bash
make slurm-experimentos RODADA=20261115-181500 SLURM_FATOR_MEM=4 SLURM_FOLGA=3
make juntar RODADA=20261115-181500           # junção manual, se o job de junção falhar
```

## Estimativa de tempo e memória por job

```
--time = TEMPO × SLURM_FOLGA + 50 µs × variáveis + SLURM_MARGEM
--mem  = max(SLURM_MEM_MIN, (600 MB + KB_var × variáveis) × SLURM_FATOR_MEM)
```

`KB_var` = 2,6 KB (4 KB com o reforço R1, que cria uma restrição por `x_ijk`).
Padrões: `SLURM_FOLGA=1.5`, `SLURM_MARGEM=300` s, `SLURM_FATOR_MEM=2`, `SLURM_MEM_MIN=2` GB.

De onde vêm os números (medidos com limite de 1 s, SCIP, que gasta mais memória que o Gurobi):

| Execução | Variáveis | Pico de RAM | Montagem do modelo |
|---|---|---|---|
| padrão, 500 VMs | 28.056 | 0,6 GB | 0,4 s |
| padrão, 2000 VMs | 228.114 | 0,85 GB | 2,7 s |
| padrão + R1/R2, 2000 VMs | 228.114 | 1,1 GB | 4,7 s |
| `s-ingenuo`, 100 VMs | 30.300 | 0,57 GB | 0,4 s |
| `s-ingenuo`, 500 VMs | 751.500 | 2,5 GB | 9,4 s |

- **Tempo**: o solver passa do limite (`resultados/solvers.csv`: SCIP em 2000 VMs levou
  761 s com limite de 600 s, +27%). Folga de 1,5× mais 5 min cobre isso e a leitura,
  guloso e limitantes. A parcela por variável (50 µs, ~4× a montagem medida) cobre o
  presolve dos modelos grandes.
- **Memória**: ~2,6 KB por variável na montagem; o fator 2 cobre a árvore de B&B e o LP.

Resultado com `TEMPO=600`:

| Execução | Variáveis | `--time` | `--mem` |
|---|---|---|---|
| todas de 50 a 1000 VMs (padrão e reforços) | ≤ 74.074 | ~20 min | 2 GB |
| 2000 VMs (padrão e reforços) | 228.114 | ~20 min | 3 GB |
| `s-ingenuo` 500 | 751.500 | ~21 min | 5 GB |
| `s-ingenuo` 1000 | ~3,0 M | ~23 min | 17 GB |
| `s-ingenuo` 2000 | ~12 M | 30 min | 61 GB |

`s-ingenuo` 1000 e 2000 são **extrapolações** (não cabem na máquina onde a medição foi
feita). Se o cluster não tiver nós com 61 GB, rode o `s-ingenuo` só até 1000:
`make slurm-experimentos NS_INGENUO="50 100 500 1000"`.

Com `TEMPO` maior, as estimativas acompanham (ex.: `TEMPO=3600` → ~1h35 por job).

## Gurobi no cluster

A "Named-User Academic License" fica presa à máquina onde o `grbgetkey` rodou e não
vale nos nós do cluster. Use a "Academic WLS License" (`gurobi.lic` com `WLSACCESSID`)
ou a licença do próprio cluster, apontando `GRB_LICENSE_FILE` no `config.mk`. A WLS
exige internet nos nós durante a otimização.

**Limite de sessões.** A WLS acadêmica permite **2 sessões simultâneas**, e cada processo
segura o token até 5 min (`WLSTokenDuration` mínimo) depois de fechar o ambiente. Por isso
o `slurm-experimentos` distribui os jobs Gurobi em `GUROBI_SIMULT` faixas (padrão 2):

- todos os jobs de uma faixa têm o mesmo nome (`bpp-gurobi-faixa1`, `bpp-gurobi-faixa2`)
  e `--dependency=singleton`, então o SLURM roda **um por vez** em cada faixa;
- ao terminar, o job Gurobi espera `GUROBI_ESPERA` s (padrão 300) antes de liberar a
  faixa, para o token do job anterior expirar antes do próximo pegar outro;
- o `--time` desses jobs inclui a espera (~25 min em vez de ~20).

Os jobs SCIP não são afetados e rodam todos em paralelo. Os 30 jobs Gurobi viram duas
filas de 15: no pior caso (todos no limite de 600 s) são ~15 × 15 min ≈ 3h45.

```bash
make slurm-experimentos GUROBI_SIMULT=4            # licença com mais sessões
make slurm-experimentos GUROBI_SIMULT=0            # sem limite (licença Site)
make slurm-experimentos GUROBI_ESPERA=0            # aceita exceder brevemente o limite
```

`singleton` vale por nome e usuário em todo o cluster: outros jobs seus com o nome
`bpp-gurobi-faixaN` (de outra rodada, por exemplo) entram na mesma fila. Um job que
nunca é escalonado (ex.: `s-ingenuo` 2000 pedindo 61 GB num cluster sem nós desse
tamanho) trava a sua faixa; cancele-o com `scancel`.
