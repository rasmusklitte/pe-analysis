"""Afkastets kilder og omkostninger (kapitalkontoen) samt kapitalens anvendelse (meddelelserne)."""
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter

from ..style import (PPIM_SAGE_DARK, PPIM_SAGE_LIGHT, PPIM_TAUPE, PPIM_BROWN, INK, LINE, GRID,
                     legend_swatches, _dk, mult)
from .kerne import KAT_FARVE, KAT_NAVN, MIN_NAV_ANDEL, brudt, pct, stabl, vandfald


class Kilder:
    def _aarsetiketter(self, aar):
        """Indeværende år er ikke et helt år, medmindre opgørelsen er en årsultimo."""
        hel = self.as_of.month == 12
        return [f"{a} ÅTD" if a == self.as_of.year and not hel else str(a) for a in aar]

    def _kat_legend(self, ax, kolonner, ekstra=(), ncol=4):
        """Forklaringen i et bånd over søjlerne, så den aldrig dækker dem."""
        poster = [(KAT_FARVE[k], KAT_NAVN[k]) for k in kolonner] + list(ekstra)
        lav, hoej = ax.get_ylim()
        ax.set_ylim(lav, hoej + (hoej - lav) * 0.11 * -(-len(poster) // ncol))
        legend_swatches(ax, poster, fontsize=10, loc="upper left", ncol=ncol)

    def graf_kilder_tid(self):
        """Slide 5: akkumuleret resultat pr. opgørelsesdato, stablet efter kilde."""
        if not self._kraever(self.HAR_KILDER and len(self.kat) >= 3,
                             "kapitalkonto siden start over mindst tre opgørelser"):
            return
        k = self.kat / 1e6
        x = np.arange(len(k))
        fig, ax = self._figur(
            "Hvor kommer resultatet fra: akkumuleret siden start",
            f"Kapitalkontoens resultatlinjer som GP'en opgør dem, uden ind- og udbetalinger "
            f"· mio. {self.valuta}")
        stabl(ax, x, k, KAT_FARVE)
        netto = k.sum(axis=1)
        ax.plot(x, netto.values, color=INK, linewidth=1.8, marker="o", markersize=3.5, zorder=4)
        ax.axhline(0, color=LINE, linewidth=0.9)
        self._kvartalsakse(ax, list(k.index))
        self._mio_akse(ax)
        self._kat_legend(ax, k.columns, [(INK, f"Nettoresultat  {self.dm(self.NETTO_GP)}")])
        self._gem(fig, "kilder_tid", ax, self._kilde_note())

    def graf_kilder_aar(self):
        """Slide 6: resultatet pr. kalenderår, stablet efter kilde, med årets netto som prik."""
        if not self._kraever(self.HAR_KILDER and len(self.kat_aar) >= 2,
                             "kapitalkonto over mindst to kalenderår"):
            return
        k = self.kat_aar / 1e6
        x = np.arange(len(k))
        fig, ax = self._figur(
            "Resultatet år for år",
            f"Kapitalkontoens resultatlinjer pr. kalenderår · prikken er årets nettoresultat "
            f"· mio. {self.valuta}")
        pos, neg = stabl(ax, x, k, KAT_FARVE, width=0.6)
        netto = k.sum(axis=1)
        ax.scatter(x, netto, s=42, color=INK, zorder=4)
        for i, v in enumerate(netto):
            ax.annotate(("+" if v >= 0 else "−") + _dk(abs(v), self.dec), (i, pos[i]),
                        xytext=(0, 4), textcoords="offset points", ha="center", va="bottom",
                        fontsize=10.5, fontweight="bold")
        ax.axhline(0, color=LINE, linewidth=0.9)
        ax.set_xticks(x, self._aarsetiketter(k.index), fontsize=10.5)
        ax.set_xlim(-0.7, len(k) - 0.3)
        ax.margins(y=0.14)
        self._mio_akse(ax)
        self._kat_legend(ax, k.columns, [(INK, "Årets nettoresultat (prik, tal over søjlen)")])
        self._gem(fig, "kilder_aar", ax, self._kilde_note())

    def _kilde_note(self):
        note = ""
        if abs(self.RESTAT_SUM) > 0.5:
            note += f" · efterreguleringer af årsultimo indgår i {KAT_NAVN[self.RESTAT_I].lower()}"
        if self.SAMLET:
            note += " · GP'en opdeler ikke længere resultatet"
        return note

    def graf_brutto_netto(self):
        """Slide 7: fra bruttoresultat til nettoresultat, led for led siden start."""
        if not self._kraever(self.HAR_KILDER and len(self.kat.columns) >= 2,
                             "kapitalkonto med mere end én resultatlinje"):
            return
        nu = self.kat.iloc[-1] / 1e6
        led = lambda kol: [(brudt(KAT_NAVN[k]), nu[k], "bev") for k in kol if abs(nu[k]) > 5e-7]
        trin = led(self.brutto_kol)
        if self.HAR_HONORAR:
            trin.append(("Brutto-\nresultat", self.BRUTTO / 1e6, "total"))
        trin += led(self.omk_kol) + [("Netto-\nresultat", self.NETTO_GP / 1e6, "total")]
        if self.HAR_HONORAR:
            titel = "Fra brutto til netto: hvad koster forvaltningen"
            under = (f"Siden start · mio. {self.valuta}"
                     + (f" · honorar, omkostninger og carry tager {pct(100 * self.OMK_ANDEL, 0)} af "
                        f"bruttoresultatet, svarende til {mult(-self.OMK / self.GP_INDBETALT)} "
                        f"på indbetalt kapital" if pd.notna(self.OMK_ANDEL) else ""))
        else:
            titel = "Nettoresultatet siden start, led for led"
            under = (f"Kapitalkontoens resultatlinjer som GP'en opgør dem · mio. {self.valuta} "
                     f"· forvaltningshonoraret er ikke udskilt og ligger i resultatlinjen")
        fig, ax = self._figur(titel, under)
        vandfald(ax, trin, self.dec, fs=10)
        self._mio_akse(ax)
        self._gem(fig, "brutto_netto", ax, self._kilde_note())

    def graf_omkostninger(self):
        """Slide 8: omkostningerne pr. år i beløb og de løbende i pct. af tilsagn og NAV."""
        if not self._kraever(self.HAR_HONORAR, "forvaltningshonorar udskilt i kapitalkontoen"):
            return
        o = self.omk_aar
        x = np.arange(len(o))
        if self.HAR_OMK_PA:
            fig, (ax, ax2) = self._figur(
                "Omkostninger år for år",
                "Som GP'en bogfører dem på vores kapitalkonto · pct. er omregnet til helårsniveau, "
                "hvor året ikke er helt",
                ncols=2, gridspec_kw=dict(width_ratios=[1.15, 1]))
        else:
            fig, ax = self._figur("Omkostninger år for år",
                                  "Som GP'en bogfører dem på vores kapitalkonto")
        stabl(ax, x, o[self.omk_kol] / 1e6, KAT_FARVE, width=0.6)
        ialt = o[self.omk_kol].sum(axis=1) / 1e6
        for i, v in enumerate(ialt):
            top = (o[self.omk_kol].iloc[i].clip(lower=0).sum()) / 1e6
            ax.annotate(_dk(v, self.dec if abs(v) >= 0.1 else 3), (i, top), xytext=(0, 4),
                        textcoords="offset points", ha="center", va="bottom", fontsize=10,
                        fontweight="bold")
        ax.axhline(0, color=LINE, linewidth=0.9)
        ax.set_xticks(x, self._aarsetiketter(o.index))
        ax.set_xlim(-0.7, len(o) - 0.3)
        ax.margins(y=0.14)
        self._mio_akse(ax)
        ax.set_title(f"Omkostninger, mio. {self.valuta} (positiv = omkostning)", loc="left",
                     fontsize=12, fontweight="bold")
        self._kat_legend(ax, self.omk_kol, ncol=2)
        if not self.HAR_OMK_PA:
            return self._gem(fig, "omkostninger", ax,
                             " · første opgørelse kan rumme honorar fra før vores indtræden")

        b = 0.36
        ax2.bar(x - b / 2, 100 * o["honorar_pct_tilsagn"], width=b, color=PPIM_BROWN)
        ax2.bar(x + b / 2, 100 * o["loebende_pct_nav"], width=b, color=PPIM_TAUPE)
        for dx, kol in ((-b / 2, "honorar_pct_tilsagn"), (b / 2, "loebende_pct_nav")):
            for i, v in enumerate(100 * o[kol]):
                if pd.notna(v):
                    ax2.annotate(_dk(v, 1), (i + dx, max(v, 0)), xytext=(0, 3),
                                 textcoords="offset points", ha="center", va="bottom", fontsize=9)
        ax2.axhline(0, color=LINE, linewidth=0.9)
        ax2.set_xticks(x, self._aarsetiketter(o.index))
        ax2.set_xlim(-0.7, len(o) - 0.3)
        ax2.margins(y=0.16)
        ax2.yaxis.set_major_formatter(FuncFormatter(lambda y, _: _dk(y, 1) + " %"))
        ax2.set_title("Løbende omkostninger, pct. p.a.", loc="left", fontsize=12, fontweight="bold")
        lav, hoej = ax2.get_ylim()
        ax2.set_ylim(lav, hoej + (hoej - lav) * 0.22)
        legend_swatches(ax2, [(PPIM_BROWN, "Honorar i pct. af tilsagn"),
                              (PPIM_TAUPE, "Honorar + fondsomkostninger i pct. af gns. NAV")],
                        loc="upper left", fontsize=10)
        note = "" if o["loebende_pct_nav"].notna().all() else \
            (f" · pct. af NAV vises ikke for år, hvor NAV var under "
             f"{pct(100 * MIN_NAV_ANDEL, 0)} af sit højeste")
        self._gem(fig, "omkostninger", ax, note)

    # ------------------------------------------------------------------ kapitalens anvendelse

    def _vandret(self, ax, d, titel, farve):
        d = d[d.abs() > 0.5][::-1] / 1e6
        total, brutto = d.sum(), d.clip(lower=0).sum()
        ax.barh(range(len(d)), d.values, color=farve, height=0.62)
        ax.set_yticks(range(len(d)), d.index, fontsize=10.5)
        spaend = max(d.max(), 0) - min(d.min(), 0)
        for i, v in enumerate(d.values):
            # andelen er af det, der er kaldt hhv. udloddet før tilbagebetalinger
            tekst = f"{_dk(v, self.dec)}  ({pct(100 * v / brutto, 0)})" if v >= 0 else \
                "−" + _dk(abs(v), self.dec)
            ax.text(max(v, 0) + 0.012 * spaend, i, tekst, va="center", fontsize=10)
        ax.grid(axis="y", visible=False)
        ax.grid(axis="x", color=GRID, linewidth=0.8)
        ax.axvline(0, color=LINE, linewidth=0.8)
        ax.set_xlim(min(d.min(), 0) * 1.05, max(d.max(), 0) + 0.34 * spaend)
        ax.set_ylim(-0.6, max(len(d), 3) - 0.4)
        self._mio_akse(ax, "x")
        ax.set_title(f"{titel}\n{self.m(total * 1e6)} i alt", loc="left", fontsize=12,
                     fontweight="bold")

    def graf_formaal(self):
        """Slide 9: hvad indkaldene er gået til, og hvad udlodningerne består af."""
        if not self._kraever(self.HAR_CF_SPLIT, "indkald opdelt efter formål i meddelelserne"):
            return
        har_udl = self.udlodninger.abs().sum() > 0.5
        fig, axes = self._figur(
            "Kapitalens anvendelse: indkald efter formål" + (" og udlodninger efter art"
                                                            if har_udl else ""),
            f"Som GP'ens meddelelser opdeler dem · siden start · mio. {self.valuta} "
            f"· andel i parentes",
            ncols=2 if har_udl else 1)
        ax = np.atleast_1d(axes)[0]
        self._vandret(ax, self.indkald, "Indbetalt", PPIM_TAUPE)
        if har_udl:
            self._vandret(axes[1], self.udlodninger, "Udloddet", PPIM_SAGE_DARK)
        self._gem(fig, "formaal", ax, " · udligningsrenter og kildeskat ikke medregnet")

    def graf_tilsagn(self):
        """Slide 10: tilsagnets udnyttelse over tid og hvor længe resttilsagnet rækker."""
        s = self.serie
        if not self._kraever(len(s) >= 2, "to opgørelser"):
            return
        n = self.nu
        x = np.arange(len(s))
        trukket = (s["commitment"] - s["resttilsagn"]) / 1e6
        under = (f"Resttilsagn {self.m(n['resttilsagn'])} "
                 f"({pct(100 * n['resttilsagn'] / n['commitment'], 0)} af tilsagnet)")
        foer = self.as_of - pd.DateOffset(years=1) + pd.offsets.MonthEnd(0)
        if foer in s.index:
            kaldt = n["indbetalt"] - s.loc[foer, "indbetalt"]
            under += f" · indbetalt seneste 12 måneder {self.m(kaldt)}"
            if kaldt > 0 and n["resttilsagn"] > 0:
                under += f" · i den takt rækker resttilsagnet {_dk(n['resttilsagn'] / kaldt, 1)} år"
        fig, ax = self._figur("Tilsagnets udnyttelse", under + f" · mio. {self.valuta}")
        ax.bar(x, trukket, width=0.72, color=PPIM_TAUPE)
        ax.bar(x, s["resttilsagn"] / 1e6, width=0.72, bottom=trukket, color=PPIM_SAGE_LIGHT)
        ax.plot(x, s["nav"] / 1e6, color=PPIM_SAGE_DARK, linewidth=2.4, marker="o", markersize=4)
        self._kvartalsakse(ax, list(s.index))
        self._mio_akse(ax)
        ax.set_ylim(0, max(s["commitment"].max(), s["nav"].max()) / 1e6 * 1.22)
        genind = n["genindkaldelig"] > 0
        legend_swatches(ax, [(PPIM_TAUPE, "Trukket af tilsagnet"
                              + (" (indbetalt minus genindkaldelige udlodninger)" if genind else "")),
                             (PPIM_SAGE_LIGHT, "Resttilsagn"),
                             (PPIM_SAGE_DARK, f"NAV  {self.m(n['nav'])}")],
                        loc="upper left", fontsize=10.5, ncol=3)
        self._gem(fig, "tilsagn", ax)
