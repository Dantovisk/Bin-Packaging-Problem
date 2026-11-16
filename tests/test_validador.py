import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from bpp.experimentos.rodar import salvar_solucao_json
from bpp.experimentos.validador import validar
from bpp.modelo.comum import Opcoes
from bpp.modelo.instancia import ler_csv
from bpp.modelo.limitantes import calcular_S, custo, melhor_guloso
from bpp.modelo.solver import obter_solver

RAIZ = Path(__file__).resolve().parents[1]
TESTE_12 = RAIZ / "data/instancias/teste/teste_12_1.csv"


@pytest.fixture(scope="module")
def inst():
    return ler_csv(str(TESTE_12))


@pytest.fixture(scope="module")
def sol_json(inst, tmp_path_factory):
    sol0 = melhor_guloso(inst)
    res = obter_solver("scip").resolver(inst, calcular_S(inst, custo(inst, sol0)),
                                        Opcoes(tempo_limite=30), sol0)
    caminho = salvar_solucao_json(inst, "scip", res, str(tmp_path_factory.mktemp("sol")))
    with open(caminho) as f:
        return json.load(f), caminho


def test_solucao_do_solver_valida(inst, sol_json):
    rel = validar(sol_json[0], inst)
    assert rel.valida, rel.erros
    assert rel.custo_calculado == rel.custo_declarado


def _alterar(sol, f):
    s = copy.deepcopy(sol)
    f(s)
    return s


@pytest.mark.parametrize("alteracao, trecho", [
    (lambda s: s["servidores"][0]["vms"].pop(), "alocada 0 vez"),
    (lambda s: s["servidores"][0]["vms"].append(s["servidores"][1]["vms"][0]), "alocada 2 vez"),
    (lambda s: s["servidores"][0]["vms"].append("vm_inexistente"), "não existe"),
    (lambda s: s["servidores"][0].update(tipo=9), "tipo 9 inválido"),
    (lambda s: s.update(custo=s["custo"] - 20), "custo declarado"),
    (lambda s: s.pop("servidores"), "servidores"),
])
def test_detecta_erros(inst, sol_json, alteracao, trecho):
    rel = validar(_alterar(sol_json[0], alteracao), inst)
    assert not rel.valida
    assert any(trecho in e for e in rel.erros), rel.erros


def test_detecta_capacidade(inst, sol_json):
    def juntar_tudo(s):
        todas = [vm for srv in s["servidores"] for vm in srv["vms"]]
        s["servidores"] = [{"id": "t1_0", "tipo": 1, "vms": todas}]
        s["custo"] = 100
    rel = validar(_alterar(sol_json[0], juntar_tudo), inst)
    assert any("CPU" in e or "RAM" in e for e in rel.erros), rel.erros


def test_servidor_vazio_e_aviso(inst, sol_json):
    def vazio(s):
        s["servidores"].append({"id": "extra", "tipo": 1, "vms": []})
        s["custo"] += 100
    rel = validar(_alterar(sol_json[0], vazio), inst)
    assert rel.valida and any("sem VMs" in a for a in rel.avisos)


def test_cli_codigo_de_saida(inst, sol_json, tmp_path):
    ruim = tmp_path / "ruim.json"
    ruim.write_text(json.dumps(_alterar(sol_json[0], lambda s: s.update(custo=1))))
    # o CSV vem do campo "instancia" (teste_12_1 -> data/instancias/teste/)
    cmd = [sys.executable, "-m", "bpp.experimentos.validador"]
    def rodar(arq):
        return subprocess.run(cmd + [arq], capture_output=True, cwd=RAIZ).returncode
    assert rodar(sol_json[1]) == 0
    assert rodar(str(ruim)) == 1
    assert rodar(str(Path(sol_json[1]).parent)) == 0  # pasta
