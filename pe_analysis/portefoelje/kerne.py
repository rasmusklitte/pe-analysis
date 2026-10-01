"""Porteføljeanalysens kerne: indlæsning, berigelse, aggregater og afstemning.

Alt er FONDSNIVEAU - hele fondens beholdninger, brutto for honorar og carry, som GP'en
rapporterer dem i rpt.v_portfolio_holding. Beløb regnes om til mio. af fondens valuta her.

Hvilke slides der kan tegnes, afgøres af kolonnerne og ikke af fondens navn. HAR_*-flagene
sættes én gang på seneste rapportdato, og hver grafmetode spørger dem.
"""
import textwrap

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import FancyBboxPatch
from matplotlib.ticker import FuncFormatter
from matplotlib.transforms import blended_transform_factory

from .. import data, fondskonfig
from .. import style as ps
from ..analyse import Analyse
from ..fondskonfig import MAKS_GRUPPER, MIN_MOVE, VALUTATEGN
from ..style import (PPIM_SAGE_DARK, PPIM_SAGE_MID, PPIM_SAGE_LIGHT, PPIM_OLIVE, PPIM_BROWN,
                     PPIM_TAUPE, PPIM_TAUPE_LIGHT, PPIM_TERRACOTTA, PPIM_CREAM, PPIM_BEIGE,
                     PPIM_RED_MUTED, MX, BOTTOM_FRAC, BG, INK, MUTED, _dk, money, mult,
                     add_header, add_footer, source_line, save)

F_DPI, F_RVPI = PPIM_SAGE_DARK, PPIM_SAGE_LIGHT      # realiseret / urealiseret
F_POS, F_NEG = PPIM_SAGE_DARK, PPIM_RED_MUTED        # gevinst / tab
F_POS_LYS, F_NEG_LYS = PPIM_SAGE_LIGHT, "#D6BCBC"    # samme fortegn, lysere tone: år til dato
GRUPPE_PALET = [PPIM_SAGE_DARK, PPIM_OLIVE, PPIM_TAUPE, PPIM_TERRACOTTA, PPIM_BROWN,
                PPIM_TAUPE_LIGHT, PPIM_SAGE_MID, PPIM_BEIGE]

MULT = FuncFormatter(lambda v, _: _dk(v, 1) + "x")
PROC = FuncFormatter(lambda v, _: _dk(v * 100, 0) + " %")
PROC1 = FuncFormatter(lambda v, _: _dk(v * 100, 1) + " %")

NUM = ["invested", "proceeds", "fair_value", "total_value"]


def pct(v, dec=1):
    """Andel (0,157) som tekst: 15,7 %."""
    return "–" if pd.isna(v) else _dk(v * 100, dec) + " %"


def dmoney(v, dec=1, enhed=False):
    """Ændring i mio. med fortegn. Under MIN_MOVE skrives "≈ 0": "+€0,0m" ligner en retning,
    der ikke er der.

    En valuta uden tegn ("12,3 mio. DKK") er for lang til en søjleetiket, så i grafer og
    tabeller skrives kun tallet - aksen eller kolonnen bærer enheden. enhed=True til løbende tekst."""
    if pd.isna(v):
        return "–"
    if abs(v) < MIN_MOVE:
        return "≈ 0"
    fortegn = "+" if v >= 0 else "−"
    if enhed or ps.VALUTATEGN.get(ps.VALUTA):
        return fortegn + money(abs(v), dec)
    return fortegn + _dk(abs(v), dec)


def dpct(v, dec=1):
    """Afkast i procent med fortegn: +3,4 %."""
    return "–" if pd.isna(v) else ("+" if v >= 0 else "−") + _dk(abs(v) * 100, dec) + " %"


def lille(navn):
    """Gruppenavn midt i en sætning: "Senior/sikret gæld" -> "senior/sikret gæld", men
    forkortelser som PIK, CSOV og LPG bliver stående."""
    navn = str(navn)
    return navn[0].lower() + navn[1:] if len(navn) > 1 and navn[1].islower() else navn


def brudt(tekst, bredde=13):
    """Gruppenavn delt over linjer til en akseetiket: "Senior/sikret gæld" -> to linjer."""
    return "\n".join(textwrap.wrap(str(tekst).replace("/", "/ "), bredde)).replace("/ ", "/")


def reflabel(ax, y, tekst, farve=None, over=False):
    """Navn på en referencelinje, ankret i aksens venstre kant og altid øverst."""
    tr = blended_transform_factory(ax.transAxes, ax.transData)
    ax.text(0.008, y, tekst, transform=tr, ha="left", va="bottom" if over else "top",
            fontsize=9.5, color=farve or MUTED, fontweight="bold", zorder=8,
            bbox=dict(boxstyle="round,pad=0.18", fc=BG, ec="none", alpha=0.85))


def soejlelabel(ax, xs, ys, tekster, dy=0.012, farve=None, fs=9.5, va="bottom"):
    """Værditekst over (eller under) hver søjle, målt i akse-fraktion af y-området."""
    lo, hi = ax.get_ylim()
    off = (hi - lo) * dy
    for x, y, t in zip(xs, ys, tekster):
        if pd.isna(y):
            continue
        ax.text(x, y + (off if y >= 0 else -off), t, ha="center",
                va=va if y >= 0 else "top", fontsize=fs, color=farve or INK, zorder=5)


def kort(fig, x, y, w, h, label, vaerdi, note=None, accent=False):
    """Nøgletalskort til overbliksslidet - tegnes i figur-koordinater."""
    fc = PPIM_SAGE_DARK if accent else PPIM_CREAM
    ec = PPIM_SAGE_DARK if accent else PPIM_BEIGE
    tc = "white" if accent else INK
    fig.add_artist(FancyBboxPatch((x, y), w, h, transform=fig.transFigure,
                                  boxstyle="round,pad=0,rounding_size=0.010",
                                  facecolor=fc, edgecolor=ec, linewidth=1.2, zorder=1))
    fig.text(x + 0.016, y + h - 0.045, label.upper(), fontsize=9.5, color=tc,
             fontweight="bold", va="top", zorder=2)
    fig.text(x + 0.016, y + h * 0.44, vaerdi, fontsize=27 if len(vaerdi) <= 9 else 21, color=tc,
             fontweight="bold", va="center", zorder=2)
    if note:
        fig.text(x + 0.016, y + 0.035, note, fontsize=9.5, color=tc, va="bottom", zorder=2)


def opsummer(d, kol, med_irr=True):
    """Aggregerer beløb FØR forhold beregnes - aldrig gennemsnit af multipler."""
    g = d.groupby(kol, dropna=False).agg(
        investeret=("invested", "sum"), udlodninger=("proceeds", "sum"),
        dagsvaerdi=("fair_value", "sum"), samlet=("total_value", "sum"),
        tab=("tab", "sum"), antal=("invested", "size"))
    g["realiseret_kap"] = (d[d["realiseret"]].groupby(kol, dropna=False)["invested"].sum()
                           .reindex(g.index).fillna(0.0))
    inv = g["investeret"].replace(0, np.nan)
    g["tvpi"] = g["samlet"] / inv
    g["dpi"] = g["udlodninger"] / inv
    g["rvpi"] = g["dagsvaerdi"] / inv
    g["gevinst"] = g["samlet"] - g["investeret"]
    g["andel"] = g["investeret"] / g["investeret"].sum()
    g["tabsrate"] = g["tab"] / inv
    g["realiseret_andel"] = g["realiseret_kap"] / inv

    if med_irr:
        def _vaegtet(x):
            m = x["irr"].notna() & (x["invested"] > 0)
            return np.average(x.loc[m, "irr"], weights=x.loc[m, "invested"]) if m.any() else np.nan
        g["irr_vaegtet"] = d.groupby(kol, dropna=False)[["irr", "invested"]].apply(_vaegtet)
        g["irr_median"] = d.groupby(kol, dropna=False)["irr"].median()
    return g


def _med_vaerdier(h):
    """De beholdningslinjer, analysen kan bruge: investeret kapital og en værdi."""
    return h[h["invested"].notna() & (h["fair_value"].notna() | h["total_value"].notna())]


def har_data(fund_code):
    """Kan porteføljeanalysen køres? Nogle GP'er oplyser kun tilsagn pr. beholdning (ATP),
    andre slet ingen beholdninger."""
    return not _med_vaerdier(data.holdings(fund_code)).empty


class Kerne(Analyse):
    def __init__(self, fund_code, as_of=None, charts="charts", exports="exports"):
        """as_of=None -> seneste fondsrapport med beholdninger."""
        super().__init__(fund_code, "portefoelje", charts, exports)
        self.cfg = fondskonfig.for_fond(self.fond)
        self.advarsler = []

        h = data.holdings(self.kode)
        if as_of:
            h = h[h["report_date"] <= pd.Timestamp(as_of)]
        h = _med_vaerdier(h)
        if h.empty:
            raise ValueError(f"{self.kode} har ingen beholdninger med investeret kapital og "
                             f"værdi i rpt.v_portfolio_holding - porteføljeanalysen kan ikke køres")

        ps.VALUTA = self.valuta
        ps.FUND = self.navn
        ps.KILDE = "PE-databasen, GP'ens fondsrapporter"
        tegn = ps.VALUTATEGN.get(self.valuta)
        self.BELOB = FuncFormatter(lambda v, _: money(v, 0) if tegn else _dk(v, 0))
        self.MIO, self.MIO_STOR = f"mio. {self.valuta}", f"Mio. {self.valuta}"

        self.alle = self._berig(h.reset_index(drop=True))
        self.DATOER = [pd.Timestamp(d) for d in sorted(self.alle["report_date"].unique())]
        self.as_of = self.REPORT_DATE = self.DATOER[-1]
        self.REPORT_DK = ps.REPORT_DK = f"{self.as_of:%d.%m.%Y}"
        self.FOERSTE = self.DATOER[0]
        self.FORRIGE = self.DATOER[-2] if len(self.DATOER) > 1 else None
        # År til dato måles fra seneste årsskifte, hvis rapporten findes; ellers fra ældste dato
        primo = pd.Timestamp(year=self.as_of.year - 1, month=12, day=31)
        self.PRIMO_AAR = primo if primo in self.DATOER else self.FOERSTE
        self.AAR_ER_AARSSKIFTE = self.PRIMO_AAR == primo
        self.FORRIGE_DK = f"{self.FORRIGE:%d.%m.%Y}" if self.FORRIGE is not None else None
        self.AAR_DK = f"{self.PRIMO_AAR:%d.%m.%Y}"

        self.raw = self.snapshot(self.as_of)
        self.prev = self.snapshot(self.FORRIGE)
        self._flag()
        self._aggreger()
        self._afstem()

        print(f"{self.kode}: {self.navn} · pr. {self.REPORT_DK} · {len(self.DATOER)} rapportdatoer "
              f"({self.FOERSTE:%d.%m.%Y} →) · {self.N_INV} {self.cfg.enhed} / {self.N_TR} linjer")
        print(f"  Investeret {money(self.tot['invested'])} | udlodninger "
              f"{money(self.tot['proceeds'])} | dagsværdi {money(self.tot['fair_value'])} | "
              f"TVPI {mult(self.pool_tvpi)} = DPI {mult(self.pool_dpi)} + RVPI {mult(self.pool_rvpi)}")
        print("  Datagrundlag: " + ", ".join(
            f"{navn} {'ja' if v else 'nej'}" for navn, v in [
                (self.cfg.gruppe_omtale, self.HAR_GRUPPE), ("instrument", self.HAR_INSTRUMENT),
                ("IRR pr. handel", self.HAR_IRR), ("realiseret/urealiseret", self.HAR_REAL),
                ("exit-dato", self.HAR_EXIT), ("vintage", self.HAR_VINTAGE),
                ("handelsvaluta", self.HAR_VALUTA), ("flere datoer", self.HAR_PERIODE)]))
        for a in self.advarsler:
            print(f"ADVARSEL: {a}")

    # ------------------------------------------------------------------ indlæsning

    def _berig(self, h):
        """Fra viewets linjer til analysens: mio., ét navn pr. selskab, afledte dimensioner."""
        d = self.cfg.rens(h.copy())
        alias = data.company_alias()
        d["investment"] = d["investment"].map(lambda n: alias.get(str(n).lower(), n))

        d["invested"] = d["invested"].fillna(0.0) / 1e6
        d["proceeds"] = d["distributions"].fillna(0.0) / 1e6
        d["fair_value"] = d["fair_value"].fillna(0.0) / 1e6
        # Samlet værdi ER udlodninger + dagsværdi. GP'ens egen kolonne er afrundet for sig (op
        # til 0,1 pr. linje) og mangler helt hos MIF, så den bruges kun som kontrol - ellers
        # stemmer ændringen i merværdi ikke med periodeafkastet.
        d["total_value_gp"] = d["total_value"] / 1e6
        d["total_value"] = d["proceeds"] + d["fair_value"]
        d["irr"] = d["irr_pct"] / 100

        d["valuta"] = d["local_currency"].map(lambda v: VALUTATEGN.get(v, v) if pd.notna(v) else None)
        har_begge = d["instrument"].notna() & d["valuta"].notna()
        d["tranche"] = d["tranche_tekst"].where(d["tranche_tekst"] != "", d["instrument"].fillna(""))
        d.loc[har_begge, "tranche"] = (d.loc[har_begge, "instrument"] + " ("
                                       + d.loc[har_begge, "valuta"] + ")")
        d["label"] = np.where(d["tranche"] != "", d["investment"] + " · " + d["tranche"],
                              d["investment"])

        d["realiseret"] = (d["section"] == "REALISED") | d["exit_date"].notna()
        if self.cfg.afviklet_ved_nul:
            d["realiseret"] |= (d["fair_value"] < MIN_MOVE) & (d["proceeds"] > 0)
        d["vintage"] = d["trade_date"].dt.year.fillna(d["vintage"])
        d["exit_aar"] = d["exit_date"].dt.year
        # Holdeperioden måles til den rapportdato, rækken tilhører - ikke til seneste kvartal
        d["holdeperiode"] = (d["exit_date"].fillna(d["report_date"]) - d["trade_date"]).dt.days / 365.25
        d["mom"] = d["total_value"] / d["invested"].replace(0, np.nan)
        d["gevinst"] = d["total_value"] - d["invested"]
        d["tab"] = (d["invested"] - d["total_value"]).clip(lower=0)
        return d[["report_date", "investment", "tranche", "label", "instrument", "gruppe", "valuta",
                  "trade_date", "exit_date", "vintage", "exit_aar", "realiseret", "holdeperiode",
                  "invested", "proceeds", "fair_value", "total_value", "total_value_gp", "irr",
                  "mom", "gevinst", "tab"]]

    def snapshot(self, dato):
        """Den berigede opgørelse pr. en vilkårlig rapportdato (None -> None)."""
        if dato is None:
            return None
        return self.alle[self.alle["report_date"] == dato].copy()

    def _flag(self):
        raw = self.raw
        n_navne = raw["investment"].nunique()
        n_grp = raw["gruppe"].nunique(dropna=True)
        self.HAR_GRUPPE = bool(raw["gruppe"].notna().all() and 2 <= n_grp <= MAKS_GRUPPER
                               and n_grp <= 0.6 * n_navne)
        if not self.HAR_GRUPPE:           # én gruppe: "segment" er fx unikt pr. selskab
            self.alle["gruppe"] = "Hele porteføljen"
            raw["gruppe"] = "Hele porteføljen"
            if self.prev is not None:
                self.prev["gruppe"] = "Hele porteføljen"
        self.HAR_INSTRUMENT = bool(raw["instrument"].notna().all())
        self.UNDER = "instrument" if self.HAR_INSTRUMENT else "gruppe"
        self.UNDER_NAVN = self.cfg.under_navn if self.HAR_INSTRUMENT else self.cfg.gruppe_navn
        self.HAR_IRR = int(raw["irr"].notna().sum()) >= 3
        self.HAR_EXIT = int(raw["exit_date"].notna().sum()) >= 3
        self.HAR_REAL = bool(raw["realiseret"].any() and (~raw["realiseret"]).any())
        self.HAR_VINTAGE = bool(raw["vintage"].notna().mean() > 0.8 and raw["vintage"].nunique() >= 2)
        self.HAR_VALUTA = bool(raw["valuta"].notna().all() and raw["valuta"].nunique() >= 2)
        self.HAR_ALDER = bool(raw["holdeperiode"].notna().mean() > 0.8)
        self.HAR_PERIODE = self.FORRIGE is not None
        self.HAR_TRANCHE = bool((raw["tranche"] != "").any())
        # Første dato, hvor rapporten har linjer pr. tranche og ikke kun pr. selskab
        if self.HAR_INSTRUMENT:
            andel = self.alle.groupby("report_date")["instrument"].apply(lambda s: s.notna().mean())
            self.DETALJE_FRA = pd.Timestamp(andel[andel > 0.9].index.min())
        else:
            self.DETALJE_FRA = self.FOERSTE

        kap = raw.groupby("gruppe")["invested"].sum().sort_values(ascending=False)
        orden = [g for g in self.cfg.gruppe_orden if g in kap.index]
        self.GRUPPE_ORDEN = orden + [g for g in kap.index if g not in orden]
        self.GRUPPE_FARVE = dict(zip(self.GRUPPE_ORDEN, GRUPPE_PALET))

    # ------------------------------------------------------------------ aggregater

    def _aggreger(self):
        raw = self.raw
        self.tot = raw[NUM].sum()
        t = self.tot
        self.pool_tvpi = t["total_value"] / t["invested"]
        self.pool_dpi = t["proceeds"] / t["invested"]
        self.pool_rvpi = t["fair_value"] / t["invested"]
        self.GEVINST = t["total_value"] - t["invested"]
        self.N_INV, self.N_TR = raw["investment"].nunique(), len(raw)
        self.N_NM = int(raw["irr"].isna().sum()) if self.HAR_IRR else 0
        self.REAL, self.UREAL = raw[raw["realiseret"]], raw[~raw["realiseret"]]

        # Selskabsniveau: linjer lagt sammen. Gruppen sættes efter den STØRSTE linje, så et
        # selskab med både gæld og egenkapital placeres der, hvor pengene er.
        dom = (raw.groupby(["investment", "gruppe"])["invested"].sum()
               .sort_values(ascending=False).reset_index().drop_duplicates("investment")
               .set_index("investment")["gruppe"])
        inv = (raw.groupby("investment")
               .agg(**{k: (k, "sum") for k in NUM},
                    trade_date=("trade_date", "min"), exit_date=("exit_date", "max"),
                    vintage=("vintage", "min"), antal_trancher=("invested", "size"),
                    alle_realiseret=("realiseret", "all"),
                    holdeperiode=("holdeperiode", "max")).reset_index())
        inv["gruppe"] = inv["investment"].map(dom)
        inv["mom"] = inv["total_value"] / inv["invested"].replace(0, np.nan)
        inv["gevinst"] = inv["total_value"] - inv["invested"]
        inv["tab"] = (inv["invested"] - inv["total_value"]).clip(lower=0)
        self.inv = inv

        self.g_under = opsummer(raw, self.UNDER).sort_values("investeret", ascending=False)
        self.g_gruppe = opsummer(raw, "gruppe").reindex(self.GRUPPE_ORDEN)
        self.g_vintage = opsummer(raw[raw["vintage"].notna()], "vintage").sort_index()
        self.g_valuta = (opsummer(raw, "valuta").sort_values("investeret", ascending=False)
                         if self.HAR_VALUTA else None)
        self.UNDER_TIL_GRUPPE = dict(zip(raw[self.UNDER], raw["gruppe"]))

        # Tab, følsomhed og koncentration - bruges af både grafer, tabeller og tekst
        self.tabere = raw[raw["tab"] > MIN_MOVE].sort_values("tab")
        self.TABSRATE = raw["tab"].sum() / t["invested"]
        self.break_even = self.GEVINST / t["fair_value"] if t["fair_value"] > 0 else np.nan
        self.bidrag = inv.sort_values("gevinst", ascending=False).reset_index(drop=True)
        self.kum = self.bidrag["gevinst"].cumsum() / self.GEVINST
        self.hhi = ((inv["invested"] / inv["invested"].sum()) ** 2).sum()
        self.top5 = self.kum.iloc[min(4, len(self.kum) - 1)]
        self.top10 = self.kum.iloc[min(9, len(self.kum) - 1)]
        r = self.REAL[(self.REAL["invested"] >= fondskonfig.MIN_INVESTED)
                      & self.REAL["holdeperiode"].notna()]
        self.REAL_LEVETID = (np.average(r["holdeperiode"], weights=r["invested"])
                             if self.HAR_EXIT and len(r) else np.nan)

    def _afstem(self):
        """Ingen graf må hvile på tal, der ikke summerer til rapportens totaler."""
        raw, tot = self.raw, self.tot
        raa = {"investeret": "invested", "udlodninger": "proceeds",
               "dagsvaerdi": "fair_value", "samlet": "total_value"}
        dims = ["gruppe", "realiseret"] + [k for k, har in (
            ("instrument", self.HAR_INSTRUMENT), ("valuta", self.HAR_VALUTA)) if har]
        self.AFSTEM = {}
        for dim in dims:
            g = opsummer(raw, dim, med_irr=False)
            self.AFSTEM[dim] = g[list(raa)].sum()
            for k, r in raa.items():
                assert abs(self.AFSTEM[dim][k] - tot[r]) < 0.05, f"{dim}/{k} afviger fra totalen"
        assert abs(self.inv[NUM].sum() - tot).max() < 0.05, "selskabsniveau summerer ikke til totalen"
        if self.cfg.kraev_kendt_gruppe:
            ukendt = raw.loc[raw["gruppe"].isna() | raw["gruppe"].eq("Øvrige")]
            assert ukendt.empty, "linjer uden kendt instrumenttype: " + ", ".join(ukendt["label"])
        # GP'ens egen "samlet værdi" mod udlodninger + dagsværdi. Afrunding giver op til 0,1 pr.
        # linje; mere end det er en fejl i rapporten eller i indlæsningen.
        afv = (raw["total_value"] - raw["total_value_gp"]).abs()
        if afv.max() > 0.15:
            v = raw.loc[afv.idxmax()]
            self.advarsler.append(
                f"GP'ens samlede værdi afviger fra udlodninger + dagsværdi for "
                f"{int((afv > 0.15).sum())} linjer (størst: {v['label']}, {money(afv.max(), 1)}). "
                "Analysen bruger udlodninger + dagsværdi.")
        if self.HAR_REAL:
            fv_real = self.REAL["fair_value"].sum()
            if fv_real > 0.05 * tot["fair_value"]:
                self.advarsler.append(
                    f"De realiserede linjer bærer stadig {money(fv_real, 1)} i dagsværdi.")
        self.afstem_tabel = pd.DataFrame(self.AFSTEM).T
        self.afstem_tabel.loc["RAPPORT"] = [tot[raa[k]] for k in raa]

    # ------------------------------------------------------------------ fælles småting

    def afslut(self, fig, title, subtitle, navn, ax=None, note="", rect=None):
        """Titelblok, layout, footer og gem som ét 16:9-slide. rect[3]=None -> under titlen."""
        top = add_header(fig, title, subtitle)
        rect = list(rect or [MX, BOTTOM_FRAC, 1 - MX, top])
        rect[3] = top if rect[3] is None else rect[3]
        fig.tight_layout(rect=rect)
        add_footer(fig, source_line(note), ax=ax)
        save(fig, self.C(navn))
        plt.show()

    def gruppefarve(self, navn):
        """Farven for en gruppe - eller for et instrument via dets gruppe."""
        return self.GRUPPE_FARVE.get(navn) or self.GRUPPE_FARVE.get(
            self.UNDER_TIL_GRUPPE.get(navn), PPIM_SAGE_DARK)

    def note_belob(self):
        return f" · beløb i {self.MIO}"
