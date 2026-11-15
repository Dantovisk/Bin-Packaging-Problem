"""Valida soluções em JSON (formato de resultados/solucoes/) contra as instâncias CSV.

O CSV de cada JSON é achado pelo campo `instancia` em data/instancias/ e
data/instancias/teste/.

Serve para qualquer método (Gurobi, SCIP, SA, guloso...). As checagens não usam o
código dos solvers, para a validação ser independente do que está sendo validado.

    bpp-validador                                          # resultados/solucoes/ (com subpastas)
    bpp-validador resultados/solucoes/instancia_50_vms__scip.json
    bpp-validador resultados/solucoes/reforcos resultados/teste/solucoes

Sai com código 1 se alguma solução for inválida.
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from bpp.dados.azure import RAW_DIR, garantir_csv
from bpp.modelo.instancia import Instancia, ler_csv

TOL = 1e-6
PADRAO_JSONS = "resultados/solucoes"
INST_DIRS = ["data/instancias", "data/instancias/teste"]


@dataclass
class Relatorio:
    arquivo: str
    instancia: str = ""
    metodo: str = ""
    custo_declarado: float | None = None
    custo_calculado: float | None = None
    servidores: int = 0
    erros: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    @property
    def valida(self) -> bool:
        return not self.erros


def validar(sol: dict, inst: Instancia, arquivo: str = "") -> Relatorio:
    rel = Relatorio(arquivo, str(sol.get("instancia", "")), str(sol.get("metodo", "")))
    servidores = sol.get("servidores")
    if not isinstance(servidores, list):
        rel.erros.append("campo 'servidores' ausente ou não é uma lista")
        return rel
    rel.servidores = len(servidores)
    tipos = {t.k: t for t in inst.tipos}

    # multiplicidade por id: um id repetido no CSV deve aparecer o mesmo nº de vezes
    esperado = Counter(inst.ids)
    atributos: dict[str, tuple[float, float]] = {}
    for i, vm in enumerate(inst.ids):
        atributos.setdefault(vm, (inst.cpu[i], inst.ram[i]))
    alocado: Counter[str] = Counter()

    custo = 0.0
    for pos, s in enumerate(servidores):
        nome = f"servidor {s.get('id', pos)!s}" if isinstance(s, dict) else f"servidor {pos}"
        if not isinstance(s, dict) or not isinstance(s.get("vms"), list):
            rel.erros.append(f"{nome}: sem lista 'vms'")
            continue
        t = tipos.get(s.get("tipo"))
        if t is None:
            rel.erros.append(f"{nome}: tipo {s.get('tipo')!r} inválido (válidos: {sorted(tipos)})")
            continue
        custo += t.custo
        if "nome_tipo" in s and s["nome_tipo"] != t.nome:
            rel.avisos.append(f"{nome}: nome_tipo {s['nome_tipo']!r} != {t.nome!r} (tipo {t.k})")
        if not s["vms"]:
            rel.avisos.append(f"{nome}: ligado sem VMs (custo {t.custo} desnecessário)")

        cpu = ram = 0.0
        for vm in map(str, s["vms"]):
            alocado[vm] += 1
            if vm not in atributos:
                rel.erros.append(f"{nome}: VM {vm} não existe na instância")
                continue
            cpu += atributos[vm][0]
            ram += atributos[vm][1]
        if cpu > t.cpu + TOL:
            rel.erros.append(f"{nome} (tipo {t.k}): CPU {cpu:g} > {t.cpu:g}")
        if ram > t.ram + TOL:
            rel.erros.append(f"{nome} (tipo {t.k}): RAM {ram:g} > {t.ram:g}")

    for vm, n in esperado.items():
        if alocado[vm] != n:
            rel.erros.append(f"VM {vm} alocada {alocado[vm]} vez(es), esperado {n}")

    rel.custo_calculado = custo
    declarado = sol.get("custo")
    if declarado is None:
        rel.avisos.append("custo não declarado")
    else:
        rel.custo_declarado = float(declarado)
        if abs(rel.custo_declarado - custo) > TOL * max(1.0, abs(custo)):
            rel.erros.append(f"custo declarado {rel.custo_declarado:g} != calculado {custo:g}")
    return rel


def achar_instancia(nome: str, dirs: list[str], raw_dir: str | Path = RAW_DIR) -> Path:
    for d in dirs:
        caminho = Path(d) / f"{nome}.csv"
        if caminho.exists():
            return caminho
    # instância real ausente: gera a partir do dataset, como o bpp-solvers
    caminho = garantir_csv(Path(dirs[0]) / f"{nome}.csv", raw_dir)
    if not caminho.exists():
        raise FileNotFoundError(f"instância {nome!r} não encontrada em {dirs}")
    return caminho


def expandir(entradas: list[str]) -> list[str]:
    arquivos = []
    for e in entradas:
        if Path(e).is_dir():
            arquivos += sorted(map(str, Path(e).rglob("*.json")))
        else:
            arquivos += sorted(glob.glob(e)) or [e]
    return list(dict.fromkeys(arquivos))


def validar_arquivo(arquivo: str, a: argparse.Namespace,
                    cache: dict[str, Instancia]) -> Relatorio:
    try:
        with open(arquivo, encoding="utf-8") as f:
            sol = json.load(f)
        caminho = str(achar_instancia(str(sol.get("instancia", "")), a.inst_dir, a.raw_dir))
        if caminho not in cache:
            cache[caminho] = ler_csv(caminho, col_id=a.col_id, col_cpu=a.col_cpu,
                                     col_ram=a.col_ram)
        return validar(sol, cache[caminho], arquivo)
    except (OSError, ValueError, KeyError) as e:
        return Relatorio(arquivo, erros=[f"{type(e).__name__}: {e}"])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("jsons", nargs="*", default=[PADRAO_JSONS],
                    help=f"JSONs, pastas (recursivo) ou curingas (padrão: {PADRAO_JSONS})")
    ap.add_argument("--inst-dir", nargs="+", default=INST_DIRS,
                    help="pastas onde procurar <instancia>.csv")
    ap.add_argument("--raw-dir", default=str(RAW_DIR))
    ap.add_argument("--col-id")
    ap.add_argument("--col-cpu")
    ap.add_argument("--col-ram")
    ap.add_argument("--max-erros", type=int, default=5,
                    help="erros mostrados por arquivo (0 = todos)")
    a = ap.parse_args()

    arquivos = expandir(a.jsons)
    if not arquivos:
        sys.exit("nenhum JSON encontrado")
    cache: dict[str, Instancia] = {}
    invalidas = 0
    for arq in arquivos:
        rel = validar_arquivo(arq, a, cache)
        invalidas += not rel.valida
        custo = "-" if rel.custo_calculado is None else f"{rel.custo_calculado:g}"
        print(f"{'OK      ' if rel.valida else 'INVÁLIDA'} {arq}  "
              f"[{rel.instancia} {rel.metodo}] servidores={rel.servidores} custo={custo}")
        lim = a.max_erros or None
        for msg in rel.erros[:lim]:
            print(f"    erro:  {msg}")
        if lim and len(rel.erros) > lim:
            print(f"    ... mais {len(rel.erros) - lim} erro(s)")
        for msg in rel.avisos[:lim]:
            print(f"    aviso: {msg}")
    print(f"{len(arquivos) - invalidas}/{len(arquivos)} válidas")
    sys.exit(1 if invalidas else 0)


if __name__ == "__main__":
    main()
