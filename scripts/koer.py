"""Kør en analyses notebook for én eller alle fonde (fra notebookens egen mappe, som i Jupyter).

    python scripts/koer.py overblik            # alle fonde, der har funds/<fond>/overblik/
    python scripts/koer.py overblik NEP5 PSCP4

Notebooken gemmes med output; charts/ og exports/ overskrives.
"""
import subprocess
import sys
from pathlib import Path

ROD = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    analyse, fonde = sys.argv[1], [f.lower() for f in sys.argv[2:]]
    notebooks = sorted(p for p in (ROD / "funds").glob(f"*/{analyse}/{analyse}.ipynb")
                       if not fonde or p.parents[1].name in fonde)
    if not notebooks:
        sys.exit(f"Ingen notebooks fundet for analysen '{analyse}'")
    fejlede = []
    for nb in notebooks:
        print(f"== {nb.relative_to(ROD)}", flush=True)
        r = subprocess.run(
            [sys.executable, "-m", "jupyter", "nbconvert", "--to", "notebook", "--execute",
             "--inplace", "--ExecutePreprocessor.timeout=900", nb.name],
            cwd=nb.parent, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode:
            fejlede.append(nb.parents[1].name)
            print(r.stderr[-3000:])
        else:
            print(f"   ok: {len(list((nb.parent / 'charts').glob('*.png')))} slides, "
                  + ", ".join(p.name for p in sorted((nb.parent / "exports").iterdir())))
    if fejlede:
        sys.exit(f"Fejlede: {', '.join(fejlede)}")
