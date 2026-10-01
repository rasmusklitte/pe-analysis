"""Slides på seneste rapportdato: overblik, struktur, spredning/tab/koncentration, IRR, vintage.

Porteret fra return-data/pscp/pscp.ipynb (Del 2), hvor de var bundet til PSCP's regneark.
Her er de bundet til kolonnerne: en metode tegner, hvis fonden har det, den skal bruge.
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D

from ..fondskonfig import MIN_INVESTED, MIN_LABEL, MIN_MOVE
from ..style import (PPIM_SAGE_DARK, PPIM_SAGE_LIGHT, PPIM_OLIVE, PPIM_BROWN, PPIM_TAUPE,
                     PPIM_BLACK, PPIM_RED_MUTED, SLIDE, MX, BOTTOM_FRAC, BG, INK, MUTED, LINE, GRID,
                     style_ax, add_header, add_footer, source_line, ref_pill, legend_swatches,
                     save, _dk, money, mult)
from .kerne import (F_DPI, F_RVPI, F_POS, F_NEG, MULT, PROC, PROC1, brudt, kort, lille, pct,
                    reflabel, soejlelabel)


def _vandret(ax):
    """Vandrette søjler: gitterlinjerne følger værdiaksen."""
    style_ax(ax)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)


def _titel(ax, tekst):
    ax.set_title(tekst, fontsize=12, color=INK, loc="left", pad=10)


def _legend(ax, **kw):
    lg = ax.legend(frameon=False, **kw)
    for t in lg.get_texts():
        t.set_color(INK)
    return lg


class Bog:
    # ------------------------------------------------------------------ 1. overblik og værdibro

    def graf_noegletal(self):
        """Nøgletalstavle: otte kort."""
        tot, raw = self.tot, self.raw
        under = raw[raw["mom"] < 1.0]
        antal = (f"{self.N_INV} {self.cfg.enhed} · {self.N_TR} investeringer"
                 if self.N_TR != self.N_INV else f"{self.N_INV} {self.cfg.enhed}")
        fig = plt.figure(figsize=SLIDE)
        top_frac = add_header(fig, f"Nøgletal for {self.navn}",
                              f"{antal} · hele fonden, brutto som rapporteret · pr. {self.REPORT_DK}")
        kolonner, gab, hoejde = 4, 0.016, 0.255
        bredde = (1 - 2 * MX - (kolonner - 1) * gab) / kolonner
        y0 = top_frac - 0.075
        real = (pct(self.REAL["invested"].sum() / tot["invested"], 0),
                f"{len(self.REAL)} af {self.N_TR} investeringer") if self.HAR_REAL else \
            (pct(self.pool_dpi / self.pool_tvpi, 0), "andel af værdien udloddet")
        kort_data = [
            ("Investeret kapital", money(tot["invested"], 0), antal, False),
            ("Udlodninger", money(tot["proceeds"], 0), f"DPI {mult(self.pool_dpi)}", False),
            ("Dagsværdi", money(tot["fair_value"], 0), f"RVPI {mult(self.pool_rvpi)}", False),
            ("Samlet værdi", money(tot["total_value"], 0), f"Gevinst {money(self.GEVINST, 0)}", False),
            ("TVPI", mult(self.pool_tvpi), "Poolet, brutto for honorar og carry", True),
            ("Andel af værdi realiseret", pct(self.pool_dpi / self.pool_tvpi, 0),
             "resten er dagsværdi", False),
            ("Kapital realiseret" if self.HAR_REAL else "Udloddet af værdien", *real, False),
            ("Kapital under 1,0x", pct(under["invested"].sum() / tot["invested"], 0),
             f"{len(under)} investeringer", False),
        ]
        if not self.HAR_REAL:      # uden realiseret-markering er de to kort ens - vis tabsraten
            kort_data[6] = ("Tabsrate", pct(self.TABSRATE, 1), "tab i pct. af investeret kapital",
                            False)
        for i, (lab, val, note, acc) in enumerate(kort_data):
            r, c = divmod(i, kolonner)
            kort(fig, MX + c * (bredde + gab), y0 - (r + 1) * hoejde - r * gab,
                 bredde, hoejde, lab, val, note, accent=acc)
        add_footer(fig, source_line(self.note_belob()))
        save(fig, self.C("noegletal"))
        plt.show()

    def graf_vaerdibro(self):
        """Fra investeret kapital til samlet værdi, delt på realiseret og urealiseret gevinst."""
        tot = self.tot
        delt = self.HAR_REAL
        g_real = self.REAL["gevinst"].sum() if delt else 0.0
        g_ureal = self.UREAL["gevinst"].sum() if delt else self.GEVINST
        trin = [("Investeret kapital", tot["invested"], 0.0, PPIM_TAUPE, money(tot["invested"], 0))]
        niveau = tot["invested"]
        dele = ([("Værdiskabelse\nrealiserede", g_real, F_POS),
                 ("Værdiskabelse\nurealiserede", g_ureal, PPIM_OLIVE)] if delt
                else [("Værdiskabelse", g_ureal, F_POS)])
        for navn, v, farve in dele:
            trin.append((navn, v, niveau, farve if v >= 0 else F_NEG,
                         ("+" if v >= 0 else "−") + money(abs(v), 0)))
            niveau += v

        fig, ax = plt.subplots(figsize=SLIDE)
        style_ax(ax)
        x = np.arange(len(trin) + 1)
        for i, (_, h, bund, farve, _) in enumerate(trin):
            ax.bar(x[i], h, bottom=bund, color=farve, width=0.62, zorder=2)
        # Sidste søjle deles i kasse og marks - samme totalhøjde, men to farver
        ax.bar(x[-1], tot["proceeds"], color=F_DPI, width=0.62, zorder=2)
        ax.bar(x[-1], tot["fair_value"], bottom=tot["proceeds"], color=F_RVPI, width=0.62, zorder=2)
        toppe = [max(b, b + h) for _, h, b, _, _ in trin] + [tot["total_value"]]
        ender = [b + h for _, h, b, _, _ in trin]
        for i, y in enumerate(ender):
            ax.plot([x[i] + 0.31, x[i + 1] - 0.31], [y, y], color=LINE, linewidth=1.0,
                    linestyle=(0, (3, 3)), zorder=1)
        ax.set_xticks(x)
        ax.set_xticklabels([t[0] for t in trin] + ["Samlet værdi"])
        ax.set_xlim(-0.6, len(x) - 0.4)
        ax.set_ylim(0, max(toppe) * 1.16)
        ax.yaxis.set_major_formatter(self.BELOB)
        ax.set_ylabel(self.MIO_STOR)
        soejlelabel(ax, x, toppe, [t[4] for t in trin] + [money(tot["total_value"], 0)], fs=12)
        if tot["proceeds"] > 0.08 * tot["total_value"]:
            ax.text(x[-1], tot["proceeds"] / 2, f"Udlodninger\n{money(tot['proceeds'], 0)}",
                    ha="center", va="center", color="white", fontsize=10, fontweight="bold", zorder=4)
        ax.text(x[-1], tot["proceeds"] + tot["fair_value"] / 2,
                f"Dagsværdi\n{money(tot['fair_value'], 0)}", ha="center", va="center", color=INK,
                fontsize=10, fontweight="bold", zorder=4)
        self.afslut(fig, "Fra investeret kapital til samlet værdi",
                    ("Værdiskabelsen delt på realiserede og urealiserede investeringer · "
                     if delt else "Hele fonden · ")
                    + f"TVPI {mult(self.pool_tvpi)} · pr. {self.REPORT_DK}",
                    "vaerdibro", ax=ax,
                    note=self.note_belob() + f" · {pct(self.pool_dpi / self.pool_tvpi, 0)} af den "
                                             "samlede værdi er udloddet")

    def graf_boeger(self):
        """De to bøger side om side: den realiserede er facit, den urealiserede er dagsværdi."""
        if not self._kraever(self.HAR_REAL, "opdeling i realiseret og urealiseret"):
            return
        REAL, UREAL = self.REAL, self.UREAL
        boger = pd.DataFrame({
            n: [f["invested"].sum(), f["proceeds"].sum(), f["fair_value"].sum(),
                f["total_value"].sum(), len(f)]
            for n, f in (("Realiserede", REAL), ("Urealiserede", UREAL))},
            index=["investeret", "udlodninger", "dagsvaerdi", "samlet", "antal"]).T
        boger["tvpi"] = boger["samlet"] / boger["investeret"]
        boger["gevinst"] = boger["samlet"] - boger["investeret"]

        fig, axes = plt.subplots(1, 2, figsize=SLIDE, gridspec_kw={"width_ratios": [1.15, 1]})
        ax = axes[0]
        style_ax(ax)
        xs = np.arange(2)
        ax.bar(xs - 0.19, boger["investeret"], width=0.36, color=PPIM_TAUPE, zorder=2,
               label="Investeret kapital")
        ax.bar(xs + 0.19, boger["udlodninger"], width=0.36, color=F_DPI, zorder=2, label="Udlodninger")
        ax.bar(xs + 0.19, boger["dagsvaerdi"], width=0.36, bottom=boger["udlodninger"], color=F_RVPI,
               zorder=2, label="Dagsværdi")
        ax.set_xticks(xs)
        ax.set_xticklabels([f"{n}\n{int(boger.loc[n, 'antal'])} investeringer" for n in boger.index])
        ax.set_xlim(-0.6, 1.6)
        ax.set_ylim(0, max(boger["investeret"].max(), boger["samlet"].max()) * 1.22)
        ax.yaxis.set_major_formatter(self.BELOB)
        ax.set_ylabel(self.MIO_STOR)
        soejlelabel(ax, xs - 0.19, boger["investeret"], [money(v, 0) for v in boger["investeret"]])
        soejlelabel(ax, xs + 0.19, boger["samlet"], [money(v, 0) for v in boger["samlet"]])
        _legend(ax, loc="upper left", handlelength=1.2)
        _titel(ax, "Kapital og værdi")

        ax2 = axes[1]
        style_ax(ax2)
        ax2.bar(xs, boger["tvpi"], width=0.46, color=[F_DPI, F_RVPI], zorder=2)
        ax2.axhline(1.0, color=LINE, linestyle=(0, (4, 3)), linewidth=1.0, zorder=3)
        ax2.axhline(self.pool_tvpi, color=PPIM_SAGE_DARK, linewidth=1.5, zorder=3)
        ax2.set_xticks(xs)
        ax2.set_xticklabels(["Realiserede", "Urealiserede"])
        ax2.set_xlim(-0.6, 1.6)
        ax2.set_ylim(0, max(boger["tvpi"].max() * 1.25, 1.6))
        ax2.yaxis.set_major_formatter(MULT)
        ax2.set_ylabel("TVPI")
        soejlelabel(ax2, xs, boger["tvpi"], [mult(v) for v in boger["tvpi"]], fs=12)
        reflabel(ax2, self.pool_tvpi, f"Poolet {mult(self.pool_tvpi)}", PPIM_SAGE_DARK)
        reflabel(ax2, 1.0, "Break-even")
        _titel(ax2, "Multipel pr. bog")
        self.afslut(fig, "Realiseret mod urealiseret bog",
                    f"Den realiserede bog er facit; den urealiserede er dagsværdi · pr. {self.REPORT_DK}",
                    "boeger", ax=axes[0],
                    note=self.note_belob() + " · realiserede bidrager "
                         f"{money(boger.loc['Realiserede', 'gevinst'], 0)} af gevinsten, urealiserede "
                         f"{money(boger.loc['Urealiserede', 'gevinst'], 0)}")

    # ------------------------------------------------------------------ 2. struktur

    def _split_soejler(self, g, title, subtitle, navn, note="", rotation=90, fs=8.5):
        """Variabel-bredde TVPI-søjler (DPI + RVPI). Bredden er investeret kapital, så et
        segments visuelle vægt svarer til dets kapitalvægt. Indekset bruges som etiket."""
        d = g[g["investeret"] > 0].sort_values("tvpi", ascending=False)
        widths = d["investeret"].to_numpy(float)
        lefts = np.concatenate([[0.0], np.cumsum(widths)[:-1]])
        centers = lefts + widths / 2
        w_tvpi = d["samlet"].sum() / d["investeret"].sum()

        fig, ax = plt.subplots(figsize=SLIDE)
        style_ax(ax)
        ax.bar(centers, d["dpi"], width=widths, color=F_DPI, edgecolor=BG, linewidth=0.8, zorder=2)
        ax.bar(centers, d["rvpi"], width=widths, bottom=d["dpi"], color=F_RVPI, edgecolor=BG,
               linewidth=0.8, zorder=2)
        # En smal søjle med en ekstrem multipel (1 mio. i 6x) må ikke presse resten flad
        top = min(d["tvpi"].max() * 1.14, max(2.2 * w_tvpi, 2.5))
        klippet = d.index[d["tvpi"] > top]
        ax.set_xlim(0, widths.sum())
        ax.set_ylim(0, top)
        ax.margins(x=0)
        ref_pill(ax, 1.0, "1,0x")
        ref_pill(ax, w_tvpi, mult(w_tvpi), accent=True)
        for c, w, y, navn_i in zip(centers, widths, d["tvpi"], d.index.astype(str)):
            if w >= 0.012 * widths.sum() or rotation:      # en hårfin søjle kan ikke bære et navn
                ax.text(c, min(y, top) + top * 0.012, navn_i, rotation=rotation, va="bottom",
                        ha="center", color=MUTED, fontsize=fs)
        ax.xaxis.set_major_formatter(self.BELOB)
        ax.yaxis.set_major_formatter(MULT)
        ax.set_ylabel("TVPI")
        ax.set_xlabel(f"Akkumuleret investeret kapital ({self.MIO})")
        legend_swatches(ax, [(F_DPI, "Realiseret (DPI)"), (F_RVPI, "Urealiseret (RVPI)")],
                        loc="upper right", bbox_to_anchor=(0.995, 0.99))
        if len(klippet):
            note += " · uden for aksen: " + ", ".join(
                f"{i} ({mult(d.loc[i, 'tvpi'])} på {money(d.loc[i, 'investeret'], 0)})" for i in klippet)
        self.afslut(fig, title, subtitle, navn, ax=ax, note=note,
                    rect=[MX, BOTTOM_FRAC, 0.90, None])

    def graf_gruppemix(self):
        """Investeret kapital pr. instrumenttype (eller gruppe), farvet efter gruppe."""
        if not self._kraever(self.HAR_GRUPPE, f"opdeling på {self.cfg.gruppe_omtale}"):
            return
        d = self.g_under.sort_values("investeret")
        fig, ax = plt.subplots(figsize=SLIDE)
        _vandret(ax)
        ys = np.arange(len(d))
        ax.barh(ys, d["investeret"], color=[self.gruppefarve(i) for i in d.index], height=0.68,
                zorder=2)
        for y, v, a, t in zip(ys, d["investeret"], d["andel"], d["tvpi"]):
            ax.text(v + self.tot["invested"] * 0.006, y,
                    f"{money(v, 0)}   ({pct(a, 0)})   TVPI {mult(t)}", va="center", ha="left",
                    fontsize=9.5, color=INK)
        ax.set_yticks(ys)
        ax.set_yticklabels(d.index)
        ax.set_xlim(0, d["investeret"].max() * 1.42)
        ax.xaxis.set_major_formatter(self.BELOB)
        ax.set_xlabel(f"Investeret kapital ({self.MIO})")
        if self.HAR_INSTRUMENT:
            legend_swatches(ax, [(self.GRUPPE_FARVE[g], g) for g in self.GRUPPE_ORDEN],
                            loc="lower right", bbox_to_anchor=(0.995, 0.02))
        self.afslut(fig, f"Kapitalmix pr. {self.UNDER_NAVN.lower()}",
                    f"Investeret kapital fordelt på {len(d)} "
                    f"{self.UNDER_NAVN.lower()}r · pr. {self.REPORT_DK}"
                    if self.HAR_INSTRUMENT else
                    f"Investeret kapital og TVPI pr. {self.cfg.gruppe_omtale} · pr. {self.REPORT_DK}",
                    "gruppemix", ax=ax, note=self.note_belob())

    def graf_gruppe_tvpi(self):
        """TVPI pr. instrumenttype/gruppe, bredde = investeret kapital."""
        if not self._kraever(self.HAR_GRUPPE, f"opdeling på {self.cfg.gruppe_omtale}"):
            return
        faa = len(self.g_under) <= 6
        self._split_soejler(
            self.g_under, f"TVPI pr. {self.UNDER_NAVN.lower()}",
            f"Søjlebredde = investeret kapital · opdelt i realiseret (DPI) og urealiseret (RVPI) "
            f"· pr. {self.REPORT_DK}", "gruppe_tvpi", rotation=0 if faa else 90,
            fs=11 if faa else 8.5,
            note=self.note_belob() + " · forhold beregnes på summerede beløb, ikke som gennemsnit "
                                     "af multipler")

    def graf_kapitalgruppe(self):
        """Grupperne på kapitalvægt, multipel, IRR og tabsrate."""
        if not self._kraever(self.HAR_GRUPPE, f"opdeling på {self.cfg.gruppe_omtale}"):
            return
        g = self.g_gruppe
        paneler = [("Andel af investeret kapital", g["andel"], PROC, lambda v: pct(v, 0), None),
                   ("TVPI", g["tvpi"], MULT, mult, 1.0)]
        if self.HAR_IRR:
            paneler.append(("Kapitalvægtet IRR (GP)", g["irr_vaegtet"], PROC, lambda v: pct(v, 1), 0.0))
        paneler.append(("Tabsrate", g["tabsrate"], PROC1, lambda v: pct(v, 1), None))

        fig, axes = plt.subplots(1, len(paneler), figsize=SLIDE)
        xs = np.arange(len(g))
        farver = [self.GRUPPE_FARVE[i] for i in g.index]
        etiketter = [brudt(i) for i in g.index]
        for ax, (titel, serie, fmt, tekst, ref) in zip(axes, paneler):
            style_ax(ax)
            ax.bar(xs, serie, width=0.62, color=farver, zorder=2)
            if titel == "TVPI":
                ax.bar(xs, g["dpi"], width=0.62, color=PPIM_BLACK, alpha=0.18, zorder=3)
            if ref is not None:
                ax.axhline(ref, color=LINE, linestyle=(0, (4, 3)), linewidth=1.0, zorder=4)
            ax.set_xticks(xs)
            ax.set_xticklabels(etiketter, fontsize=9 if len(g) <= 3 else 8)
            ax.set_xlim(-0.65, len(xs) - 0.35)
            ax.set_ylim(0, max(np.nanmax(serie) * 1.28, 1e-9))
            ax.yaxis.set_major_formatter(fmt)
            ax.set_title(titel, fontsize=11.5, color=INK, loc="left", pad=10)
            soejlelabel(ax, xs, serie, [tekst(v) for v in serie], fs=10.5 if len(g) <= 3 else 9)
        axes[1].text(len(xs) - 0.45, g["tvpi"].max() * 1.20, "mørkt felt = DPI", ha="right",
                     va="top", fontsize=9, color=MUTED)
        maal = "kapitalvægt, multipel" + (", IRR" if self.HAR_IRR else "") + " og tabsrate"
        self.afslut(fig, self.cfg.titel_gruppe,
                    f"{len(g)} {self.cfg.gruppe_flertal} på {maal} · pr. {self.REPORT_DK}",
                    "kapitalgruppe", ax=axes[0],
                    note=(f" · IRR er GP's egen pr. handel, kapitalvægtet ({self.N_NM} handler uden "
                          "IRR indgår ikke)" if self.HAR_IRR else "")
                         + " · tabsrate = tab på positioner under 1,0x i pct. af investeret kapital")

    # ------------------------------------------------------------------ 3. spredning, tab, koncentration

    def graf_spredning(self):
        """Investeret kapital fordelt på multipelbånd."""
        kanter = [0, 0.5, 1.0, 1.25, 1.5, 2.0, 3.0, np.inf]
        navne = ["under 0,5x", "0,5-1,0x", "1,0-1,25x", "1,25-1,5x", "1,5-2,0x", "2,0-3,0x",
                 "over 3,0x"]
        d = self.raw[self.raw["invested"] >= MIN_INVESTED].copy()
        d["baand"] = pd.cut(d["mom"], kanter, labels=navne, right=False)
        sp = d.groupby("baand", observed=False).agg(kapital=("invested", "sum"),
                                                    antal=("mom", "size"))
        sp["andel"] = sp["kapital"] / sp["kapital"].sum()
        under = sp.loc[navne[:2], "kapital"].sum()

        fig, ax = plt.subplots(figsize=SLIDE)
        style_ax(ax)
        xs = np.arange(len(sp))
        ax.bar(xs, sp["kapital"], width=0.68, color=[F_NEG if i < 2 else F_DPI for i in xs], zorder=2)
        ax.set_xticks(xs)
        ax.set_xticklabels(sp.index)
        ax.set_xlim(-0.65, len(sp) - 0.35)
        ax.set_ylim(0, sp["kapital"].max() * 1.20)
        ax.yaxis.set_major_formatter(self.BELOB)
        ax.set_ylabel(f"Investeret kapital ({self.MIO})")
        ax.set_xlabel("Samlet værdi i forhold til investeret kapital (MoM)")
        soejlelabel(ax, xs, sp["kapital"],
                    [f"{money(k, 0)}\n{pct(a, 0)} · {int(n)} stk." for k, a, n in
                     zip(sp["kapital"], sp["andel"], sp["antal"])], fs=10)
        legend_swatches(ax, [(F_NEG, "Under break-even"), (F_DPI, "Over break-even")],
                        loc="upper left", bbox_to_anchor=(0.005, 0.99))
        self.afslut(fig, "Afkastspredning målt i kapital",
                    f"Investeret kapital fordelt på multipelbånd · {len(d)} investeringer over "
                    f"{money(MIN_INVESTED, 0)} · pr. {self.REPORT_DK}", "spredning", ax=ax,
                    note=self.note_belob() + f" · {pct(under / d['invested'].sum(), 0)} af kapitalen "
                         f"ligger under 1,0x · positioner under {money(MIN_INVESTED, 0)} udeladt "
                         "(afrundingsstøj)")

    def graf_tabsanalyse(self):
        """Hvem taber penge, og hvor meget - og tabsraten pr. gruppe."""
        raw, tabere = self.raw, self.tabere
        vis = tabere.tail(12)                       # de største; en lang liste kan ikke læses
        antal_under = int((raw["mom"] < 1.0).sum())
        maks_tab = vis["tab"].max() if len(vis) else 1.0

        fig, axes = plt.subplots(1, 2, figsize=SLIDE, gridspec_kw={"width_ratios": [1.35, 1]})
        ax = axes[0]
        _vandret(ax)
        ys = np.arange(len(vis))
        ax.barh(ys, vis["tab"], color=F_NEG, height=0.55, zorder=2)
        for y, (_, r) in zip(ys, vis.iterrows()):
            ax.text(r["tab"] + maks_tab * 0.03, y,
                    f"{money(r['tab'], 1)}   ({mult(r['mom'])} af {money(r['invested'], 1)})",
                    va="center", fontsize=9.5, color=INK)
        ax.set_yticks(ys)
        # Samme selskab kan optræde med flere lots af samme tranche - handelsåret skiller dem ad
        aar = lambda r: f"  ({r['trade_date']:%Y})" if pd.notna(r["trade_date"]) else ""
        ax.set_yticklabels([(r["label"] if len(r["label"]) <= 44 else r["label"][:42] + "…") + aar(r)
                            for _, r in vis.iterrows()], fontsize=9.5 if len(vis) <= 8 else 8.5)
        ax.set_ylim(-0.7, max(len(vis), 8) - 0.3)
        ax.set_xlim(0, maks_tab * 1.75)
        if not len(vis):
            # En ung fond kan være helt uden tab - så skal panelet sige det i stedet for at stå tomt
            ax.text(0.5, 0.5, f"Ingen position har tabt mere end {money(MIN_MOVE, 2)}\n"
                              f"pr. {self.REPORT_DK}",
                    transform=ax.transAxes, ha="center", va="center", fontsize=12, color=MUTED)
            ax.set_xticks([])
            ax.grid(False)
            ax.spines["bottom"].set_visible(False)
        ax.xaxis.set_major_formatter(self.BELOB)
        ax.set_xlabel(f"Tab i forhold til investeret kapital ({self.MIO})" if len(vis) else "")
        _titel(ax, ("Tabsgivende positioner" if not len(vis) else
                    f"Alle {len(vis)} tabsgivende positioner" if len(vis) == len(tabere) else
                    f"De {len(vis)} største af {len(tabere)} tabsgivende positioner"))

        ax2 = axes[1]
        style_ax(ax2)
        rater = pd.Series({"Hele porteføljen": self.TABSRATE})
        farver = [PPIM_BROWN]
        if self.HAR_GRUPPE:
            rater = pd.concat([self.g_gruppe["tabsrate"], rater])
            farver = [self.GRUPPE_FARVE[i] for i in self.g_gruppe.index] + farver
        xs = np.arange(len(rater))
        ax2.bar(xs, rater, width=0.6, zorder=2, color=farver)
        ax2.set_xticks(xs)
        ax2.set_xticklabels([brudt(i) for i in rater.index], fontsize=9.5 if len(rater) <= 4 else 8.5)
        ax2.set_xlim(-0.6, len(rater) - 0.4)
        ax2.set_ylim(0, max(rater.max() * 1.30, 0.01))
        ax2.yaxis.set_major_formatter(PROC1)
        ax2.set_ylabel("Tabsrate")
        soejlelabel(ax2, xs, rater, [pct(v, 1) for v in rater], fs=11)
        _titel(ax2, f"Tabsrate pr. {self.cfg.gruppe_omtale}" if self.HAR_GRUPPE else "Tabsrate")

        # Overskriften følger data: ligger tabene samlet i én gruppe, siger den hvilken
        titel = ("Porteføljen har endnu ikke tabt kapital" if self.TABSRATE < 0.0005
                 else "Ingen tab af betydning")
        if len(tabere):
            titel = "Hvor ligger tabene"
            pr_gruppe = tabere.groupby("gruppe")["tab"].sum()
            stoerst = pr_gruppe.idxmax()
            # kun en pointe, hvis gruppen ikke i forvejen er næsten hele porteføljen
            if (self.HAR_GRUPPE and pr_gruppe.max() / pr_gruppe.sum() > 0.95
                    and self.g_gruppe.loc[stoerst, "andel"] < 0.6):
                titel = f"Tabene ligger ét sted: {lille(stoerst)}"
        self.afslut(fig, titel,
                    f"Tabsrate = tab i forhold til investeret kapital · {antal_under} af {self.N_TR} "
                    f"investeringer er under 1,0x · pr. {self.REPORT_DK}", "tabsanalyse", ax=axes[0],
                    note=self.note_belob() + f" · samlet tabsrate {pct(self.TABSRATE, 1)} · "
                         "urealiserede tab er dagsværdi, ikke realiseret")

    def graf_nedskrivning(self):
        """TVPI som funktion af en generel nedskrivning af den urealiserede dagsværdi."""
        tot = self.tot
        if not self._kraever(tot["fair_value"] > 0, "urealiseret dagsværdi"):
            return
        tvpi_ved = lambda hh: (tot["proceeds"] + tot["fair_value"] * (1 - hh)) / tot["invested"]
        h = np.linspace(0, 1, 201)
        tvpi_h = tvpi_ved(h)
        be = self.break_even

        fig, ax = plt.subplots(figsize=SLIDE)
        style_ax(ax)
        ax.plot(h, tvpi_h, color=PPIM_SAGE_DARK, linewidth=2.6, zorder=4)
        ax.fill_between(h, 1.0, tvpi_h, where=tvpi_h >= 1.0, color=PPIM_SAGE_LIGHT, alpha=0.55, zorder=2)
        ax.fill_between(h, tvpi_h, 1.0, where=tvpi_h < 1.0, color=PPIM_RED_MUTED, alpha=0.30, zorder=2)
        ax.axhline(1.0, color=LINE, linestyle=(0, (4, 3)), linewidth=1.0, zorder=3)
        ax.axhline(self.pool_dpi, color=PPIM_TAUPE, linewidth=1.4, zorder=3)
        spaend = self.pool_tvpi - min(self.pool_dpi, 1.0)
        if 0 < be < 1:
            ax.axvline(be, color=PPIM_RED_MUTED, linestyle=(0, (4, 3)), linewidth=1.4, zorder=3)
            ax.plot([be], [1.0], marker="o", markersize=9, color=PPIM_RED_MUTED, zorder=5)
            ax.annotate(f"Hele gevinsten er væk ved en\nnedskrivning på {pct(be, 0)} af dagsværdien",
                        xy=(be, 1.0), xytext=(min(be + 0.06, 0.70), 1.0 + spaend * 0.70),
                        fontsize=11.5, color=INK,
                        arrowprops=dict(arrowstyle="-", color=LINE, linewidth=1.0))
        ax.text(0.015, self.pool_dpi + spaend * 0.03,
                f"DPI {mult(self.pool_dpi)} - allerede udloddet og uafhængigt af marks",
                ha="left", va="bottom", fontsize=10.5, color=PPIM_TAUPE)
        for hh in (0.10, 0.25):
            ax.plot([hh], [tvpi_ved(hh)], marker="o", markersize=6, color=PPIM_SAGE_DARK, zorder=5)
            ax.text(hh, tvpi_ved(hh) + spaend * 0.04, f"−{pct(hh, 0)}  →  {mult(tvpi_ved(hh))}",
                    ha="center", va="bottom", fontsize=10.5, color=INK)
        ax.set_xlim(0, 1)
        ax.set_ylim(min(self.pool_dpi, 1.0) - spaend * 0.12, self.pool_tvpi + spaend * 0.18)
        ax.xaxis.set_major_formatter(PROC)
        ax.yaxis.set_major_formatter(MULT)
        ax.set_xlabel("Nedskrivning af den urealiserede dagsværdi")
        ax.set_ylabel("Poolet TVPI")
        self.afslut(fig, "Hvor følsom er track record'et over for dagsværdien",
                    f"TVPI som funktion af en generel nedskrivning af de "
                    f"{money(tot['fair_value'], 0)}, der endnu ikke er realiseret · pr. {self.REPORT_DK}",
                    "nedskrivning", ax=ax,
                    note=self.note_belob() + " · udlodningerne er kontant og påvirkes ikke · en "
                         "generel nedskrivning er en illustration, ikke en forventning")

    def graf_koncentration(self):
        """Hvor få beholdninger bærer resultatet."""
        if not self._kraever(self.N_INV >= 6 and self.GEVINST > 0, "gevinst at fordele på mindst "
                                                                   "seks beholdninger"):
            return
        bidrag, kum = self.bidrag, self.kum
        fig, axes = plt.subplots(1, 2, figsize=SLIDE, gridspec_kw={"width_ratios": [1, 1.25]})
        ax = axes[0]
        style_ax(ax)
        xs = np.arange(1, len(bidrag) + 1)
        ax.plot(xs, kum, color=PPIM_SAGE_DARK, linewidth=2.4, zorder=4)
        ax.fill_between(xs, 0, kum, color=PPIM_SAGE_LIGHT, alpha=0.45, zorder=2)
        ax.axhline(1.0, color=LINE, linestyle=(0, (4, 3)), linewidth=1.0, zorder=3)
        for n, v, farve in ((5, self.top5, PPIM_TAUPE), (10, self.top10, PPIM_BROWN)):
            if 2 * n <= len(bidrag):        # "top 10 af 13" er ikke en koncentration
                ax.plot([n], [v], marker="o", markersize=8, color=farve, zorder=5)
                ax.annotate(f"Top {n}: {pct(v, 0)} af gevinsten", xy=(n, v),
                            xytext=(n + max(len(bidrag) * 0.06, 0.6), v - 0.13), fontsize=11,
                            color=INK, arrowprops=dict(arrowstyle="-", color=LINE, linewidth=1.0))
        ax.set_xlim(1, len(bidrag))
        ax.set_ylim(0, max(kum.max(), 1.0) * 1.10)
        ax.yaxis.set_major_formatter(PROC)
        ax.set_xlabel(f"{self.cfg.enhed.capitalize()}, rangeret efter bidrag")
        ax.set_ylabel("Akkumuleret andel af samlet gevinst")
        _titel(ax, "Kumuleret gevinstbidrag")

        ax2 = axes[1]
        _vandret(ax2)
        n_top, n_bund = (10, 5) if len(bidrag) >= 15 else (min(len(bidrag), 10), 0)
        vis = pd.concat([bidrag.head(n_top), bidrag.tail(n_bund)]).drop_duplicates("investment") \
            .sort_values("gevinst")
        ys = np.arange(len(vis))
        ax2.barh(ys, vis["gevinst"], color=[F_POS if v >= 0 else F_NEG for v in vis["gevinst"]],
                 height=0.66, zorder=2)
        spand = max(abs(vis["gevinst"].min()), vis["gevinst"].max())
        for y, v, m in zip(ys, vis["gevinst"], vis["mom"]):
            # en negativ søjles tekst sættes til højre for nullinjen - til venstre ligger navnene
            ax2.text(max(v, 0) + spand * 0.025, y, f"{money(v, 0)}  ({mult(m)})", va="center",
                     ha="left", fontsize=9.5, color=INK)
        ax2.set_yticks(ys)
        ax2.set_yticklabels([n if len(n) <= 34 else n[:32] + "…" for n in vis["investment"]],
                            fontsize=9.5)
        ax2.set_xlim(min(vis["gevinst"].min() * 1.15, 0), spand * 1.30)
        ax2.axvline(0, color=LINE, linewidth=1.0)
        ax2.xaxis.set_major_formatter(self.BELOB)
        ax2.set_xlabel(f"Gevinst i forhold til investeret kapital ({self.MIO})")
        _titel(ax2, "De ti største og de fem mindste bidragydere" if n_bund else
               f"De {n_top} største bidragydere")
        self.afslut(fig, "Koncentration - hvor få handler bærer resultatet",
                    f"Gevinstbidrag pr. beholdning · {self.N_INV} {self.cfg.enhed} · pr. {self.REPORT_DK}",
                    "koncentration", ax=axes[0],
                    note=self.note_belob() + f" · top 5 står for {pct(self.top5, 0)} af gevinsten · "
                         f"HHI på investeret kapital {_dk(self.hhi, 3)} (svarer til "
                         f"{1 / self.hhi:.0f} lige store positioner)")

    # ------------------------------------------------------------------ 4. afkast mod tid

    def graf_irr_vs_mom(self):
        """IRR mod multipel, boble = investeret kapital."""
        if not self._kraever(self.HAR_IRR, "IRR pr. handel"):
            return
        raw = self.raw
        d = raw[(raw["invested"] >= MIN_INVESTED) & raw["irr"].notna() & raw["mom"].notna()].copy()
        fig, ax = plt.subplots(figsize=SLIDE)
        style_ax(ax)
        ax.grid(axis="x", color=GRID, linewidth=0.8)
        skala = 2600 / d["invested"].max()
        for g in self.GRUPPE_ORDEN:
            for real, alpha, kant in ((True, 0.85, "none"), (False, 0.30, self.GRUPPE_FARVE[g])):
                m = (d["gruppe"] == g) & (d["realiseret"] == real)
                if m.any():
                    ax.scatter(d.loc[m, "irr"], d.loc[m, "mom"], s=d.loc[m, "invested"] * skala,
                               color=self.GRUPPE_FARVE[g], alpha=alpha, edgecolors=kant,
                               linewidths=1.4, zorder=3)
        ax.axhline(1.0, color=LINE, linestyle=(0, (4, 3)), linewidth=1.0, zorder=2)
        ax.axvline(0.0, color=LINE, linestyle=(0, (4, 3)), linewidth=1.0, zorder=2)
        x_hi, y_hi = d["irr"].quantile(0.99) * 1.25, d["mom"].quantile(0.99) * 1.35
        # Midterfeltet er så tæt, at navne på alt ville blive ulæseligt - kun yderpunkterne
        # og de største positioner navngives
        navne = pd.concat([d.nlargest(6, "invested"), d.nlargest(4, "mom"), d.nlargest(4, "irr"),
                           d.nsmallest(3, "mom")]).drop_duplicates()
        for _, r in navne.iterrows():
            if r["irr"] <= x_hi and r["mom"] <= y_hi:
                ax.annotate(r["investment"], (r["irr"], r["mom"]), textcoords="offset points",
                            xytext=(0, 11), ha="center", fontsize=8.5, color=INK, zorder=6)
        ax.set_xlim(min(d["irr"].min() * 1.1, -0.05), x_hi)
        ax.set_ylim(0, y_hi)
        ax.xaxis.set_major_formatter(PROC)
        ax.yaxis.set_major_formatter(MULT)
        ax.set_xlabel("IRR pr. handel (GP)")
        ax.set_ylabel("Samlet værdi / investeret kapital (MoM)")
        h = [Line2D([0], [0], marker="o", linestyle="none", markersize=11,
                    color=self.GRUPPE_FARVE[g], alpha=0.85,
                    label=g if self.HAR_GRUPPE else "Realiseret (fyldt)")
             for g in self.GRUPPE_ORDEN]
        if self.HAR_REAL:
            h.append(Line2D([0], [0], marker="o", linestyle="none", markersize=11,
                            markerfacecolor="white", markeredgecolor=LINE, markeredgewidth=1.4,
                            color="none", label="Urealiseret (åben cirkel)"))
        _legend(ax, handles=h, loc="upper right", handletextpad=1.0, labelspacing=0.8)
        self.afslut(fig, "IRR mod multipel - to måder at tjene penge på",
                    "Boblestørrelse = investeret kapital · de største og de mest yderliggående er "
                    f"navngivet · pr. {self.REPORT_DK}", "irr_vs_mom", ax=ax,
                    note=f" · {len(d)} af {self.N_TR} investeringer har både IRR og multipel"
                         + (f" ({self.N_NM} er uden IRR)" if self.N_NM else "")
                         + " · aksen er beskåret ved 99. percentil")

    def graf_irr_fordeling(self):
        """IRR-kvartiler pr. gruppe, delt på realiseret og urealiseret bog."""
        if not self._kraever(self.HAR_IRR, "IRR pr. handel"):
            return
        raw = self.raw
        raekker = []
        for g in self.GRUPPE_ORDEN:
            for real, tekst in ((True, "realiseret"), (False, "urealiseret")):
                s = raw[(raw["gruppe"] == g) & (raw["realiseret"] == real) & raw["irr"].notna()]
                if len(s) >= 2 and s["invested"].sum() > 0:
                    raekker.append(dict(gruppe=g, bog=tekst, n=len(s), p25=s["irr"].quantile(0.25),
                                        p50=s["irr"].median(), p75=s["irr"].quantile(0.75),
                                        vaegtet=np.average(s["irr"], weights=s["invested"])))
        if not self._kraever(raekker, "grupper med mindst to handler med IRR"):
            return
        fordeling = pd.DataFrame(raekker).iloc[::-1].reset_index(drop=True)

        fig, ax = plt.subplots(figsize=SLIDE)
        _vandret(ax)
        ys = np.arange(len(fordeling))
        spand = max(fordeling["p75"].max(), fordeling["vaegtet"].max()) - min(fordeling["p25"].min(), 0)
        for y, r in zip(ys, fordeling.itertuples()):
            farve = self.GRUPPE_FARVE[r.gruppe]
            ax.plot([r.p25, r.p75], [y, y], color=farve, linewidth=13,
                    alpha=0.85 if r.bog == "realiseret" else 0.35, solid_capstyle="butt", zorder=2)
            ax.plot([r.p50], [y], marker="|", markersize=20, markeredgewidth=3, zorder=4,
                    color=BG if r.bog == "realiseret" else INK)
            ax.plot([r.vaegtet], [y], marker="D", markersize=8, color=PPIM_BROWN, zorder=5)
            ax.text(max(r.p75, r.vaegtet) + spand * 0.04, y,
                    f"median {pct(r.p50, 1)} · vægtet {pct(r.vaegtet, 1)}", va="center",
                    fontsize=9.5, color=INK)
        ax.set_yticks(ys)
        ax.set_yticklabels([f"{r.gruppe}\n{r.bog} ({r.n} stk.)" for r in fordeling.itertuples()],
                           fontsize=9.5)
        ax.axvline(0, color=LINE, linewidth=1.0)
        ax.set_xlim(min(fordeling["p25"].min() * 1.2, -0.02),
                    max(fordeling["p75"].max(), fordeling["vaegtet"].max()) + spand * 0.70)
        ax.set_ylim(-0.7, len(fordeling) - 0.3)
        ax.xaxis.set_major_formatter(PROC)
        ax.set_xlabel("IRR pr. handel (GP)")
        h = [Line2D([0], [0], color=PPIM_SAGE_DARK, linewidth=13, alpha=0.85, label="25.-75. percentil"),
             Line2D([0], [0], marker="|", linestyle="none", markersize=16, markeredgewidth=3,
                    color=MUTED, label="Median"),
             Line2D([0], [0], marker="D", linestyle="none", markersize=8, color=PPIM_BROWN,
                    label="Kapitalvægtet gennemsnit")]
        _legend(ax, handles=h, loc="lower right", labelspacing=0.8)
        # Overskriften følger data: hvilken gruppe har det bredeste interkvartilspænd
        titel = "Spredningen i IRR pr. handel"
        if self.HAR_GRUPPE:
            bredest = (fordeling.assign(spaend=fordeling["p75"] - fordeling["p25"])
                       .groupby("gruppe")["spaend"].max().idxmax())
            titel = f"Spredningen i IRR er størst i {lille(bredest)}"
        self.afslut(fig, titel,
                    f"25.-75. percentil pr. {self.cfg.gruppe_omtale}, delt på realiseret og "
                    f"urealiseret bog · pr. {self.REPORT_DK}", "irr_fordeling", ax=ax,
                    note=" · IRR er GP's egen pr. handel"
                         + (f" · {self.N_NM} handler uden IRR indgår ikke" if self.N_NM else "")
                         + " · urealiserede IRR'er bygger på dagsværdi")

    def graf_holdeperiode(self):
        """Holdeperiode og multipel på de realiserede handler."""
        if not self._kraever(self.HAR_EXIT, "exit-datoer"):
            return
        r = self.REAL[(self.REAL["invested"] >= MIN_INVESTED) & self.REAL["holdeperiode"].notna()]
        levetid = self.REAL_LEVETID

        fig, axes = plt.subplots(1, 2, figsize=SLIDE, gridspec_kw={"width_ratios": [1.3, 1]})
        ax = axes[0]
        style_ax(ax)
        ax.grid(axis="x", color=GRID, linewidth=0.8)
        skala = 1800 / r["invested"].max()
        for g in self.GRUPPE_ORDEN:
            m = r["gruppe"] == g
            if m.any():
                ax.scatter(r.loc[m, "holdeperiode"], r.loc[m, "mom"], s=r.loc[m, "invested"] * skala,
                           color=self.GRUPPE_FARVE[g], alpha=0.80, zorder=3, label=g)
        ax.set_xlim(0, r["holdeperiode"].max() * 1.12)
        ax.set_ylim(0, r["mom"].quantile(0.99) * 1.20)
        ax.axhline(1.0, color=LINE, linestyle=(0, (4, 3)), linewidth=1.0, zorder=2)
        ax.axvline(levetid, color=PPIM_BROWN, linewidth=1.4, zorder=2)
        ax.text(levetid + 0.08, ax.get_ylim()[1], f"Kapitalvægtet levetid {_dk(levetid, 1)} år",
                va="top", fontsize=10.5, color=PPIM_BROWN)
        for _, row in r[r["invested"] >= MIN_LABEL].iterrows():
            ax.annotate(row["investment"], (row["holdeperiode"], row["mom"]),
                        textcoords="offset points", xytext=(0, 9), ha="center", fontsize=7.8,
                        color=MUTED, zorder=5)
        ax.yaxis.set_major_formatter(MULT)
        ax.set_xlabel("Holdeperiode (år)")
        ax.set_ylabel("Realiseret multipel (MoM)")
        lg = _legend(ax, loc="upper left", scatterpoints=1, labelspacing=0.8)
        for hnd in lg.legend_handles:
            hnd.set_sizes([90])
        _titel(ax, "Realiserede handler")

        ax2 = axes[1]
        style_ax(ax2)
        navne = ["under 1 år", "1-2 år", "2-3 år", "3-4 år", "4-5 år", "over 5 år"]
        rr = r.copy()
        rr["baand"] = pd.cut(rr["holdeperiode"], [0, 1, 2, 3, 4, 5, 100], labels=navne, right=False)
        hp = rr.groupby("baand", observed=False).agg(kapital=("invested", "sum"),
                                                     samlet=("total_value", "sum"),
                                                     antal=("mom", "size"))
        hp["mom"] = hp["samlet"] / hp["kapital"].replace(0, np.nan)
        xs = np.arange(len(hp))
        ax2.bar(xs, hp["kapital"], width=0.66, color=PPIM_TAUPE, zorder=2)
        ax2.set_xticks(xs)
        ax2.set_xticklabels(hp.index, rotation=30, ha="right", fontsize=9.5)
        ax2.set_xlim(-0.6, len(hp) - 0.4)
        ax2.set_ylim(0, hp["kapital"].max() * 1.24)
        ax2.yaxis.set_major_formatter(self.BELOB)
        ax2.set_ylabel(f"Realiseret kapital ({self.MIO})")
        soejlelabel(ax2, xs, hp["kapital"],
                    [f"{mult(m)}\n{int(n)} stk." if n else "" for m, n in zip(hp["mom"], hp["antal"])],
                    fs=10)
        _titel(ax2, "Kapital og multipel pr. holdeperiode")
        self.afslut(fig, "Hvor længe arbejder kapitalen",
                    f"{len(r)} realiserede investeringer · kapitalvægtet levetid {_dk(levetid, 1)} år "
                    f"· pr. {self.REPORT_DK}", "holdeperiode", ax=axes[0],
                    note=self.note_belob() + " · holdeperiode er exit-dato minus handelsdato · "
                         f"positioner under {money(MIN_INVESTED, 0)} udeladt")

    # ------------------------------------------------------------------ 5. vintage og realiseringstakt

    def graf_vintage_kapital(self):
        """Kapital pr. vintage og hvor meget der er realiseret."""
        if not self._kraever(self.HAR_VINTAGE, "vintage"):
            return
        vg = self.g_vintage.copy()
        vg["urealiseret_kap"] = vg["investeret"] - vg["realiseret_kap"]
        xs = np.arange(len(vg))
        fig, ax = plt.subplots(figsize=SLIDE)
        style_ax(ax)
        ax.bar(xs, vg["realiseret_kap"], width=0.66, color=F_DPI, zorder=2)
        ax.bar(xs, vg["urealiseret_kap"], width=0.66, bottom=vg["realiseret_kap"], color=F_RVPI,
               zorder=2)
        ax.set_xticks(xs)
        ax.set_xticklabels([int(v) for v in vg.index], fontsize=10 if len(vg) <= 10 else 8.5)
        ax.set_xlim(-0.6, len(vg) - 0.4)
        ax.set_ylim(0, vg["investeret"].max() * 1.24)
        ax.yaxis.set_major_formatter(self.BELOB)
        ax.set_ylabel(f"Investeret kapital ({self.MIO})")
        ax.set_xlabel(self.cfg.vintage_navn)
        taet = len(vg) > 10
        soejlelabel(ax, xs, vg["investeret"],
                    [f"{money(k, 0)}\n{mult(t)}" if taet else
                     f"{money(k, 0)}\n{int(n)} stk. · {mult(t)}"
                     for k, n, t in zip(vg["investeret"], vg["antal"], vg["tvpi"])],
                    fs=8 if taet else 10)
        if self.HAR_REAL:
            legend_swatches(ax, [(F_DPI, "Realiseret kapital"), (F_RVPI, "Urealiseret kapital")],
                            loc="upper left", bbox_to_anchor=(0.005, 0.99))
        self.afslut(fig, "Kapital og modenhed pr. vintage",
                    f"Investeret kapital pr. {self.cfg.vintage_omtale}"
                    + (", delt på realiseret og urealiseret" if self.HAR_REAL else "")
                    + f" · pr. {self.REPORT_DK}", "vintage_kapital", ax=ax,
                    note=self.note_belob() + " · multiplen ved hver søjle er årgangens samlede TVPI "
                                             "· unge årgange er endnu ikke modnet")

    def graf_vintage_tvpi(self):
        """TVPI pr. vintage, bredde = investeret kapital."""
        if not self._kraever(self.HAR_VINTAGE, "vintage"):
            return
        mange = len(self.g_vintage) > 10
        self._split_soejler(
            self.g_vintage.rename(index=lambda v: str(int(v))), "TVPI pr. vintage",
            f"Søjlebredde = investeret kapital · opdelt i realiseret (DPI) og urealiseret (RVPI) "
            f"· pr. {self.REPORT_DK}", "vintage_tvpi", rotation=90 if mange else 0,
            fs=9 if mange else 11,
            note=self.note_belob() + f" · vintage er {self.cfg.vintage_omtale}")

    def graf_exits(self):
        """Realiseringstakt: kapital, værdi og multipel pr. exit-år."""
        if not self._kraever(self.HAR_EXIT, "exit-datoer"):
            return
        REAL = self.REAL[self.REAL["exit_aar"].notna()]
        ex = REAL.groupby("exit_aar").agg(kapital=("invested", "sum"),
                                          samlet=("total_value", "sum"), antal=("mom", "size"))
        ex["mom"] = ex["samlet"] / ex["kapital"]
        samlet_mom = REAL["total_value"].sum() / REAL["invested"].sum()

        fig, axes = plt.subplots(1, 2, figsize=SLIDE)
        ax = axes[0]
        style_ax(ax)
        xs = np.arange(len(ex))
        ax.bar(xs - 0.19, ex["kapital"], width=0.36, color=PPIM_TAUPE, zorder=2,
               label="Investeret kapital")
        ax.bar(xs + 0.19, ex["samlet"], width=0.36, color=F_DPI, zorder=2, label="Realiseret værdi")
        ax.set_xticks(xs)
        ax.set_xticklabels([int(v) for v in ex.index])
        ax.set_xlim(-0.6, len(ex) - 0.4)
        ax.set_ylim(0, max(ex["kapital"].max(), ex["samlet"].max()) * 1.24)
        ax.yaxis.set_major_formatter(self.BELOB)
        ax.set_ylabel(self.MIO_STOR)
        ax.set_xlabel("Exit-år")
        soejlelabel(ax, xs + 0.19, ex["samlet"], [f"{int(n)} stk." for n in ex["antal"]], fs=10)
        _legend(ax, loc="upper left", handlelength=1.2)
        _titel(ax, "Realiseret kapital og værdi pr. exit-år")

        ax2 = axes[1]
        style_ax(ax2)
        ax2.bar(xs, ex["mom"], width=0.6, color=F_DPI, zorder=2)
        ax2.axhline(1.0, color=LINE, linestyle=(0, (4, 3)), linewidth=1.0, zorder=3)
        ax2.axhline(samlet_mom, color=PPIM_SAGE_DARK, linewidth=1.5, zorder=3)
        ax2.set_xticks(xs)
        ax2.set_xticklabels([int(v) for v in ex.index])
        ax2.set_xlim(-0.6, len(ex) - 0.4)
        ax2.set_ylim(0, ex["mom"].max() * 1.26)
        ax2.yaxis.set_major_formatter(MULT)
        ax2.set_ylabel("Realiseret multipel (MoM)")
        ax2.set_xlabel("Exit-år")
        soejlelabel(ax2, xs, ex["mom"], [mult(v) for v in ex["mom"]], fs=10.5)
        reflabel(ax2, samlet_mom, f"Samlet realiseret {mult(samlet_mom)}", PPIM_SAGE_DARK, over=True)
        _titel(ax2, "Multipel pr. exit-årgang")
        # Overskriften følger data: det exit-år, der bærer mest realiseret værdi
        self.afslut(fig, f"Realiseringerne er koncentreret om {int(ex['samlet'].idxmax())}",
                    f"{len(REAL)} realiserede investeringer fordelt på exit-år · {self.as_of.year} "
                    f"dækker til {self.REPORT_DK}", "exits", ax=axes[0],
                    note=self.note_belob() + " · exit-år er året for den registrerede exit-dato")
