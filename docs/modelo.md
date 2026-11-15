# Modelo — Solução via solvers (Gurobi e SCIP)

Implementação do modelo do relatório (variáveis `x_ijk`, `y_jk`) nos dois solvers,
lendo as instâncias de `data/instancias/`.

| Arquivo | O que faz |
|---|---|
| `src/bpp/modelo/instancia.py` | Lê o CSV da instância e guarda os 3 tipos de servidor (CPU, RAM, custo) |
| `src/bpp/modelo/limitantes.py` | Guloso FFD adaptado (UB), limitantes inferiores LB1 ≤ LB2 ≤ LB3 (seção 3.1 do relatório), cálculo de `S_k = ⌊UB/p_k⌋` |
| `src/bpp/modelo/comum.py` | Opções, formato do resultado, utilitários comuns aos dois modelos |
| `src/bpp/modelo/solver.py` | Classe base `Solver`: monta os índices do modelo, warm start, escala, gap e status; `obter_solver(nome)` |
| `src/bpp/modelo/gurobi.py` | `GurobiSolver` (`gurobipy`) |
| `src/bpp/modelo/scip.py` | `ScipSolver` (`pyscipopt`) |
| `src/bpp/experimentos/rodar.py` | `bpp-solvers`: roda os solvers e grava `resultados/solvers.csv` + JSONs das soluções |
| `src/bpp/experimentos/tabela.py` | `bpp-tabela`: monta a tabela da seção (Markdown ou `--latex`) a partir do CSV |
| `src/bpp/dados/azure.py` | `bpp-dataset`: baixa o vmtable e gera `instancia_<N>_vms.csv` |
| `src/bpp/dados/sintetico.py` | `bpp-sintetico`: instâncias **sintéticas** só para testar o código (não usar no relatório) |

Para usar outro solver, basta criar uma subclasse de `Solver` que implemente
`_otimizar(dados, op)` e registrá-la em `obter_solver`.

## Instalação

```bash
make setup     # ou: uv sync   (pandas, gurobipy, pyscipopt)
```

- **SCIP**: o `pyscipopt` já vem com o SCIP, não precisa de licença.
- **Gurobi**: o pacote traz uma licença restrita (máx. 2000 variáveis e 2000
  restrições), que só roda as instâncias de 50 VMs. Para as de 100 e 500 é preciso a
  **licença acadêmica**: criar conta em gurobi.com com o e-mail da USP e gerar uma
  "Named-User Academic License" (rodar `grbgetkey <chave>` **conectado à rede da USP**
  ou VPN) ou uma "Academic WLS License" (baixar o `gurobi.lic`). O arquivo `gurobi.lic`
  fica na pasta do usuário e o `gurobipy` o encontra sozinho (ou via `GRB_LICENSE_FILE`).

## Instâncias

`data/instancias/instancia_<N>_vms.csv`: colunas `vmid`, `vmcorecount`, `vmmemory`; as N
primeiras VMs do vmtable. São geradas por `bpp-dataset --n <N>` (ou `make instancias
NS="..."`), que baixa o dataset para `data/raw/` se ele ainda não estiver lá. O
`bpp-solvers` também gera sozinho uma instância nesse padrão de nome que não exista.

As de `data/instancias/teste/` são **sintéticas** (`bpp-sintetico`) e servem só para
testar o código.

## Como rodar

Sempre a partir da raiz do repositório. Cada alvo do Makefile corresponde a um comando:

```bash
# experimento principal: instâncias reais, os dois solvers, 600 s, 1 thread
make solvers
uv run bpp-solvers data/instancias/instancia_{50,100,500,1000,2000}_vms.csv --tempo 600

# tabela de resultados da seção 4 (só a configuração sem reforços), pronta para o .tex
make tabela
uv run bpp-tabela resultados/solvers.csv --latex --reforcos nenhum

# teste dos reforços (as 4 combinações) em todas as instâncias (50 a 2000)
make reforcos                       # ou NS_REFORCOS="100 500" para restringir

# comparação com S_k = n em todas as instâncias (mostra por que a redução é necessária)
make s-ingenuo                      # ou NS_INGENUO="50 100" para restringir

# teste rápido do código com as instâncias sintéticas (resultados separados)
make teste-sintetico
```

Opções úteis do `bpp-solvers` (no Makefile, via `EXTRA_ARGS`): `--solver gurobi scip`,
`--tempo`, `--threads`, `--reforcos {nenhum,xy,simetria,ambos,todos}`,
`--sem-warm-start`, `--escala-custo`, `--semente`, `--saida`, `--solucoes`,
`--col-cpu/--col-ram/--col-id` (se o CSV usar outros nomes de coluna), `--verbose`
(log do solver).

Cada execução **acrescenta** uma linha ao CSV de saída (não sobrescreve).

## Decisões de implementação

- **S_k = ⌊UB/p_k⌋**, com UB = custo do melhor guloso. Também limitado ao número de VMs
  que cabem no tipo k. Não corta o ótimo (ver `limitantes.py`).
- **Warm start**: a solução gulosa entra como incumbente inicial nos dois solvers
  (desligar com `--sem-warm-start`). Assim todo resultado com limite de tempo tem pelo
  menos uma solução viável.
- `x_ijk` só é criada se a VM i cabe sozinha no tipo k.
- **Comparação justa**: mesmo limite de tempo, `--threads 1` por padrão (o SCIP é
  sequencial), mesma tolerância de gap (1e-4) e a coluna `maquina` registra onde rodou.
- **Gap de otimalidade** calculado igual para os dois: `(custo − bound) / custo`. A coluna
  `gap_lb3` traz também o gap na convenção da seção 3.1 do relatório, `(z − LB3)/LB3`,
  para comparar com o SA nas instâncias que o solver não fecha.
- **Bound arredondado**: como 100, 140 e 120 são múltiplos de 20, todo custo viável é
  múltiplo de 20 e o bound do solver pode subir ao próximo múltiplo (colunas
  `bound_arred` e `gap_arred`). Ex.: bound 3790,6 → 3800.
- `--escala-custo` divide os custos por 20 na função objetivo (modelo equivalente). Nos
  testes não mudou nada no SCIP, por isso fica desligado por padrão.
- O leitor reconhece as colunas `vmcorecount` e `vmmemory` do vmtable (as que o
  relatório usa) e vários outros nomes; se o particionador usar outros, `--col-cpu`,
  `--col-ram` e `--col-id`. Se aparecerem faixas abertas (`>24`, `>64`), elas viram
  32 e 128 em `instancia.FAIXAS_ABERTAS` — confirmar com a Pessoa 1. (Nas 500 primeiras
  linhas do vmtable não aparece nenhuma: os valores são exatos, como 1 núcleo/1,75 GB e
  8 núcleos/56 GB.)

## Saída

`resultados/solvers.csv`: instancia, n_vms, metodo, reforcos, status, custo, bound, gap,
bound_arred, gap_arred, tempo, servidores_tipo1/2/3, servidores_vazios, ub_guloso, lb1/lb2/lb3, gap_lb3, S_1/S_2/S_3, n_vars,
n_restricoes, nos, tempo_limite, threads, warm_start, escala_custo, valida, mensagem, maquina, data.

Status: `otimo`, `limite_tempo` (tem solução, não provou otimalidade), `sem_solucao`,
`inviavel`, `erro` (ex.: licença restrita do Gurobi).

`resultados/solucoes/<instancia>__<metodo>.json`, no formato da seção 3.1 do relatório
(lista de servidores abertos com o tipo k e as VMs alocadas), para o `validador.py`:

```json
{"instancia": "instancia_30_vms", "metodo": "gurobi", "status": "otimo", "custo": 280.0,
 "servidores": [{"id": "t2_0", "tipo": 2, "nome_tipo": "Memória",
                 "vms": ["1XiU+KpvIa3T1XP8kk3ZY71Of03+ogFL5Pag9Mc2jBuh0YqeW0Zcb9lepKLdPEDg", "..."]}]}
```
