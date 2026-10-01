"""Valuta: hvad er afkastet i DKK, og hvor meget af det er kursbevægelse.

Kun for fonde i anden valuta end DKK. Indbetalinger og udlodninger er omregnet med
Nationalbankens kurs på hver pengestrøms dato, NAV med kursen på opgørelsesdatoen.
"""
import pandas as pd
from matplotlib.ticker import FuncFormatter

from ..style import (PPIM_SAGE_DARK, PPIM_TAUPE, PPIM_TAUPE_LIGHT, LINE, legend_swatches, ref_pill,
                     _dk, mult)
from .kerne import pct, vandfald


class Valuta:
    def graf_valutabro(self):
        """Slide 11: fra indbetalt til værdi i DKK - afkast i fondens valuta og valutaeffekt."""
        if not self._kraever(self.HAR_VALUTA, "valutaeffekt (fonden er i DKK)"):
            return
        fx, n = self.fx, self.nu
        trin = [("Indbetalt", fx["indbetalt"], "total"),
                (f"Afkast i {self.valuta}\ntil dagens kurs", fx["lokalt"], "bev"),
                ("Valutaeffekt på\nindbetalt kapital", fx["fx_indbetalt"], "bev")]
        if n["udloddet"] > 0:
            trin.append(("Valutaeffekt på\nudlodninger", fx["fx_udloddet"], "bev"))
        trin.append(("NAV + udloddet", fx["vaerdi"], "total"))
        under = (f"Mio. DKK · {self.valuta}/DKK {_dk(fx['kurs'], 2)} pr. {self.as_of:%d.%m.%Y} mod "
                 f"{_dk(fx['kurs_indbetalt'], 2)} i gennemsnit ved indbetaling")
        if pd.notna(fx["irr"]):
            under += f" · IRR {pct(100 * fx['irr'])} i DKK mod {pct(100 * n['irr'])} i {self.valuta}"
        fig, ax = self._figur("Afkastet i DKK: fondens afkast og valutaens bidrag", under)
        vandfald(ax, [(navn, v / 1e6, art) for navn, v, art in trin], 1, fs=10.5)
        ax.set_xlim(-0.7, len(trin) - 0.3)
        self._mio_akse(ax)
        self._gem(fig, "valutabro", ax,
                  " · Nationalbankens kurs på hver pengestrøms dato og på opgørelsesdatoen")

    def graf_valuta_tid(self):
        """Slide 12: TVPI i fondens valuta mod DKK over tid, og kursen ved hver indbetaling."""
        if not self._kraever(self.HAR_VALUTA and len(self.serie) >= 3,
                             "valutaudvikling over mindst tre opgørelser"):
            return
        t, fx = self.fx_tid, self.fx
        fig, (ax, ax2) = self._figur(
            "Valutaen over tid",
            f"TVPI målt i {self.valuta} og i DKK · kursen på hver indbetaling mod kursen i dag",
            ncols=2)
        ax.plot(t.index, t["tvpi"], color=PPIM_SAGE_DARK, linewidth=2.4, marker="o", markersize=4)
        ax.plot(t.index, t["tvpi_dkk"], color=PPIM_TAUPE, linewidth=2.2, marker="s", markersize=4)
        ax.axhline(1.0, color=LINE, linewidth=0.9, linestyle=(0, (4, 3)))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: _dk(y, 2) + "x"))
        spaend = t[["tvpi", "tvpi_dkk"]].max().max() - t[["tvpi", "tvpi_dkk"]].min().min()
        if spaend < 0.2:      # en næsten flad serie må ikke zoomes ind til støj
            midt = (t[["tvpi", "tvpi_dkk"]].max().max() + t[["tvpi", "tvpi_dkk"]].min().min()) / 2
            ax.set_ylim(midt - 0.12, midt + 0.12)
        self._tidsakse(ax, list(t.index))
        ax.set_title("TVPI pr. opgørelsesdato", loc="left", fontsize=12, fontweight="bold")
        legend_swatches(ax, [(PPIM_SAGE_DARK, f"I {self.valuta}  {mult(t['tvpi'].iloc[-1])}"),
                             (PPIM_TAUPE, f"I DKK  {mult(t['tvpi_dkk'].iloc[-1])}")],
                        loc="best", fontsize=10.5)

        c = self.cf[self.cf["flow_class"] == "CONTRIBUTION"].groupby("value_date")[
            ["amount", "amount_dkk"]].sum()
        c = c[c["amount"] < 0]
        kurs = c["amount_dkk"] / c["amount"]
        ax2.scatter(c.index, kurs, s=40 + 520 * c["amount"].abs() / c["amount"].abs().max(),
                    color=PPIM_TAUPE_LIGHT, edgecolor=PPIM_TAUPE, linewidth=0.8, zorder=3)
        ax2.plot(t.index, t["kurs"], color=PPIM_SAGE_DARK, linewidth=1.8, zorder=2)
        ref_pill(ax2, fx["kurs_indbetalt"], f"Snit {_dk(fx['kurs_indbetalt'], 2)}")
        ax2.yaxis.set_major_formatter(FuncFormatter(lambda y, _: _dk(y, 2)))
        lav, hoej = min(kurs.min(), t["kurs"].min()), max(kurs.max(), t["kurs"].max())
        ax2.set_ylim(lav - 0.15 * (hoej - lav) - 0.02, hoej + 0.15 * (hoej - lav) + 0.02)
        self._tidsakse(ax2, list(c.index) + list(t.index))
        ax2.set_title(f"{self.valuta}/DKK: kurs ved hver indbetaling", loc="left", fontsize=12,
                      fontweight="bold")
        legend_swatches(ax2, [(PPIM_TAUPE_LIGHT, "Indbetaling (størrelse efter beløb)"),
                              (PPIM_SAGE_DARK, f"Kurs pr. opgørelsesdato  {_dk(fx['kurs'], 2)}")],
                        loc="best", fontsize=10.5)
        self._gem(fig, "valuta_tid", ax, " · Danmarks Nationalbanks kurser",
                  rect=[0.055, 0.075, 1 - 0.085, self._top])
