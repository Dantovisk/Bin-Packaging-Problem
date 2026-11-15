"""Submete cada execução de `make experimentos` como um job SLURM independente.

Cada job grava um CSV parcial em <resultados>/parcial/<rodada>/. Um último job
(dependência afterany) junta os parciais em solvers.csv, reforcos.csv e
s_ingenuo.csv. Estimativa de tempo e memória: docs/cluster.md.

    bpp-slurm --ns 50 100 500 1000 2000 --tempo 600 --dry-run
    bpp-juntar resultados/parcial/<rodada> --resultados resultados
"""

from __future__ import annotations

import argparse
import csv
import math
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from bpp.dados.azure import garantir_csv
from bpp.experimentos.rodar import CONFIGS, anexar_csv
from bpp.modelo.instancia import ler_csv
from bpp.modelo.limitantes import calcular_S, custo, melhor_guloso
from bpp.modelo.solver import SOLVERS

GRUPOS = ("solvers", "reforcos", "s_ingenuo")
SCRIPT = "scripts/slurm.sbatch"

# Coeficientes medidos com o SCIP (o mais pesado dos dois); ver docs/cluster.md
BASE_MB = 600
KB_POR_VAR = 2.6
KB_POR_VAR_XY = 4.0      # R1 acrescenta uma restrição por x_ijk
SEG_POR_VAR = 50e-6      # montagem do modelo + presolve


@dataclass(frozen=True)
class Execucao:
    grupo: str
    n: int
    solver: str
    cfg: str

    @property
    def ingenuo(self) -> bool:
        return self.grupo == "s_ingenuo"

    @property
    def nome(self) -> str:
        return f"{self.grupo}__{self.n}__{self.solver}__{self.cfg}"


def planejar(ns, ns_reforcos, ns_ingenuo, solvers, reforcos="nenhum") -> list[Execucao]:
    """As mesmas execuções dos alvos solvers, reforcos e s-ingenuo do Makefile."""
    plano = [Execucao("solvers", n, s, reforcos) for n in ns for s in solvers]
    plano += [Execucao("reforcos", n, s, c) for n in ns_reforcos for s in solvers for c in CONFIGS]
    plano += [Execucao("s_ingenuo", n, s, "nenhum") for n in ns_ingenuo for s in solvers]
    return plano


def n_variaveis(caminho: str | Path, ingenuo: bool) -> int:
    """Nº de variáveis (y + x) sem montar o modelo."""
    inst = ler_csv(str(caminho))
    if ingenuo:
        S = {t.k: inst.n for t in inst.tipos}
    else:
        S = calcular_S(inst, custo(inst, melhor_guloso(inst)))
    cabem = {t.k: sum(inst.cabe(i, t) for i in range(inst.n)) for t in inst.tipos}
    return sum(S[k] * (1 + cabem[k]) for k in S)


def recursos(e: Execucao, variaveis: int, tempo: float, folga: float, margem: float,
             fator_mem: float, mem_min_gb: int) -> tuple[int, int]:
    """(segundos, GB) pedidos ao SLURM para uma execução."""
    kb = KB_POR_VAR_XY if CONFIGS[e.cfg]["reforco_xy"] else KB_POR_VAR
    mem_gb = math.ceil((BASE_MB + kb * variaveis / 1024) * fator_mem / 1024)
    seg = math.ceil(tempo * folga + SEG_POR_VAR * variaveis + margem)
    return seg, max(mem_min_gb, mem_gb)


def hms(seg: int) -> str:
    return f"{seg // 3600:02d}:{seg % 3600 // 60:02d}:{seg % 60:02d}"


def _sbatch(opcoes: list[str], comando: list[str], dry: bool, ficticio: str) -> str:
    cmd = ["sbatch", "--parsable", *opcoes, SCRIPT, *comando]
    if dry:
        print(shlex.join(cmd))
        return ficticio
    saida = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    return saida.strip().split(";")[0]


def _feito(rodada: Path, nome: str) -> bool:
    return (rodada / f"{nome}.csv").exists() or (rodada / "juntados" / f"{nome}.csv").exists()


def submeter(a: argparse.Namespace) -> None:
    resultados = Path(a.resultados)
    rodada = resultados / "parcial" / a.rodada
    logs = Path(a.log_dir) / a.rodada
    rodada.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)

    plano = planejar(a.ns, a.ns_reforcos or a.ns, a.ns_ingenuo or a.ns, a.solvers, a.reforcos)
    cache: dict[tuple[int, bool], tuple[str, int]] = {}
    extra = shlex.split(a.extra_args)
    comuns = [f"--cpus-per-task={a.threads}",
              *([f"--partition={a.particao}"] if a.particao else []), *shlex.split(a.sbatch_args)]
    n_gurobi = 0

    novo_tsv = not (rodada / "plano.tsv").exists()
    ids = []
    with open(rodada / "plano.tsv", "a", encoding="utf-8") as tsv:
        if novo_tsv:
            tsv.write("nome\tjob\ttempo\tmem_gb\tvariaveis\n")
        print(f"rodada {a.rodada}: {len(plano)} execuções planejadas")
        for idx, e in enumerate(plano):
            if _feito(rodada, e.nome):
                print(f"  pula {e.nome} (já tem resultado)")
                continue
            if (e.n, e.ingenuo) not in cache:
                inst = str(garantir_csv(Path(a.inst_dir) / f"instancia_{e.n}_vms.csv", a.raw_dir))
                cache[e.n, e.ingenuo] = (inst, n_variaveis(inst, e.ingenuo))
            inst, nv = cache[e.n, e.ingenuo]
            seg, mem = recursos(e, nv, a.tempo, a.folga, a.margem, a.fator_mem, a.mem_min)
            comando = [a.uv, "run", "--no-sync", "bpp-solvers", inst, "--solver", e.solver,
                       "--tempo", str(a.tempo), "--threads", str(a.threads),
                       "--reforcos", e.cfg, *(["--s-ingenuo"] if e.ingenuo else []),
                       "--saida", str(rodada / f"{e.nome}.csv"),
                       "--solucoes", a.solucoes if e.grupo == "solvers" else "", *extra]
            nome_job, extra_job = f"bpp-{e.nome}", []
            if e.solver == "gurobi" and a.gurobi_simult > 0:
                # licença WLS acadêmica: 2 sessões. Jobs com o mesmo nome + singleton
                # rodam um por vez, então cada faixa usa no máximo 1 sessão.
                nome_job = f"bpp-gurobi-faixa{n_gurobi % a.gurobi_simult + 1}"
                extra_job = ["--dependency=singleton",
                             f"--export=ALL,BPP_ESPERA_FIM={int(a.gurobi_espera)}"]
                seg += int(a.gurobi_espera)
                n_gurobi += 1
            job = _sbatch([f"--job-name={nome_job}", f"--output={logs}/{e.nome}-%j.out",
                           f"--time={hms(seg)}", f"--mem={mem}G", *extra_job, *comuns],
                          comando, a.dry_run, f"DRY{idx}")
            ids.append(job)
            tsv.write(f"{e.nome}\t{job}\t{hms(seg)}\t{mem}\t{nv}\n")
            print(f"  {job:>10}  {e.nome:<38} tempo={hms(seg)} mem={mem}G vars={nv}"
                  + (f" [{nome_job}]" if extra_job else ""))

    if not ids:
        print("nada a submeter")
        return
    junta = _sbatch(["--job-name=bpp-juntar", f"--output={logs}/juntar-%j.out",
                     "--time=00:15:00", "--mem=2G",
                     f"--dependency=afterany:{':'.join(ids)}", *comuns],
                    [a.uv, "run", "--no-sync", "bpp-juntar", str(rodada),
                     "--resultados", str(resultados)], a.dry_run, "DRYJ")
    verbo = "planejados (dry-run)" if a.dry_run else "submetidos"
    print(f"{len(ids)} jobs {verbo}; junção: job {junta} (logs em {logs}/)")


def _ordem(caminho: Path) -> tuple:
    grupo, n, solver, cfg = caminho.stem.split("__")
    return GRUPOS.index(grupo), int(n), solver, list(CONFIGS).index(cfg)


def juntar(rodada: str | Path, resultados: str | Path) -> list[str]:
    """Acrescenta os CSVs parciais ainda não juntados; devolve as execuções faltantes."""
    rodada, resultados = Path(rodada), Path(resultados)
    juntados = rodada / "juntados"
    juntados.mkdir(exist_ok=True)
    for parcial in sorted(rodada.glob("*__*.csv"), key=_ordem):
        destino = resultados / f"{parcial.name.split('__')[0]}.csv"
        with open(parcial, newline="", encoding="utf-8") as f:
            for linha in csv.DictReader(f):
                anexar_csv(linha, str(destino))
        # movido para não ser juntado de novo numa ressubmissão da mesma rodada
        parcial.rename(juntados / parcial.name)
        print(f"juntado {parcial.name} -> {destino}")

    faltam = []
    if (rodada / "plano.tsv").exists():
        with open(rodada / "plano.tsv", encoding="utf-8") as f:
            nomes = {r["nome"] for r in csv.DictReader(f, delimiter="\t")}
        faltam = sorted(n for n in nomes if not (juntados / f"{n}.csv").exists())
    for n in faltam:
        print(f"FALTANDO {n} (ver logs; ressubmeter com RODADA={rodada.name})")
    return faltam


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ns", type=int, nargs="+", default=[50, 100, 500, 1000, 2000])
    ap.add_argument("--ns-reforcos", type=int, nargs="*", help="padrão: --ns")
    ap.add_argument("--ns-ingenuo", type=int, nargs="*", help="padrão: --ns")
    ap.add_argument("--solvers", nargs="+", default=list(SOLVERS), choices=list(SOLVERS))
    ap.add_argument("--reforcos", default="nenhum", choices=list(CONFIGS),
                    help="configuração do grupo solvers")
    ap.add_argument("--tempo", type=float, default=600.0, help="limite do solver (s)")
    ap.add_argument("--threads", type=int, default=1)
    ap.add_argument("--extra-args", default="", help="repassado ao bpp-solvers")
    ap.add_argument("--inst-dir", default="data/instancias")
    ap.add_argument("--raw-dir", default="data/raw")
    ap.add_argument("--resultados", default="resultados")
    ap.add_argument("--solucoes", default="resultados/solucoes")
    ap.add_argument("--rodada", default=datetime.now().strftime("%Y%m%d-%H%M%S"),
                    help="mesma rodada = só ressubmete o que falta")
    ap.add_argument("--folga", type=float, default=1.5, help="multiplica --tempo no --time")
    ap.add_argument("--margem", type=float, default=300, help="segundos somados ao --time")
    ap.add_argument("--fator-mem", type=float, default=2.0)
    ap.add_argument("--mem-min", type=int, default=2, help="GB mínimos por job")
    ap.add_argument("--gurobi-simult", type=int, default=2,
                    help="jobs Gurobi simultâneos (sessões da licença; 0 = sem limite)")
    ap.add_argument("--gurobi-espera", type=float, default=300,
                    help="s que o job Gurobi segura a faixa após terminar (token WLS dura 5 min)")
    ap.add_argument("--particao")
    ap.add_argument("--log-dir", default="logs")
    ap.add_argument("--sbatch-args", default="", help="opções extras do sbatch")
    ap.add_argument("--uv", default="uv")
    ap.add_argument("--dry-run", action="store_true", help="só mostra os sbatch")
    submeter(ap.parse_args())


def main_juntar() -> None:
    ap = argparse.ArgumentParser(description="Junta os CSVs parciais de uma rodada SLURM.")
    ap.add_argument("rodada", help="pasta resultados/parcial/<rodada>")
    ap.add_argument("--resultados", default="resultados")
    a = ap.parse_args()
    juntar(a.rodada, a.resultados)


if __name__ == "__main__":
    main()
