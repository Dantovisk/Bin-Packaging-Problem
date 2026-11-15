"""Modelo de Bin Packing 2D com servidores heterogêneos no SCIP (pyscipopt)."""

from __future__ import annotations

import time

from pyscipopt import Model, quicksum

from bpp.modelo.instancia import Instancia
from bpp.modelo.limitantes import Solucao
from bpp.modelo.comum import (Opcoes, Resultado, calcular_gap, fator_escala,
                              indices_servidores, mapear_warm_start, pares_validos)

_STATUS = {
    "optimal": "otimo",
    "gaplimit": "otimo",       # parou por atingir a tolerância de gap
    "timelimit": "limite_tempo",
    "infeasible": "inviavel",
}


def resolver(inst: Instancia, S: dict[int, int], op: Opcoes,
             sol_inicial: Solucao | None = None) -> Resultado:
    t0 = time.perf_counter()
    tipos = {t.k: t for t in inst.tipos}
    servidores = indices_servidores(S)
    triplas = pares_validos(inst, servidores)
    g = fator_escala(inst, op)

    m = Model(f"binpacking_{inst.nome}")
    if not op.verbose:
        m.hideOutput()
    m.setParam("limits/time", op.tempo_limite)
    m.setParam("limits/gap", op.gap_tolerancia)
    m.setParam("randomization/randomseedshift", op.semente)

    y = {s: m.addVar(vtype="B", name=f"y[{s[0]},{s[1]}]") for s in servidores}
    x = {(i, k, j): m.addVar(vtype="B", name=f"x[{i},{k},{j}]") for (i, k, j) in triplas}

    m.setObjective(quicksum(tipos[k].custo / g * y[k, j] for (k, j) in servidores), "minimize")

    por_vm: dict[int, list] = {i: [] for i in range(inst.n)}
    por_servidor: dict[tuple[int, int], list[int]] = {s: [] for s in servidores}
    for (i, k, j) in triplas:
        por_vm[i].append(x[i, k, j])
        por_servidor[k, j].append(i)

    for i in range(inst.n):
        m.addCons(quicksum(por_vm[i]) == 1, name=f"aloc[{i}]")
    for (k, j), vms in por_servidor.items():
        m.addCons(quicksum(inst.cpu[i] * x[i, k, j] for i in vms) <= tipos[k].cpu * y[k, j],
                  name=f"cpu[{k},{j}]")
        m.addCons(quicksum(inst.ram[i] * x[i, k, j] for i in vms) <= tipos[k].ram * y[k, j],
                  name=f"ram[{k},{j}]")

    if op.reforco_xy:  # R1
        for (i, k, j) in triplas:
            m.addCons(x[i, k, j] <= y[k, j], name=f"xy[{i},{k},{j}]")
    if op.simetria:    # R2
        for k in S:
            for j in range(S[k] - 1):
                m.addCons(y[k, j] >= y[k, j + 1], name=f"sim[{k},{j}]")

    n_vars, n_cons = m.getNVars(), m.getNConss()

    if op.warm_start and sol_inicial is not None:
        mapa = mapear_warm_start(sol_inicial, S)
        s0 = m.createSol()
        for s in servidores:
            m.setSolVal(s0, y[s], 1 if s in mapa else 0)
        for (i, k, j) in triplas:
            m.setSolVal(s0, x[i, k, j], 1 if i in mapa.get((k, j), ()) else 0)
        m.addSol(s0, free=True)

    m.optimize()

    st = m.getStatus()
    status = _STATUS.get(st, f"scip_{st}")
    tem_sol = m.getNSols() > 0
    custo = g * m.getObjVal() if tem_sol else None
    db = m.getDualbound()
    # se o SCIP não concluiu o nó raiz, o dual bound é -infinito (-1e20): não há limitante
    bound = None if status == "inviavel" or m.isInfinity(abs(db)) else g * db
    if status == "limite_tempo" and not tem_sol:
        status = "sem_solucao"

    sol = None
    if tem_sol:
        melhor = m.getBestSol()
        sol = []
        for (k, j) in servidores:
            if m.getSolVal(melhor, y[k, j]) > 0.5:
                sol.append((k, [i for i in por_servidor[k, j]
                                if m.getSolVal(melhor, x[i, k, j]) > 0.5]))

    return Resultado(status, custo, bound, calcular_gap(custo, bound),
                     m.getSolvingTime(), n_vars, n_cons, nos=m.getNNodes(), solucao=sol,
                     extra={"tempo_total": time.perf_counter() - t0})
