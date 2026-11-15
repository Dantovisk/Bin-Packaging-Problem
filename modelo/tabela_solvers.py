"""Gera as tabelas da seção "Solução via Solvers" a partir de resultados/solvers.csv.

    python modelo/tabela_solvers.py resultados/solvers.csv                              # Markdown
    python modelo/tabela_solvers.py resultados/solvers.csv --latex --reforcos nenhum    # LaTeX

Com --reforcos, só entra essa configuração e a coluna "Reforços" sai da tabela (é o
formato da tabela de resultados do relatorio/secao_solvers.tex). No LaTeX os números
saem com vírgula decimal, como no texto do relatório.

Se a mesma (instância, método, reforços) aparecer mais de uma vez no CSV, vale a última.
"""

import argparse
import csv

STATUS = {"otimo": "Ótimo", "limite_tempo": "Limite de tempo", "sem_solucao": "Sem solução",
          "inviavel": "Inviável", "erro": "Erro"}
# No LaTeX a coluna Status vira "Ótimo provado?" (Sim/Não), mais fácil de ler no relatório
STATUS_LATEX = {**STATUS, "otimo": "Sim", "limite_tempo": "Não", "sem_solucao": "Não"}
# Cabeçalho em duas linhas no LaTeX: (linha de cima, linha de baixo)
CAB_LATEX = {"Status": ("Ótimo", "provado?"), "Bound": ("Limite", "inferior"),
             "Servidores (T1/T2/T3)": ("Servidores", "T1/T2/T3")}
SOLVER = {"gurobi": "Gurobi", "scip": "SCIP"}


def fmt(v, casas=1, pct=False, virgula=False):
    if v in (None, "", "None"):
        return "–"
    x = float(v)
    s = f"{100 * x:.2f}%" if pct else f"{x:.{casas}f}"
    return s.replace(".", ",") if virgula else s


def carregar(caminho):
    ult = {}
    with open(caminho, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ult[(r["instancia"], r["metodo"], r["reforcos"])] = r
    return sorted(ult.values(), key=lambda r: (int(r["n_vms"]), r["instancia"],
                                               r["reforcos"], r["metodo"]))


def tabela(linhas, latex=False, com_reforcos=True):
    cab = ["Instância", "$n$" if latex else "n", "Solver", "Reforços", "Status", "Custo",
           "Bound", "Gap", "Tempo (s)", "Servidores (T1/T2/T3)"]
    alin = ["l", "r", "l", "l", "l", "r", "r", "r", "r", "c"]
    v = latex
    corpo = []
    for r in linhas:
        corpo.append([r["instancia"], r["n_vms"], SOLVER.get(r["metodo"], r["metodo"]),
                      r["reforcos"], (STATUS_LATEX if latex else STATUS).get(r["status"], r["status"]),
                      fmt(r["custo"], 0, virgula=v), fmt(r["bound"], 1, virgula=v),
                      fmt(r["gap"], pct=True, virgula=v), fmt(r["tempo"], 2, virgula=v),
                      f'{r["servidores_tipo1"] or "–"}/{r["servidores_tipo2"] or "–"}/'
                      f'{r["servidores_tipo3"] or "–"}'])
    if not com_reforcos:
        for lista in [cab, alin] + corpo:
            del lista[3]
    if latex:
        # versão compacta para caber na página: n no lugar do nome da instância
        # e cabeçalho em duas linhas
        for lista in [cab, alin] + corpo:
            del lista[0]
        nc = len(cab)
        cima = [CAB_LATEX.get(c, ("", c))[0] for c in cab]
        baixo = [CAB_LATEX.get(c, ("", c))[1] for c in cab]
        out = ["\\begin{tabular}{" + " ".join(alin) + "}", "\\hline",
               " & ".join(cima) + " \\\\", " & ".join(baixo) + " \\\\", "\\hline"]
        out += [" & ".join(c.replace("_", "\\_").replace("%", "\\%") for c in l) + " \\\\"
                for l in corpo]
        out.append("\\hline")
        if any(r["bound"] in ("", "None") for r in linhas):
            out.append(f"\\multicolumn{{{nc}}}{{l}}{{\\footnotesize --: o solver não chegou "
                       "a calcular um limite inferior.} \\\\")
        out.append("\\end{tabular}")
    else:
        out = ["| " + " | ".join(cab) + " |", "|" + "---|" * len(cab)]
        out += ["| " + " | ".join(l) + " |" for l in corpo]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--latex", action="store_true")
    ap.add_argument("--reforcos", help="filtrar uma configuração (ex.: nenhum)")
    a = ap.parse_args()
    linhas = carregar(a.csv)
    if a.reforcos:
        linhas = [r for r in linhas if r["reforcos"] == a.reforcos]
    print(tabela(linhas, a.latex, com_reforcos=not a.reforcos))


if __name__ == "__main__":
    main()
