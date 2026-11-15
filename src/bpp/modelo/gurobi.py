"""Modelo de Bin Packing 2D com servidores heterogêneos no Gurobi (gurobipy)."""

from __future__ import annotations

import time

import gurobipy as gp
from gurobipy import GRB

from bpp.modelo.comum import Opcoes, Resultado
from bpp.modelo.solver import DadosModelo, Solver

_STATUS = {
    GRB.OPTIMAL: "otimo",
    GRB.TIME_LIMIT: "limite_tempo",
    GRB.INFEASIBLE: "inviavel",
    GRB.INF_OR_UNBD: "inviavel",
}


class GurobiSolver(Solver):
    nome = "gurobi"

    def _otimizar(self, d: DadosModelo, op: Opcoes) -> Resultado:
        t0 = time.perf_counter()
        inst, S, tipos, servidores, triplas = d.inst, d.S, d.tipos, d.servidores, d.triplas

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

            m.setObjective(gp.quicksum(tipos[k].custo / d.g * y[k, j] for (k, j) in servidores),
                           GRB.MINIMIZE)

            m.addConstrs((x.sum(i, "*", "*") == 1 for i in range(inst.n)), name="aloc")
            for (k, j), vms in d.por_servidor.items():
                m.addConstr(gp.quicksum(inst.cpu[i] * x[i, k, j] for i in vms)
                            <= tipos[k].cpu * y[k, j], name=f"cpu[{k},{j}]")
                m.addConstr(gp.quicksum(inst.ram[i] * x[i, k, j] for i in vms)
                            <= tipos[k].ram * y[k, j], name=f"ram[{k},{j}]")

            if op.reforco_xy:  # R1
                m.addConstrs((x[i, k, j] <= y[k, j] for (i, k, j) in triplas), name="xy")
            if op.simetria:    # R2
                m.addConstrs((y[k, j] >= y[k, j + 1] for k in S for j in range(S[k] - 1)),
                             name="sim")

            if d.warm_start is not None:
                for s in servidores:
                    y[s].Start = 1 if s in d.warm_start else 0
                for (i, k, j) in triplas:
                    x[i, k, j].Start = 1 if i in d.warm_start.get((k, j), ()) else 0

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
            custo = m.ObjVal if tem_sol else None
            bound = m.ObjBound if m.Status in (GRB.OPTIMAL, GRB.TIME_LIMIT) else None
            if bound is not None and abs(bound) >= GRB.INFINITY:  # raiz não concluída
                bound = None

            sol = None
            if tem_sol:
                sol = [(k, [i for i in d.por_servidor[k, j] if x[i, k, j].X > 0.5])
                       for (k, j) in servidores if y[k, j].X > 0.5]
            return Resultado(status, custo, bound, None, m.Runtime, n_vars, n_cons,
                             nos=m.NodeCount, solucao=sol)
        finally:
            m.dispose()
            env.dispose()
