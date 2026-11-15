import csv
from pathlib import Path

from bpp.experimentos.rodar import COLUNAS
from bpp.experimentos.slurm import (Execucao, juntar, n_variaveis, planejar, recursos)

RAIZ = Path(__file__).resolve().parents[1]
NS = [50, 100, 500, 1000, 2000]


def test_plano_cobre_experimentos():
    plano = planejar(NS, NS, NS, ["gurobi", "scip"])
    assert len(plano) == 10 + 40 + 10
    assert len({e.nome for e in plano}) == len(plano)


def test_variaveis_batem_com_resultados_commitados():
    # n_vars registrado em resultados/solvers.csv e s_ingenuo.csv
    inst = RAIZ / "data/instancias/instancia_100_vms.csv"
    assert n_variaveis(inst, ingenuo=False) == 2222
    assert n_variaveis(inst, ingenuo=True) == 30300


def test_recursos_acima_do_limite_do_solver():
    e = Execucao("solvers", 2000, "scip", "nenhum")
    seg, mem = recursos(e, 228114, tempo=600, folga=1.5, margem=300, fator_mem=2, mem_min_gb=2)
    assert seg > 600 and mem >= 2
    _, mem_ing = recursos(Execucao("s_ingenuo", 2000, "scip", "nenhum"), 12_006_000,
                          600, 1.5, 300, 2, 2)
    assert mem_ing > mem


def test_juntar_acrescenta_e_marca(tmp_path):
    rodada = tmp_path / "parcial" / "r"
    rodada.mkdir(parents=True)
    nomes = ["solvers__100__scip__nenhum", "solvers__50__scip__nenhum", "reforcos__50__scip__xy"]
    with open(rodada / "plano.tsv", "w") as f:
        f.write("nome\tjob\ttempo\tmem_gb\tvariaveis\n")
        for n in nomes + ["s_ingenuo__50__scip__nenhum"]:
            f.write(f"{n}\t1\t00:20:00\t2\t1\n")
    for n in nomes:
        with open(rodada / f"{n}.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUNAS)
            w.writeheader()
            w.writerow({"instancia": n, "n_vms": n.split("__")[1]})

    faltam = juntar(rodada, tmp_path)
    assert faltam == ["s_ingenuo__50__scip__nenhum"]
    with open(tmp_path / "solvers.csv") as f:
        assert [r["n_vms"] for r in csv.DictReader(f)] == ["50", "100"]
    assert not list(rodada.glob("*.csv"))

    juntar(rodada, tmp_path)  # de novo: não duplica
    with open(tmp_path / "solvers.csv") as f:
        assert len(list(csv.DictReader(f))) == 2
