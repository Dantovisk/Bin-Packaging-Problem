"""Partes compartilhadas entre o modelo do Gurobi e o do SCIP.

Modelo (o mesmo do relatório):

    min  sum_k sum_{j<=S_k} p_k * y_jk
    s.a. sum_k sum_j x_ijk = 1                          para toda VM i
         sum_i cpu_i * x_ijk <= C_k,CPU * y_jk          para todo (j, k)
         sum_i ram_i * x_ijk <= C_k,RAM * y_jk          para todo (j, k)
         x_ijk, y_jk binárias

Reforços opcionais:
    (R1) x_ijk <= y_jk                                  para todo (i, j, k)
    (R2) y_jk >= y_(j+1)k                               quebra de simetria por tipo

Detalhe de implementação: x_ijk só é criada se a VM i cabe sozinha no tipo k
(senão ela seria fixada em 0 de qualquer jeito).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from bpp.modelo.instancia import Instancia
from bpp.modelo.limitantes import Solucao


@dataclass
class Opcoes:
    tempo_limite: float = 600.0
    threads: int = 1            # 1 = comparação justa com o SCIP (que é sequencial)
    gap_tolerancia: float = 1e-4
    reforco_xy: bool = False    # R1
    simetria: bool = False      # R2
    warm_start: bool = True     # usa a solução gulosa como incumbente inicial
    escala_custo: bool = False  # divide os custos pelo MDC (100,140,120 -> 5,7,6)
    semente: int = 0
    verbose: bool = False


@dataclass
class Resultado:
    status: str                 # otimo | limite_tempo | inviavel | sem_solucao | erro
    custo: float | None
    bound: float | None
    gap: float | None
    tempo: float
    n_vars: int
    n_restricoes: int
    nos: float | None = None
    solucao: Solucao | None = None
    mensagem: str = ""
    extra: dict = field(default_factory=dict)


def indices_servidores(S: dict[int, int]) -> list[tuple[int, int]]:
    """Lista de servidores candidatos (k, j), j = 0..S_k-1."""
    return [(k, j) for k in sorted(S) for j in range(S[k])]


def pares_validos(inst: Instancia, servidores: list[tuple[int, int]]) -> list[tuple[int, int, int]]:
    """Triplas (i, k, j) para as quais x_ijk existe."""
    tipos = {t.k: t for t in inst.tipos}
    return [(i, k, j) for i in range(inst.n) for (k, j) in servidores
            if inst.cabe(i, tipos[k])]


def mapear_warm_start(sol: Solucao, S: dict[int, int]) -> dict[tuple[int, int], list[int]]:
    """Numera os servidores da solução gulosa como (k, 0), (k, 1), ... por tipo.

    Numerar de forma contígua garante que a solução respeita a quebra de simetria R2.
    """
    cont = {k: 0 for k in S}
    mapa = {}
    for k, lista in sol:
        j = cont[k]
        if j >= S[k]:
            raise ValueError(f"warm start usa mais servidores do tipo {k} que S_k={S[k]}")
        mapa[(k, j)] = lista
        cont[k] += 1
    return mapa


def fator_escala(inst: Instancia, op: Opcoes) -> float:
    """MDC dos custos, se forem inteiros (ex.: 20 para 100/140/120).

    Dividir a função objetivo pelo MDC não muda o modelo, mas deixa os coeficientes
    inteiros e pequenos: o solver percebe que o objetivo só assume valores inteiros e
    arredonda o bound para cima (na escala original, para o próximo múltiplo de 20).
    Isso fecha o gap mais cedo quando o incumbente já é ótimo.
    """
    if not op.escala_custo:
        return 1.0
    return mdc_custos(inst)


def mdc_custos(inst: Instancia) -> float:
    custos = [t.custo for t in inst.tipos]
    if any(c != int(c) for c in custos):
        return 1.0
    return float(math.gcd(*[int(c) for c in custos]))


def arredondar_bound(bound: float | None, g: float) -> float | None:
    """Todo custo viável é múltiplo de g, então o bound pode subir ao próximo múltiplo."""
    if bound is None or g <= 1:
        return bound
    return math.ceil(bound / g - 1e-6) * g


def calcular_gap(custo: float | None, bound: float | None) -> float | None:
    """Gap relativo (custo - bound) / custo, calculado igual para os dois solvers."""
    if custo is None or bound is None or custo == 0:
        return None
    return max(0.0, (custo - bound) / abs(custo))
