"""Fælles grundlag for analyserne: fondens stamdata, filnavne, slide-ramme og deck-udvælgelse.

En analyse er en klasse med én metode pr. slide. Hver metode tjekker selv, om fonden har de
data, den skal bruge (`_kraever`), tegner på husstilens 16:9-ramme (`_figur` / `_gem`) og
gemmer en PNG i charts/. Decket bygges til sidst af de PNG'er, der faktisk blev tegnet
(`_slides`), så den samme analyse kan køre for fonde med meget forskelligt datagrundlag.
"""
import re
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import FuncFormatter

from . import data
from .style import MX, BOTTOM_FRAC, SLIDE, _dk, add_footer, add_header, save, source_line, style_ax


def kortnavn(fund_name):
    """Fondens navn uden selskabsform - forsidens titel skal kunne stå på én linje."""
    return re.sub(r",?\s+(L\.P\.|K/S|SCSp|B K/S)$", "", fund_name).strip()


class Analyse:
    def __init__(self, fund_code, analyse, charts="charts", exports="exports"):
        self.fond = data.fond(fund_code)
        self.kode = self.fond["fund_code"]
        self.slug = self.kode.lower()
        self.navn = kortnavn(self.fond["fund_name"])
        self.valuta = self.fond["currency"]
        self.charts, self.exports = Path(charts), Path(exports)
        self.charts.mkdir(exist_ok=True)
        self.exports.mkdir(exist_ok=True)
        self.PRAEFIKS = f"{self.slug}_{analyse}"
        # Decket bygges af de PNG'er, der findes. Slides fra en tidligere kørsel (en tabelside
        # mere, en graf der nu springes over) må ikke hænge ved.
        for gammel in self.charts.glob(f"{self.PRAEFIKS}_*.png"):
            gammel.unlink()

    def C(self, navn):
        return str(self.charts / f"{self.PRAEFIKS}_{navn}.png")

    def _eksportsti(self, endelse):
        return self.exports / f"{self.PRAEFIKS}_{self.as_of:%d%m%Y}.{endelse}"

    def _kraever(self, betingelse, hvad):
        if not betingelse:
            print(f"Ingen {hvad} for {self.kode} - springer over")
        return bool(betingelse)

    # ------------------------------------------------------------------ akser

    def _mio_akse(self, ax, akse="y"):
        a = ax.yaxis if akse == "y" else ax.xaxis

        def fmt(v, _):      # decimaler efter afstanden mellem mærkerne, så etiketterne er ens
            t = a.get_ticklocs()
            trin = abs(t[1] - t[0]) if len(t) > 1 else 1
            return _dk(v, next((d for d in (0, 1, 2) if abs(trin * 10 ** d % 1) < 1e-6
                                or abs(trin * 10 ** d % 1 - 1) < 1e-6), 3))
        a.set_major_formatter(FuncFormatter(fmt))

    def _tidsakse(self, ax, datoer):
        """Årstal ved lang historik, ellers kvartalsultimoer."""
        spaend = (max(datoer) - min(datoer)).days / 365.25
        if spaend > 4:
            ax.xaxis.set_major_locator(mdates.YearLocator())
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        else:
            ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=(3, 6, 9, 12), bymonthday=-1)
                                       if spaend <= 2 else mdates.MonthLocator(bymonth=(6, 12),
                                                                              bymonthday=-1))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%m.%Y"))

    def _kvartalsakse(self, ax, datoer):
        """Kategoriakse med én søjle pr. dato; hver anden etiket ved lang historik."""
        n = len(datoer)
        hop = 1 if n <= 14 else 2 if n <= 28 else 4
        vis = [i for i in range(n) if (n - 1 - i) % hop == 0]      # seneste dato vises altid
        ax.set_xticks(vis, [f"{datoer[i]:%m.%y}" for i in vis])
        ax.set_xlim(-0.7, n - 0.3)

    # ------------------------------------------------------------------ slide-ramme

    def _figur(self, titel, undertitel, ncols=1, **kw):
        fig, axes = plt.subplots(1, ncols, figsize=SLIDE, **kw)
        self._top = add_header(fig, titel, undertitel)
        for ax in np.atleast_1d(axes):
            style_ax(ax)
        return fig, axes

    def _gem(self, fig, navn, ax, kilde_extra="", layout=True, rect=None):
        if layout:
            fig.tight_layout(rect=rect or [MX, BOTTOM_FRAC, 1 - MX, self._top], w_pad=3.0)
        add_footer(fig, source_line(kilde_extra), ax=ax)
        save(fig, self.C(navn))
        plt.show()

    def _slides(self, *navne):
        """De af kandidaterne, der faktisk blev tegnet - inkl. en tabels _side1, _side2 ..."""
        ud = []
        for navn in navne:
            sider = sorted(self.charts.glob(f"{self.PRAEFIKS}_{navn}_side*.png"),
                           key=lambda p: int(re.search(r"_side(\d+)", p.name).group(1)))
            ud += sider or [p for p in [Path(self.C(navn))] if p.exists()]
        return ud
