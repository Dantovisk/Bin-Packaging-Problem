# modelo/ — Solução via solvers (Gurobi e SCIP)

Implementação do modelo do relatório (variáveis `x_ijk`, `y_jk`) nos dois solvers,
lendo os CSVs do `particao_dataset.py`.

| Arquivo | O que faz |
|---|---|
| `instancia.py` | Lê o CSV da instância e guarda os 3 tipos de servidor (CPU, RAM, custo) |
| `limitantes.py` | Guloso FFD adaptado (UB), limitantes inferiores LB1 ≤ LB2 ≤ LB3 (seção 3.1 do relatório), cálculo de `S_k = ⌊UB/p_k⌋` |
| `modelo_comum.py` | Opções, formato do resultado, partes comuns aos dois modelos |
| `modelo_gurobi.py` | Modelo no Gurobi (`gurobipy`) |
| `modelo_scip.py` | Modelo no SCIP (`pyscipopt`) |
| `rodar_solvers.py` | Roda os solvers nas instâncias e grava `resultados/solvers.csv` + JSONs das soluções |
| `tabela_solvers.py` | Monta a tabela da seção (Markdown ou `--latex`) a partir do CSV |
| `gerar_instancia_teste.py` | Instâncias **sintéticas** só para testar o código (não usar no relatório) |

## Instalação

```bash
pip install -r requirements.txt     # na raiz do repositório (pandas, gurobipy, pyscipopt)
```

- **SCIP**: o `pyscipopt` já vem com o SCIP, não precisa de licença.
- **Gurobi**: o `pip install` traz uma licença restrita (máx. 2000 variáveis e 2000
  restrições), que só roda as instâncias de 50 VMs. Para as de 100 e 500 é preciso a
  **licença acadêmica**: criar conta em gurobi.com com o e-mail da USP e gerar uma
  "Named-User Academic License" (rodar `grbgetkey <chave>` **conectado à rede da USP**
  ou VPN) ou uma "Academic WLS License" (baixar o `gurobi.lic`). O arquivo `gurobi.lic`
  fica na pasta do usuário e o `gurobipy` o encontra sozinho.

## Instâncias

As instâncias são os CSVs `instancias/instancia_<N>_vms.csv` gravados pelo
`particao_dataset.py` (colunas `vmid`, `vmcorecount`, `vmmemory`; as N primeiras VMs do
vmtable). Para gerar as de 50, 100, 500, 1000 e 2000 VMs, trocar `N_AMOSTRAS` no script e rodá-lo uma
vez para cada valor.

As de `instancias/teste/` são **sintéticas** (`gerar_instancia_teste.py`) e servem só para
testar o código.

## Como rodar

Sempre a partir da raiz do repositório.

```bash
# experimento principal: instâncias reais, os dois solvers, 600 s, 1 thread
python modelo/rodar_solvers.py instancias/instancia_50_vms.csv instancias/instancia_100_vms.csv instancias/instancia_500_vms.csv instancias/instancia_1000_vms.csv instancias/instancia_2000_vms.csv --tempo 600

# tabela de resultados da seção 4 (só a configuração sem reforços), pronta para o .tex
python modelo/tabela_solvers.py resultados/solvers.csv --latex --reforcos nenhum

# teste dos reforços (as 4 combinações) nas instâncias de 100 e 500 VMs
python modelo/rodar_solvers.py instancias/instancia_100_vms.csv instancias/instancia_500_vms.csv --reforcos todos --tempo 600 --saida resultados/reforcos.csv --solucoes ""

# só R2 (a melhor configuração) nas instâncias de 1000 e 2000 VMs
python modelo/rodar_solvers.py instancias/instancia_1000_vms.csv instancias/instancia_2000_vms.csv --reforcos simetria --tempo 600 --saida resultados/reforcos.csv --solucoes ""

# comparação com S_k = n (mostra por que a redução é necessária)
python modelo/rodar_solvers.py instancias/instancia_50_vms.csv instancias/instancia_100_vms.csv --s-ingenuo --tempo 600 --saida resultados/s_ingenuo.csv --solucoes ""

# teste rápido do código com as instâncias sintéticas (resultados separados)
python modelo/rodar_solvers.py instancias/teste/*.csv --tempo 60 --saida resultados/teste/teste_sintetico.csv --solucoes resultados/teste/solucoes
```

Opções úteis: `--solver gurobi scip`, `--tempo`, `--threads`, `--reforcos
{nenhum,xy,simetria,ambos,todos}`, `--sem-warm-start`, `--saida`, `--solucoes`,
`--col-cpu/--col-ram/--col-id` (se o particionador usar outros nomes de coluna),
`--verbose` (log do solver).

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
