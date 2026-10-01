"""Periodeafkast: hvad har investeringen givet pr. kvartal, over 12 måneder og pr. horisont."""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .. import style as ps
from ..style import (PPIM_SAGE_DARK, PPIM_SAGE_LIGHT, PPIM_RED_MUTED, PPIM_RED_LIGHT, SLIDE, MX,
                     BOTTOM_FRAC, LINE, add_header, _dk, mult)
from .kerne import MIN_KAPITAL, dpct, pct, pct_akse, tavle


class Perioder:
    def graf_noegletal(self):
        """Slide 1: nøgletalstavle - periodeafkast, resultat, omkostninger og valuta."""
        n, k, p = self.nu, self.kvt, self.per
        periode = f"{k['start']:%d.%m.%Y} → {ps.REPORT_DK}"
        kort = [("Seneste kvartal" if not k["lang"] else "Seneste periode",
                 dpct(100 * k["afkast"]) if k["vis_pct"] else self.dm(k["vaerdiskabelse"]),
                 f"{self.dm(k['vaerdiskabelse'])} · {periode}" if k["vis_pct"] else periode,
                 k["vaerdiskabelse"] < 0)]
        if pd.notna(k["vaerdiskabelse_12m"]):
            har = pd.notna(k["afkast_12m"])
            kort.append(("Seneste 12 måneder",
                         dpct(100 * k["afkast_12m"]) if har else self.dm(k["vaerdiskabelse_12m"]),
                         f"{self.dm(k['vaerdiskabelse_12m'])} i værdiskabelse" if har
                         else "værdiskabelse", k["vaerdiskabelse_12m"] < 0))
        kort.append(("IRR siden start", pct(100 * n["irr"]) if pd.notna(n["irr"]) else "–",
                     f"TVPI {mult(n['tvpi'])} · efter omkostninger" if pd.notna(n["irr"])
                     else "under ét års historik", pd.notna(n["irr"]) and n["irr"] < 0))
        kort.append(("Nettoresultat siden start", self.dm(n["nettovaerdi"]),
                     f"på {self.m(n['indbetalt'])} indbetalt", n["nettovaerdi"] < 0))
        if self.HAR_HONORAR:
            kort.append(("Bruttoresultat", self.dm(self.BRUTTO),
                         "før honorar, omkostninger og carry", self.BRUTTO < 0))
            kort.append(("Omkostninger og carry", self.dm(self.OMK),
                         f"{pct(100 * self.OMK_ANDEL, 0)} af bruttoresultatet"
                         if pd.notna(self.OMK_ANDEL) else "siden start", False))
        elif self.HAR_KILDER and "carry" in self.kat:
            kort.append(("Carried interest", self.dm(self.kat["carry"].iloc[-1]),
                         "afsat af GP'en siden start", False))
        if self.HAR_VALUTA:
            fx = self.fx
            kort.append(("Valutaeffekt", self.dkk(fx["fx"]),
                         f"{self.valuta}/DKK {_dk(fx['kurs'], 2)} mod {_dk(fx['kurs_indbetalt'], 2)} "
                         f"ved indbetaling", fx["fx"] < 0))
            if pd.notna(fx["irr"]):
                kort.append(("IRR i DKK", pct(100 * fx["irr"]),
                             f"mod {pct(100 * n['irr'])} i {self.valuta}", fx["irr"] < 0))
        fyld = [("NAV", self.m(n["nav"]), f"RVPI {mult(n['rvpi'])}", False),
                ("Udloddet", self.m(n["udloddet"]), f"DPI {mult(n['dpi'])}", False),
                ("Resttilsagn", self.m(n["resttilsagn"]),
                 f"{pct(100 * n['resttilsagn'] / n['commitment'], 0)} af tilsagnet", False),
                ("Indbetalt", self.m(n["indbetalt"]),
                 f"{pct(100 * n['indbetalt'] / n['commitment'], 0)} af tilsagnet", False)]
        kort = (kort + fyld)[:8]

        fig = plt.figure(figsize=SLIDE)
        top = add_header(fig, "Afkastet i nøgletal",
                         f"{self.fond['investorer']} · vores investering, efter omkostninger "
                         f"· pr. {ps.REPORT_DK}")
        ax = fig.add_axes([MX, BOTTOM_FRAC + 0.03, 1 - 2 * MX, top - BOTTOM_FRAC - 0.05])
        tavle(ax, kort)
        self._gem(fig, "noegletal", None, layout=False)

    def graf_kvartalsafkast(self):
        """Slide 2: værdiskabelse pr. opgørelsesperiode med afkastet i pct. over søjlen."""
        p = self.per
        if not self._kraever(len(p) >= 2, "to opgørelser at måle en periode imellem"):
            return
        v = p["vaerdiskabelse"] / 1e6
        x = np.arange(len(p))
        farver = [(PPIM_SAGE_LIGHT if l else PPIM_SAGE_DARK) if b >= 0 else
                  (PPIM_RED_LIGHT if l else PPIM_RED_MUTED) for b, l in zip(v, p["lang"])]
        fig, ax = self._figur(
            "Værdiskabelse pr. kvartal",
            f"Ændring i NAV plus udlodninger minus indbetalinger · mio. {self.valuta} "
            f"· procenten er periodens afkast (Modified Dietz)")
        ax.bar(x, v, width=0.72, color=farver)
        hop = 1 if len(p) <= 16 else 2
        for i, r in enumerate(p.itertuples()):
            if r.vis_pct and (len(p) - 1 - i) % hop == 0:
                ax.annotate(dpct(100 * r.afkast), (i, v.iloc[i]), xytext=(0, 3 if v.iloc[i] >= 0 else -3),
                            textcoords="offset points", ha="center",
                            va="bottom" if v.iloc[i] >= 0 else "top",
                            fontsize=8.5 if len(p) > 12 else 9.5,
                            fontweight="bold" if i == len(p) - 1 else "normal")
        ax.axhline(0, color=LINE, linewidth=0.9)
        ax.margins(y=0.14)
        self._kvartalsakse(ax, list(p.index))
        self._mio_akse(ax)
        note = []
        if p["lang"].any():
            note.append("lyse søjler dækker mere end ét kvartal")
        if not p["vis_pct"].all():
            note.append(f"pct. vises først, når den bundne kapital er over "
                        f"{pct(100 * MIN_KAPITAL, 0)} af tilsagnet")
        self._gem(fig, "kvartalsafkast", ax, "".join(f" · {t}" for t in note))

    def graf_rullende(self):
        """Slide 3: rullende 12 måneder - værdiskabelse i beløb og afkast i pct."""
        p = self.per[self.per["vaerdiskabelse_12m"].notna()]
        if not self._kraever(len(p) >= 2, "rullende 12 måneder (kræver mere end ét års opgørelser)"):
            return
        har_pct = p["afkast_12m"].notna().sum() >= 2
        fig, axes = self._figur(
            "Rullende 12 måneder",
            "Hver dato viser de foregående 12 måneder" + (" · afkastet er kvartalernes "
                                                         "Modified Dietz kædet sammen" if har_pct else ""),
            ncols=2 if har_pct else 1)
        ax = np.atleast_1d(axes)[0]
        v = p["vaerdiskabelse_12m"] / 1e6
        x = np.arange(len(p))
        ax.bar(x, v, width=0.72, color=[PPIM_SAGE_DARK if b >= 0 else PPIM_RED_MUTED for b in v])
        ax.axhline(0, color=LINE, linewidth=0.9)
        ax.set_title(f"Værdiskabelse, mio. {self.valuta}\nseneste: {self.dm(p['vaerdiskabelse_12m'].iloc[-1])}",
                     loc="left", fontsize=12, fontweight="bold")
        self._kvartalsakse(ax, list(p.index))
        self._mio_akse(ax)
        note = ""
        if har_pct:
            ax2 = axes[1]
            r = 100 * p["afkast_12m"]
            ax2.plot(x, r.values, color=PPIM_SAGE_DARK, linewidth=2.4, marker="o", markersize=4.5)
            ax2.axhline(0, color=LINE, linewidth=0.9)
            # De første 12 måneder er afkast på en lille kapital og kan være flere hundrede pct.
            gyldig = r.dropna()
            loft = max(2.5 * gyldig.abs().median(), 2 * abs(gyldig.iloc[-1]), 10.0)
            if gyldig.abs().max() > loft:
                ax2.set_ylim(max(gyldig.min(), -loft) - 1 if gyldig.min() < 0 else -1,
                             min(gyldig.max(), loft))
                note = f" · afkast uden for ±{_dk(loft, 0)} % er skåret af"
            pct_akse(ax2)
            ax2.set_title(f"Afkast i pct.\nseneste: {dpct(gyldig.iloc[-1])}", loc="left",
                          fontsize=12, fontweight="bold")
            self._kvartalsakse(ax2, list(p.index))
        self._gem(fig, "rullende", ax, note)

    def graf_horisont(self):
        """Slide 4: IRR over 1, 3 og 5 år og siden start."""
        h = [x for x in self.horisonter if pd.notna(x["irr"])]
        if not self._kraever(len(h) >= 2, "afkast pr. horisont (kræver mere end ét års opgørelser)"):
            return
        fig, ax = self._figur(
            "Afkast pr. horisont",
            "IRR p.a. på periodens pengestrømme, med NAV ved periodens start som indskud "
            "· værdiskabelsen i perioden står under søjlen")
        r = [100 * x["irr"] for x in h]
        x = np.arange(len(h))
        ax.bar(x, r, width=0.5, color=[PPIM_SAGE_DARK if v >= 0 else PPIM_RED_MUTED for v in r])
        for i, v in enumerate(r):
            ax.annotate(pct(v), (i, v), xytext=(0, 4 if v >= 0 else -4), textcoords="offset points",
                        ha="center", va="bottom" if v >= 0 else "top", fontsize=13, fontweight="bold")
        ax.set_xticks(x, [f"{t['navn']}\nfra {t['start']:%d.%m.%Y}\n{self.dm(t['vaerdiskabelse'])}"
                          for t in h], fontsize=10.5)
        ax.set_xlim(-0.7, len(h) - 0.3)
        ax.axhline(0, color=LINE, linewidth=0.9)
        ax.margins(y=0.16)
        pct_akse(ax)
        self._gem(fig, "horisont", ax, " · inkl. udligningsrenter, ekskl. kildeskat")
