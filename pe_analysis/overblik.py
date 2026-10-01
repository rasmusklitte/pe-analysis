"""Overbliksanalysen: samme slides for enhver fond i databasen.

Notebooken i funds/<fond>/overblik/ er bevidst tynd - den vælger fonden og kalder én metode
pr. slide. Al logik ligger her, så ti fonde ikke bliver til ti kopier af grafkoden.

    ob = Overblik("NEP5")          # indlæser, afstemmer og sætter husstilens fond/dato/valuta
    ob.graf_noegletal()            # ... én metode pr. slide, hver gemmer en PNG i charts/
    ob.excel(); ob.deck()

To niveauer, som aldrig lægges sammen (analysis-data-guide.md, afsnit 2):
- Investorniveau (HAR_LP): vores pengestrømme og vores NAV.
- Fondsniveau (HAR_FOND): GP'ens nøgletal og beholdninger for HELE fonden.
En metode, hvis data ikke findes for fonden, skriver hvorfor og springer over.
"""
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Rectangle
from matplotlib.ticker import FuncFormatter, MaxNLocator

from . import data, metrics
from .analyse import Analyse
from . import style as ps
from .deck import byg_deck
from .style import (PPIM_SAGE_DARK, PPIM_SAGE_MID, PPIM_SAGE_LIGHT, PPIM_OLIVE, PPIM_TAUPE,
                    PPIM_TAUPE_LIGHT, PPIM_CREAM, PPIM_RED_MUTED, SLIDE, MX, BOTTOM_FRAC, INK,
                    LINE, GRID, style_ax, add_header, add_footer, source_line, ref_pill,
                    legend_swatches, save, _dk, mult, render_table)

N_TOP = 15            # antal beholdninger, der navngives på koncentrations-sliden
BRO_TOLERANCE = 0.001   # NAV-broens rest under 0,1 % af ultimo-NAV er afrunding i GP'ens opgørelse

BRO_NAVNE = {
    "CA110": "Indbetalinger", "CA120": "Udlodninger", "CA200": "Nettoindtægt",
    "CA210": "Forvaltnings-\nhonorar", "CA220": "Fonds-\nomkostninger",
    "CA230": "Finansielle\nposter", "CA290": "Resultat\n(ikke opdelt)",
    "CA300": "Realiseret\ngevinst/tab", "CA310": "Urealiseret\nværdiændring",
    "CA490": "Øvrige\nbevægelser", "CA400": "Carried\ninterest",
    "RESTAT": "Efterregulering\naf årsultimo", "REST": "Ikke forklaret",
}
BRO_ORDEN = list(BRO_NAVNE)

FLOW_DK = {"CONTRIBUTION": "Indbetaling", "DISTRIBUTION": "Udlodning",
           "WITHHOLDING_TAX": "Kildeskat", "EQUALISATION": "Udligningsrente"}

# Fondsniveauets nøgletal i prioriteret orden: (metric_code, titel, unit). GP'erne rapporterer
# hver deres sæt, så sliden tegner de første fire, der findes helt frem til seneste rapport.
FOND_METRICS = [("FUND_NAV", "Fondens NAV", "CCY"), ("NET_TVPI", "Netto-TVPI", "X"),
                ("NET_DPI", "Netto-DPI", "X"), ("NET_IRR", "Netto-IRR", "PCT"),
                ("GROSS_IRR", "Brutto-IRR", "PCT"), ("PAID_IN", "Indbetalt kapital", "CCY"),
                ("CALLED_PCT", "Indkaldt af tilsagn", "PCT"),
                ("NUMBER_OF_COMPANIES", "Antal selskaber", "COUNT"),
                ("NUMBER_OF_INVESTMENTS", "Antal investeringer", "COUNT"),
                ("DEBT_TO_EBITDA", "Gæld / EBITDA (vægtet)", "X"),
                ("WA_EQUITY_CUSHION", "Egenkapitalpude (vægtet)", "PCT")]
N_FOND_PANELER = 4


def pct(v, dec=1):
    return _dk(v, dec) + " %"


class Overblik(Analyse):
    def __init__(self, fund_code, as_of=None, nav_kolonne="restated_nav",
                 charts="charts", exports="exports"):
        """as_of=None -> seneste NAV-dato (eller seneste fondsrapport, hvis vi ikke er investor).

        nav_kolonne: "restated_nav" (reviderede årsultimoer) eller "nav" (som først rapporteret).
        """
        super().__init__(fund_code, "overblik", charts, exports)
        self.nav_kolonne = nav_kolonne
        self.afstemning = []
        self.advarsler = []      # afvigelser mod GP'ens egne tal; ender som forbehold i decket

        cut = pd.Timestamp(as_of) if as_of else pd.Timestamp.max
        f = lambda df, kol: df[df[kol] <= cut].reset_index(drop=True)
        self.nav = f(data.nav(self.kode), "period_end")
        self.metrics = f(data.fund_metrics(self.kode), "report_date")
        self.holdings = f(data.holdings(self.kode), "report_date")
        self.ca = f(data.capital_account(self.kode), "period_end")

        self.HAR_LP = not self.nav.empty
        self.HAR_FOND = not (self.metrics.empty and self.holdings.empty)
        if not (self.HAR_LP or self.HAR_FOND):
            raise ValueError(f"Ingen godkendte data for {self.kode} i databasen")

        if self.HAR_LP:
            self.as_of = self.nav["period_end"].max()
            # Pengestrømme efter seneste NAV-dato hører til næste opgørelse (som v_fund_summary)
            self.cf = f(data.cash_flows(self.kode), "value_date")
            self.cf = self.cf[self.cf["value_date"] <= self.as_of].reset_index(drop=True)
            self.serie = metrics.kvartalsserie(self.cf, self.nav, nav_kolonne)
            self.nu = self.serie.iloc[-1]
            self.bro = metrics.nav_bro(self.ca, self.as_of)
            self.huller = metrics.manglende_kvartaler(self.serie.index)
            self._afstem(er_seneste=as_of is None)
        else:
            self.as_of = max(d["report_date"].max() for d in (self.metrics, self.holdings)
                             if not d.empty)
            self.cf, self.serie, self.nu, self.bro, self.huller = None, None, None, None, []
            print(f"Ingen investordata for {self.kode} - kun fondsniveau (springer del 1 over)")

        # Beløb vises i mio.; små tilsagn får to decimaler, ellers forsvinder bevægelserne
        stoerst = self.nu["commitment"] if self.HAR_LP else 1e9
        self.dec = 2 if stoerst < 50e6 else 1

        ps.FUND = self.navn
        ps.REPORT_DK = f"{self.as_of:%d.%m.%Y}"
        ps.VALUTA = self.valuta
        ps.KILDE = "PE-databasen, GP'ens opgørelser"
        print(f"{self.kode}: {self.navn} · pr. {ps.REPORT_DK} · {self.valuta} · "
              f"investorniveau: {'ja' if self.HAR_LP else 'nej'} · "
              f"fondsniveau: {'ja' if self.HAR_FOND else 'nej'}")

    # ------------------------------------------------------------------ hjælpere

    def m(self, v, dec=None):
        """Beløb i hele enheder -> tekst i mio. af fondens valuta."""
        return ps.money(v / 1e6, self.dec if dec is None else dec)

    def _afstem(self, er_seneste):
        """Egne tal mod rpt.v_fund_summary. Ingen graf må hvile på tal, der ikke stemmer."""
        if er_seneste:
            sm = data.fund_summary(self.kode)
            sm = sm[sm["as_of"] == self.as_of]
            for navn, egen, view in [
                    ("Indbetalt", self.nu["indbetalt"], sm["paid_in"].sum()),
                    ("Udloddet", self.nu["udloddet"], sm["distributions"].sum()),
                    ("Resttilsagn", self.nu["resttilsagn"], sm["unfunded"].sum())]:
                self.afstemning.append(dict(post=navn, beregnet=egen, kontrol=view,
                                            kilde="rpt.v_fund_summary"))
                assert abs(egen - view) < 0.01, f"{navn} stemmer ikke: {egen} mod {view}"
        if self.bro is not None:
            b = self.bro
            self.afstemning.append(dict(post=f"NAV-bro ({b['basis']}) ultimo",
                                        beregnet=b["ultimo"] - b["rest"], kontrol=b["ultimo"],
                                        kilde="fund.capital_account CA900"))
            if b["basis"].startswith("ITD"):
                bev = b["bevaegelser"].set_index("account_code")["amount"]
                gp_ind, gp_udl = bev.get("CA110", 0.0), bev.get("CA120", 0.0)
                for navn, egen, gp in [("NAV-bro indbetalt", self.nu["indbetalt"], gp_ind),
                                       ("NAV-bro udloddet", -self.nu["udloddet"], gp_udl)]:
                    self.afstemning.append(dict(post=navn, beregnet=egen, kontrol=gp,
                                                kilde="fund.capital_account ITD"))
                # Pengestrømmene mod GP'ens egen akkumulerede opgørelse. Stemmer nettoen, har
                # GP'en blot modregnet (typisk genindkaldelige udlodninger); ellers mangler der
                # meddelelser i databasen, og indbetalt/TVPI/IRR er tilsvarende skæve.
                mio2 = lambda v: f"{_dk(v / 1e6, 2)} mio. {self.valuta}"
                d_ind = self.nu["indbetalt"] - gp_ind
                d_netto = d_ind - (self.nu["udloddet"] + gp_udl)
                if abs(d_netto) > 0.01 * self.nu["indbetalt"]:
                    self.advarsler.append(
                        f"Pengestrømmene i databasen afviger fra GP'ens egen opgørelse: indbetalt "
                        f"er {mio2(self.nu['indbetalt'])} mod GP'ens {mio2(gp_ind)}. Der mangler "
                        f"formentlig meddelelser, så indbetalt, TVPI og IRR skal læses med forbehold.")
                elif abs(d_ind) > 0.01 * self.nu["indbetalt"]:
                    self.advarsler.append(
                        f"GP'ens kapitalkonto viser {mio2(abs(d_ind))} "
                        f"{'mindre' if d_ind > 0 else 'mere'} i både indbetalinger og udlodninger "
                        f"end pengestrømmene, fordi den modregner dem i hinanden. Nettoen er ens.")
        print("Afstemning:")
        for a in self.afstemning:
            afv = a["beregnet"] - a["kontrol"]
            print(f"  {a['post']:<28} {_dk(a['beregnet'], 0):>16}  mod {_dk(a['kontrol'], 0):>16}"
                  f"  ({a['kilde']}){'' if abs(afv) < 1 else f'  afvigelse {_dk(afv, 0)}'}")
        for a in self.advarsler:
            print(f"ADVARSEL: {a}")

    # ------------------------------------------------------------------ del 1: investorniveau

    def graf_noegletal(self):
        """Slide 1: nøgletalstavle."""
        if not self._kraever(self.HAR_LP, "investordata"):
            return
        n = self.nu
        irr = pct(n["irr"] * 100) if pd.notna(n["irr"]) else "–"
        irr_note = "XIRR inkl. NAV, netto" if pd.notna(n["irr"]) else "under ét års historik"
        kort = [
            ("Tilsagn", self.m(n["commitment"]), ""),
            ("Indbetalt", self.m(n["indbetalt"]),
             f"{pct(100 * n['indbetalt'] / n['commitment'], 0)} af tilsagnet"),
            ("Udloddet", self.m(n["udloddet"]),
             f"heraf {self.m(n['genindkaldelig'])} genindkaldelig" if n["genindkaldelig"] else ""),
            ("NAV", self.m(n["nav"]), f"{_dk(n['nav_dkk'] / 1e6, 1)} mio. DKK"
             if self.valuta != "DKK" else ""),
            ("TVPI", mult(n["tvpi"]), f"DPI {mult(n['dpi'])} + RVPI {mult(n['rvpi'])}"),
            ("IRR", irr, irr_note),
            ("Merværdi", self.m(n["mervaerdi"]), "NAV + udloddet − indbetalt"),
            ("Resttilsagn", self.m(n["resttilsagn"]),
             f"{pct(100 * n['resttilsagn'] / n['commitment'], 0)} af tilsagnet"),
        ]
        fig = plt.figure(figsize=SLIDE)
        top = add_header(fig, "Nøgletal for vores investering",
                         f"{self.fond['investorer']} · beløb i {self.valuta} · pr. {ps.REPORT_DK}")
        ax = fig.add_axes([MX, BOTTOM_FRAC + 0.03, 1 - 2 * MX, top - BOTTOM_FRAC - 0.05])
        ax.set_axis_off()
        ax.set_xlim(0, 4)
        ax.set_ylim(0, 2)
        for i, (label, vaerdi, note) in enumerate(kort):
            x, y = i % 4, 1 - i // 4
            ax.add_patch(Rectangle((x + 0.04, y + 0.06), 0.92, 0.86, facecolor=PPIM_CREAM,
                                   edgecolor="none"))
            ax.add_patch(Rectangle((x + 0.04, y + 0.06), 0.012, 0.86, facecolor=PPIM_SAGE_DARK,
                                   edgecolor="none"))
            negativ = label == "Merværdi" and self.nu["mervaerdi"] < 0
            ax.text(x + 0.12, y + 0.76, label.upper(), fontsize=10, fontweight="bold", va="center")
            ax.text(x + 0.12, y + 0.50, vaerdi, fontsize=25 if len(vaerdi) <= 11 else 20,
                    fontweight="bold", va="center",
                    color=PPIM_RED_MUTED if negativ else PPIM_SAGE_DARK)
            ax.text(x + 0.12, y + 0.24, note, fontsize=10.5, va="center")
        self._gem(fig, "noegletal", None, layout=False)

    def graf_kapitalforloeb(self):
        """Slide 2: akkumuleret indbetalt og udloddet (dag for dag) mod NAV pr. opgørelse."""
        if not self._kraever(self.HAR_LP, "investordata"):
            return
        cf, s = self.cf, self.serie
        fig, ax = self._figur(
            "Kapitalforløb: indbetalt, udloddet og NAV",
            f"Akkumulerede pengestrømme og NAV pr. opgørelsesdato · mio. {self.valuta}")
        slut = self.as_of
        for klasse, fortegn, farve in (("CONTRIBUTION", -1, PPIM_TAUPE),
                                       ("DISTRIBUTION", 1, PPIM_SAGE_LIGHT)):
            d = cf[cf["flow_class"] == klasse].groupby("value_date")["amount"].sum().cumsum()
            if d.empty:
                continue
            d = pd.concat([d, pd.Series({slut: d.iloc[-1]})]) * fortegn / 1e6
            ax.step(d.index, d.values, where="post", color=farve, linewidth=2.2)
        ax.plot(s.index, s["nav"] / 1e6, color=PPIM_SAGE_DARK, linewidth=2.2, marker="o",
                markersize=4.5)
        ax.set_ylim(bottom=min(0, ax.get_ylim()[0]))
        self._mio_akse(ax)
        self._tidsakse(ax, list(cf["value_date"]) + list(s.index))
        legend_swatches(ax, [(PPIM_TAUPE, f"Indbetalt  {self.m(self.nu['indbetalt'])}"),
                             (PPIM_SAGE_DARK, f"NAV  {self.m(self.nu['nav'])}"),
                             (PPIM_SAGE_LIGHT, f"Udloddet  {self.m(self.nu['udloddet'])}")],
                        loc="upper left", fontsize=10.5)
        self._gem(fig, "kapitalforloeb", ax)

    def graf_pengestroemme(self):
        """Slide 3: indkald mod udlodninger pr. kvartal, med nettostrømmen som markør."""
        if not self._kraever(self.HAR_LP, "investordata"):
            return
        cf = self.cf[self.cf["flow_class"].isin(["CONTRIBUTION", "DISTRIBUTION"])].copy()
        cf["kvt"] = cf["value_date"].dt.to_period("Q")
        p = (cf.pivot_table(index="kvt", columns="flow_class", values="amount", aggfunc="sum")
             .reindex(columns=["CONTRIBUTION", "DISTRIBUTION"]).fillna(0) / 1e6)
        p = p.reindex(pd.period_range(p.index.min(), self.as_of.to_period("Q"), freq="Q"),
                      fill_value=0)
        x = np.arange(len(p))
        fig, ax = self._figur(
            "Pengestrømme pr. kvartal",
            f"Indbetalinger (negative) og udlodninger (positive), set fra investor · mio. {self.valuta}")
        ax.bar(x, p["CONTRIBUTION"], width=0.72, color=PPIM_TAUPE)
        ax.bar(x, p["DISTRIBUTION"], width=0.72, color=PPIM_SAGE_DARK)
        netto = p.sum(axis=1)
        ax.scatter(x, netto, s=26, color=INK, zorder=4)
        ax.axhline(0, color=LINE, linewidth=0.8)
        datoer = [k.end_time for k in p.index]
        self._kvartalsakse(ax, datoer)
        self._mio_akse(ax)
        legend_swatches(ax, [(PPIM_TAUPE, "Indbetalinger"), (PPIM_SAGE_DARK, "Udlodninger"),
                             (INK, "Netto (prik)")], loc="lower right", fontsize=10.5, ncol=3)
        self._gem(fig, "pengestroemme", ax, " · udligningsrenter og kildeskat ikke medregnet")

    def graf_tvpi(self):
        """Slide 4: TVPI pr. opgørelsesdato, opdelt i DPI (realiseret) og RVPI (urealiseret)."""
        if not self._kraever(self.HAR_LP, "investordata"):
            return
        s = self.serie
        x = np.arange(len(s))
        fig, ax = self._figur(
            "TVPI over tid, opdelt i DPI og RVPI",
            "DPI = udloddet / indbetalt · RVPI = NAV / indbetalt · pr. opgørelsesdato")
        ax.bar(x, s["dpi"], width=0.72, color=PPIM_SAGE_DARK)
        ax.bar(x, s["rvpi"], width=0.72, bottom=s["dpi"], color=PPIM_SAGE_LIGHT)
        hop = 1 if len(s) <= 14 else 2 if len(s) <= 28 else 4
        for i in range(len(s)):
            if (len(s) - 1 - i) % hop == 0 and pd.notna(s["tvpi"].iloc[i]):
                ax.text(i, s["tvpi"].iloc[i], mult(s["tvpi"].iloc[i]), ha="center", va="bottom",
                        fontsize=8.5 if len(s) > 14 else 9.5,
                        fontweight="bold" if i == len(s) - 1 else "normal")
        ax.set_ylim(0, max(1.15, s["tvpi"].max() * 1.12))
        ref_pill(ax, 1.0, "1,00x")
        self._kvartalsakse(ax, list(s.index))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: _dk(v, 2) + "x"))
        legend_swatches(ax, [(PPIM_SAGE_DARK, "DPI (realiseret)"),
                             (PPIM_SAGE_LIGHT, "RVPI (urealiseret)")],
                        loc="upper left", fontsize=10.5, ncol=2)
        self._gem(fig, "tvpi", ax)

    def graf_jkurve(self):
        """Slide 5: J-kurven - akkumuleret nettopengestrøm og nettoværdi (netto + NAV)."""
        if not self._kraever(self.HAR_LP, "investordata"):
            return
        s = self.serie
        fig, ax = self._figur(
            "J-kurve: nettopengestrøm og nettoværdi",
            f"Nettoværdi = akkumuleret nettopengestrøm + NAV, dvs. gevinsten i {self.valuta} "
            f"· mio. {self.valuta}")
        ax.plot(s.index, s["netto_cash"] / 1e6, color=PPIM_TAUPE, linewidth=2.2, marker="o",
                markersize=4)
        v = s["nettovaerdi"] / 1e6
        ax.plot(s.index, v, color=PPIM_SAGE_DARK, linewidth=2.4, marker="o", markersize=4)
        ax.fill_between(s.index, 0, v, where=v >= 0, color=PPIM_SAGE_LIGHT, alpha=0.6,
                        interpolate=True)
        ax.fill_between(s.index, 0, v, where=v < 0, color=ps.PPIM_RED_LIGHT, alpha=0.6,
                        interpolate=True)
        ax.axhline(0, color=LINE, linewidth=0.9)
        self._mio_akse(ax)
        self._tidsakse(ax, list(s.index))
        legend_swatches(ax, [(PPIM_SAGE_DARK, f"Nettoværdi  {self.m(self.nu['nettovaerdi'])}"),
                             (PPIM_TAUPE, f"Akk. nettopengestrøm  {self.m(self.nu['netto_cash'])}")],
                        loc="best", fontsize=10.5)
        self._gem(fig, "jkurve", ax, " · inkl. udligningsrenter, ekskl. kildeskat")

    def gp_irr(self):
        """GP'ens egen netto-IRR pr. dato i pct.: kapitalkontoens MM150, ellers fondsrapportens."""
        mm = self.ca[self.ca["account_code"] == "MM150"].groupby("period_end")["amount"].last()
        fm = self.metrics[(self.metrics["metric_code"] == "NET_IRR")
                          & (self.metrics["unit"] == "PCT")].set_index("report_date")["value"]
        # kapitalkontoens tal er vores eget, men nogle GP'er oplyser det kun på seneste opgørelse
        if len(mm) and len(mm) >= min(len(fm), 2):
            return mm, "vores kapitalkonto"
        return fm, "hele fonden"

    def graf_irr(self):
        """Slide 6: vores beregnede IRR over tid mod GP'ens rapporterede netto-IRR."""
        if not self._kraever(self.HAR_LP, "investordata"):
            return
        irr = (self.serie["irr"] * 100).dropna()
        if not self._kraever(len(irr) >= 2, "IRR-serie (kræver mindst to opgørelser efter et år)"):
            return
        gp, gp_kilde = self.gp_irr()
        gp = gp[gp.index >= irr.index.min()]
        fig, ax = self._figur(
            "IRR siden start, pr. opgørelsesdato",
            "XIRR på vores pengestrømme med NAV som slutværdi · vist fra ét års historik")
        ax.plot(irr.index, irr.values, color=PPIM_SAGE_DARK, linewidth=2.4, marker="o",
                markersize=4.5)
        poster = [(PPIM_SAGE_DARK, f"Beregnet IRR  {pct(irr.iloc[-1])}")]
        if len(gp):
            ax.plot(gp.index, gp.values, color=PPIM_TAUPE, linewidth=1.8, linestyle=(0, (4, 3)),
                    marker="s", markersize=4)
            poster.append((PPIM_TAUPE, f"GP-rapporteret netto-IRR ({gp_kilde})  {pct(gp.iloc[-1])}"))
        ax.axhline(0, color=LINE, linewidth=0.9)
        # De første opgørelser giver en IRR på flere hundrede procent af en lille indbetaling;
        # uden et loft bliver resten af kurven en streg langs bunden.
        alle = pd.concat([irr, gp])
        loft = max(2.5 * irr.median(), 2 * irr.iloc[-1], 10.0)
        note = ""
        if alle.max() > loft or alle.min() < -loft:
            ax.set_ylim(max(alle.min(), -loft) - 1 if alle.min() < 0 else -1, min(alle.max(), loft))
            note = f" · tidlige værdier uden for ±{_dk(loft, 0)} % er skåret af"
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: _dk(v, 0) + " %"))
        self._tidsakse(ax, list(irr.index))
        legend_swatches(ax, poster, loc="upper right", fontsize=10.5)
        self._gem(fig, "irr", ax, note)

    def graf_nav_bro(self):
        """Slide 7: fra primo-NAV til ultimo-NAV efter kapitalkontoens egne linjer."""
        if not self._kraever(self.HAR_LP and self.bro is not None, "kapitalkonto"):
            return
        b = self.bro
        bev = b["bevaegelser"].copy()
        if abs(b["rest"]) > BRO_TOLERANCE * abs(b["ultimo"]):
            print(f"ADVARSEL: NAV-broen efterlader {_dk(b['rest'], 0)} uforklaret")
            bev.loc[len(bev)] = ["REST", b["rest"]]
        bev["orden"] = bev["account_code"].map(lambda k: BRO_ORDEN.index(k))
        bev = bev.sort_values("orden")
        siden_start = b["basis"].startswith("ITD")
        trin = ([] if siden_start else [("Primo-NAV", b["primo"], "total")]) \
            + [(BRO_NAVNE[k], a, "bev") for k, a in zip(bev["account_code"], bev["amount"])] \
            + [("NAV\n" + f"{b['dato']:%d.%m.%Y}", b["ultimo"], "total")]
        periode = "siden start" if siden_start else \
            f"år til dato {b['dato']:%Y}" if b["basis"] == "YTD" else "seneste kvartal"
        fig, ax = self._figur(
            f"NAV-bro {periode}: hvad har flyttet vores NAV",
            f"Kapitalkontoens bevægelser som GP'en opgør dem · mio. {self.valuta}")
        niveau = 0.0
        for i, (navn, beloeb, art) in enumerate(trin):
            v = beloeb / 1e6
            if art == "total":
                ax.bar(i, v, width=0.66, color=PPIM_SAGE_DARK)
                top, niveau = v, v
            else:
                # ind- og udbetalinger er ikke afkast og får en neutral farve
                farve = PPIM_TAUPE_LIGHT if navn in ("Indbetalinger", "Udlodninger") else                     PPIM_SAGE_LIGHT if v >= 0 else PPIM_RED_MUTED
                ax.bar(i, v, width=0.66, bottom=niveau, color=farve)
                top = max(niveau, niveau + v)
                if i + 1 < len(trin):
                    ax.plot([i - 0.33, i + 1.33], [niveau + v] * 2, color=LINE, linewidth=0.7)
                niveau += v
            tekst = _dk(v, self.dec) if art == "total" else \
                ("+" if v >= 0 else "−") + _dk(abs(v), self.dec)
            ax.text(i, top, tekst, ha="center", va="bottom", fontsize=9.5,
                    fontweight="bold" if art == "total" else "normal")
        ax.set_xticks(range(len(trin)), [t[0] for t in trin], fontsize=9.5)
        ax.axhline(0, color=LINE, linewidth=0.8)
        ax.margins(y=0.12)
        self._mio_akse(ax)
        note = " · YTD-opgørelser kædet år for år" if "kædet" in b["basis"] else ""
        self._gem(fig, "nav_bro", ax, note)

    # ------------------------------------------------------------------ del 2: fondsniveau

    def fond_serier(self):
        """De af FOND_METRICS, der har mindst to datoer og når frem til seneste fondsrapport."""
        ud = []
        if self.metrics.empty:
            return ud
        seneste = self.metrics["report_date"].max()
        for kode, titel, unit in FOND_METRICS:
            d = self.metrics[(self.metrics["metric_code"] == kode) & (self.metrics["unit"] == unit)]
            if len(d) >= 2 and d["report_date"].max() == seneste:
                ud.append((titel, unit, d.set_index("report_date")["value"]))
        return ud

    def graf_fond_noegletal(self):
        """Slide 8: GP'ens nøgletal for hele fonden over tid (op til fire paneler)."""
        serier = self.fond_serier()[:N_FOND_PANELER]
        if not self._kraever(serier, "fondsnøgletal over tid"):
            return
        fig, axes = self._figur(
            "Hele fonden: GP'ens nøgletal over tid",
            f"Fondsniveau - alle investorer under ét, ikke vores andel · beløb i mio. {self.valuta}",
            ncols=len(serier))
        for ax, (titel, unit, s) in zip(np.atleast_1d(axes), serier):
            v = s / 1e6 if unit == "CCY" else s
            ax.plot(v.index, v.values, color=PPIM_SAGE_DARK, linewidth=2.2, marker="o",
                    markersize=3.5)
            fmt = {"CCY": lambda x: _dk(x, 0), "X": lambda x: _dk(x, 2) + "x",
                   "PCT": lambda x: _dk(x, 1) + " %", "COUNT": lambda x: _dk(x, 0)}[unit]
            ax.set_title(f"{titel}\n{fmt(v.iloc[-1])}", loc="left", fontsize=12, fontweight="bold")
            ax.yaxis.set_major_locator(MaxNLocator(nbins=6, steps=[1, 2, 5, 10]))
            ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _, f=fmt: f(x)))
            if unit != "CCY" and v.min() < 0:
                ax.axhline(0, color=LINE, linewidth=0.9)
            # en næsten flad serie må ikke zoomes ind, til afrundingen ligner en bevægelse
            min_spaend = {"X": 0.2, "PCT": 4.0}.get(unit, 0)
            if v.max() - v.min() < min_spaend:
                bund = (v.max() + v.min()) / 2 - min_spaend / 2
                bund = max(bund, 0) if v.min() >= 0 else bund
                ax.set_ylim(bund, bund + min_spaend)
            aar = v.index.max().year - v.index.min().year
            ax.xaxis.set_major_locator(mdates.YearLocator(max(1, -(-aar // 3))) if aar >= 2 else
                                       mdates.MonthLocator(bymonth=(6, 12), bymonthday=-1))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y" if aar >= 2 else "%m.%y"))
        self._gem(fig, "fond_noegletal", np.atleast_1d(axes)[0],
                  f" · fondsrapporter til {self.metrics['report_date'].max():%d.%m.%Y}")

    def beholdninger(self):
        """Seneste rapportdatos beholdninger lagt sammen pr. navn i fondens valuta.

        Målt på dagsværdi; oplyser GP'en ikke den pr. beholdning (ATP), bruges tilsagnet.
        Returnerer (Series, dato, målets navn) eller (None, dato, None).
        """
        h = self.holdings
        if h.empty:
            return None, None, None
        dato = h["report_date"].max()
        h = h[h["report_date"] == dato].copy()
        for kol, maal in (("fair_value", "Dagsværdi"), ("commitment", "Tilsagn")):
            if (h[kol] > 0).any():
                break
        else:
            return None, dato, None
        h = h[h[kol] > 0]
        if (h["currency"] != self.valuta).any():           # ATP: beholdninger i lokal valuta
            kurs = data.dkk_kurser(dato)
            h[kol] *= h["currency"].map(kurs) / kurs[self.valuta]
        return h.groupby("name")[kol].sum().sort_values(ascending=False), dato, maal

    def graf_fond_beholdninger(self):
        """Slide 9: de største beholdninger og hvor koncentreret dagsværdien er."""
        b, dato, maal = self.beholdninger()
        if not self._kraever(b is not None and len(b) >= 2,
                             "beholdninger med dagsværdi eller tilsagn"):
            return
        total = b.sum()
        top = b.head(N_TOP)[::-1]
        fig, (ax, ax2) = self._figur(
            "Hele fonden: største beholdninger og koncentration",
            f"{maal} pr. {dato:%d.%m.%Y} · {len(b)} beholdninger, i alt {self.m(total, 0)} "
            f"· fondsniveau, ikke vores andel",
            ncols=2, gridspec_kw=dict(width_ratios=[1.35, 1]))
        ax.barh(range(len(top)), top.values / 1e6, color=PPIM_SAGE_DARK, height=0.7)
        ax.set_yticks(range(len(top)), [n if len(n) <= 46 else n[:44] + "…" for n in top.index],
                      fontsize=9)
        for i, v in enumerate(top.values):
            ax.text(v / 1e6, i, f"  {_dk(v / 1e6, 0 if total > 2e9 else 1)}  "
                    f"({pct(100 * v / total)})", va="center", fontsize=9)
        ax.grid(axis="y", visible=False)
        ax.grid(axis="x", color=GRID, linewidth=0.8)
        ax.set_xlim(0, top.max() / 1e6 * 1.28)
        self._mio_akse(ax, "x")
        ax.set_title(f"De {len(top)} største, mio. {self.valuta}", loc="left", fontsize=12,
                     fontweight="bold")

        kum = 100 * b.cumsum() / total
        ax2.plot(np.arange(1, len(b) + 1), kum.values, color=PPIM_SAGE_DARK, linewidth=2.4)
        ax2.fill_between(np.arange(1, len(b) + 1), 0, kum.values, color=PPIM_SAGE_LIGHT, alpha=0.5)
        for n in (5, 10):
            if len(b) > n:
                ax2.scatter([n], [kum.iloc[n - 1]], color=PPIM_SAGE_DARK, zorder=4, s=36)
                ax2.annotate(f"Top {n}: {pct(kum.iloc[n - 1], 0)}", (n, kum.iloc[n - 1]),
                             xytext=(10, -14), textcoords="offset points", fontsize=10,
                             fontweight="bold")
        ax2.set_ylim(0, 104)
        ax2.set_xlim(1, len(b))
        ax2.xaxis.set_major_locator(MaxNLocator(integer=True))
        ax2.yaxis.set_major_formatter(FuncFormatter(lambda v, _: _dk(v, 0) + " %"))
        ax2.set_xlabel("Antal beholdninger, størst først")
        ax2.set_title(f"Akkumuleret andel af {maal.lower()}", loc="left", fontsize=12,
                      fontweight="bold")
        self._gem(fig, "fond_beholdninger", ax)

    # ------------------------------------------------------------------ tabeller

    def tabel_noegletal(self):
        if not self._kraever(self.HAR_LP, "investordata"):
            return
        n = self.nu
        mio = lambda v: _dk(v / 1e6, 2)
        dkk = self.valuta != "DKK"
        gp, gp_kilde = self.gp_irr()
        gp = gp[gp.index <= self.as_of]
        rows = [
            ["Tilsagn", mio(n["commitment"]), ""],
            ["Indbetalt", mio(n["indbetalt"]), mio(n["indbetalt_dkk"])],
            ["Udloddet", mio(n["udloddet"]), mio(n["udloddet_dkk"])],
            ["  heraf genindkaldelig", mio(n["genindkaldelig"]), ""],
            ["NAV", mio(n["nav"]), mio(n["nav_dkk"])],
            ["Merværdi (NAV + udloddet − indbetalt)", mio(n["mervaerdi"]),
             mio(n["nav_dkk"] + n["udloddet_dkk"] - n["indbetalt_dkk"])],
            ["Resttilsagn", mio(n["resttilsagn"]), ""],
            ["DPI", mult(n["dpi"]), ""],
            ["RVPI", mult(n["rvpi"]), ""],
            ["TVPI", mult(n["tvpi"]), mult((n["nav_dkk"] + n["udloddet_dkk"]) / n["indbetalt_dkk"])],
            ["IRR (beregnet)", pct(n["irr"] * 100) if pd.notna(n["irr"]) else "–", ""],
            [f"IRR (GP-rapporteret, {gp_kilde})", pct(gp.iloc[-1]) if len(gp) else "–", ""],
            ["Første pengestrøm", f"{self.cf['value_date'].min():%d.%m.%Y}", ""],
            ["Antal opgørelser", str(len(self.serie)), ""],
        ]
        kol = ["Nøgletal", f"mio. {self.valuta}", "mio. DKK"]
        if not dkk:
            rows, kol = [r[:2] for r in rows], kol[:2]
        render_table(
            "Nøgletal for vores investering", kol, rows,
            [3.2, 1, 1][:len(kol)], ["left", "right", "right"][:len(kol)], self.C("tabel_noegletal"),
            subtitle=f"{self.fond['investorer']} · pr. {ps.REPORT_DK}"
                     + (" · DKK omregnet med Nationalbankens kurs på hver pengestrøms dato" if dkk else ""),
            highlight_row=9, source=source_line())

    def tabel_kvartaler(self):
        if not self._kraever(self.HAR_LP, "investordata"):
            return
        s = self.serie
        rows = [[f"{d:%d.%m.%Y}", _dk(r.indbetalt / 1e6, 2), _dk(r.udloddet / 1e6, 2),
                 _dk(r.nav / 1e6, 2), _dk(r.mervaerdi / 1e6, 2),
                 mult(r.dpi), mult(r.rvpi), mult(r.tvpi),
                 pct(r.irr * 100) if pd.notna(r.irr) else "–"]
                for d, r in zip(s.index, s.itertuples())]
        render_table(
            "Udvikling pr. opgørelsesdato",
            ["Dato", "Indbetalt", "Udloddet", "NAV", "Merværdi", "DPI", "RVPI", "TVPI", "IRR"],
            rows, [1.2, 1, 1, 1, 1, 0.8, 0.8, 0.8, 0.8], ["left"] + ["right"] * 8,
            self.C("tabel_kvartaler"), subtitle="Akkumulerede tal til og med datoen",
            highlight_row=len(rows) - 1)

    def pengestroemme_pr_dato(self):
        """Pengestrømmene samlet pr. valørdato og type (ét indkald kan have flere komponenter)."""
        g = (self.cf.groupby(["value_date", "flow_class"], sort=False)
             .agg(amount=("amount", "sum"), amount_dkk=("amount_dkk", "sum"),
                  reference=("flow_ref", "first")).reset_index()
             .sort_values(["value_date", "flow_class"]))
        g["type"] = g["flow_class"].map(FLOW_DK)
        return g

    def tabel_pengestroemme(self):
        if not self._kraever(self.HAR_LP, "investordata"):
            return
        g = self.pengestroemme_pr_dato()
        rows = [[f"{r.value_date:%d.%m.%Y}", r.type, str(r.reference or "")[:60],
                 _dk(r.amount / 1e6, 3), _dk(r.amount_dkk / 1e6, 3)] for r in g.itertuples()]
        render_table(
            "Pengestrømme", ["Valørdato", "Type", "GP'ens reference", f"mio. {self.valuta}",
                             "mio. DKK"],
            rows, [1, 1.2, 4, 1.1, 1.1], ["left", "left", "left", "right", "right"],
            self.C("tabel_pengestroemme"),
            subtitle="Set fra investor: betalt til fonden er negativ, modtaget er positiv")

    # ------------------------------------------------------------------ samlet kørsel og eksport

    def koer_alt(self):
        """Alle slides i rækkefølge, så Excel og deck. Notebooken kan også kalde dem enkeltvis."""
        for f in (self.graf_noegletal, self.graf_kapitalforloeb, self.graf_pengestroemme,
                  self.graf_tvpi, self.graf_jkurve, self.graf_irr, self.graf_nav_bro,
                  self.graf_fond_noegletal, self.graf_fond_beholdninger,
                  self.tabel_noegletal, self.tabel_kvartaler, self.tabel_pengestroemme):
            f()
        self.excel()
        return self.deck()

    def excel(self):
        """Alle tabellerne bag graferne i ét regneark, så tallene kan efterprøves række for række."""
        ark = {}
        if self.HAR_LP:
            ark["Kvartalsserie"] = self.serie.reset_index().rename(columns={
                "period_end": "Dato", "commitment": "Tilsagn", "indbetalt": "Indbetalt",
                "udloddet": "Udloddet", "genindkaldelig": "Heraf genindkaldelig", "nav": "NAV",
                "netto_cash": "Akk. nettopengestrøm", "indbetalt_dkk": "Indbetalt DKK",
                "udloddet_dkk": "Udloddet DKK", "nav_dkk": "NAV DKK", "irr": "IRR",
                "dpi": "DPI", "rvpi": "RVPI", "tvpi": "TVPI", "resttilsagn": "Resttilsagn",
                "mervaerdi": "Merværdi", "nettovaerdi": "Nettoværdi"})
            ark["Pengestrømme"] = self.cf[[
                "value_date", "notice_date", "investor_code", "account_code", "account_name",
                "flow_class", "is_recallable", "amount", "currency", "fx_rate", "amount_dkk",
                "flow_ref", "file_name"]]
            ark["NAV"] = self.nav[["period_end", "investor_code", "nav", "restatement",
                                   "restated_nav", "currency", "commitment", "fx_rate", "nav_dkk",
                                   "restated_nav_dkk"]]
            if self.bro is not None:
                b = self.bro
                bro = b["bevaegelser"].copy()
                bro["post"] = bro["account_code"].map(BRO_NAVNE).str.replace("-\n", "").str.replace("\n", " ")
                bro = pd.concat([
                    pd.DataFrame([dict(account_code="CA100", post="Primo-NAV", amount=b["primo"])]),
                    bro,
                    pd.DataFrame([dict(account_code="", post="Ikke forklaret", amount=b["rest"]),
                                  dict(account_code="CA900", post=f"Ultimo-NAV {b['dato']:%d.%m.%Y}",
                                       amount=b["ultimo"])])], ignore_index=True)
                bro["basis"] = b["basis"]
                ark["NAV-bro"] = bro[["account_code", "post", "amount", "basis"]]
            ark["Afstemning"] = pd.DataFrame(self.afstemning).assign(
                afvigelse=lambda d: d["beregnet"] - d["kontrol"])
        if not self.metrics.empty:
            ark["Fondsnøgletal (hele fonden)"] = self.metrics.pivot_table(
                index="report_date", columns="metric_code", values="value").reset_index()
        if not self.holdings.empty:
            h = self.holdings
            ark["Beholdninger (hele fonden)"] = h[h["report_date"] == h["report_date"].max()] \
                .drop(columns=["fund_code", "fund_name", "document_id"]).dropna(axis=1, how="all")
        sti = self._eksportsti("xlsx")
        with pd.ExcelWriter(sti, engine="openpyxl", datetime_format="DD-MM-YYYY") as xl:
            for navn, df in ark.items():
                df.to_excel(xl, sheet_name=navn[:31], index=False)
                ws = xl.sheets[navn[:31]]
                for kol in ws.columns:
                    ws.column_dimensions[kol[0].column_letter].width = min(
                        48, max(12, max(len(str(c.value)) for c in kol[:50] if c.value is not None) + 2))
        print(f"gemt: {sti}  ({len(ark)} ark)")
        return sti

    def hovedpunkter(self):
        """Dækkets tekst regnes ud her i stedet for at blive skrevet af - så følger den data."""
        punkter = []
        if self.HAR_LP:
            n, s = self.nu, self.serie
            punkter.append(
                f"{self.navn} står pr. {ps.REPORT_DK} i en TVPI på {mult(n['tvpi'])}: "
                f"{mult(n['dpi'])} er udloddet (DPI), og {mult(n['rvpi'])} står som NAV (RVPI). "
                f"Merværdien er {self.m(n['mervaerdi'])} på {self.m(n['indbetalt'])} indbetalt.")
            punkter.append(
                f"Af tilsagnet på {self.m(n['commitment'])} er {self.m(n['indbetalt'])} indbetalt "
                f"({pct(100 * n['indbetalt'] / n['commitment'], 0)}). Resttilsagnet er "
                f"{self.m(n['resttilsagn'])}"
                + (f", inklusive {self.m(n['genindkaldelig'])} genindkaldelige udlodninger."
                   if n["genindkaldelig"] else ".")
                + (" Indbetalt overstiger tilsagnet, fordi genindkaldte udlodninger er indbetalt igen."
                   if n["indbetalt"] > n["commitment"] else ""))
            if pd.notna(n["irr"]):
                gp, gp_kilde = self.gp_irr()
                gp = gp[gp.index <= self.as_of]
                punkter.append(
                    f"IRR siden første indbetaling ({self.cf['value_date'].min():%d.%m.%Y}) er "
                    f"{pct(n['irr'] * 100)} efter omkostninger"
                    + (f"; GP'en rapporterer {pct(gp.iloc[-1])} ({gp_kilde}, "
                       f"pr. {gp.index[-1]:%d.%m.%Y})." if len(gp) else "."))
            else:
                punkter.append("Investeringen er under ét år gammel, så en annualiseret IRR er "
                               "endnu ikke meningsfuld og vises ikke.")
            foer = s[s.index <= self.as_of - pd.DateOffset(months=11)]
            if len(foer):
                f = foer.iloc[-1]
                punkter.append(
                    f"Siden {foer.index[-1]:%d.%m.%Y} er TVPI gået fra {mult(f['tvpi'])} til "
                    f"{mult(n['tvpi'])}, og merværdien er ændret med "
                    f"{self.m(n['mervaerdi'] - f['mervaerdi'])}. I samme periode er der indbetalt "
                    f"{self.m(n['indbetalt'] - f['indbetalt'])} og udloddet "
                    f"{self.m(n['udloddet'] - f['udloddet'])}.")
        serier = self.fond_serier()[:N_FOND_PANELER]
        if serier:
            vis = {"CCY": lambda v: self.m(v, 0), "X": mult, "PCT": pct,
                   "COUNT": lambda v: _dk(v, 0)}
            punkter.append(
                f"For hele fonden rapporterer GP'en pr. {self.metrics['report_date'].max():%d.%m.%Y}: "
                + ", ".join(f"{t[0].lower() + t[1:]} {vis[u](v.iloc[-1])}" for t, u, v in serier) + ".")
        b, dato, maal = self.beholdninger()
        if b is not None and len(b) >= 5:
            punkter.append(
                f"Hele fonden har pr. {dato:%d.%m.%Y} {len(b)} beholdninger; de fem største udgør "
                f"{pct(100 * b.head(5).sum() / b.sum(), 0)} målt på {maal.lower()}.")
        return punkter

    def forbehold(self):
        punkter = list(self.advarsler)
        if self.HAR_LP:
            punkter.append(
                "Investorniveau er vores egne pengestrømme (kapitalindkald og udlodningsmeddelelser) "
                "og NAV fra GP'ens kapitalkontoopgørelser. Udlodninger er brutto; udligningsrenter "
                "ved sen indtræden indgår ikke i indbetalt/udloddet, og kildeskat trækkes ikke fra.")
            punkter.append(
                "IRR er XIRR (faktisk/365) på pengestrømmene med NAV som slutværdi, inklusive "
                "udligningsrenter og eksklusive kildeskat. Den vises først efter ét års historik.")
            if self.nav_kolonne == "restated_nav" and self.nav["restatement"].fillna(0).ne(0).any():
                punkter.append(
                    "NAV ved årsultimo er den reviderede værdi (GP'ens efterregulering lagt til "
                    "den først rapporterede Q4-NAV). De øvrige kvartaler er som rapporteret.")
            if self.huller:
                punkter.append(
                    "Der mangler opgørelser for " + ", ".join(f"{d:%d.%m.%Y}" for d in self.huller)
                    + ". Graferne springer disse datoer over; pengestrømmene er med alligevel.")
            if self.bro is not None and not self.bro["basis"].startswith("ITD"):
                punkter.append(
                    "NAV-broen dækker kun " + ("år til dato" if self.bro["basis"] == "YTD"
                                               else "seneste kvartal")
                    + ", fordi opgørelserne ikke rækker ubrudt tilbage til fondens start.")
        if self.HAR_FOND:
            punkter.append(
                "Slides mærket \"hele fonden\" er GP'ens tal for alle investorer under ét, fra "
                "fondsrapporterne. De kan ikke lægges sammen med vores egne tal, og hvilke "
                "nøgletal der findes, afhænger af hvad den enkelte GP rapporterer.")
        if not self.HAR_LP:
            punkter.append("Ingen af vores investorer er i fonden, så decket har kun fondsniveau.")
        punkter.append("NAV og dagsværdier er GP'ens egne værdiansættelser og ikke realiserede.")
        return punkter

    def deck(self):
        """Alle slides samlet i ét deck på PPIM-masteren."""
        kandidater = [
            ("Overblik", ["noegletal"]),
            ("Kapitalforløb", ["kapitalforloeb", "pengestroemme"]),
            ("Afkast", ["tvpi", "jkurve", "irr"]),
            ("NAV-bro", ["nav_bro"]),
            ("Hele fonden", ["fond_noegletal", "fond_beholdninger"]),
            ("Tabeller", ["tabel_noegletal", "tabel_kvartaler", "tabel_pengestroemme"]),
        ]
        sektioner = [dict(titel=t, slides=s) for t, navne in kandidater
                     if (s := self._slides(*navne))]
        fakta = None
        if self.HAR_LP:
            n = self.nu
            fakta = [("TVPI", mult(n["tvpi"])),
                     ("IRR", pct(n["irr"] * 100)) if pd.notna(n["irr"])
                     else ("Indbetalt", self.m(n["indbetalt"])),
                     ("NAV", self.m(n["nav"]))]
        return byg_deck(
            self._eksportsti("pptx"), titel=self.navn, undertitel=f"Overblik pr. {ps.REPORT_DK}",
            sektioner=sektioner, fakta=fakta,
            tekstslides=[t for t in (dict(titel="Hovedpunkter", punkter=self.hovedpunkter()),
                                     dict(titel="Metode og forbehold", punkter=self.forbehold()))
                         if t["punkter"]])
