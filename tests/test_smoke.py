import gzip
from pathlib import Path

import pytest

from bpp.dados.azure import COLUNAS, AzureVMTable, garantir_csv
from bpp.modelo.comum import Opcoes
from bpp.modelo.instancia import ler_csv
from bpp.modelo.limitantes import (calcular_S, custo, limitantes_inferiores,
                                   melhor_guloso, verificar)
from bpp.modelo.solver import SOLVERS, obter_solver

RAIZ = Path(__file__).resolve().parents[1]
TESTE_12 = RAIZ / "data/instancias/teste/teste_12_1.csv"


@pytest.fixture(scope="module")
def inst():
    return ler_csv(str(TESTE_12))


def test_guloso_e_limitantes(inst):
    sol = melhor_guloso(inst)
    assert verificar(inst, sol) == []
    lbs = limitantes_inferiores(inst)
    assert lbs["lb1"] <= lbs["lb2"] + 1e-6 <= lbs["lb3"] + 2e-6 <= custo(inst, sol) + 3e-6


@pytest.mark.parametrize("nome", SOLVERS)
def test_solver_otimo(inst, nome):
    sol0 = melhor_guloso(inst)
    S = calcular_S(inst, custo(inst, sol0))
    res = obter_solver(nome).resolver(inst, S, Opcoes(tempo_limite=30), sol0)
    assert res.status == "otimo"
    assert verificar(inst, res.solucao) == []
    assert res.custo == pytest.approx(custo(inst, res.solucao))
    assert res.custo >= limitantes_inferiores(inst)["lb3"] - 1e-6


def test_particionar_sem_rede(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    linhas = [f"vm{i},s,d,0,1,9,5,8,Interactive,{i % 4 + 1},{1.75 * (i + 1)}" for i in range(10)]
    with gzip.open(raw / "trace_data_vmtable_vmtable.csv.gz", "wt") as f:
        f.write("\n".join(linhas) + "\n")

    ds = AzureVMTable(raw, tmp_path / "inst", url="http://invalido.local/nao-baixar")
    destino = ds.garantir_instancia(4)
    assert destino.read_text().splitlines() == [
        "vmid,vmcorecount,vmmemory", "vm0,1,1.75", "vm1,2,3.5", "vm2,3,5.25", "vm3,4,7.0"]
    assert len(COLUNAS) == 11

    # caminho no padrão instancia_<N>_vms.csv ausente é gerado sozinho
    assert garantir_csv(tmp_path / "inst" / "instancia_3_vms.csv", raw).exists()
    # fora do padrão: devolvido como veio
    assert not garantir_csv(tmp_path / "outro.csv", raw).exists()
