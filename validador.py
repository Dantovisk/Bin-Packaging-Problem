"""Validador independente de soluções (seção 3.1 do relatório).

Recebe soluções no formato JSON comum (lista de servidores abertos, com o tipo k
e as VMs alocadas) e confere, a partir apenas do JSON e do CSV da instância:

  (i)   cada VM da instância aparece em exatamente um servidor;
  (ii)  em cada servidor, a soma das demandas de CPU e a de RAM não excedem
        C_k^cpu e C_k^ram;
  (iii) o custo informado coincide com sum_k p_k * (nº de servidores do tipo k),
        recalculado a partir da própria solução.

Uma solução só é válida se passar nos três testes.

O validador não usa nada dos solvers nem da heurística: de `modelo/` ele só
aproveita o leitor de instâncias (`instancia.py`), para que os dados das VMs e
dos tipos de servidor sejam exatamente os mesmos de todos os métodos.

Uso (a partir da raiz do repositório):

    python validador.py resultados/solucoes/*.json
    python validador.py solucao.json --instancia instancias/instancia_50_vms.csv

Sem --instancia, o CSV é procurado pelo campo "instancia" do JSON dentro de
--dir-instancias (padrão: instancias/, incluindo subpastas).
O código de saída é 0 se todas as soluções são válidas e 1 caso contrário.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass, field

RAIZ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(RAIZ, "modelo"))

from instancia import Instancia, ler_csv  # noqa: E402

TOL = 1e-6          # folga numérica nas comparações de capacidade e custo
MAX_ERROS = 10      # erros listados por teste na saída (o total é sempre informado)


@dataclass
class Relatorio:
    """Resultado da validação de uma solução."""
    alocacao: list[str] = field(default_factory=list)      # erros do teste (i)
    capacidade: list[str] = field(default_factory=list)    # erros do teste (ii)
    custo: list[str] = field(default_factory=list)         # erros do teste (iii)
    avisos: list[str] = field(default_factory=list)        # não invalidam a solução
    custo_informado: float | None = None
    custo_recalculado: float | None = None
    servidores_por_tipo: dict[int, int] = field(default_factory=dict)

    @property
    def valida(self) -> bool:
        return not (self.alocacao or self.capacidade or self.custo)

    @property
    def erros(self) -> list[str]:
        return self.alocacao + self.capacidade + self.custo


def validar(inst: Instancia, dados: dict) -> Relatorio:
    """Aplica os três testes da seção 3.1 à solução `dados` (JSON já carregado)."""
    rel = Relatorio()
    tipos = {t.k: t for t in inst.tipos}
    rel.servidores_por_tipo = {k: 0 for k in tipos}

    # demanda de cada VM, pelo identificador usado no JSON
    demanda = {vid: (inst.cpu[i], inst.ram[i]) for i, vid in enumerate(inst.ids)}
    esperado = Counter(inst.ids)
    if len(demanda) != inst.n:
        rel.avisos.append("a instância tem identificadores de VM repetidos")

    servidores = dados.get("servidores")
    if not isinstance(servidores, list):
        rel.alocacao.append('o JSON não tem a lista "servidores"')
        rel.custo.append("não foi possível recalcular o custo")
        return rel

    alocado: Counter = Counter()
    custo_ok = True
    total = 0.0
    for pos, srv in enumerate(servidores):
        if not isinstance(srv, dict):
            srv = {}
        rotulo = f"servidor {srv.get('id', pos)}"
        vms = srv.get("vms")
        if not isinstance(vms, list):
            rel.alocacao.append(f'{rotulo}: sem a lista "vms"')
            vms = []
        vms = [str(v) for v in vms]
        alocado.update(vms)

        k = srv.get("tipo")
        tipo = tipos.get(k) if isinstance(k, int) and not isinstance(k, bool) else None
        if tipo is None:
            # sem tipo válido não há capacidade nem custo para conferir
            rel.capacidade.append(f"{rotulo}: tipo desconhecido ({k!r})")
            custo_ok = False
            continue
        rel.servidores_por_tipo[k] += 1
        total += tipo.custo
        if not vms:
            rel.avisos.append(f"{rotulo} (tipo {k}) está aberto sem nenhuma VM")

        conhecidas = [v for v in vms if v in demanda]
        cpu = sum(demanda[v][0] for v in conhecidas)
        ram = sum(demanda[v][1] for v in conhecidas)
        if cpu > tipo.cpu + TOL:
            rel.capacidade.append(f"{rotulo} (tipo {k}): CPU {cpu:g} > {tipo.cpu:g}")
        if ram > tipo.ram + TOL:
            rel.capacidade.append(f"{rotulo} (tipo {k}): RAM {ram:g} > {tipo.ram:g}")

    # (i) alocação única
    for vid in esperado:
        if alocado[vid] != esperado[vid]:
            rel.alocacao.append(f"VM {vid}: alocada {alocado[vid]} vez(es), "
                                f"esperado {esperado[vid]}")
    for vid in alocado:
        if vid not in esperado:
            rel.alocacao.append(f"VM {vid}: não pertence à instância")

    # (iii) custo
    informado = dados.get("custo")
    if isinstance(informado, (int, float)) and not isinstance(informado, bool):
        rel.custo_informado = float(informado)
    if custo_ok:
        rel.custo_recalculado = total
    if rel.custo_informado is None:
        rel.custo.append(f'o JSON não traz um "custo" numérico ({informado!r})')
    elif not custo_ok:
        rel.custo.append("não foi possível recalcular o custo (servidor de tipo desconhecido)")
    elif abs(rel.custo_informado - total) > TOL:
        rel.custo.append(f"custo informado {rel.custo_informado:g} != recalculado {total:g}")
    return rel


def achar_instancia(nome: str, pasta: str) -> str | None:
    achados = sorted(glob.glob(os.path.join(pasta, "**", f"{nome}.csv"), recursive=True))
    return achados[0] if achados else None


def validar_arquivo(caminho_json: str, caminho_csv: str | None = None,
                    dir_instancias: str | None = None) -> Relatorio:
    """Lê o JSON e a instância correspondente e devolve o relatório de validação."""
    with open(caminho_json, encoding="utf-8") as f:
        dados = json.load(f)
    if not isinstance(dados, dict):
        raise ValueError("o JSON da solução deve ser um objeto")
    if caminho_csv is None:
        nome = dados.get("instancia")
        if not nome:
            raise ValueError('o JSON não tem o campo "instancia"; informe --instancia')
        pasta = dir_instancias or os.path.join(RAIZ, "instancias")
        caminho_csv = achar_instancia(str(nome), pasta)
        if caminho_csv is None:
            raise FileNotFoundError(f"instância {nome!r} não encontrada em {pasta}")
    return validar(ler_csv(caminho_csv), dados)


def _imprimir(caminho: str, rel: Relatorio) -> None:
    print(f"{caminho}: {'VÁLIDA' if rel.valida else 'INVÁLIDA'}")
    testes = [("(i) alocação única", rel.alocacao),
              ("(ii) capacidade", rel.capacidade),
              ("(iii) custo", rel.custo)]
    for nome, erros in testes:
        print(f"  {nome}: {'ok' if not erros else f'{len(erros)} erro(s)'}")
        for e in erros[:MAX_ERROS]:
            print(f"    - {e}")
        if len(erros) > MAX_ERROS:
            print(f"    ... e mais {len(erros) - MAX_ERROS}")
    if rel.custo_recalculado is not None:
        por_tipo = "/".join(str(v) for _, v in sorted(rel.servidores_por_tipo.items()))
        print(f"  custo recalculado: {rel.custo_recalculado:g} (servidores por tipo: {por_tipo})")
    for a in rel.avisos:
        print(f"  aviso: {a}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Valida soluções no formato JSON comum.")
    ap.add_argument("solucoes", nargs="+", help="arquivos JSON de solução")
    ap.add_argument("--instancia", help="CSV da instância (vale para todos os JSONs dados)")
    ap.add_argument("--dir-instancias", help="pasta onde procurar o CSV pelo nome "
                                             "(padrão: instancias/)")
    a = ap.parse_args()

    invalidas = 0
    for caminho in a.solucoes:
        try:
            rel = validar_arquivo(caminho, a.instancia, a.dir_instancias)
        except (OSError, ValueError, KeyError) as e:
            print(f"{caminho}: ERRO ({e})")
            invalidas += 1
            continue
        _imprimir(caminho, rel)
        invalidas += not rel.valida
    print(f"\n{len(a.solucoes) - invalidas} de {len(a.solucoes)} soluções válidas")
    return 1 if invalidas else 0


if __name__ == "__main__":
    sys.exit(main())
