"""Opret mappen til en analyse af en fond: funds/<fond>/<analyse>/ med notebook, charts/ og exports/.

    python scripts/ny_analyse.py NEP5 overblik      # standardoverblikket (templates/overblik.ipynb)
    python scripts/ny_analyse.py PSCP4 watchlist    # ny, tom analyse (templates/analyse.ipynb)
    python scripts/ny_analyse.py alle overblik      # for hver fond i databasen
    python scripts/ny_analyse.py alle portefoelje   # ... som analysen har data til

En eksisterende notebook overskrives aldrig.
"""
import argparse
import importlib
import re
from pathlib import Path

ROD = Path(__file__).resolve().parents[1]


def opret(fund_code, analyse):
    mappe = ROD / "funds" / fund_code.lower() / analyse
    notebook = mappe / f"{analyse}.ipynb"
    for under in ("charts", "exports"):
        (mappe / under).mkdir(parents=True, exist_ok=True)
    if notebook.exists():
        print(f"findes allerede: {notebook.relative_to(ROD)}")
        return
    skabelon = ROD / "templates" / f"{analyse}.ipynb"
    if not skabelon.exists():
        skabelon = ROD / "templates" / "analyse.ipynb"
    tekst = skabelon.read_text(encoding="utf-8")
    notebook.write_text(tekst.replace("__FUND_CODE__", fund_code.upper())
                             .replace("__ANALYSE__", analyse), encoding="utf-8")
    print(f"oprettet: {notebook.relative_to(ROD)}  (fra templates/{skabelon.name})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("fond", help="fund_code fra databasen, eller 'alle'")
    ap.add_argument("analyse", help="analysens navn: små bogstaver, tal og _")
    a = ap.parse_args()
    if not re.fullmatch(r"[a-z0-9_]+", a.analyse):
        ap.error("analysens navn må kun bestå af små bogstaver, tal og _")

    from pe_analysis import data          # først her, så --help virker uden databaseadgang
    if a.fond.lower() == "alle":
        # en analyse kan sige, hvilke fonde den har data til (pe_analysis.<analyse>.har_data)
        try:
            har_data = importlib.import_module(f"pe_analysis.{a.analyse}").har_data
        except (ImportError, AttributeError):
            har_data = lambda kode: True
        for kode in data.fonde()["fund_code"]:
            if har_data(kode):
                opret(kode, a.analyse)
            else:
                print(f"springer over: {kode} har ikke data til '{a.analyse}'")
    else:
        opret(data.fond(a.fond)["fund_code"], a.analyse)
