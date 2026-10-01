"""Tabeller, Excel-eksport og deck for afkastanalysen. Deckets tekst regnes ud af data."""
import pandas as pd

from .. import style as ps
from ..deck import byg_deck
from ..style import _dk, mult, render_table
from .kerne import KAT_NAVN, MIN_KAPITAL, dpct, pct

# Slides i deckets rækkefølge. Notebook-skabelonen (scripts/byg_skabeloner.py) følger samme liste.
SLIDES = [
    ("Periodeafkast", ["graf_noegletal", "graf_kvartalsafkast", "graf_rullende", "graf_horisont"]),
    ("Afkastets kilder og omkostninger", ["graf_kilder_tid", "graf_kilder_aar", "graf_brutto_netto",
                                          "graf_omkostninger"]),
    ("Kapitalens anvendelse", ["graf_formaal", "graf_tilsagn"]),
    ("Valuta", ["graf_valutabro", "graf_valuta_tid"]),
    ("Tabeller", ["tabel_perioder", "tabel_kilder", "tabel_omkostninger"]),
]

KORT_NAVN = {"indtaegt": "Indtægt", "realiseret": "Realiseret", "urealiseret": "Urealiseret",
             "resultat": "Ikke opdelt", "oevrige": "Øvrige", "hul": "Uden opg.",
             "honorar": "Honorar", "omk": "Fondsomk.", "finans": "Finansielt", "carry": "Carry"}


class Eksport:
    # ------------------------------------------------------------------ tabeller

    def tabel_perioder(self):
        p = self.per
        mio = lambda v: _dk(v / 1e6, 2)
        rows = [[f"{d:%d.%m.%Y}", str(int(r.dage)), mio(r.nav_primo), mio(r.netto_indbetalt),
                 mio(r.nav_ultimo), mio(r.vaerdiskabelse),
                 dpct(100 * r.afkast) if r.vis_pct else "–",
                 dpct(100 * r.afkast_12m) if pd.notna(r.afkast_12m) else "–"]
                for d, r in zip(p.index, p.itertuples())]
        n = self.nu
        rows.append(["Siden start", str(int(p["dage"].sum())), "", mio(p["netto_indbetalt"].sum()),
                     mio(n["nav"]), mio(p["vaerdiskabelse"].sum()),
                     pct(100 * n["irr"]) + " p.a." if pd.notna(n["irr"]) else "–", ""])
        render_table(
            "Afkast pr. opgørelsesperiode",
            ["Periode slut", "Dage", "NAV primo", "Nettoindbetalt", "NAV ultimo", "Værdiskabelse",
             "Afkast", "12 mdr."],
            rows, [1.2, 0.6, 1, 1.1, 1, 1.1, 0.9, 0.9], ["left"] + ["right"] * 7,
            self.C("tabel_perioder"),
            subtitle="Nettoindbetalt = indbetalinger minus udlodninger i perioden · afkast er "
                     "Modified Dietz, sidste række IRR", highlight_row=len(rows) - 1)

    def tabel_kilder(self):
        if not self._kraever(self.HAR_KILDER, "kapitalkonto siden start"):
            return
        k = self.kat_aar
        mio = lambda v: _dk(v / 1e6, 2)
        rows = [[e] + [mio(v) for v in r] + [mio(r.sum())]
                for e, (_, r) in zip(self._aarsetiketter(k.index), k.iterrows())]
        rows.append(["Siden start"] + [mio(v) for v in k.sum()] + [mio(k.sum().sum())])
        render_table(
            "Resultatets kilder pr. år", ["År"] + [KORT_NAVN[c] for c in k.columns] + ["Netto"],
            rows, [1.1] + [1] * (len(k.columns) + 1), ["left"] + ["right"] * (len(k.columns) + 1),
            self.C("tabel_kilder"),
            subtitle="Kapitalkontoens resultatlinjer som GP'en opgør dem, uden ind- og udbetalinger",
            highlight_row=len(rows) - 1)

    def tabel_omkostninger(self):
        if not self._kraever(self.HAR_HONORAR, "forvaltningshonorar udskilt i kapitalkontoen"):
            return
        o = self.omk_aar
        mio = lambda v: _dk(v / 1e6, 3)
        p = lambda v: pct(100 * v, 2) if pd.notna(v) and self.HAR_OMK_PA else "–"
        rows = [[e] + [mio(r[c]) for c in self.omk_kol] + [mio(r[self.omk_kol].sum()),
                                                           p(r["honorar_pct_tilsagn"]),
                                                           p(r["loebende_pct_nav"])]
                for e, (_, r) in zip(self._aarsetiketter(o.index), o.iterrows())]
        rows.append(["Siden start"] + [mio(o[c].sum()) for c in self.omk_kol]
                    + [mio(o[self.omk_kol].sum().sum()), p(self.HONORAR_PA), p(self.LOEBENDE_PA)])
        n = len(self.omk_kol)
        render_table(
            "Omkostninger pr. år",
            ["År"] + [KAT_NAVN[c] for c in self.omk_kol] + ["I alt", "Honorar, % af tilsagn p.a.",
                                                            "Løbende, % af gns. NAV p.a."],
            rows, [0.9] + [1.2] * n + [1, 1.5, 1.5], ["left"] + ["right"] * (n + 3),
            self.C("tabel_omkostninger"),
            subtitle="Positiv = omkostning · løbende = honorar + fondsomkostninger · pct. er "
                     "omregnet til helårsniveau", highlight_row=len(rows) - 1)

    # ------------------------------------------------------------------ Excel

    def excel(self):
        """Alle tabellerne bag graferne i ét regneark, så tallene kan efterprøves række for række."""
        ark = {
            "Perioder": self.per.reset_index().rename(columns={
                "period_end": "Periode slut", "start": "Periode start", "dage": "Dage",
                "nav_primo": "NAV primo", "nav_ultimo": "NAV ultimo",
                "netto_indbetalt": "Nettoindbetalt", "vaerdiskabelse": "Værdiskabelse",
                "kapital": "Bundet kapital (Dietz)", "afkast": "Afkast", "indeks": "Indeks",
                "nettovaerdi": "Akk. værdiskabelse", "afkast_12m": "Afkast 12 mdr.",
                "vaerdiskabelse_12m": "Værdiskabelse 12 mdr.", "vis_pct": "Pct. vises",
                "lang": "Mere end ét kvartal"}),
            "Horisonter": pd.DataFrame(self.horisonter).rename(columns={
                "navn": "Horisont", "start": "Fra", "irr": "IRR", "vaerdiskabelse": "Værdiskabelse"}),
            "Kvartalsserie": self.serie.reset_index(),
        }
        if self.HAR_KILDER:
            ark["Kilder akkumuleret"] = self.kat.rename(columns=KAT_NAVN).reset_index()
            ark["Kilder pr. periode"] = self.kat_per.rename(columns=KAT_NAVN).reset_index()
            ark["Kilder pr. år"] = self.kat_aar.rename(columns=KAT_NAVN).reset_index()
            ark["Kapitalkonto akkumuleret"] = self.kum.reset_index()
        if self.HAR_HONORAR:
            ark["Omkostninger pr. år"] = self.omk_aar.rename(columns={
                **KAT_NAVN, "aarsbroek": "Andel af året", "tilsagn": "Tilsagn",
                "gns_nav": "Gns. NAV", "honorar_pct_tilsagn": "Honorar / tilsagn p.a.",
                "loebende_pct_nav": "Løbende / gns. NAV p.a."}).reset_index()
        ark["Indkald efter formål"] = self.indkald.rename("Beløb").rename_axis("Formål").reset_index()
        if len(self.udlodninger):
            ark["Udlodninger efter art"] = self.udlodninger.rename("Beløb").rename_axis("Art") \
                .reset_index()
        if self.HAR_VALUTA:
            ark["Valuta"] = pd.DataFrame([self.fx]).T.rename(columns={0: "Værdi"}) \
                .rename_axis("Post").reset_index()
            ark["Valuta over tid"] = self.fx_tid.reset_index()
        ark["Afstemning"] = pd.DataFrame(self.afstemning).assign(
            afvigelse=lambda d: d["beregnet"] - d["kontrol"])

        sti = self._eksportsti("xlsx")
        with pd.ExcelWriter(sti, engine="openpyxl", datetime_format="DD-MM-YYYY") as xl:
            for navn, df in ark.items():
                df.to_excel(xl, sheet_name=navn[:31], index=False)
                ws = xl.sheets[navn[:31]]
                for kol in ws.columns:
                    bredde = max((len(str(c.value)) for c in kol[:50] if c.value is not None),
                                 default=8)
                    ws.column_dimensions[kol[0].column_letter].width = min(48, max(12, bredde + 2))
        print(f"gemt: {sti}  ({len(ark)} ark)")
        return sti

    # ------------------------------------------------------------------ deckets tekst

    def hovedpunkter(self):
        n, k, p = self.nu, self.kvt, self.per
        punkter = []
        t = (f"Seneste {'periode' if k['lang'] else 'kvartal'} ({k['start']:%d.%m.%Y} → "
             f"{ps.REPORT_DK}) gav {self.dm(k['vaerdiskabelse'])} i værdiskabelse"
             + (f", et afkast på {dpct(100 * k['afkast'])}" if k["vis_pct"] else ""))
        if pd.notna(k["vaerdiskabelse_12m"]):
            t += (f". Over de seneste 12 måneder er det {self.dm(k['vaerdiskabelse_12m'])}"
                  + (f" ({dpct(100 * k['afkast_12m'])})" if pd.notna(k["afkast_12m"]) else ""))
        punkter.append(t + ".")

        vist = p[p["vis_pct"] & ~p["lang"]]
        if len(vist) >= 4:
            punkter.append(
                f"{int((vist['afkast'] > 0).sum())} af {len(vist)} kvartaler har været positive. "
                f"Det bedste gav {dpct(100 * vist['afkast'].max())} "
                f"({vist['afkast'].idxmax():%d.%m.%Y}), det svageste "
                f"{dpct(100 * vist['afkast'].min())} ({vist['afkast'].idxmin():%d.%m.%Y}).")
        h = [x for x in self.horisonter if pd.notna(x["irr"])]
        if len(h) >= 2:
            punkter.append("IRR pr. horisont: " + ", ".join(
                f"{x['navn'].lower()} {pct(100 * x['irr'])}" for x in h)
                + f". Siden start er nettoresultatet {self.dm(n['nettovaerdi'])} på "
                  f"{self.m(n['indbetalt'])} indbetalt (TVPI {mult(n['tvpi'])}).")
        else:
            punkter.append(
                f"Siden første indbetaling ({self.cf['value_date'].min():%d.%m.%Y}) er "
                f"nettoresultatet {self.dm(n['nettovaerdi'])} på {self.m(n['indbetalt'])} indbetalt "
                f"(TVPI {mult(n['tvpi'])}). Investeringen er for ung til en annualiseret IRR.")

        if self.HAR_KILDER:
            nu = self.kat.iloc[-1]
            kilder = nu[self.brutto_kol]
            kilder = kilder[kilder.abs() > 0.005 * max(abs(self.BRUTTO), 1)].sort_values(ascending=False)
            led = ", ".join(f"{KAT_NAVN[i].lower()} {self.dm(v)}" for i, v in kilder.items())
            if self.HAR_HONORAR:
                vaesentlig = 0.005 * max(abs(self.BRUTTO), 1)
                t = (f"Bruttoresultatet siden start er {self.dm(self.BRUTTO)} ({led}). Heraf går "
                     + ", ".join(f"{self.m(-nu[c])} til {KAT_NAVN[c].lower()}" for c in self.omk_kol
                                 if nu[c] < -vaesentlig))
                if pd.notna(self.OMK_ANDEL):
                    t += (f" - i alt {pct(100 * self.OMK_ANDEL, 0)} af bruttoresultatet eller "
                          f"{mult(-self.OMK / self.GP_INDBETALT)} på indbetalt kapital")
                punkter.append(t + ".")
                if self.HAR_OMK_PA:
                    punkter.append(
                        f"Set over hele perioden svarer forvaltningshonoraret til "
                        f"{pct(100 * self.HONORAR_PA, 2)} af tilsagnet p.a., og honorar plus "
                        f"fondsomkostninger til {pct(100 * self.LOEBENDE_PA, 2)} af den "
                        f"gennemsnitlige NAV p.a.")
            else:
                punkter.append(
                    f"Kapitalkontoens nettoresultat siden start er {self.dm(self.NETTO_GP)}: {led}"
                    + (f", og carried interest {self.dm(nu['carry'])}" if "carry" in nu else "")
                    + ". GP'en udskiller ikke forvaltningshonoraret, så en brutto-netto-bro kan "
                      "ikke opstilles.")
        if self.HAR_CF_SPLIT:
            brutto = self.INDKALDT_BRUTTO
            retur = -self.indkald[self.indkald < 0].sum()
            punkter.append(
                f"Af {self.m(brutto)} indkaldt er " + ", ".join(
                    f"{pct(100 * v / brutto, 0)} {i.lower()}" for i, v in self.indkald.items()
                    if v / brutto >= 0.005)
                + (f"; {self.m(retur)} er betalt tilbage ved udligning" if retur > 0.5 else "") + "."
                + (f" Resttilsagnet er {self.m(n['resttilsagn'])}." if n["resttilsagn"] > 0 else ""))
        if self.HAR_VALUTA:
            fx = self.fx
            punkter.append(
                f"I DKK er merværdien {self.dkk(fx['mervaerdi'])}: "
                f"{self.dkk(fx['lokalt'])} er fondens afkast i {self.valuta} til dagens "
                f"kurs, og {self.dkk(fx['fx'])} er valutaeffekt ({self.valuta}/DKK "
                f"{_dk(fx['kurs'], 2)} mod {_dk(fx['kurs_indbetalt'], 2)} i gennemsnit ved "
                f"indbetaling)"
                + (f". IRR er {pct(100 * fx['irr'])} i DKK mod {pct(100 * n['irr'])} i {self.valuta}"
                   if pd.notna(fx["irr"]) else "") + ".")
        return punkter

    def forbehold(self):
        p = list(self.advarsler)
        p.append(
            "Alt er investorniveau: vores pengestrømme, vores NAV og vores kapitalkonto, efter "
            "honorar og carry. Værdiskabelse er ændringen i NAV plus udlodninger minus "
            "indbetalinger, inklusive udligningsrenter og eksklusive kildeskat.")
        p.append(
            "Periodeafkast er Modified Dietz: værdiskabelsen divideret med primo-NAV plus "
            "periodens nettoindbetalinger, vægtet med den del af perioden de har været inde. "
            f"Procenten vises først, når den bundne kapital er over {pct(100 * MIN_KAPITAL, 0)} "
            "af tilsagnet; 12 måneders afkast er kvartalerne kædet sammen.")
        if len([x for x in self.horisonter if pd.notna(x["irr"])]) >= 2:
            p.append("IRR pr. horisont behandler NAV ved horisontens start som et indskud og "
                     "NAV i dag som slutværdi (XIRR, faktisk/365).")
        if self.HAR_KILDER:
            p.append(
                "Afkastets kilder er kapitalkontoens linjer, som GP'en selv opgør dem, lagt "
                "sammen siden start. Hvor fint resultatet er opdelt, afhænger af GP'en"
                + (f"; efterreguleringer af årsultimo ({self.dm(self.RESTAT_SUM)} i alt) indgår i "
                   f"{KAT_NAVN[self.RESTAT_I].lower()}" if abs(self.RESTAT_SUM) > 0.5 else "") + ".")
            if self.SAMLET:
                p.append("GP'en er holdt op med at opdele resultatet i sine opgørelser, så hele "
                         "historikken vises samlet, og honoraret kan ikke udskilles.")
            if "hul" in self.kat:
                p.append(f"{self.dm(self.kat['hul'].iloc[-1])} af resultatet ligger i perioder "
                         "uden opgørelse og kan ikke fordeles på kilder.")
        else:
            p.append("Kapitalkontoen kan ikke lægges sammen siden start for fonden, så afkastets "
                     "kilder og omkostninger er ikke vist.")
        if self.huller:
            p.append("Der mangler opgørelser for " + ", ".join(f"{d:%d.%m.%Y}" for d in self.huller)
                     + ". Perioden hen over et hul vises som én lang periode.")
        if self.HAR_VALUTA:
            p.append("DKK-tal er omregnet med Danmarks Nationalbanks kurs på hver pengestrøms dato "
                     "og på opgørelsesdatoen. Valutaeffekten er forskellen mellem merværdien i DKK "
                     "og merværdien i fondens valuta omregnet til dagens kurs; den er ikke afdækket.")
        p.append("NAV er GP'ens egen værdiansættelse og ikke realiseret.")
        return p

    # ------------------------------------------------------------------ deck og samlet kørsel

    def deck(self):
        """Alle slides samlet i ét deck på PPIM-masteren."""
        sektioner = [dict(titel=t, slides=s) for t, metoder in SLIDES
                     if (s := self._slides(*[m.removeprefix("graf_") for m in metoder]))]
        n, k = self.nu, self.kvt
        fakta = [("Afkast seneste 12 mdr.", dpct(100 * k["afkast_12m"])) if pd.notna(k["afkast_12m"])
                 else ("Værdiskabelse, seneste periode", self.dm(k["vaerdiskabelse"])),
                 ("IRR siden start", pct(100 * n["irr"])) if pd.notna(n["irr"])
                 else ("TVPI", mult(n["tvpi"])),
                 ("Omkostninger af bruttoresultat", pct(100 * self.OMK_ANDEL, 0))
                 if self.HAR_KILDER and pd.notna(self.OMK_ANDEL)
                 else ("Nettoresultat siden start", self.dm(n["nettovaerdi"]))]
        return byg_deck(
            self._eksportsti("pptx"), titel=self.navn, undertitel=f"Afkastanalyse pr. {ps.REPORT_DK}",
            sektioner=sektioner, fakta=fakta,
            tekstslides=[dict(titel="Hovedpunkter", punkter=self.hovedpunkter()),
                         dict(titel="Metode og forbehold", punkter=self.forbehold())])

    def koer_alt(self):
        """Alle slides i deckets rækkefølge, så Excel og deck."""
        for _, metoder in SLIDES:
            for navn in metoder:
                getattr(self, navn)()
        self.excel()
        return self.deck()
