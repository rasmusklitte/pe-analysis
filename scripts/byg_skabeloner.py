"""Skriv notebook-skabelonerne i templates/ (overblik, portefoelje, afkast og analyse).

Skabelonerne vedligeholdes her som kode, fordi en .ipynb er besværlig at rette i hånden.
Kør scriptet efter en ændring; eksisterende notebooks i funds/ røres ikke.

    python scripts/byg_skabeloner.py
"""
from pathlib import Path

import nbformat
from nbformat.v4 import new_code_cell as code
from nbformat.v4 import new_markdown_cell as md
from nbformat.v4 import new_notebook

ROD = Path(__file__).resolve().parents[1]


def gem(celler, navn):
    nb = new_notebook(cells=celler, metadata={
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"}})
    for i, c in enumerate(nb.cells):
        c["id"] = f"c{i:02d}"
    sti = ROD / "templates" / navn
    sti.parent.mkdir(exist_ok=True)
    nbformat.write(nb, sti)
    print(f"gemt: {sti.relative_to(ROD)}  ({len(celler)} celler)")


OVERBLIK = [
    md("""# __FUND_CODE__ – overblik

Standardoverblikket for én fond, direkte fra PE-databasen: vores kapitalforløb, afkast og NAV-bro
(investorniveau) samt GP'ens nøgletal og beholdninger for hele fonden (fondsniveau).

Al logik ligger i `pe_analysis/overblik.py`; notebooken vælger kun fonden og kalder én metode pr.
slide. Hver metode gemmer en PNG i `charts/`, og de sidste to celler skriver Excel og PowerPoint
til `exports/`.

> En metode, hvis data ikke findes for fonden, skriver hvorfor og springer over – decket bygges af
> de slides, der blev tegnet."""),
    code("from pe_analysis.overblik import Overblik"),
    md("## Konfiguration\n\nDe eneste værdier, der er tænkt redigeret."),
    code('''FUND_CODE   = "__FUND_CODE__"
AS_OF       = None             # None = seneste NAV-dato; ellers fx "2025-12-31"
NAV_KOLONNE = "restated_nav"   # reviderede årsultimoer; "nav" = som først rapporteret'''),
    md("""## Indlæsning og afstemning

Egne tal afstemmes mod `rpt.v_fund_summary` og kapitalkontoen, før noget tegnes."""),
    code("ob = Overblik(FUND_CODE, as_of=AS_OF, nav_kolonne=NAV_KOLONNE)"),
    md("# Del 1: Vores investering (investorniveau)\n\n## 1. Nøgletal"),
    code("ob.graf_noegletal()"),
    md("## 2. Kapitalforløb"),
    code("ob.graf_kapitalforloeb()"),
    code("ob.graf_pengestroemme()"),
    md("## 3. Afkast\n\nTVPI opdelt i DPI og RVPI, J-kurven og IRR over tid."),
    code("ob.graf_tvpi()"),
    code("ob.graf_jkurve()"),
    code("ob.graf_irr()"),
    md("""## 4. NAV-bro

Hvad har flyttet vores NAV: ind- og udbetalinger, resultat, honorar og carried interest, som GP'en
selv opgør det."""),
    code("ob.graf_nav_bro()"),
    md("""# Del 2: Hele fonden (fondsniveau)

GP'ens tal for alle investorer under ét. De lægges aldrig sammen med tallene i del 1."""),
    code("ob.graf_fond_noegletal()"),
    code("ob.graf_fond_beholdninger()"),
    md("# Tabeller"),
    code("ob.tabel_noegletal()"),
    code("ob.tabel_kvartaler()"),
    code("ob.tabel_pengestroemme()"),
    md("# Eksport\n\nExcel med alle tabellerne bag graferne, og ét deck på PPIM-masteren."),
    code("ob.excel()"),
    code("ob.deck()"),
]

ANALYSE = [
    md("# __FUND_CODE__ – __ANALYSE__\n\n*Beskriv hvad analysen skal svare på, og hvem der skal læse den.*"),
    code('''import re
import numpy as np
import pandas as pd
from pathlib import Path
import matplotlib.pyplot as plt

from pe_analysis import data, metrics
from pe_analysis import style as ps
from pe_analysis.style import (
    PPIM_SAGE_DARK, PPIM_SAGE_MID, PPIM_SAGE_LIGHT, PPIM_OLIVE, PPIM_BROWN, PPIM_TAUPE,
    PPIM_TAUPE_LIGHT, PPIM_TERRACOTTA, PPIM_CREAM, PPIM_BEIGE, PPIM_RED_MUTED, PPIM_RED_LIGHT,
    SLIDE, MX, BOTTOM_FRAC, INK, LINE, GRID, style_ax, add_header, add_footer, source_line,
    ref_pill, ref_pill_v, legend_swatches, save, _dk, money, mult, render_table,
)
from pe_analysis.deck import byg_deck'''),
    md("## Konfiguration"),
    code('''FUND_CODE = "__FUND_CODE__"
PRAEFIKS  = f"{FUND_CODE.lower()}___ANALYSE__"   # præfiks på alle filer i charts/ og exports/

Path("charts").mkdir(exist_ok=True)
Path("exports").mkdir(exist_ok=True)
C = lambda navn: str(Path("charts") / f"{PRAEFIKS}_{navn}.png")'''),
    md("""## Indlæsning

Se `analysis-data-guide.md` for viewene. Investorniveau (`cash_flows`, `nav`) og fondsniveau
(`fund_metrics`, `holdings`, `breakdown`) må ikke lægges sammen."""),
    code('''fond = data.fond(FUND_CODE)
holdings = data.holdings(FUND_CODE)
REPORT_DATE = holdings["report_date"].max()

# Husstilen læser fond, dato og valuta som modulattributter (sidehoved, kildelinje, money())
ps.FUND = fond["fund_name"]
ps.REPORT_DK = f"{REPORT_DATE:%d.%m.%Y}"
ps.VALUTA = fond["currency"]
ps.KILDE = "PE-databasen, GP'ens fondsrapporter"
print(f"{FUND_CODE}: {len(holdings)} beholdningslinjer, seneste rapport {ps.REPORT_DK}")'''),
    md("""## 1. Første graf

Mønsteret for et slide: figur i 16:9, sidehoved, layout inden for sidehovedet, kildelinje, `save`."""),
    code('''d = (holdings[holdings["report_date"] == REPORT_DATE].groupby("name")["fair_value"].sum()
     .sort_values(ascending=False).head(10)[::-1] / 1e6)

fig, ax = plt.subplots(figsize=SLIDE)
style_ax(ax)
top = add_header(fig, "De ti største beholdninger", f"Dagsværdi i mio. {ps.VALUTA} · hele fonden")
ax.barh(d.index, d.values, color=PPIM_SAGE_DARK)
fig.tight_layout(rect=[MX, BOTTOM_FRAC, 1 - MX, top])
add_footer(fig, source_line(), ax=ax)
save(fig, C("stoerste"))
plt.show()'''),
    md("""## Præsentation

Højst syv sektioner (agenda-layoutet har syv rækker). Tallene i tekstslides regnes ud, de skrives
ikke af."""),
    code('''byg_deck(
    f"exports/{PRAEFIKS}_{REPORT_DATE:%d%m%Y}.pptx",
    titel=FUND_CODE, undertitel=f"__ANALYSE__ pr. {ps.REPORT_DK}",
    sektioner=[{"titel": "Beholdninger", "slides": [C("stoerste")]}],
)'''),
]

PF_TEKST = {
    "Overblik og værdibro": "Hvor står fonden, og hvor meget af værdien er kasse? TVPI alene siger ikke, "
                            "om afkastet er tjent hjem eller lovet.",
    "Struktur": "Hvad består porteføljen af, og hvad betaler de enkelte dele sig i? For PSCP er det "
                "kapitalstrukturen (instrumenttype og kapitalgruppe), for NEP investeringstypen.",
    "Afkastspredning, tab og koncentration": "En poolet multipel kan dække over en jævn portefølje eller "
                                             "nogle få store gevinster oven på en stribe tab.",
    "Afkast mod tid": "Multipel og IRR belønner to forskellige ting. Periodeafkastet (Modified Dietz) er "
                      "det eneste sted, der findes et procentafkast for en periode.",
    "Vintage og realiseringstakt": "Hvornår blev kapitalen sat i arbejde, og hvor moden er hver årgang?",
    "Porteføljen i dag": "De urealiserede positioner er den del af track record'et, der endnu ikke er "
                         "afgjort - og den hviler på GP'ens egne dagsværdier.",
    "Nøgletal i tabelform": "De samme tal som graferne, men til at læse i.",
}


def portefoelje_celler():
    from pe_analysis.portefoelje.eksport import SLIDES     # én liste styrer både deck og notebook
    celler = [
        md("""# __FUND_CODE__ – porteføljeanalyse

Hvor kommer fondens afkast fra, hvad koster det i risiko, og hvor sikkert er det? Analysen er
**fondsniveau**: hele fondens beholdninger, brutto for honorar og carry, fra
`rpt.v_portfolio_holding` - ikke vores andel.

Al logik ligger i `pe_analysis/portefoelje/`; notebooken vælger fonden og kalder én metode pr.
slide. Hver metode gemmer en PNG i `charts/`, og de sidste celler skriver Excel og PowerPoint
til `exports/`.

> Hvilke slides der tegnes, afgøres af fondens data. En metode, der mangler det, den skal bruge
> (IRR pr. handel, exit-datoer, instrumenttype ...), skriver hvorfor og springer over."""),
        code("from pe_analysis.portefoelje import Portefoelje"),
        md("## Konfiguration"),
        code('''FUND_CODE = "__FUND_CODE__"
AS_OF     = None      # None = seneste fondsrapport; ellers fx "2025-12-31"'''),
        md("""## Indlæsning og afstemning

Beholdningerne beriges (ét navn pr. selskab, instrumenttype, gruppe, vintage) og afstemmes: hver
dimension skal summere til rapportens totaler, og positionerne til fondens egen ændring."""),
        code("pf = Portefoelje(FUND_CODE, as_of=AS_OF)"),
    ]
    for nr, (titel, metoder) in enumerate(SLIDES, 1):
        celler.append(md(f"# {nr}. {titel}\n\n{PF_TEKST[titel]}"))
        celler += [code(f"pf.{m}()") for m in metoder]
    celler += [md("# Eksport\n\nExcel med alle tabellerne bag graferne, og ét deck på PPIM-masteren."),
               code("pf.excel()"), code("pf.deck()")]
    return celler


AF_TEKST = {
    "Periodeafkast": "Hvad har investeringen givet pr. kvartal, over 12 måneder og pr. horisont? "
                     "Værdiskabelse er ændringen i NAV plus udlodninger minus indbetalinger; "
                     "procenten er Modified Dietz på de faktiske valørdatoer.",
    "Afkastets kilder og omkostninger": "Kapitalkontoens linjer lagt sammen siden start: hvad er "
                                        "indtægt, realiseret og urealiseret, og hvor meget af "
                                        "bruttoresultatet går til honorar, omkostninger og carry?",
    "Kapitalens anvendelse": "Hvad er indkaldene gået til, hvad består udlodningerne af, og hvor "
                             "meget af tilsagnet står tilbage?",
    "Valuta": "Afkastet i DKK delt i fondens afkast og valutaens bidrag. Kun fonde i anden valuta.",
    "Tabeller": "De samme tal som graferne, men til at læse i.",
}


def afkast_celler():
    from pe_analysis.afkast.eksport import SLIDES     # én liste styrer både deck og notebook
    celler = [
        md("""# __FUND_CODE__ – afkastanalyse

Hvad har vores investering givet pr. periode, hvor kommer resultatet fra, hvad koster
forvaltningen, og hvad er afkastet i DKK? Analysen er **investorniveau**: vores pengestrømme, vores
NAV og vores kapitalkonto, efter honorar og carry.

Al logik ligger i `pe_analysis/afkast/`; notebooken vælger fonden og kalder én metode pr. slide.
Hver metode gemmer en PNG i `charts/`, og de sidste celler skriver Excel og PowerPoint til
`exports/`.

> Hvilke slides der tegnes, afgøres af fondens data. En metode, der mangler det, den skal bruge
> (honorar udskilt i kapitalkontoen, indkald opdelt efter formål, anden valuta end DKK ...), skriver
> hvorfor og springer over."""),
        code("from pe_analysis.afkast import Afkast"),
        md("## Konfiguration"),
        code('''FUND_CODE   = "__FUND_CODE__"
AS_OF       = None             # None = seneste NAV-dato; ellers fx "2025-12-31"
NAV_KOLONNE = "restated_nav"   # reviderede årsultimoer; "nav" = som først rapporteret'''),
        md("""## Indlæsning og afstemning

Perioderne skal summere til nettoresultatet, kapitalkontoens linjer til NAV, og valutabroens led
til værdien i DKK, før noget tegnes."""),
        code("af = Afkast(FUND_CODE, as_of=AS_OF, nav_kolonne=NAV_KOLONNE)"),
    ]
    for nr, (titel, metoder) in enumerate(SLIDES, 1):
        celler.append(md(f"# {nr}. {titel}\n\n{AF_TEKST[titel]}"))
        celler += [code(f"af.{m}()") for m in metoder]
    celler += [md("# Eksport\n\nExcel med alle tabellerne bag graferne, og ét deck på PPIM-masteren."),
               code("af.excel()"), code("af.deck()")]
    return celler


if __name__ == "__main__":
    gem(afkast_celler(), "afkast.ipynb")
    gem(OVERBLIK, "overblik.ipynb")
    gem(ANALYSE, "analyse.ipynb")
    gem(portefoelje_celler(), "portefoelje.ipynb")
