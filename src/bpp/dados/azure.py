"""Download do vmtable do Azure Public Dataset v1 e geração das instâncias reais.

Cada instância `instancia_<N>_vms.csv` são as N primeiras VMs do vmtable, só com as
colunas `vmid`, `vmcorecount`, `vmmemory`. O `.gz` (~155 MB) só é baixado quando
alguma instância pedida ainda não existe.

    bpp-dataset --n 50 100 500 1000 2000
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.request
from pathlib import Path

import pandas as pd

URL = ("https://github.com/Azure/AzurePublicDataset/releases/download/"
       "dataset-v1/trace_data_vmtable_vmtable.csv.gz")
ARQUIVO = "trace_data_vmtable_vmtable.csv.gz"
RAW_DIR = Path("data/raw")
INST_DIR = Path("data/instancias")

COLUNAS = ["vmid", "subscriptionid", "deploymentid", "vmcreated", "vmdeleted",
           "max_cpu", "avg_cpu", "p95_cpu", "vmcategory", "vmcorecount", "vmmemory"]
COLUNAS_BPP = ["vmid", "vmcorecount", "vmmemory"]

PADRAO_INSTANCIA = re.compile(r"instancia_(\d+)_vms\.csv$")


class AzureVMTable:
    def __init__(self, raw_dir: str | Path = RAW_DIR, inst_dir: str | Path = INST_DIR,
                 url: str = URL):
        self.raw_dir = Path(raw_dir)
        self.inst_dir = Path(inst_dir)
        self.url = url

    @property
    def arquivo(self) -> Path:
        return self.raw_dir / ARQUIVO

    def caminho_instancia(self, n: int) -> Path:
        return self.inst_dir / f"instancia_{n}_vms.csv"

    def baixar(self, forcar: bool = False) -> Path:
        """Baixa o vmtable se ainda não estiver em `raw_dir`."""
        if self.arquivo.exists() and not forcar:
            return self.arquivo
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        parcial = self.arquivo.with_name(self.arquivo.name + ".part")
        print(f"Baixando {self.url}\n  -> {self.arquivo}", file=sys.stderr)
        with urllib.request.urlopen(self.url) as resp, open(parcial, "wb") as f:
            total = int(resp.headers.get("Content-Length") or 0)
            feito = 0
            while bloco := resp.read(1 << 20):
                f.write(bloco)
                feito += len(bloco)
                _progresso(feito, total)
        print(file=sys.stderr)
        if total and feito != total:
            parcial.unlink(missing_ok=True)
            raise OSError(f"download incompleto: {feito} de {total} bytes")
        # .part + rename: download interrompido nunca deixa um .gz truncado no lugar
        parcial.replace(self.arquivo)
        return self.arquivo

    def particionar(self, n: int) -> Path:
        """Grava as N primeiras VMs do vmtable em `instancia_<N>_vms.csv`."""
        bruto = pd.read_csv(self.baixar(), names=COLUNAS, nrows=n)
        destino = self.caminho_instancia(n)
        destino.parent.mkdir(parents=True, exist_ok=True)
        bruto[COLUNAS_BPP].to_csv(destino, index=False)
        return destino

    def garantir_instancia(self, n: int, forcar: bool = False) -> Path:
        destino = self.caminho_instancia(n)
        if forcar or not destino.exists():
            self.particionar(n)
            print(f"gerada {destino}", file=sys.stderr)
        return destino


def garantir_csv(caminho: str | Path, raw_dir: str | Path = RAW_DIR) -> Path:
    """Se `caminho` é uma instância real ausente, gera a partir do dataset."""
    caminho = Path(caminho)
    m = PADRAO_INSTANCIA.search(caminho.name)
    if caminho.exists() or not m:
        return caminho
    return AzureVMTable(raw_dir, caminho.parent).garantir_instancia(int(m.group(1)))


def _progresso(feito: int, total: int) -> None:
    mb = feito / 2**20
    msg = f"\r  {mb:7.1f} MB" + (f" / {total / 2**20:.1f} MB ({100 * feito / total:5.1f}%)"
                                 if total else "")
    print(msg, end="", file=sys.stderr, flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, nargs="*", default=[],
                    help="tamanhos das instâncias (sem --n: só baixa o dataset)")
    ap.add_argument("--raw-dir", default=str(RAW_DIR))
    ap.add_argument("--inst-dir", default=str(INST_DIR))
    ap.add_argument("--url", default=URL)
    ap.add_argument("--forcar", action="store_true",
                    help="regera as instâncias mesmo se já existirem")
    a = ap.parse_args()

    ds = AzureVMTable(a.raw_dir, a.inst_dir, a.url)
    if not a.n:
        print(ds.baixar())
    for n in a.n:
        print(ds.garantir_instancia(n, forcar=a.forcar))


if __name__ == "__main__":
    main()
