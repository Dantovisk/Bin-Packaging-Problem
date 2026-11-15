"""Limitante superior (guloso) e inferior de custo, e cálculo de S_k.

O guloso aqui serve só para obter um UB e daí S_k = floor(UB / p_k). Ele também
vira solução inicial (warm start) dos solvers. A versão "oficial" do guloso, usada
como ponto de partida do SA, é a da Pessoa 4; se ela der custo menor, basta
trocar a função `melhor_guloso` por ela.

Por que S_k = floor(UB / p_k) não perde o ótimo: o ótimo custa no máximo UB, e
como todos os custos são positivos, ele não pode ligar mais que floor(UB / p_k)
servidores do tipo k. A própria solução gulosa respeita esse limite, então o
modelo reduzido continua viável.
"""

from __future__ import annotations

import math

from instancia import Instancia, TipoServidor

# Uma solução é uma lista de servidores ligados: (tipo k, [índices das VMs])
Solucao = list[tuple[int, list[int]]]


def custo(inst: Instancia, sol: Solucao) -> float:
    p = {t.k: t.custo for t in inst.tipos}
    return sum(p[k] for k, _ in sol)


def limitante_inferior(inst: Instancia) -> float:
    """LB1 = max_d (sum_i w_id) * min_k (p_k / C_kd), d em {CPU, RAM}.

    Mantida por compatibilidade; o relatório (seção 3.1) usa LB1 <= LB2 <= LB3,
    todas em `limitantes_inferiores`.
    """
    lb_cpu = sum(inst.cpu) * min(t.custo / t.cpu for t in inst.tipos)
    lb_ram = sum(inst.ram) * min(t.custo / t.ram for t in inst.tipos)
    return max(lb_cpu, lb_ram)


def _lb2(inst: Instancia, w_cpu: float, w_ram: float) -> float:
    """LB2: min sum p_k z_k  s.a  sum C_kd z_k >= W_d (d = cpu, ram), z >= 0.

    LP com 2 restrições: o ótimo está num vértice com no máximo 2 variáveis
    positivas, então basta enumerar os vértices (1 ou 2 tipos ativos).
    """
    melhor = math.inf
    tipos = inst.tipos
    # um tipo só: z_k cobre as duas dimensões
    for t in tipos:
        z = max(w_cpu / t.cpu, w_ram / t.ram)
        melhor = min(melhor, t.custo * z)
    # dois tipos, as duas restrições ativas: resolve o sistema 2x2
    for a in range(len(tipos)):
        for b in range(a + 1, len(tipos)):
            ta, tb = tipos[a], tipos[b]
            det = ta.cpu * tb.ram - tb.cpu * ta.ram
            if abs(det) < 1e-12:
                continue
            za = (w_cpu * tb.ram - w_ram * tb.cpu) / det
            zb = (ta.cpu * w_ram - ta.ram * w_cpu) / det
            if za >= -1e-9 and zb >= -1e-9:
                melhor = min(melhor, ta.custo * max(za, 0) + tb.custo * max(zb, 0))
    return melhor


def _lb3(inst: Instancia, w_cpu: float, w_ram: float) -> float:
    """LB3: o mesmo programa de LB2 com z_k inteiro, por enumeração.

    Enumera z_k dos primeiros m-1 tipos e fecha o último com o mínimo que
    atende a demanda restante. Com 3 tipos isso é O(ub^2), desprezível.
    """
    tipos = inst.tipos

    def ub_sozinho(t) -> int:
        return math.ceil(max(w_cpu / t.cpu, w_ram / t.ram) - 1e-9)

    melhor = math.inf

    def rec(idx: int, rc: float, rr: float, custo_parcial: float) -> None:
        nonlocal melhor
        if custo_parcial >= melhor:
            return
        t = tipos[idx]
        if idx == len(tipos) - 1:
            z = max(0, math.ceil(max(rc / t.cpu, rr / t.ram) - 1e-9))
            melhor = min(melhor, custo_parcial + t.custo * z)
            return
        for z in range(ub_sozinho(inst.tipos[idx]) + 1 if rc > 0 or rr > 0 else 1):
            if z and rc <= 0 and rr <= 0:
                break
            rec(idx + 1, rc - z * t.cpu, rr - z * t.ram, custo_parcial + z * t.custo)

    rec(0, w_cpu, w_ram, 0.0)
    return melhor


def limitantes_inferiores(inst: Instancia) -> dict[str, float]:
    """LB1 <= LB2 <= LB3, como na seção 3.1 do relatório (ignoram a
    indivisibilidade das VMs, logo valem para qualquer instância)."""
    w_cpu, w_ram = sum(inst.cpu), sum(inst.ram)
    lb1 = limitante_inferior(inst)
    lb2 = _lb2(inst, w_cpu, w_ram)
    lb3 = _lb3(inst, w_cpu, w_ram)
    return {"lb1": lb1, "lb2": lb2, "lb3": lb3}


def _tipo_mais_barato_que_comporta(inst: Instancia, cpu: float, ram: float) -> TipoServidor | None:
    cands = [t for t in inst.tipos if cpu <= t.cpu and ram <= t.ram]
    return min(cands, key=lambda t: t.custo) if cands else None


def _escolher_tipo(inst: Instancia, i: int, resto_cpu: float, resto_ram: float,
                   regra: str | int) -> TipoServidor:
    cabem = [t for t in inst.tipos if inst.cabe(i, t)]
    if isinstance(regra, int):  # tipo fixo, se couber
        fixo = [t for t in cabem if t.k == regra]
        if fixo:
            return fixo[0]
        regra = "agregado"
    if regra == "agregado":
        # custo por "unidade" da demanda restante: p_k / min(C_cpu/D_cpu, C_ram/D_ram)
        def razao(t):
            return t.custo / min(t.cpu / max(resto_cpu, 1e-9), t.ram / max(resto_ram, 1e-9))
    else:  # "vm": mesma conta, mas com o perfil da própria VM
        def razao(t):
            return t.custo / min(t.cpu / inst.cpu[i], t.ram / inst.ram[i])
    return min(cabem, key=razao)


def guloso(inst: Instancia, ordem: str = "max", regra: str | int = "agregado") -> Solucao:
    """First Fit Decreasing adaptado a 2 dimensões e servidores heterogêneos."""
    cmax = max(t.cpu for t in inst.tipos)
    rmax = max(t.ram for t in inst.tipos)
    if ordem == "max":
        chave = lambda i: max(inst.cpu[i] / cmax, inst.ram[i] / rmax)
    else:
        chave = lambda i: inst.cpu[i] / cmax + inst.ram[i] / rmax
    vms = sorted(range(inst.n), key=chave, reverse=True)

    resto_cpu, resto_ram = sum(inst.cpu), sum(inst.ram)
    servidores = []  # [tipo, livre_cpu, livre_ram, [vms]]
    for i in vms:
        for s in servidores:
            if inst.cpu[i] <= s[1] + 1e-9 and inst.ram[i] <= s[2] + 1e-9:
                s[1] -= inst.cpu[i]
                s[2] -= inst.ram[i]
                s[3].append(i)
                break
        else:
            t = _escolher_tipo(inst, i, resto_cpu, resto_ram, regra)
            servidores.append([t, t.cpu - inst.cpu[i], t.ram - inst.ram[i], [i]])
        resto_cpu -= inst.cpu[i]
        resto_ram -= inst.ram[i]

    # pós-processamento: cada servidor vira o tipo mais barato que comporta sua carga
    sol: Solucao = []
    for t, _, _, lista in servidores:
        carga_cpu = sum(inst.cpu[i] for i in lista)
        carga_ram = sum(inst.ram[i] for i in lista)
        melhor = _tipo_mais_barato_que_comporta(inst, carga_cpu, carga_ram)
        sol.append((melhor.k, lista))
    return sol


def melhor_guloso(inst: Instancia) -> Solucao:
    """Roda algumas variantes do guloso e devolve a de menor custo."""
    regras = ["agregado", "vm"] + [t.k for t in inst.tipos]
    variantes = [guloso(inst, o, r) for o in ("max", "soma") for r in regras]
    return min(variantes, key=lambda s: custo(inst, s))


def calcular_S(inst: Instancia, ub: float) -> dict[int, int]:
    """S_k = floor(UB / p_k), limitado pelo nº de VMs que cabem no tipo k."""
    S = {}
    for t in inst.tipos:
        cabem = sum(1 for i in range(inst.n) if inst.cabe(i, t))
        S[t.k] = min(math.floor(ub / t.custo + 1e-9), cabem)
    return S


def verificar(inst: Instancia, sol: Solucao) -> list[str]:
    """Checagem rápida (o validador oficial é o validador.py da Pessoa 2)."""
    erros = []
    tipos = {t.k: t for t in inst.tipos}
    vistos = [0] * inst.n
    for j, (k, lista) in enumerate(sol):
        t = tipos[k]
        c = sum(inst.cpu[i] for i in lista)
        r = sum(inst.ram[i] for i in lista)
        if c > t.cpu + 1e-6:
            erros.append(f"servidor {j} (tipo {k}): CPU {c} > {t.cpu}")
        if r > t.ram + 1e-6:
            erros.append(f"servidor {j} (tipo {k}): RAM {r} > {t.ram}")
        for i in lista:
            vistos[i] += 1
    for i, v in enumerate(vistos):
        if v != 1:
            erros.append(f"VM {inst.ids[i]} alocada {v} vezes")
    return erros
