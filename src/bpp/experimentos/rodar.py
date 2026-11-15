"""Roda Gurobi e/ou SCIP nas instâncias e registra os resultados em CSV.

Exemplos (a partir da raiz do repositório). Instâncias reais ausentes
(data/instancias/instancia_<N>_vms.csv) são geradas a partir do dataset, que é
baixado se preciso.

    # instâncias reais, os dois solvers, 600 s, sem reforços
    bpp-solvers data/instancias/instancia_50_vms.csv data/instancias/instancia_100_vms.csv

    # teste dos reforços na instância de 100 VMs, só SCIP
    bpp-solvers data/instancias/instancia_100_vms.csv --solver scip --reforcos todos

    # só uma instância, mostrando o log do solver
    bpp-solvers data/instancias/instancia_50_vms.csv --solver gurobi --verbose

A Pessoa 5 pode importar `rodar_instancia` direto no rodar_experimentos.py.
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import platform
import subprocess
import time
from datetime import datetime

from bpp.dados.azure import garantir_csv
from bpp.modelo.comum import (Opcoes, Resultado, arredondar_bound, calcular_gap,
                              mdc_custos)
from bpp.modelo.instancia import Instancia, ler_csv
from bpp.modelo.limitantes import (calcular_S, custo, limitantes_inferiores,
                                   melhor_guloso, verificar)
from bpp.modelo.solver import SOLVERS, obter_solver

CONFIGS = {
    "nenhum":   dict(reforco_xy=False, simetria=False),
    "xy":       dict(reforco_xy=True,  simetria=False),
    "simetria": dict(reforco_xy=False, simetria=True),
    "ambos":    dict(reforco_xy=True,  simetria=True),
}

COLUNAS = ["instancia", "n_vms", "metodo", "reforcos", "status", "custo", "bound", "gap",
           "bound_arred", "gap_arred",
           "tempo", "servidores_tipo1", "servidores_tipo2", "servidores_tipo3",
           "servidores_vazios", "ub_guloso", "lb1", "lb2", "lb3", "gap_lb3",
           "S_1", "S_2", "S_3", "n_vars",
           "n_restricoes", "nos", "tempo_limite", "threads", "warm_start", "escala_custo", "valida",
           "mensagem", "maquina", "data"]


def modelo_cpu() -> str:
    # platform.processor() volta vazio no Linux, onde rodam os experimentos
    try:
        if platform.system() == "Linux":
            with open("/proc/cpuinfo", encoding="utf-8") as f:
                for linha in f:
                    if linha.startswith("model name"):
                        return " ".join(linha.split(":", 1)[1].split())
        elif platform.system() == "Darwin":
            return subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                                  capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        pass
    return platform.processor() or platform.machine()


def maquina() -> str:
    return f"{platform.node()} | {modelo_cpu()} | " \
           f"{os.cpu_count()} cpus | {platform.system()} {platform.release()}"


def salvar_solucao_json(inst: Instancia, metodo: str, res: Resultado, pasta: str) -> str:
    """Formato proposto para o JSON comum (ajustar ao que for combinado com a Pessoa 2)."""
    os.makedirs(pasta, exist_ok=True)
    tipos = {t.k: t for t in inst.tipos}
    dados = {
        "instancia": inst.nome,
        "metodo": metodo,
        "status": res.status,
        "custo": res.custo,
        "servidores": [
            {"id": f"t{k}_{n}", "tipo": k, "nome_tipo": tipos[k].nome,
             "vms": [inst.ids[i] for i in lista]}
            for n, (k, lista) in enumerate(res.solucao or [])
        ],
    }
    caminho = os.path.join(pasta, f"{inst.nome}__{metodo}.json")
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)
    return caminho


def rodar_instancia(caminho: str, solver: str, op: Opcoes, nome_config: str = "nenhum",
                    pasta_solucoes: str | None = None, s_ingenuo: bool = False,
                    **kw_leitura) -> dict:
    inst = ler_csv(caminho, **kw_leitura)
    sol0 = melhor_guloso(inst)
    ub = custo(inst, sol0)
    assert not verificar(inst, sol0), "guloso gerou solução inválida"
    lbs = limitantes_inferiores(inst)
    S = calcular_S(inst, ub)
    if s_ingenuo:  # S_k = n, só para mostrar no relatório o tamanho do modelo sem a redução
        S = {t.k: inst.n for t in inst.tipos}

    res = obter_solver(solver).resolver(inst, S, op, sol0)

    erros = verificar(inst, res.solucao) if res.solucao is not None else ["sem solução"]
    por_tipo = {t.k: 0 for t in inst.tipos}
    vazios = 0
    for k, lista in res.solucao or []:
        por_tipo[k] += 1
        vazios += not lista

    if s_ingenuo:
        nome_config += "+S=n"
    b_arr = arredondar_bound(res.bound, mdc_custos(inst))
    g_arr = calcular_gap(res.custo, b_arr)
    metodo = solver if nome_config == "nenhum" else f"{solver}+{nome_config}"
    if pasta_solucoes and res.solucao is not None:
        salvar_solucao_json(inst, metodo, res, pasta_solucoes)

    return {
        "instancia": inst.nome, "n_vms": inst.n, "metodo": solver, "reforcos": nome_config,
        "status": res.status, "custo": res.custo,
        "bound": None if res.bound is None else round(res.bound, 4),
        "gap": None if res.gap is None else round(res.gap, 6),
        "bound_arred": b_arr, "gap_arred": None if g_arr is None else round(g_arr, 6),
        "tempo": round(res.tempo, 3),
        "servidores_tipo1": por_tipo.get(1), "servidores_tipo2": por_tipo.get(2),
        "servidores_tipo3": por_tipo.get(3), "servidores_vazios": vazios,
        "ub_guloso": ub,
        "lb1": round(lbs["lb1"], 4), "lb2": round(lbs["lb2"], 4), "lb3": round(lbs["lb3"], 4),
        # gap na convenção do relatório (seção 3.1): (z - LB)/LB, com LB = LB3
        "gap_lb3": None if res.custo is None else round((res.custo - lbs["lb3"]) / lbs["lb3"], 6),
        "S_1": S.get(1), "S_2": S.get(2), "S_3": S.get(3),
        "n_vars": res.n_vars, "n_restricoes": res.n_restricoes,
        "nos": None if res.nos is None else int(res.nos),
        "tempo_limite": op.tempo_limite, "threads": op.threads,
        "warm_start": op.warm_start,
        "escala_custo": op.escala_custo, "valida": not erros,
        "mensagem": res.mensagem or ("; ".join(erros[:3]) if res.solucao else ""),
        "maquina": maquina(), "data": datetime.now().isoformat(timespec="seconds"),
    }


def anexar_csv(linha: dict, caminho: str) -> None:
    os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)
    novo = not os.path.exists(caminho)
    with open(caminho, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS)
        if novo:
            w.writeheader()
        w.writerow(linha)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("instancias", nargs="+",
                    help="CSVs das instâncias (aceita curingas; instancia_<N>_vms.csv ausente é gerada)")
    ap.add_argument("--solver", nargs="+", default=["gurobi", "scip"],
                    choices=list(SOLVERS))
    ap.add_argument("--tempo", type=float, default=600.0, help="limite de tempo (s)")
    ap.add_argument("--threads", type=int, default=1)
    ap.add_argument("--gap", type=float, default=1e-4, help="tolerância de gap relativo")
    ap.add_argument("--reforcos", default="nenhum", choices=list(CONFIGS) + ["todos"])
    ap.add_argument("--sem-warm-start", action="store_true")
    ap.add_argument("--escala-custo", action="store_true",
                    help="divide os custos pelo MDC na função objetivo (5/7/6 em vez de 100/140/120)")
    ap.add_argument("--s-ingenuo", action="store_true",
                    help="usa S_k = n (comparação com a redução S_k = floor(UB/p_k))")
    ap.add_argument("--semente", type=int, default=0)
    ap.add_argument("--saida", default="resultados/solvers.csv")
    ap.add_argument("--solucoes", default="resultados/solucoes",
                    help="pasta dos JSONs de solução ('' para não salvar)")
    ap.add_argument("--col-id")
    ap.add_argument("--col-cpu")
    ap.add_argument("--col-ram")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    arquivos = sorted({f for padrao in a.instancias for f in (glob.glob(padrao) or [padrao])})
    arquivos = [str(garantir_csv(f)) for f in arquivos]
    configs = list(CONFIGS) if a.reforcos == "todos" else [a.reforcos]
    leitura = dict(col_id=a.col_id, col_cpu=a.col_cpu, col_ram=a.col_ram)

    for arq in arquivos:
        for solver in a.solver:
            for cfg in configs:
                op = Opcoes(tempo_limite=a.tempo, threads=a.threads, gap_tolerancia=a.gap,
                            warm_start=not a.sem_warm_start,
                            escala_custo=a.escala_custo, semente=a.semente,
                            verbose=a.verbose, **CONFIGS[cfg])
                t = time.perf_counter()
                linha = rodar_instancia(arq, solver, op, cfg, a.solucoes or None,
                                        a.s_ingenuo, **leitura)
                anexar_csv(linha, a.saida)
                g = "-" if linha["gap"] is None else f"{100 * linha['gap']:.2f}%"
                print(f"{linha['instancia']:<22} {solver:<6} {cfg:<9} {linha['status']:<13} "
                      f"custo={linha['custo']} bound={linha['bound']} gap={g} "
                      f"(arred.: {linha['bound_arred']}) "
                      f"t={linha['tempo']}s UB0={linha['ub_guloso']} LB3={linha['lb3']} "
                      f"valida={linha['valida']} ({time.perf_counter() - t:.1f}s)",
                      flush=True)
                if linha["mensagem"]:
                    print("   ", linha["mensagem"][:200])


if __name__ == "__main__":
    main()
