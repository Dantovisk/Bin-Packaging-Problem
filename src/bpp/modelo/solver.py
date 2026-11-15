"""Classe base dos solvers: o que é igual no Gurobi e no SCIP fica aqui.

O modelo está descrito em `bpp.modelo.comum`. Cada subclasse só traduz o modelo
para a API do seu solver em `_otimizar`.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

from bpp.modelo.comum import (Opcoes, Resultado, calcular_gap, fator_escala,
                              indices_servidores, mapear_warm_start, pares_validos)
from bpp.modelo.instancia import Instancia, TipoServidor
from bpp.modelo.limitantes import Solucao


@dataclass
class DadosModelo:
    """Índices do modelo, montados uma vez e entregues ao solver."""
    inst: Instancia
    S: dict[int, int]
    tipos: dict[int, TipoServidor]
    servidores: list[tuple[int, int]]           # (k, j)
    triplas: list[tuple[int, int, int]]         # (i, k, j) com x_ijk existente
    por_servidor: dict[tuple[int, int], list[int]]
    por_vm: dict[int, list[tuple[int, int]]]    # i -> [(k, j)]
    g: float                                    # divisor dos custos no objetivo
    warm_start: dict[tuple[int, int], list[int]] | None


class Solver(ABC):
    nome: str

    def resolver(self, inst: Instancia, S: dict[int, int], op: Opcoes,
                 sol_inicial: Solucao | None = None) -> Resultado:
        t0 = time.perf_counter()
        dados = self._montar(inst, S, op, sol_inicial)
        res = self._otimizar(dados, op)
        if res.custo is not None:
            res.custo *= dados.g
        if res.bound is not None:
            res.bound *= dados.g
        if res.status == "limite_tempo" and res.solucao is None:
            res.status = "sem_solucao"
        res.gap = calcular_gap(res.custo, res.bound)
        res.extra.setdefault("tempo_total", time.perf_counter() - t0)
        return res

    @staticmethod
    def _montar(inst: Instancia, S: dict[int, int], op: Opcoes,
                sol_inicial: Solucao | None) -> DadosModelo:
        servidores = indices_servidores(S)
        triplas = pares_validos(inst, servidores)
        por_servidor: dict[tuple[int, int], list[int]] = {s: [] for s in servidores}
        por_vm: dict[int, list[tuple[int, int]]] = {i: [] for i in range(inst.n)}
        for (i, k, j) in triplas:
            por_servidor[k, j].append(i)
            por_vm[i].append((k, j))
        warm = (mapear_warm_start(sol_inicial, S)
                if op.warm_start and sol_inicial is not None else None)
        return DadosModelo(inst, S, {t.k: t for t in inst.tipos}, servidores, triplas,
                           por_servidor, por_vm, fator_escala(inst, op), warm)

    @abstractmethod
    def _otimizar(self, d: DadosModelo, op: Opcoes) -> Resultado:
        """Constrói e resolve o modelo.

        Devolve custo e bound na escala do objetivo (divididos por `d.g`); a base
        desfaz a escala, calcula o gap e ajusta o status.
        """


def obter_solver(nome: str) -> Solver:
    # import tardio: o SCIP roda mesmo se o gurobipy falhar ao importar
    if nome == "gurobi":
        from bpp.modelo.gurobi import GurobiSolver
        return GurobiSolver()
    if nome == "scip":
        from bpp.modelo.scip import ScipSolver
        return ScipSolver()
    raise ValueError(f"solver desconhecido: {nome!r}")


SOLVERS = ("gurobi", "scip")
