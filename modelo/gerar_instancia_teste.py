"""Gera instâncias SINTÉTICAS só para testar o código dos solvers.

Usam faixas de tamanho de VM do Azure (núcleos 2/4/8/24/>24, RAM 2/4/8/32/64/>64 GB),
mas NÃO são o dataset real: as N primeiras linhas do vmtable têm valores exatos e poucos
perfis (ex.: 1 núcleo/1,75 GB, 2/3,5, 8/56). Os resultados do relatório devem usar os
CSVs do particao_dataset.py.

    python modelo/gerar_instancia_teste.py --n 50 100 500 --pasta instancias/teste
"""

import argparse
import csv
import os
import random

# (núcleos, RAM, peso) — combinações típicas de tamanhos de VM
PERFIS = [
    ("2", "2", 10), ("2", "4", 30), ("2", "8", 12),
    ("4", "8", 15), ("4", "32", 6),
    ("8", "32", 10), ("8", "64", 4),
    ("24", "64", 5), ("24", ">64", 3),
    (">24", ">64", 2),
]


def gerar(n: int, semente: int) -> list[tuple[str, str, str]]:
    rnd = random.Random(semente)
    perfis = [(c, r) for c, r, _ in PERFIS]
    pesos = [w for _, _, w in PERFIS]
    return [(f"vm{i:04d}", *rnd.choices(perfis, pesos)[0]) for i in range(n)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, nargs="+", default=[50, 100, 500])
    ap.add_argument("--repeticoes", type=int, default=1)
    ap.add_argument("--pasta", default="instancias/teste")
    a = ap.parse_args()
    os.makedirs(a.pasta, exist_ok=True)
    for n in a.n:
        for r in range(1, a.repeticoes + 1):
            caminho = os.path.join(a.pasta, f"teste_{n}_{r}.csv")
            with open(caminho, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["vm_id", "vmcorecountbucket", "vmmemorybucket"])
                w.writerows(gerar(n, semente=1000 * n + r))
            print(caminho)


if __name__ == "__main__":
    main()
