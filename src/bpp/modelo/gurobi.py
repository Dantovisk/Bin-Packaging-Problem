"""Modelo de Bin Packing 2D com servidores heterogêneos no Gurobi (gurobipy)."""

from __future__ import annotations

import time

import gurobipy as gp
from gurobipy import GRB

from bpp.modelo.instancia import Instancia
from bpp.modelo.limitantes import Solucao
from bpp.modelo.comum import (Opcoes, Resultado, calcular_gap, fator_escala,
                              indices_servidores, mapear_warm_start, pares_validos)

_STATUS = {
    GRB.OPTIMAL: "otimo",
    GRB.TIME_LIMIT: "limite_tempo",
    GRB.INFEASIBLE: "inviavel",
    GRB.INF_OR_UNBD: "inviavel",
}


def resolver(inst: Instancia, S: dict[int, int], op: Opcoes,
             sol_inicial: Solucao | None = None) -> Resultado:
    t0 = time.perf_counter()
    tipos = {t.k: t for t in inst.tipos}
    servidores = indices_servidores(S)
    triplas = pares_validos(inst, servidores)
    g = fator_escala(inst, op)

    env = gp.Env(empty=True)
    env.setParam("OutputFlag", 1 if op.verbose else 0)
    env.start()
    m = gp.Model(f"binpacking_{inst.nome}", env=env)
    try:
        m.Params.TimeLimit = op.tempo_limite
        m.Params.Threads = op.threads
        m.Params.MIPGap = op.gap_tolerancia
        m.Params.Seed = op.semente

        y = m.addVars(servidores, vtype=GRB.BINARY, name="y")
        x = m.addVars(triplas, vtype=GRB.BINARY, name="x")

        m.setObjective(gp.quicksum(tipos[k].custo / g * y[k, j] for (k, j) in servidores),
                       GRB.MINIMIZE)

        # cada VM em exatamente um servidor
        m.addConstrs((x.sum(i, "*", "*") == 1 for i in range(inst.n)), name="aloc")

        # capacidade de CPU e RAM (só vale se o servidor estiver ligado)
        por_servidor: dict[tuple[int, int], list[int]] = {s: [] for s in servidores}
        for (i, k, j) in triplas:
            por_servidor[k, j].append(i)
        for (k, j), vms in por_servidor.items():
            m.addConstr(gp.quicksum(inst.cpu[i] * x[i, k, j] for i in vms)
                        <= tipos[k].cpu * y[k, j], name=f"cpu[{k},{j}]")
            m.addConstr(gp.quicksum(inst.ram[i] * x[i, k, j] for i in vms)
                        <= tipos[k].ram * y[k, j], name=f"ram[{k},{j}]")

        if op.reforco_xy:  # R1
            m.addConstrs((x[i, k, j] <= y[k, j] for (i, k, j) in triplas), name="xy")
        if op.simetria:    # R2
            m.addConstrs((y[k, j] >= y[k, j + 1] for k in S for j in range(S[k] - 1)),
                         name="sim")

        if op.warm_start and sol_inicial is not None:
            mapa = mapear_warm_start(sol_inicial, S)
            for s in servidores:
                y[s].Start = 1 if s in mapa else 0
            for (i, k, j) in triplas:
                x[i, k, j].Start = 1 if i in mapa.get((k, j), ()) else 0

        m.update()
        n_vars, n_cons = m.NumVars, m.NumConstrs
        try:
            m.optimize()
        except gp.GurobiError as e:
            # ex.: "Model too large for size-limited license"
            return Resultado("erro", None, None, None, time.perf_counter() - t0,
                             n_vars, n_cons, mensagem=str(e))

        status = _STATUS.get(m.Status, f"gurobi_{m.Status}")
        tem_sol = m.SolCount > 0
        custo = g * m.ObjVal if tem_sol else None
        bound = g * m.ObjBound if m.Status in (GRB.OPTIMAL, GRB.TIME_LIMIT) else None
        if bound is not None and abs(bound) >= GRB.INFINITY:  # sem limitante (raiz não concluída)
            bound = None
        if status == "limite_tempo" and not tem_sol:
            status = "sem_solucao"

        sol = None
        if tem_sol:
            sol = []
            for (k, j) in servidores:
                if y[k, j].X > 0.5:
                    sol.append((k, [i for i in por_servidor[k, j] if x[i, k, j].X > 0.5]))
            # servidor ligado sem VM não é útil: o custo fica, mas indica solução não-ótima
        return Resultado(status, custo, bound, calcular_gap(custo, bound),
                         m.Runtime, n_vars, n_cons, nos=m.NodeCount, solucao=sol,
                         extra={"tempo_total": time.perf_counter() - t0})
    finally:
        m.dispose()
        env.dispose()
