# Bin Packing Problem
 Trabalho realizado para a disciplina de Programação Matemática, resolveldo uma aplicação do problema do empacotamento, relacionado à alocação de máquinas virtuais.

## Dataset

Rodar o arquivo particao_dataset.py, que limpará o dataset "trace_data_vmtable_vmtable.csv.gz", e salvará as primeiras N amostras em um csv simplificado na pasta `instancias/`.
Obter arquivo aqui: https://github.com/Azure/AzurePublicDataset/releases/download/dataset-v1/trace_data_vmtable_vmtable.csv.gz

## Estrutura

| Caminho | Conteúdo |
|---|---|
| `particao_dataset.py` | Particionador do dataset (gera `instancias/instancia_<N>_vms.csv`) |
| `instancias/` | Instâncias reais `instancia_<N>_vms.csv` |
| `instancias/teste/` | Instâncias sintéticas, só para testar o código |
| `modelo/` | Solução via solvers (Gurobi e SCIP) — ver [`modelo/README.md`](modelo/README.md) |
| `resultados/` | `solvers.csv` (resultados principais), `reforcos.csv`, `s_ingenuo.csv` e `solucoes/` (JSONs das soluções) |
| `resultados/teste/` | Resultados das instâncias sintéticas |
| `relatorio/` | Seções do relatório em LaTeX |

## Solução via solvers

```bash
pip install -r requirements.txt
python modelo/rodar_solvers.py instancias/instancia_50_vms.csv instancias/instancia_100_vms.csv instancias/instancia_500_vms.csv instancias/instancia_1000_vms.csv instancias/instancia_2000_vms.csv --tempo 600
python modelo/tabela_solvers.py resultados/solvers.csv --latex --reforcos nenhum
```

#### Referências

Dataset obtido de *Azure Public Dataset* no GitHub, link: 

https://github.com/Azure/AzurePublicDataset/tree/master

Trabalho original:

> E. Cortez, A. Bonde, A. Muzio, M. Russinovich, M. Fontoura, and R. Bianchini, *"Resource Central: Understanding and Predicting Workloads for Improved Resource Management in Large Cloud Platforms,"* in Proceedings of the 26th Symposium on Operating Systems Principles (SOSP '17), 2017.

