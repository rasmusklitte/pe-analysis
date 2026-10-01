"""Tabeller, Excel-eksport og deck for porteføljeanalysen.

Tabellerne er de samme tal som graferne, men til at læse i. Excel-arket rummer det hele, så
alt i decket kan spores tilbage til en række. Deckets tekst regnes ud her i stedet for at
blive skrevet af - så følger den data.
"""
import numpy as np
import pandas as pd

from ..deck import byg_deck
from ..fondskonfig import DIETZ_VAEGT, MIN_INVESTED, MIN_MOVE, UR_KOSTPRIS, UR_MODEN
from ..style import _dk, money, mult, render_table
from .kerne import NUM, dmoney, dpct, lille, pct
from .tid import POS_KEY


def _kort(tekst, n=44):
    tekst = str(tekst)
    return tekst if len(tekst) <= n else tekst[:n - 2] + "…"


# Slides i deckets rækkefølge. Notebook-skabelonen (scripts/byg_skabeloner.py) følger samme liste.
SLIDES = [
    ("Overblik og værdibro", ["graf_noegletal", "graf_vaerdibro", "graf_boeger", "graf_tidsserie"]),
    ("Struktur", ["graf_gruppemix", "graf_gruppe_tvpi", "graf_kapitalgruppe", "graf_gruppemix_tid"]),
    ("Afkastspredning, tab og koncentration",
     ["graf_spredning", "graf_tabsanalyse", "graf_nedskrivning", "graf_koncentration"]),
    ("Afkast mod tid", ["graf_irr_vs_mom", "graf_irr_fordeling", "graf_holdeperiode",
                        "graf_periodeafkast", "graf_delboeger"]),
    ("Vintage og realiseringstakt", ["graf_vintage_kapital", "graf_vintage_tvpi", "graf_exits"]),
    ("Porteføljen i dag", ["graf_urealiseret_top", "graf_valuta", "graf_kvartal", "graf_positioner",
                           "graf_ureal_struktur", "graf_ureal_marks", "graf_ureal_modenhed",
                           "graf_ureal_kostpris", "graf_branche_geografi", "graf_branche_tid",
                           "graf_selskabs_kpi"]),
    ("Nøgletal i tabelform", ["tabel_noegletal", "tabel_gruppe", "tabel_vintage", "tabel_selskaber",
                              "tabel_positioner", "tabel_delboeger"]),
]


class Eksport:
    # ------------------------------------------------------------------ tabeller

    def _irr_samlet(self):
        m = self.raw["irr"].notna() & (self.raw["invested"] > 0)
        return np.average(self.raw.loc[m, "irr"], weights=self.raw.loc[m, "invested"]) if m.any() \
            else np.nan

    def tabel_noegletal(self):
        tot = self.tot
        rows = [
            [f"{self.cfg.enhed.capitalize()} / investeringer", f"{self.N_INV} / {self.N_TR}"],
            ["Investeret kapital", money(tot["invested"])],
            ["Udlodninger (realiseret)", money(tot["proceeds"])],
            ["Dagsværdi (urealiseret)", money(tot["fair_value"])],
            ["Samlet værdi", money(tot["total_value"])],
            ["Samlet gevinst", money(self.GEVINST)],
            ["DPI", mult(self.pool_dpi)],
            ["RVPI", mult(self.pool_rvpi)],
            ["TVPI", mult(self.pool_tvpi)],
            ["Andel af værdi realiseret", pct(self.pool_dpi / self.pool_tvpi, 0)],
        ]
        if self.HAR_REAL:
            rows += [["Realiseret bog - multipel",
                      mult(self.REAL["total_value"].sum() / self.REAL["invested"].sum())],
                     ["Urealiseret bog - multipel",
                      mult(self.UREAL["total_value"].sum() / self.UREAL["invested"].sum())]]
        rows += [
            ["Tabsrate (tab i pct. af investeret kapital)", pct(self.TABSRATE, 1)],
            ["Tabsgivende investeringer",
             f"{len(self.tabere)} af {self.N_TR}  ({pct(len(self.tabere) / self.N_TR, 0)})"],
            ["Nedskrivning der fjerner hele gevinsten", pct(self.break_even, 0)],
            ["Top 5's andel af gevinsten", pct(self.top5, 0)],
            ["Top 10's andel af gevinsten", pct(self.top10, 0)],
            ["HHI på investeret kapital",
             _dk(self.hhi, 3) + f"  (≈ {1 / self.hhi:.0f} lige store positioner)"],
        ]
        if pd.notna(self.REAL_LEVETID):
            rows.append(["Kapitalvægtet levetid, realiserede", _dk(self.REAL_LEVETID, 1) + " år"])
        if self.HAR_IRR:
            rows += [["Kapitalvægtet IRR pr. handel (GP)", pct(self._irr_samlet(), 1)],
                     ["Median-IRR pr. handel (GP)", pct(self.raw["irr"].median(), 1)]]
        if self.HAR_PERIODE:
            fk, fy = self.AFKAST_FOND["kvt"], self.AFKAST_FOND["ytd"]
            rows += [[f"Seneste kvartal ({self.FORRIGE_DK} →): merværdi / afkast",
                      f"{dmoney(fk['abs'])} / {dpct(fk['r'], 2)}"],
                     [f"År til dato ({self.AAR_DK} →): merværdi / afkast",
                      f"{dmoney(fy['abs'])} / {dpct(fy['r'], 2)}"]]
            if not self.HAR_PCT_AFKAST:
                rows = rows[:-2] + [[r[0].replace(" / afkast", ""), r[1].split(" / ")[0]]
                                    for r in rows[-2:]]
        render_table(f"Samlede nøgletal for {self.navn}", ["Nøgletal", "Værdi"], rows,
                     col_widths=[0.62, 0.38], aligns=["left", "right"],
                     outfile=self.C("tabel_noegletal"),
                     subtitle=f"Hele fonden, poolet på tværs af porteføljen · brutto · pr. {self.REPORT_DK}",
                     highlight_row=8)

    def _dimensionstabel(self, g, forste, titel, navn, undertitel):
        rows = [[_kort(i, 28), f"{int(r.antal)}", money(r.investeret, 0), pct(r.andel, 0),
                 mult(r.dpi), mult(r.rvpi), mult(r.tvpi), money(r.gevinst, 0),
                 pct(r.irr_vaegtet, 1), pct(r.realiseret_andel, 0), pct(r.tabsrate, 1)]
                for i, r in zip(g.index, g.itertuples())]
        rows.append(["I alt", f"{int(g['antal'].sum())}", money(g["investeret"].sum(), 0), "100 %",
                     mult(g["udlodninger"].sum() / g["investeret"].sum()),
                     mult(g["dagsvaerdi"].sum() / g["investeret"].sum()),
                     mult(g["samlet"].sum() / g["investeret"].sum()),
                     money(g["gevinst"].sum(), 0), pct(self._irr_samlet(), 1),
                     pct(g["realiseret_kap"].sum() / g["investeret"].sum(), 0),
                     pct(g["tab"].sum() / g["investeret"].sum(), 1)])
        render_table(titel,
                     [forste, "Antal", "Investeret", "Andel", "DPI", "RVPI", "TVPI", "Gevinst",
                      "IRR (GP)", "Realiseret", "Tabsrate"], rows,
                     col_widths=[0.20, 0.06, 0.10, 0.07, 0.07, 0.07, 0.07, 0.10, 0.09, 0.09, 0.08],
                     aligns=["left"] + ["right"] * 10, outfile=self.C(navn), subtitle=undertitel,
                     highlight_row=len(rows) - 1)

    def tabel_gruppe(self):
        if not self._kraever(self.HAR_GRUPPE, f"opdeling på {self.cfg.gruppe_omtale}"):
            return
        self._dimensionstabel(self.g_under, self.UNDER_NAVN, f"Nøgletal pr. {self.UNDER_NAVN.lower()}",
                              "tabel_gruppe",
                              f"Sorteret efter investeret kapital · beløb i {self.MIO} · pr. {self.REPORT_DK}")

    def tabel_vintage(self):
        if not self._kraever(self.HAR_VINTAGE, "vintage"):
            return
        self._dimensionstabel(self.g_vintage.rename(index=lambda v: str(int(v))), "Vintage",
                              "Nøgletal pr. vintage", "tabel_vintage",
                              f"Vintage er {self.cfg.vintage_omtale} · beløb i {self.MIO} · pr. {self.REPORT_DK}")

    def tabel_selskaber(self):
        t = self.inv.sort_values("total_value", ascending=False)
        tot = self.tot
        rows = [[_kort(r.investment, 40), f"{int(r.antal_trancher)}",
                 str(int(r.vintage)) if pd.notna(r.vintage) else "–",
                 "Realiseret" if r.alle_realiseret else "Aktiv",
                 _dk(r.invested, 1), _dk(r.proceeds, 1), _dk(r.fair_value, 1), _dk(r.total_value, 1),
                 _dk(r.gevinst, 1), mult(r.mom) if pd.notna(r.mom) else "–",
                 _dk(r.holdeperiode, 1) if pd.notna(r.holdeperiode) else "–"]
                for r in t.itertuples()]
        rows.append(["I alt", f"{self.N_TR}", "", "", _dk(tot["invested"], 1), _dk(tot["proceeds"], 1),
                     _dk(tot["fair_value"], 1), _dk(tot["total_value"], 1), _dk(self.GEVINST, 1),
                     mult(self.pool_tvpi), ""])
        render_table(f"Nøgletal pr. {self.cfg.enhed_ental}",
                     [self.cfg.enhed_ental.capitalize(), "Linjer", "Vintage", "Status", "Investeret",
                      "Udlodninger", "Dagsværdi", "Samlet værdi", "Gevinst", "MoM", "År"], rows,
                     col_widths=[0.26, 0.05, 0.06, 0.08, 0.09, 0.09, 0.09, 0.10, 0.08, 0.06, 0.04],
                     aligns=["left", "right", "right", "left"] + ["right"] * 7,
                     outfile=self.C("tabel_selskaber"),
                     subtitle=f"Sorteret efter samlet værdi · beløb i {self.MIO} · pr. {self.REPORT_DK}",
                     highlight_row=len(rows) - 1)

    def tabel_positioner(self):
        """Udviklingen i hver enkelt position (selskab og tranche)."""
        if not self._kraever(self.HAR_PERIODE and self.HAR_INSTRUMENT, "positioner pr. tranche over tid"):
            return
        p = self.pos.sort_values("d_merv_ytd", ascending=False)
        kort_gruppe = {g: g.split(" ")[0].split("/")[0] for g in self.GRUPPE_ORDEN}
        rows = [[_kort(r.label, 40), kort_gruppe.get(r.gruppe, ""), _dk(r.invested_nu, 1),
                 _dk(r.fair_value_nu, 1), mult(r.mom_nu) if pd.notna(r.mom_nu) else "–",
                 dmoney(r.d_merv_kvt), dmoney(r.d_merv_ytd), r.note]
                for r in p.itertuples()]
        rows.append(["I alt", "", _dk(p["invested_nu"].sum(), 1), _dk(p["fair_value_nu"].sum(), 1),
                     mult(self.pool_tvpi), dmoney(p["d_merv_kvt"].sum()),
                     dmoney(p["d_merv_ytd"].sum()), ""])
        render_table("Udvikling pr. position",
                     ["Position", "Gruppe", "Investeret", "Dagsværdi", "MoM", "Δ merværdi kvt.",
                      "Δ merværdi ÅTD", ""], rows,
                     col_widths=[0.30, 0.10, 0.10, 0.10, 0.08, 0.12, 0.12, 0.08],
                     aligns=["left", "left"] + ["right"] * 5 + ["left"],
                     outfile=self.C("tabel_positioner"),
                     subtitle=f"Kvartalet {self.FORRIGE_DK} → {self.REPORT_DK} · år til dato fra "
                              f"{self.AAR_DK} · beløb i {self.MIO}",
                     highlight_row=len(rows) - 1)

    def tabel_delboeger(self):
        """Delbøgerne (PSCP: PIK og Preferred) med begge perioder."""
        if not self._kraever(self.HAR_PERIODE and self.cfg.delboege, "delbøger defineret for fonden"):
            return
        for bog, cfg in self.cfg.delboege.items():
            y = self.AFKAST_POS["ytd"]
            y = y[y["delbog"] == bog].sort_values("abs", ascending=False)
            k = self.AFKAST_POS["kvt"].reindex(y.index)
            if y.empty:
                continue
            rows = [[_kort(r.label, 36), _dk(r.V0, 1), _dk(r.V1, 1), _dk(r.indbet, 1), _dk(r.udbet, 1),
                     dmoney(kv.abs), dpct(kv.r, 1), dmoney(r.abs), dpct(r.r, 1),
                     "restateret" if r.restateret else ""]
                    for r, kv in zip(y.itertuples(), k.itertuples())]
            g, gk = self.AFKAST_DELBOG["ytd"].loc[bog], self.AFKAST_DELBOG["kvt"].loc[bog]
            rows.append(["I alt", _dk(g["V0"], 1), _dk(g["V1"], 1), _dk(g["indbet"], 1),
                         _dk(g["udbet"], 1), dmoney(gk["abs"]), dpct(gk["r"], 2), dmoney(g["abs"]),
                         dpct(g["r"], 2), ""])
            render_table(f"{bog}-bogen: afkast pr. position",
                         ["Position", "Dagsv. primo", "Dagsv. nu", "Indbetalt", "Udbetalt",
                          "Afkast kvt.", "% kvt.", "Afkast ÅTD", "% ÅTD", ""], rows,
                         col_widths=[0.26, 0.09, 0.09, 0.08, 0.08, 0.10, 0.07, 0.10, 0.07, 0.06],
                         aligns=["left"] + ["right"] * 8 + ["left"],
                         outfile=self.C(f"tabel_{cfg['slug']}"),
                         subtitle=f"Primo = {self.AAR_DK} · Modified Dietz, kædet kvartal for kvartal "
                                  f"· beløb i {self.MIO}", highlight_row=len(rows) - 1)

    # ------------------------------------------------------------------ Excel

    def excel(self):
        """Alle tabellerne bag graferne i ét regneark."""
        dk = {"report_date": "Rapportdato", "investment": self.cfg.enhed_ental.capitalize(),
              "tranche": "Tranche", "instrument": "Instrumenttype", "gruppe": self.cfg.gruppe_navn,
              "valuta": "Handelsvaluta", "trade_date": "Handelsdato", "exit_date": "Exit-dato",
              "vintage": "Vintage", "realiseret": "Realiseret", "holdeperiode": "Holdeperiode (år)",
              "invested": "Investeret", "proceeds": "Udlodninger", "fair_value": "Dagsværdi",
              "total_value": "Samlet værdi", "irr": "IRR (GP)", "mom": "MoM", "gevinst": "Gevinst",
              "tab": "Tab"}
        agg = {"investeret": "Investeret", "udlodninger": "Udlodninger", "dagsvaerdi": "Dagsværdi",
               "samlet": "Samlet værdi", "tab": "Tab", "antal": "Antal",
               "realiseret_kap": "Realiseret kapital", "tvpi": "TVPI", "dpi": "DPI", "rvpi": "RVPI",
               "gevinst": "Gevinst", "andel": "Andel", "tabsrate": "Tabsrate",
               "realiseret_andel": "Realiseret andel", "irr_vaegtet": "IRR vægtet (GP)",
               "irr_median": "IRR median (GP)"}
        ark = {
            "Linjer": self.raw.drop(columns=["label", "exit_aar"]).rename(
                columns={**dk, "total_value_gp": "Samlet værdi (GP)"}),
            f"Pr. {self.cfg.enhed_ental}": self.inv.rename(columns={**dk, "antal_trancher": "Linjer",
                                                                    "alle_realiseret": "Realiseret"}),
        }
        if self.HAR_GRUPPE:
            ark[f"Pr. {self.UNDER_NAVN.lower()}"] = self.g_under.rename(columns=agg).reset_index()
            if self.HAR_INSTRUMENT:
                ark[f"Pr. {self.cfg.gruppe_omtale}"] = self.g_gruppe.rename(columns=agg).reset_index()
        if self.HAR_VINTAGE:
            ark["Pr. vintage"] = self.g_vintage.rename(columns=agg).reset_index()
        if self.HAR_VALUTA:
            ark["Pr. valuta"] = self.g_valuta.rename(columns=agg).reset_index()
        if self.HAR_PERIODE:
            ark["Udvikling pr. position"] = self.pos.reset_index()
            ark["Udvikling pr. selskab"] = self.sel_udv.reset_index()
            for p, navn in (("kvt", "Periodeafkast kvartal"), ("ytd", "Periodeafkast ÅTD")):
                ark[navn] = self.AFKAST_POS[p].reset_index()
        if hasattr(self, "TIDSSERIE"):
            ark["Track record over tid"] = self.TIDSSERIE.reset_index()
        if hasattr(self, "KPI_NU"):
            ark["Selskabsnøgletal"] = self.KPI_NU.drop(columns=["commentary", "document_id", "inv"],
                                                       errors="ignore")
            ark["Selskabsnøgletal over tid"] = self.KPI_TID.reset_index()
        if hasattr(self, "BREAKDOWN"):
            ark["GP's fordelinger"] = self.BREAKDOWN.drop(columns=["fund_code", "fund_name",
                                                                   "document_id"])
        ark["Afstemning"] = self.afstem_tabel.reset_index(names="dimension")

        sti = self._eksportsti("xlsx")
        with pd.ExcelWriter(sti, engine="openpyxl", datetime_format="DD-MM-YYYY") as xl:
            for navn, df in ark.items():
                df.to_excel(xl, sheet_name=navn[:31], index=False)
                ws = xl.sheets[navn[:31]]
                for kol in ws.columns:
                    bredde = max((len(str(c.value)) for c in kol[:50] if c.value is not None),
                                 default=8)
                    ws.column_dimensions[kol[0].column_letter].width = min(48, max(12, bredde + 2))
        print(f"gemt: {sti}  ({len(ark)} ark · beløb i {self.MIO})")
        return sti

    # ------------------------------------------------------------------ deckets tekst

    def konklusion(self):
        tot, cfg = self.tot, self.cfg
        p = [f"{self.navn} står pr. {self.REPORT_DK} i {mult(self.pool_tvpi)} på "
             f"{money(tot['invested'], 0)} investeret kapital. "
             f"{pct(self.pool_dpi / self.pool_tvpi, 0)} af værdien er allerede udloddet "
             f"({money(tot['proceeds'], 0)}); resten er GP'ens egne dagsværdier."]
        if self.HAR_REAL:
            p.append(
                f"De {len(self.REAL)} realiserede investeringer er hjemtaget til "
                f"{mult(self.REAL['total_value'].sum() / self.REAL['invested'].sum())}"
                + (f" med en kapitalvægtet levetid på {_dk(self.REAL_LEVETID, 1)} år."
                   if pd.notna(self.REAL_LEVETID) else "."))
        tab = (f"Samlet tabsrate {pct(self.TABSRATE, 1)} af investeret kapital fordelt på "
               f"{len(self.tabere)} af {self.N_TR} investeringer")
        if len(self.tabere) and self.HAR_GRUPPE:
            pr = self.tabere.groupby("gruppe")["tab"].sum()
            tab += (f" - og hvert eneste tab ligger i {lille(pr.idxmax())}."
                    if (pr > MIN_MOVE).sum() == 1 else
                    f"; {pct(pr.max() / pr.sum(), 0)} af tabet ligger i {lille(pr.idxmax())}.")
        else:
            tab += "."
        p.append(tab)
        if self.HAR_GRUPPE:
            g = self.g_gruppe
            p.append("Fordelt på " + cfg.gruppe_omtale + ": "
                     + "; ".join(f"{lille(i)} er {pct(r.andel, 0)} af kapitalen og står i {mult(r.tvpi)}"
                                 for i, r in zip(g.index, g.itertuples())) + ".")
        p.append(f"Koncentrationen: top 5 {cfg.enhed} står for {pct(self.top5, 0)} af gevinsten, "
                 f"top 10 for {pct(self.top10, 0)}, og HHI på {_dk(self.hhi, 3)} svarer til "
                 f"{1 / self.hhi:.0f} lige store positioner.")
        if self.HAR_PERIODE:
            fk, fy = self.AFKAST_FOND["kvt"], self.AFKAST_FOND["ytd"]
            op = int((self.pos["d_merv_ytd"] > MIN_MOVE).sum())
            ned = int((self.pos["d_merv_ytd"] < -MIN_MOVE).sum())
            i_pct = (lambda f: f" ({dpct(f['r'], 2)})") if self.HAR_PCT_AFKAST else (lambda f: "")
            p.append(f"Seneste kvartal ({self.FORRIGE_DK} → {self.REPORT_DK}) gav "
                     f"{dmoney(fk['abs'], enhed=True)} i merværdi{i_pct(fk)}"
                     + (f", år til dato {dmoney(fy['abs'], enhed=True)}{i_pct(fy)}"
                        if self.TO_PERIODER else "")
                     + f". {op} af {len(self.pos)} positioner steg og {ned} faldt.")
        if hasattr(self, "BOG_SKIFT"):
            s = self.BOG_SKIFT
            p.append(f"{pct(self.ANDEL_UREAL_VAERDI, 0)} af værdien er endnu ikke afgjort, og den bog "
                     f"ligner ikke den, der er hjemtaget: {lille(s)} er "
                     f"{pct(self.BOG['Realiseret'].loc[s, 'andel'], 0)} af den realiserede kapital mod "
                     f"{pct(self.BOG['Urealiseret'].loc[s, 'andel'], 0)} af den urealiserede.")
        if 0 < self.break_even < 1:
            p.append(f"En generel nedskrivning af dagsværdien på {pct(self.break_even, 0)} fjerner "
                     f"hele gevinsten; DPI på {mult(self.pool_dpi)} kan ikke tages tilbage.")
        if hasattr(self, "KPI_NU"):
            nu = self.KPI_NU
            w = lambda kol: np.average(nu.loc[nu[kol].notna(), kol],
                                       weights=nu.loc[nu[kol].notna(), "invested_amount"])
            p.append(f"Selskaberne bag har en vægtet nettogæld på {_dk(w('net_leverage'), 1)}x EBITDA "
                     f"mod {_dk(w('leverage_at_investment'), 1)}x ved investering og en værdiansættelse "
                     f"på {_dk(w('ev_to_ebitda'), 1)}x EBITDA.")
        return p

    def metode(self):
        cfg = self.cfg
        p = [f"Datagrundlag: rpt.v_portfolio_holding i PE-databasen - {self.N_TR} linjer på "
             f"{self.N_INV} {cfg.enhed} pr. {self.REPORT_DK}, og {len(self.DATOER)} rapportdatoer fra "
             f"{self.FOERSTE:%d.%m.%Y}. Alle beløb er {self.MIO} for hele fonden, brutto som "
             "GP'en rapporterer dem.",
             "Forhold beregnes altid på summerede beløb (TVPI = samlet værdi / investeret kapital), "
             "aldrig som gennemsnit af multipler.",
             "Tabsrate = summen af tab på positioner under 1,0x i pct. af investeret kapital. "
             "Merværdi = samlet værdi minus investeret kapital; et kapitalkald løfter begge sider "
             "lige meget og er derfor ikke værdiskabelse."]
        if self.HAR_INSTRUMENT:
            p.insert(2, f"{cfg.gruppe_navn}rne er en analytisk inddeling af instrumenttyperne: "
                        + "; ".join(f"{lille(g)} ({', '.join(sorted(set(self.raw.loc[self.raw['gruppe'] == g, 'instrument'])))})"
                                    for g in self.GRUPPE_ORDEN) + ".")
        if cfg.afviklet_ved_nul:
            p.append("Rapporten markerer ikke realiserede beholdninger; en beholdning regnes som "
                     "afviklet, når dagsværdien er nul og der er udloddet.")
        p.append(f"\"Til kostpris\" er {_dk(UR_KOSTPRIS[0], 2)}-{_dk(UR_KOSTPRIS[1], 2)}x, og en "
                 f"position kaldes moden efter {UR_MODEN:.0f} år. Multipler på positioner under "
                 f"{money(MIN_INVESTED, 0)} er afrundingsstøj og udeladt af forholdsgraferne.")
        if self.HAR_PERIODE and self.HAR_PCT_AFKAST:
            vaegt = "½" if DIETZ_VAEGT == 0.5 else f"{DIETZ_VAEGT:g} ×"
            p.append("Periodeafkast er Modified Dietz: (dagsværdi ultimo − dagsværdi primo + "
                     f"udbetalinger − indbetalinger) ÷ (dagsværdi primo + {vaegt} indbetalinger). "
                     "Indbetalinger vægtes midt i perioden, fordi rapporten ikke daterer dem, og år "
                     "til dato er kædet kvartal for kvartal.")
            p.append("Værdiregulering er ændringen i dagsværdi renset for ind- og udbetalinger. "
                     "\"Uændret mark\" betyder uændret i hvert eneste skridt mellem opgørelserne siden "
                     "årsskiftet, ikke blot fra første til sidste.")
        if hasattr(self, "KPI_NU"):
            p.append("Selskabsnøgletallene er selskabernes egne tal fra GP'ens rapport, vægtet med "
                     "fondens investerede beløb. De ligger typisk 1-2 kvartaler før rapportdatoen.")
        return p

    def forbehold(self):
        p = list(self.advarsler)
        p.append("Alle tal er brutto for de underliggende investeringer. Hverken honorar, carry "
                 "eller fondsomkostninger er fratrukket, så nettoafkastet til investor er lavere.")
        if self.HAR_IRR:
            p.append("IRR'erne er GP'ens egne pr. handel. Beholdningsdata rummer ikke daterede "
                     "pengestrømme, så en samlet IRR kan ikke beregnes herfra"
                     + (f" ({self.N_NM} handler er uden IRR og indgår ikke)." if self.N_NM else "."))
        if self.DETALJE_FRA > self.FOERSTE:
            p.append(f"Rapporten har først linjer pr. tranche fra {self.DETALJE_FRA:%d.%m.%Y}. "
                     "Før det findes kun ét tal pr. selskab, så historik på instrumenttype og valuta "
                     "begynder der.")
        if self.HAR_PERIODE and self.FALDNE:
            p.append(" og ".join(self.FALDNE).capitalize() + " er lavere end ved referencedatoen. "
                     "Kumulative tal kan ikke falde, så tidligere rapportering må være korrigeret; "
                     "periodeændringerne skal læses med det forbehold.")
        if self.HAR_PERIODE and self.udgaaede and not self.cfg.ustabile_navne:
            navne = list(self.pos.loc[self.udgaaede, "label"])
            p.append(f"{len(navne)} positioner står ikke længere under samme betegnelse som ved "
                     f"referencedatoen ({', '.join(navne[:4])}" + (" m.fl." if len(navne) > 4 else "")
                     + "). GP'en har omlagt tranchens navn eller valuta; de ses som udgåede og nye "
                       "positioner, mens selskabets total er uberørt.")
        if self.HAR_PERIODE and self.RESTATERET and self.HAR_PCT_AFKAST:
            navne = sorted(self.pos.loc[list(self.RESTATERET), "label"])
            p.append(f"{len(navne)} positioner er restateret i perioden og udeladt af de relative "
                     f"afkast (men ikke af beløbene): {', '.join(navne[:5])}"
                     + (" m.fl." if len(navne) > 5 else "") + ".")
        if self.cfg.ustabile_navne:
            p.append("GP'en skriver beholdningernes navne forskelligt fra rapport til rapport. Et "
                     "navneskift ses som én udgået og én ny position i bevægelsesgraferne; "
                     "totalerne påvirkes ikke.")
        p.append(f"{pct(self.ANDEL_UREAL_VAERDI, 0)} af værdien er urealiseret og dermed GP'ens egen "
                 "værdiansættelse. Nedskrivningsgrafen viser følsomheden, men er en illustration, "
                 "ikke en forventning.")
        return p

    # ------------------------------------------------------------------ deck og samlet kørsel

    def deck(self):
        """Alle slides i ét deck på PPIM-masteren - syv sektioner, som agendaen har plads til."""
        slugs = [c["slug"] for c in self.cfg.delboege.values()]
        kandidater = [
            ("Overblik og værdibro", ["noegletal", "vaerdibro", "boeger", "tidsserie"]),
            (self.cfg.sektion_struktur, ["gruppemix", "gruppe_tvpi", "kapitalgruppe", "gruppemix_tid"]),
            ("Afkastspredning, tab og koncentration",
             ["spredning", "tabsanalyse", "nedskrivning", "koncentration"]),
            ("Afkast mod tid", ["irr_vs_mom", "irr_fordeling", "holdeperiode", "periodeafkast"]
             + [f"{s}_positioner" for s in slugs]),
            ("Vintage og realiseringstakt", ["vintage_kapital", "vintage_tvpi", "exits"]),
            ("Porteføljen i dag", ["urealiseret_top", "valuta", "kvartal", "positioner",
                                   "ureal_struktur", "ureal_marks", "ureal_modenhed", "ureal_kostpris",
                                   "branche_geografi", "branche_tid", "selskabs_kpi"]),
            ("Nøgletal i tabelform", ["tabel_noegletal", "tabel_gruppe", "tabel_vintage",
                                      "tabel_selskaber", "tabel_positioner"]
             + [f"tabel_{s}" for s in slugs]),
        ]
        sektioner = [dict(titel=t, slides=s) for t, navne in kandidater if (s := self._slides(*navne))]
        return byg_deck(
            self._eksportsti("pptx"), titel=self.navn,
            undertitel=f"Porteføljeanalyse · hele fonden · pr. {self.REPORT_DK}",
            sektioner=sektioner,
            fakta=[("Poolet TVPI", mult(self.pool_tvpi)),
                   ("Investeret kapital", money(self.tot["invested"], 0)),
                   (self.cfg.enhed.capitalize(), str(self.N_INV))],
            tekstslides=[dict(titel="Konklusion", punkter=self.konklusion()),
                         dict(titel="Metode", punkter=self.metode()),
                         dict(titel="Forbehold", punkter=self.forbehold())])

    def koer_alt(self):
        """Alle slides i deckets rækkefølge, så Excel og deck."""
        for _, metoder in SLIDES:
            for navn in metoder:
                getattr(self, navn)()
        self.excel()
        return self.deck()
