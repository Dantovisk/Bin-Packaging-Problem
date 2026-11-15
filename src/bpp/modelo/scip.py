"""Modelo de Bin Packing 2D com servidores heterogêneos no SCIP (pyscipopt)."""

from __future__ import annotations

from pyscipopt import Model, quicksum

from bpp.modelo.comum import Opcoes, Resultado
from bpp.modelo.solver import DadosModelo, Solver

_STATUS = {
    "optimal": "otimo",
    "gaplimit": "otimo",       # parou por atingir a tolerância de gap
    "timelimit": "limite_tempo",
    "infeasible": "inviavel",
}


class ScipSolver(Solver):
    nome = "scip"

    def _otimizar(self, d: DadosModelo, op: Opcoes) -> Resultado:
        inst, S, tipos, servidores, triplas = d.inst, d.S, d.tipos, d.servidores, d.triplas

        m = Model(f"binpacking_{inst.nome}")
        if not op.verbose:
            m.hideOutput()
        m.setParam("limits/time", op.tempo_limite)
        m.setParam("limits/gap", op.gap_tolerancia)
        m.setParam("randomization/randomseedshift", op.semente)

        y = {s: m.addVar(vtype="B", name=f"y[{s[0]},{s[1]}]") for s in servidores}
        x = {(i, k, j): m.addVar(vtype="B", name=f"x[{i},{k},{j}]") for (i, k, j) in triplas}

        m.setObjective(quicksum(tipos[k].custo / d.g * y[k, j] for (k, j) in servidores),
                       "minimize")

        for i in range(inst.n):
            m.addCons(quicksum(x[i, k, j] for (k, j) in d.por_vm[i]) == 1, name=f"aloc[{i}]")
        for (k, j), vms in d.por_servidor.items():
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

        if d.warm_start is not None:
            s0 = m.createSol()
            for s in servidores:
                m.setSolVal(s0, y[s], 1 if s in d.warm_start else 0)
            for (i, k, j) in triplas:
                m.setSolVal(s0, x[i, k, j], 1 if i in d.warm_start.get((k, j), ()) else 0)
            m.addSol(s0, free=True)

        m.optimize()

        status = _STATUS.get(m.getStatus(), f"scip_{m.getStatus()}")
        tem_sol = m.getNSols() > 0
        custo = m.getObjVal() if tem_sol else None
        db = m.getDualbound()
        # sem nó raiz concluído o dual bound é -infinito (-1e20): não há limitante
        bound = None if status == "inviavel" or m.isInfinity(abs(db)) else db

        sol = None
        if tem_sol:
            melhor = m.getBestSol()
            sol = [(k, [i for i in d.por_servidor[k, j] if m.getSolVal(melhor, x[i, k, j]) > 0.5])
                   for (k, j) in servidores if m.getSolVal(melhor, y[k, j]) > 0.5]

        return Resultado(status, custo, bound, None, m.getSolvingTime(), n_vars, n_cons,
                         nos=m.getNNodes(), solucao=sol)
