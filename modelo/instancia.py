"""Leitura das instâncias geradas pelo particionador e dados dos tipos de servidor.

O leitor tenta descobrir sozinho as colunas de identificador, CPU e RAM do CSV
(aceita nomes como "cpu", "cores", "vmcorecountbucket", "ram", "memoria",
"vmmemorybucket"...). Se o particionador usar outros nomes, passe-os em
`col_cpu`, `col_ram` e `col_id` (ou pelas opções --col-* do rodar_solvers.py).

Valores em faixa aberta do Azure (ex.: ">24" núcleos, ">64" GB) são convertidos
pelo dicionário FAIXAS_ABERTAS. Confirmar com a Pessoa 1 qual valor o
particionador adota, para todos os métodos usarem o mesmo.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class TipoServidor:
    k: int          # índice do tipo (1, 2, 3)
    nome: str
    cpu: float      # C_k,CPU (núcleos)
    ram: float      # C_k,RAM (GB)
    custo: float    # p_k


# Tabela do escopo do trabalho
TIPOS_PADRAO = [
    TipoServidor(1, "Uso geral", 64, 256, 100),
    TipoServidor(2, "Memória", 64, 512, 140),
    TipoServidor(3, "Computação", 128, 256, 120),
]

# Conversão das faixas abertas do vmtable (Azure Public Dataset v1).
# Ajustar se o particionador adotar outro valor.
FAIXAS_ABERTAS = {">24": 32.0, ">64": 128.0}

NOMES_ID = ["vm_id", "vmid", "id", "vm"]
NOMES_CPU = ["cpu", "cpus", "cores", "nucleos", "núcleos", "vcpu", "vcpus",
             "vmcorecount", "vmcorecountbucket", "cpu_cores", "core_count"]
NOMES_RAM = ["ram", "ram_gb", "mem", "memoria", "memória", "memory", "memory_gb",
             "vmmemory", "vmmemorybucket", "mem_gb"]


@dataclass
class Instancia:
    nome: str
    ids: list[str]
    cpu: list[float]
    ram: list[float]
    tipos: list[TipoServidor] = field(default_factory=lambda: list(TIPOS_PADRAO))

    @property
    def n(self) -> int:
        return len(self.ids)

    def cabe(self, i: int, t: TipoServidor) -> bool:
        """A VM i cabe sozinha num servidor do tipo t?"""
        return self.cpu[i] <= t.cpu and self.ram[i] <= t.ram


def _numero(valor: str) -> float:
    v = valor.strip()
    if v in FAIXAS_ABERTAS:
        return FAIXAS_ABERTAS[v]
    if v.startswith(">"):
        raise ValueError(f"Faixa aberta sem conversão definida: {v!r} "
                         "(acrescente em FAIXAS_ABERTAS)")
    return float(v.replace(",", "."))


def _achar_coluna(cabecalho: list[str], candidatos: list[str], escolhida: str | None) -> str:
    if escolhida:
        if escolhida not in cabecalho:
            raise KeyError(f"Coluna {escolhida!r} não existe. Colunas: {cabecalho}")
        return escolhida
    normal = {c.strip().lower(): c for c in cabecalho}
    for cand in candidatos:
        if cand in normal:
            return normal[cand]
    raise KeyError(f"Não achei nenhuma das colunas {candidatos} em {cabecalho}. "
                   "Informe o nome com --col-cpu/--col-ram/--col-id.")


def ler_csv(caminho: str, col_id: str | None = None, col_cpu: str | None = None,
            col_ram: str | None = None, tipos: list[TipoServidor] | None = None) -> Instancia:
    with open(caminho, newline="", encoding="utf-8") as f:
        amostra = f.read(4096)
        f.seek(0)
        try:
            dialeto = csv.Sniffer().sniff(amostra, delimiters=",;\t")
        except csv.Error:
            dialeto = csv.excel
        leitor = csv.DictReader(f, dialect=dialeto)
        cab = leitor.fieldnames or []
        c_cpu = _achar_coluna(cab, NOMES_CPU, col_cpu)
        c_ram = _achar_coluna(cab, NOMES_RAM, col_ram)
        try:
            c_id = _achar_coluna(cab, NOMES_ID, col_id)
        except KeyError:
            c_id = None  # sem coluna de id: usa o número da linha

        ids, cpu, ram = [], [], []
        for linha, reg in enumerate(leitor):
            ids.append(str(reg[c_id]) if c_id else str(linha))
            cpu.append(_numero(reg[c_cpu]))
            ram.append(_numero(reg[c_ram]))

    nome = os.path.splitext(os.path.basename(caminho))[0]
    inst = Instancia(nome, ids, cpu, ram, list(tipos or TIPOS_PADRAO))
    for i in range(inst.n):
        if not any(inst.cabe(i, t) for t in inst.tipos):
            raise ValueError(f"VM {inst.ids[i]} (CPU={inst.cpu[i]}, RAM={inst.ram[i]}) "
                             "não cabe em nenhum tipo de servidor")
    return inst
