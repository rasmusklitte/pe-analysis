"""Afkastanalysens kerne: indlæsning, periode- og kildeserier, flag og afstemning.

Investorniveau hele vejen: vores pengestrømme, vores NAV og vores kapitalkonto. Kernen bygger
de serier, slide-metoderne tegner af:

    per        én række pr. opgørelsesperiode: værdiskabelse og Modified Dietz-afkast
    horisonter IRR over 1, 3 og 5 år og siden start
    kum        kapitalkontoens bevægelser akkumuleret siden start, pr. konto
    kat        de samme samlet i kategorier (KATEGORIER); kat_per og kat_aar er differenserne
    omk_aar    honorar, omkostninger og carry pr. år, også i pct. af tilsagn og NAV
    fx         afkastet i DKK delt i afkast i fondens valuta og valutaeffekt

Hvad en fond kan vise, afgøres af HAR_*-flagene, ikke af fondens navn.
"""
import textwrap

import numpy as np
import pandas as pd
from matplotlib.patches import Rectangle
from matplotlib.ticker import FuncFormatter

from .. import data, metrics
from .. import style as ps
from ..analyse import Analyse
from ..style import (PPIM_SAGE_DARK, PPIM_SAGE_MID, PPIM_SAGE_LIGHT, PPIM_OLIVE, PPIM_BROWN,
                     PPIM_TAUPE, PPIM_TAUPE_LIGHT, PPIM_TERRACOTTA, PPIM_CREAM, PPIM_BEIGE,
                     PPIM_RED_MUTED, LINE, _dk)

BRO_TOLERANCE = 0.001   # kilderne må afvige 0,1 % fra NAV (afrunding i GP'ens opgørelse)
MIN_KAPITAL = 0.05      # et periodeafkast i pct. vises først, når den bundne kapital er over
                        # 5 % af tilsagnet - ellers er det en stor procent af et lille beløb
LANG_PERIODE = 100      # dage; en længere periode dækker mere end ét kvartal (manglende opgørelse)
HORISONTER = (1, 3, 5)  # år
MIN_AAR_OMK = 2.0       # omkostninger i pct. p.a. vises først efter to års historik
MIN_NAV_ANDEL = 0.30    # omkostninger i pct. af NAV vises kun for år, hvor den gennemsnitlige
                        # NAV er mindst 30 % af sit højeste

# (nøgle, navn, konti, farve). Rækkefølgen er grafernes: resultatets kilder først, så det,
# der går fra. RESTAT lægges i den linje, GP'en selv bogfører efterreguleringen i (se _byg_kilder).
KATEGORIER = [
    ("indtaegt", "Løbende indtægt", ["CA200"], PPIM_SAGE_DARK),
    ("realiseret", "Realiseret gevinst/tab", ["CA300"], PPIM_OLIVE),
    ("urealiseret", "Urealiseret værdiændring", ["CA310"], PPIM_SAGE_LIGHT),
    ("resultat", "Resultat, ikke opdelt", ["CA290"], PPIM_SAGE_MID),
    ("oevrige", "Øvrige bevægelser", ["CA490", "REST"], PPIM_BEIGE),
    ("hul", "Perioder uden opgørelse", ["HUL"], PPIM_TAUPE_LIGHT),
    ("honorar", "Forvaltningshonorar", ["CA210"], PPIM_BROWN),
    ("omk", "Fondsomkostninger", ["CA220"], PPIM_TAUPE),
    ("finans", "Finansielle poster", ["CA230"], PPIM_TERRACOTTA),
    ("carry", "Carried interest", ["CA400"], PPIM_RED_MUTED),
]
KAT_NAVN = {k: n for k, n, _, _ in KATEGORIER}
KAT_FARVE = {k: f for k, _, _, f in KATEGORIER}
OMK_KAT = ["honorar", "omk", "finans", "carry"]

INDKALD_DK = {"CF100": "Investeringer", "CF110": "Forvaltningshonorar",
              "CF120": "Fondsomkostninger", "CF150": "Tilbagebetalt ved udligning",
              "CF190": "Øvrige", "CF199": "Ikke opdelt"}
UDLODNING_DK = {"CF200": "Tilbagebetalt kapital", "CF210": "Realiseret gevinst",
                "CF220": "Løbende indtægt", "CF230": "Genindkaldelig udlodning",
                "CF290": "Øvrige", "CF295": "Ikke opdelt"}


def pct(v, dec=1):
    return _dk(v, dec) + " %"


def dpct(v, dec=1):
    """Procent med fortegn: "+2,1 %" / "−0,4 %"."""
    return ("+" if v >= 0 else "−") + _dk(abs(v), dec) + " %"


def brudt(tekst, bredde=14):
    """Akseetiket på flere linjer; de lange sammensatte ord deles ved leddet."""
    for helt, delt in (("Forvaltningshonorar", "Forvaltnings- honorar"),
                       ("Fondsomkostninger", "Fonds- omkostninger")):
        tekst = tekst.replace(helt, delt)
    return "\n".join(textwrap.wrap(tekst, bredde, break_long_words=False))


def pct_akse(ax, akse="y"):
    """Procentakse med så mange decimaler, som afstanden mellem mærkerne kræver."""
    a = ax.yaxis if akse == "y" else ax.xaxis

    def fmt(v, _):
        t = a.get_ticklocs()
        trin = abs(t[1] - t[0]) if len(t) > 1 else 1
        return _dk(v, 0 if abs(trin - round(trin)) < 1e-6 else 1) + " %"
    a.set_major_formatter(FuncFormatter(fmt))


def har_data(fund_code):
    """Analysen er investorniveau: den kræver, at en af vores investorer er i fonden."""
    return not data.nav(fund_code).empty


def tavle(ax, kort):
    """Nøgletalskort, fire pr. række. kort: [(label, værdi, note, negativ)]."""
    raekker = -(-len(kort) // 4)
    ax.set_axis_off()
    ax.set_xlim(0, 4)
    ax.set_ylim(0, raekker)
    for i, (label, vaerdi, note, negativ) in enumerate(kort):
        x, y = i % 4, raekker - 1 - i // 4
        ax.add_patch(Rectangle((x + 0.04, y + 0.06), 0.92, 0.86, facecolor=PPIM_CREAM,
                               edgecolor="none"))
        ax.add_patch(Rectangle((x + 0.04, y + 0.06), 0.012, 0.86, facecolor=PPIM_SAGE_DARK,
                               edgecolor="none"))
        ax.text(x + 0.12, y + 0.76, label.upper(), fontsize=10, fontweight="bold", va="center")
        ax.text(x + 0.12, y + 0.50, vaerdi, fontsize=25 if len(vaerdi) <= 11 else 20,
                fontweight="bold", va="center",
                color=PPIM_RED_MUTED if negativ else PPIM_SAGE_DARK)
        ax.text(x + 0.12, y + 0.24, note, fontsize=10.5, va="center")


def vandfald(ax, trin, dec, fs=9.5):
    """trin: [(navn, beløb, art)] med art "total" (søjle fra nul), "bev" (gevinst/tab) eller
    "flow" (hverken gevinst eller tab). En total sætter niveauet; bevægelser bygger videre."""
    niveau = 0.0
    for i, (navn, v, art) in enumerate(trin):
        if art == "total":
            ax.bar(i, v, width=0.66, color=PPIM_SAGE_DARK)
            top, niveau = max(v, 0), v
        else:
            farve = PPIM_TAUPE_LIGHT if art == "flow" else \
                PPIM_SAGE_LIGHT if v >= 0 else PPIM_RED_MUTED
            ax.bar(i, v, width=0.66, bottom=niveau, color=farve)
            top = max(niveau, niveau + v)
            niveau += v
        if i + 1 < len(trin):
            ax.plot([i - 0.33, i + 1.33], [niveau] * 2, color=LINE, linewidth=0.7)
        tekst = _dk(v, dec) if art == "total" else ("+" if v >= 0 else "−") + _dk(abs(v), dec)
        ax.text(i, top, tekst, ha="center", va="bottom", fontsize=fs,
                fontweight="bold" if art == "total" else "normal")
    ax.set_xticks(range(len(trin)), [t[0] for t in trin], fontsize=fs)
    ax.axhline(0, color=LINE, linewidth=0.8)
    ax.margins(y=0.12)


def stabl(ax, x, df, farver, width=0.72):
    """Stablede søjler med fortegn: positive kolonner opad fra nul, negative nedad."""
    pos, neg = np.zeros(len(df)), np.zeros(len(df))
    for kol in df.columns:
        v = df[kol].to_numpy(dtype=float)
        ax.bar(x, v, width=width, bottom=np.where(v >= 0, pos, neg), color=farver[kol])
        pos += np.where(v >= 0, v, 0)
        neg += np.where(v < 0, v, 0)
    return pos, neg


class Kerne(Analyse):
    def __init__(self, fund_code, as_of=None, nav_kolonne="restated_nav",
                 charts="charts", exports="exports"):
        """as_of=None -> seneste NAV-dato. nav_kolonne som i overblikket."""
        super().__init__(fund_code, "afkast", charts, exports)
        self.nav_kolonne = nav_kolonne
        self.afstemning, self.advarsler = [], []

        cut = pd.Timestamp(as_of) if as_of else pd.Timestamp.max
        f = lambda df, kol: df[df[kol] <= cut].reset_index(drop=True)
        self.nav = f(data.nav(self.kode), "period_end")
        if self.nav.empty:
            raise ValueError(f"Ingen investordata for {self.kode} - afkastanalysen er investorniveau")
        self.ca = f(data.capital_account(self.kode), "period_end")
        self.as_of = self.nav["period_end"].max()
        # Pengestrømme efter seneste NAV-dato hører til næste opgørelse (som v_fund_summary)
        self.cf = f(data.cash_flows(self.kode), "value_date")
        self.cf = self.cf[self.cf["value_date"] <= self.as_of].reset_index(drop=True)
        self.serie = metrics.kvartalsserie(self.cf, self.nav, nav_kolonne)
        self.nu = self.serie.iloc[-1]
        self.huller = metrics.manglende_kvartaler(self.serie.index)
        self.dec = 2 if self.nu["commitment"] < 50e6 else 1

        ps.FUND = self.navn
        ps.REPORT_DK = f"{self.as_of:%d.%m.%Y}"
        ps.VALUTA = self.valuta
        ps.KILDE = "PE-databasen, GP'ens opgørelser"

        self._byg_perioder()
        self._byg_kilder()
        self._byg_anvendelse()
        self._byg_valuta()
        self._afstem()
        print(f"{self.kode}: {self.navn} · pr. {ps.REPORT_DK} · {self.valuta} · "
              f"{len(self.serie)} opgørelser · kapitalkonto siden start: "
              f"{'ja' if self.HAR_KILDER else 'nej'} · honorar opdelt: "
              f"{'ja' if self.HAR_HONORAR else 'nej'} · valuta: {'ja' if self.HAR_VALUTA else 'nej'}")

    # ------------------------------------------------------------------ hjælpere

    def m(self, v, dec=None):
        """Beløb i hele enheder -> tekst i mio. af fondens valuta."""
        return ps.money(v / 1e6, self.dec if dec is None else dec)

    def dm(self, v, dec=None):
        """Som m(), men med fortegn - til værdiskabelse og andre ændringer."""
        return ("+" if v >= 0 else "−") + self.m(abs(v), dec)

    def _stroemme(self, fra, til):
        """Pengestrømme til XIRR i (fra, til] - uden kildeskat, som i kvartalsserien."""
        c = self.cf[(self.cf["flow_class"] != "WITHHOLDING_TAX")
                    & (self.cf["value_date"] > fra) & (self.cf["value_date"] <= til)]
        return list(zip(c["value_date"], c["amount"]))

    # ------------------------------------------------------------------ perioder og horisonter

    def _byg_perioder(self):
        p = metrics.periodeserie(self.serie, self.cf)
        p["vis_pct"] = p["afkast"].notna() & (p["kapital"] >= MIN_KAPITAL * self.serie["commitment"])
        p["lang"] = p["dage"] > LANG_PERIODE
        for dato in p.index[p["afkast_12m"].notna()]:
            foer = dato - pd.DateOffset(years=1) + pd.offsets.MonthEnd(0)
            if not p.loc[(p.index > foer) & (p.index <= dato), "vis_pct"].all():
                p.loc[dato, "afkast_12m"] = np.nan
        self.per, self.kvt = p, p.iloc[-1]

        self.horisonter = []
        s = self.serie
        for aar in HORISONTER:
            start = self.as_of - pd.DateOffset(years=aar) + pd.offsets.MonthEnd(0)
            if start in s.index and s.loc[start, "nav"] > 0:
                irr = metrics.xirr([(start, -s.loc[start, "nav"])] + self._stroemme(start, self.as_of)
                                   + [(self.as_of, self.nu["nav"])])
                self.horisonter.append(dict(
                    navn=f"{aar} år", start=start, irr=irr,
                    vaerdiskabelse=self.nu["nettovaerdi"] - s.loc[start, "nettovaerdi"]))
        if pd.notna(self.nu["irr"]):
            self.horisonter.append(dict(navn="Siden start", start=self.cf["value_date"].min(),
                                        irr=self.nu["irr"], vaerdiskabelse=self.nu["nettovaerdi"]))

    # ------------------------------------------------------------------ afkastets kilder

    def _byg_kilder(self):
        kum, _ = metrics.kilder_serie(self.ca, self.cf, self.serie.index)
        self.HAR_KILDER = not kum.empty and self.as_of in kum.index
        self.HAR_HONORAR = False
        if not self.HAR_KILDER:
            return
        kum = kum.copy()
        if "RESTAT" not in kum:
            kum["RESTAT"] = 0.0
        if self.nav_kolonne == "restated_nav":
            # På årsultimoet er NAV den efterregulerede; opgørelsen på datoen kender den ikke endnu
            r = self.nav.groupby("period_end")["restatement"].sum()
            for dato, v in r[r.abs() > 0.005].items():
                if dato in kum.index:
                    kum.loc[dato, "RESTAT"] += v
        kum["REST"] = self.serie["nav"].reindex(kum.index) - kum.sum(axis=1)
        self.kum = kum

        seneste = set(self.ca.loc[(self.ca["period_end"] == self.as_of)
                                  & (self.ca["account_group"] == "CAPACC")
                                  & (self.ca["basis"] != "POINT"), "account_code"])
        self.HAR_HONORAR = "CA210" in seneste and "CA210" in kum \
            and abs(kum["CA210"].iloc[-1]) > 0.5
        # GP'en er holdt op med at opdele resultatet (NEP6 fra 2025): en serie, der er opdelt
        # frem til en dato og samlet derefter, kan ikke sammenlignes over tid - alt samles.
        self.SAMLET = "CA210" in kum and "CA210" not in seneste

        kat = pd.DataFrame({k: kum.reindex(columns=konti, fill_value=0.0).sum(axis=1)
                            for k, _, konti, _ in KATEGORIER})
        if self.SAMLET:
            fold = ["indtaegt", "realiseret", "urealiseret", "honorar", "omk", "finans"]
            kat["resultat"] += kat[fold].sum(axis=1)
            kat[fold] = 0.0
        # Efterreguleringen er en værdiregulering. I Q1 ligger den i GP'ens egne linjer, fra Q2
        # som ændret primo; lagt i samme kategori står den stille hen over året.
        self.RESTAT_I = "urealiseret" if "CA310" in seneste and not self.SAMLET else "resultat"
        kat[self.RESTAT_I] += kum["RESTAT"]
        self.RESTAT_SUM = kum["RESTAT"].iloc[-1]
        # en kategori, der aldrig når 0,05 % af det samlede, er afrunding og ikke en kilde
        smaa = kat.abs().max() <= max(0.5, 0.0005 * kat.abs().sum(axis=1).max())
        if smaa.any() and not smaa["resultat"]:
            kat["resultat"] += kat.loc[:, smaa].sum(axis=1)
        elif smaa.any():
            kat[kat.abs().max().idxmax()] += kat.loc[:, smaa].sum(axis=1)
        self.kat = kat.loc[:, ~smaa]
        self.kat_per = self.kat.diff()
        self.kat_per.iloc[0] = self.kat.iloc[0]
        self.kat_aar = self.kat_per.groupby(self.kat_per.index.year).sum()
        self.kat_aar.index.name = "aar"

        self.omk_kol = [k for k in OMK_KAT if k in self.kat]
        self.brutto_kol = [k for k in self.kat if k not in OMK_KAT]
        nu = self.kat.iloc[-1]
        self.NETTO_GP = nu.sum()
        self.BRUTTO = nu[self.brutto_kol].sum()
        self.OMK = nu[self.omk_kol].sum()                      # negativ = omkostning
        self.GP_INDBETALT = kum["CA110"].iloc[-1] if "CA110" in kum else np.nan
        self.OMK_ANDEL = -self.OMK / self.BRUTTO if self.HAR_HONORAR and self.BRUTTO > 0 else np.nan

        if self.HAR_HONORAR:
            self._byg_omkostninger()

    def _byg_omkostninger(self):
        """Pr. kalenderår: omkostningerne i beløb (positiv = omkostning) og de løbende i pct."""
        o = -self.kat_aar[self.omk_kol]
        per = self.per.reindex(self.kat.index)
        aar = self.kat.index.year
        o["aarsbroek"] = (per["dage"].groupby(aar).sum() / 365).clip(upper=1.0)
        o["tilsagn"] = self.serie["commitment"].reindex(self.kat.index).groupby(aar).mean()
        # gennemsnitlig NAV: årets opgørelser og forrige årsultimo
        nav = self.serie["nav"].reindex(self.kat.index)
        o["gns_nav"] = [pd.concat([nav[nav.index.year == a],
                                   nav[nav.index == pd.Timestamp(year=a - 1, month=12, day=31)]]).mean()
                        for a in o.index]
        loebende = o[[k for k in ("honorar", "omk") if k in o]].sum(axis=1)
        o["honorar_pct_tilsagn"] = o["honorar"] / o["aarsbroek"] / o["tilsagn"]
        # mod en NAV under opbygning er procenten et stort tal af et lille beløb
        stor_nok = o["gns_nav"] >= MIN_NAV_ANDEL * o["gns_nav"].max()
        o["loebende_pct_nav"] = loebende / o["aarsbroek"] / o["gns_nav"].where(stor_nok)
        self.omk_aar = o
        aar_ialt = o["aarsbroek"].sum()
        # Første opgørelse rummer ofte honorar fra før vores indtræden (udligning); omregnet
        # til årsniveau over få måneder bliver det misvisende.
        self.HAR_OMK_PA = aar_ialt >= MIN_AAR_OMK
        self.HONORAR_PA = o["honorar"].sum() / aar_ialt / self.serie["commitment"].mean()
        self.LOEBENDE_PA = loebende.sum() / (o["aarsbroek"] * o["gns_nav"]).sum()

    def dkk(self, v):
        """Beløb i hele DKK -> "+12,3 mio. DKK" med fortegn."""
        return ("+" if v >= 0 else "−") + _dk(abs(v) / 1e6, 1) + " mio. DKK"

    # ------------------------------------------------------------------ kapitalens anvendelse

    def _byg_anvendelse(self):
        """Indkald efter formål og udlodninger efter art, som meddelelserne opdeler dem."""
        def pr_konto(klasse, navne, fortegn):
            d = self.cf[self.cf["flow_class"] == klasse].groupby("account_code")["amount"].sum()
            d = (fortegn * d).rename(lambda k: navne.get(k, k))
            return d.groupby(level=0).sum().sort_values(ascending=False)
        self.indkald = pr_konto("CONTRIBUTION", INDKALD_DK, -1)
        self.udlodninger = pr_konto("DISTRIBUTION", UDLODNING_DK, 1)
        self.INDKALDT_BRUTTO = self.indkald.clip(lower=0).sum()     # før tilbagebetalinger
        self.HAR_CF_SPLIT = self.INDKALDT_BRUTTO > 0 \
            and self.indkald.get("Ikke opdelt", 0.0) / self.INDKALDT_BRUTTO < 0.5

    # ------------------------------------------------------------------ valuta

    def _byg_valuta(self):
        n = self.nu
        self.HAR_VALUTA = self.valuta != "DKK" and pd.notna(n["nav_dkk"]) and n["nav"] > 0
        if not self.HAR_VALUTA:
            return
        kurs = n["nav_dkk"] / n["nav"]
        fx = dict(kurs=kurs, kurs_indbetalt=n["indbetalt_dkk"] / n["indbetalt"],
                  indbetalt=n["indbetalt_dkk"], vaerdi=n["nav_dkk"] + n["udloddet_dkk"],
                  lokalt=n["mervaerdi"] * kurs,
                  fx_indbetalt=n["indbetalt"] * kurs - n["indbetalt_dkk"],
                  fx_udloddet=n["udloddet_dkk"] - n["udloddet"] * kurs)
        fx["fx"] = fx["fx_indbetalt"] + fx["fx_udloddet"]
        fx["mervaerdi"] = fx["vaerdi"] - fx["indbetalt"]
        c = self.cf[self.cf["flow_class"] != "WITHHOLDING_TAX"]
        fx["irr"] = metrics.xirr(list(zip(c["value_date"], c["amount_dkk"]))
                                 + [(self.as_of, n["nav_dkk"])]) if pd.notna(n["irr"]) else np.nan
        self.fx = fx

        s = self.serie
        t = pd.DataFrame({"kurs": s["nav_dkk"] / s["nav"].where(s["nav"] > 0), "tvpi": s["tvpi"],
                          "tvpi_dkk": (s["nav_dkk"] + s["udloddet_dkk"])
                          / s["indbetalt_dkk"].where(s["indbetalt_dkk"] > 0)})
        t["mervaerdi_dkk"] = s["nav_dkk"] + s["udloddet_dkk"] - s["indbetalt_dkk"]
        t["valutaeffekt"] = t["mervaerdi_dkk"] - s["mervaerdi"] * t["kurs"]
        self.fx_tid = t

    # ------------------------------------------------------------------ afstemning

    def _afstem(self):
        """Hver serie skal ramme de tal, den er en opdeling af. Ingen graf på tal, der ikke stemmer."""
        n = self.nu
        a = lambda post, beregnet, kontrol, kilde: self.afstemning.append(
            dict(post=post, beregnet=beregnet, kontrol=kontrol, kilde=kilde))
        skabt = self.per["vaerdiskabelse"].sum()
        a("Periodernes værdiskabelse", skabt, n["nettovaerdi"], "NAV + akk. nettopengestrøm")
        assert abs(skabt - n["nettovaerdi"]) < 0.01, "Perioderne summerer ikke til nettoværdien"

        if self.HAR_KILDER:
            rest = self.kum["REST"]
            a("Kapitalkontoens linjer i alt", n["nav"] - rest.iloc[-1], n["nav"], "vores NAV")
            assert abs(rest.iloc[-1]) <= max(BRO_TOLERANCE * abs(n["nav"]), 1.0), \
                f"Kapitalkontoen forklarer ikke NAV: rest {rest.iloc[-1]:,.0f}"
            stoerst = (rest.abs() / self.serie["nav"].reindex(rest.index).abs()).max()
            if stoerst > BRO_TOLERANCE:
                print(f"NB: kapitalkontoen efterlader op til {pct(100 * stoerst, 2)} af NAV uforklaret "
                      f"på en tidligere dato ({rest.abs().idxmax():%d.%m.%Y}); ligger i 'Øvrige'")
            a("Kapitalkontoens nettoresultat", self.NETTO_GP, n["mervaerdi"],
              "merværdi af vores pengestrømme")
            afv = self.NETTO_GP - n["mervaerdi"]
            if abs(afv) > 0.01 * n["indbetalt"]:
                mio2 = lambda v: f"{_dk(v / 1e6, 2)} mio. {self.valuta}"
                self.advarsler.append(
                    f"Kapitalkontoens nettoresultat siden start er {mio2(self.NETTO_GP)}, mens "
                    f"merværdien af pengestrømmene i databasen er {mio2(n['mervaerdi'])}. GP'en "
                    f"opgør indbetalt til {mio2(self.GP_INDBETALT)} mod {mio2(n['indbetalt'])} i "
                    f"databasen, så der mangler formentlig meddelelser; periodeafkast og IRR skal "
                    f"læses med det forbehold.")
        if self.HAR_VALUTA:
            fx = self.fx
            a("Valutabro i DKK", fx["indbetalt"] + fx["lokalt"] + fx["fx"], fx["vaerdi"],
              "NAV + udloddet i DKK")
            assert abs(fx["indbetalt"] + fx["lokalt"] + fx["fx"] - fx["vaerdi"]) < 1.0

        print("Afstemning:")
        for r in self.afstemning:
            afv = r["beregnet"] - r["kontrol"]
            print(f"  {r['post']:<32} {_dk(r['beregnet'], 0):>16}  mod {_dk(r['kontrol'], 0):>16}"
                  f"  ({r['kilde']}){'' if abs(afv) < 1 else f'  afvigelse {_dk(afv, 0)}'}")
        for r in self.advarsler:
            print(f"ADVARSEL: {r}")
