"""Det, databasen kan, som regnearket bag det oprindelige IC-deck ikke kunne.

- Track record over tid: alle rapportdatoer i stedet for tre.
- Gruppernes vægt og multipel over tid.
- GP'ens egne fordelinger på branche og geografi (rpt.v_portfolio_breakdown).
- Selskabernes egne nøgletal: gearing, margin og værdiansættelse (rpt.v_portfolio_company).
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .. import data
from ..style import (PPIM_SAGE_DARK, PPIM_SAGE_LIGHT, PPIM_OLIVE, PPIM_BROWN, PPIM_TAUPE,
                     PPIM_TAUPE_LIGHT, PPIM_TERRACOTTA, PPIM_RED_MUTED, SLIDE, INK, MUTED, LINE,
                     style_ax, legend_swatches, ref_pill, _dk, money, mult)
from .bog import _titel, _vandret
from .kerne import F_DPI, F_RVPI, GRUPPE_PALET, MULT, NUM, PROC, lille, pct

DIMENSION_DK = {"INDUSTRY": "Branche", "GEOGRAPHY": "Geografi", "CURRENCY": "Valuta",
                "SEGMENT": "Segment"}
MIN_ANDEL_TID = 5.0     # pct. - kategorier, der aldrig når over dette, samles i "Øvrige"


def _x(v, dec=1):
    return "–" if pd.isna(v) else _dk(v, dec) + "x"


class Ekstra:
    # ------------------------------------------------------------------ track record over tid

    def graf_tidsserie(self):
        """Investeret kapital, udlodninger og dagsværdi pr. rapportdato - og TVPI opdelt."""
        if not self._kraever(len(self.DATOER) >= 3, "mindst tre rapportdatoer"):
            return
        t = self.alle.groupby("report_date")[NUM].sum()
        t["dpi"] = t["proceeds"] / t["invested"]
        t["rvpi"] = t["fair_value"] / t["invested"]
        t["tvpi"] = t["dpi"] + t["rvpi"]
        self.TIDSSERIE = t

        fig, axes = plt.subplots(1, 2, figsize=SLIDE, gridspec_kw={"width_ratios": [1.15, 1]})
        ax = axes[0]
        style_ax(ax)
        for kol, farve, lw in (("invested", PPIM_TAUPE, 2.4), ("fair_value", PPIM_SAGE_DARK, 2.4),
                               ("proceeds", PPIM_SAGE_LIGHT, 2.4)):
            ax.plot(t.index, t[kol], color=farve, linewidth=lw, marker="o", markersize=3.5)
        ax.set_ylim(0, t[["invested", "fair_value", "proceeds"]].max().max() * 1.30)   # signatur øverst
        ax.yaxis.set_major_formatter(self.BELOB)
        ax.set_ylabel(self.MIO_STOR)
        self._tidsakse(ax, list(t.index))
        nu = t.iloc[-1]
        legend_swatches(ax, [(PPIM_TAUPE, f"Investeret kapital  {money(nu['invested'], 0)}"),
                             (PPIM_SAGE_DARK, f"Dagsværdi  {money(nu['fair_value'], 0)}"),
                             (PPIM_SAGE_LIGHT, f"Udlodninger (akk.)  {money(nu['proceeds'], 0)}")],
                        loc="upper left", fontsize=10)
        _titel(ax, "Kapital og værdi, akkumuleret")

        ax2 = axes[1]
        style_ax(ax2)
        xs = np.arange(len(t))
        ax2.bar(xs, t["dpi"], width=0.74, color=F_DPI, zorder=2)
        ax2.bar(xs, t["rvpi"], width=0.74, bottom=t["dpi"], color=F_RVPI, zorder=2)
        ax2.set_ylim(0, max(t["tvpi"].max() * 1.14, 1.15))
        ref_pill(ax2, 1.0, "1,0x")
        self._kvartalsakse(ax2, list(t.index))
        ax2.yaxis.set_major_formatter(MULT)
        ax2.text(xs[-1], nu["tvpi"], mult(nu["tvpi"]), ha="center", va="bottom", fontsize=10,
                 fontweight="bold")
        legend_swatches(ax2, [(F_DPI, "DPI (udloddet)"), (F_RVPI, "RVPI (dagsværdi)")],
                        loc="upper left", fontsize=10, ncol=2)
        _titel(ax2, "Brutto-TVPI pr. rapportdato")
        foer = t.iloc[0]
        self.afslut(fig, "Track record over tid",
                    f"{len(t)} rapportdatoer fra {t.index[0]:%d.%m.%Y} · investeret kapital "
                    f"{money(foer['invested'], 0)} → {money(nu['invested'], 0)} · TVPI "
                    f"{mult(foer['tvpi'])} → {mult(nu['tvpi'])}", "tidsserie", ax=axes[0],
                    note=self.note_belob() + " · hele fonden, brutto for honorar og carry")

    def graf_gruppemix_tid(self):
        """Gruppernes andel af dagsværdien og deres multipel over tid."""
        datoer = [d for d in self.DATOER if d >= self.DETALJE_FRA]
        if not self._kraever(self.HAR_GRUPPE and len(datoer) >= 3,
                             f"{self.cfg.gruppe_omtale} på mindst tre rapportdatoer"):
            return
        d = self.alle[self.alle["report_date"].isin(datoer) & self.alle["gruppe"].notna()]
        g = d.groupby(["report_date", "gruppe"])[NUM].sum()
        fv = g["fair_value"].unstack().reindex(columns=self.GRUPPE_ORDEN).fillna(0.0)
        andel = fv.div(fv.sum(axis=1), axis=0)
        tvpi = (g["total_value"] / g["invested"].replace(0, np.nan)).unstack().reindex(
            columns=self.GRUPPE_ORDEN)

        fig, axes = plt.subplots(1, 2, figsize=SLIDE)
        ax = axes[0]
        style_ax(ax)
        xs = np.arange(len(andel))
        bund = np.zeros(len(andel))
        for grp in self.GRUPPE_ORDEN:
            v = andel[grp].to_numpy()
            ax.bar(xs, v, bottom=bund, width=0.74, color=self.GRUPPE_FARVE[grp], zorder=2)
            for i in (0, len(xs) - 1) if len(xs) <= 12 else ():    # smalle søjler: ingen tekst
                if v[i] > 0.06:
                    ax.text(xs[i], bund[i] + v[i] / 2, pct(v[i], 0), ha="center", va="center",
                            fontsize=9, color="white", fontweight="bold", zorder=4)
            bund += v
        ax.set_ylim(0, 1)
        ax.yaxis.set_major_formatter(PROC)
        self._kvartalsakse(ax, list(andel.index))
        ax.grid(False)
        _titel(ax, "Andel af den urealiserede dagsværdi")

        ax2 = axes[1]
        style_ax(ax2)
        for grp in self.GRUPPE_ORDEN:
            ax2.plot(tvpi.index, tvpi[grp], color=self.GRUPPE_FARVE[grp], linewidth=2.2, marker="o",
                     markersize=4)
        ax2.axhline(1.0, color=LINE, linestyle=(0, (4, 3)), linewidth=1.0)
        ax2.yaxis.set_major_formatter(MULT)
        self._tidsakse(ax2, list(tvpi.index))
        lo, hi = np.nanmin(tvpi.to_numpy()), np.nanmax(tvpi.to_numpy())
        ax2.set_ylim(min(lo, 1.0) - (hi - lo) * 0.08, hi + (hi - lo) * 0.45)   # plads til signaturen
        legend_swatches(ax2, [(self.GRUPPE_FARVE[grp], f"{grp}  {mult(tvpi[grp].iloc[-1])}")
                              for grp in self.GRUPPE_ORDEN if pd.notna(tvpi[grp].iloc[-1])],
                        loc="upper left", fontsize=10)
        _titel(ax2, f"TVPI pr. {self.cfg.gruppe_omtale}")
        stoerst = (andel.iloc[-1] - andel.iloc[0]).abs().idxmax()
        self.afslut(fig, f"{self.cfg.gruppe_navn}rne over tid",
                    f"{len(datoer)} rapportdatoer fra {datoer[0]:%d.%m.%Y} · {lille(stoerst)} er "
                    f"gået fra {pct(andel[stoerst].iloc[0], 0)} til {pct(andel[stoerst].iloc[-1], 0)} "
                    "af dagsværdien", "gruppemix_tid", ax=axes[0],
                    note=" · TVPI er på hele gruppen inkl. realiserede handler"
                         + (f" · rapporten har først linjer pr. tranche fra {self.DETALJE_FRA:%d.%m.%Y}"
                            if self.DETALJE_FRA > self.FOERSTE else ""))

    # ------------------------------------------------------------------ branche og geografi

    def graf_branche_geografi(self):
        """GP'ens egne fordelinger: seneste opgørelse for to dimensioner."""
        b = data.breakdown(self.kode)
        b = b[(b["report_date"] <= self.as_of) & b["dimension"].isin(DIMENSION_DK)
              & (b["dimension"] != "CURRENCY")]
        if not self._kraever(len(b), "fordelinger på branche eller geografi fra GP'en"):
            return
        self.BREAKDOWN = b
        dims = [d for d in ("INDUSTRY", "SEGMENT", "GEOGRAPHY") if (b["dimension"] == d).any()][:2]
        fig, axes = plt.subplots(1, len(dims), figsize=SLIDE)
        datoer = {}
        for ax, dim in zip(np.atleast_1d(axes), dims):
            d = b[b["dimension"] == dim]
            dato = datoer[dim] = d["report_date"].max()
            d = d[d["report_date"] == dato].sort_values("share_pct")
            _vandret(ax)
            ys = np.arange(len(d))
            ax.barh(ys, d["share_pct"], color=PPIM_SAGE_DARK, height=0.66, zorder=2)
            for y, v in zip(ys, d["share_pct"]):
                ax.text(v + d["share_pct"].max() * 0.02, y, _dk(v, 1) + " %", va="center",
                        fontsize=10, color=INK)
            ax.set_yticks(ys)
            ax.set_yticklabels(d["category"], fontsize=10)
            ax.set_xlim(0, d["share_pct"].max() * 1.22)
            ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: _dk(v, 0) + " %"))
            _titel(ax, f"{DIMENSION_DK[dim]} · pr. {dato:%d.%m.%Y}")
        top = {dim: b[(b["dimension"] == dim) & (b["report_date"] == datoer[dim])]
               .nlargest(1, "share_pct").iloc[0] for dim in dims}
        self.afslut(fig, "Branche og geografi" if "INDUSTRY" in dims else "GP'ens fordelinger",
                    "GP'ens egen fordeling af porteføljens dagsværdi · størst: "
                    + " og ".join(f"{t['category']} ({_dk(t['share_pct'], 0)} %)" for t in top.values()),
                    "branche_geografi", ax=np.atleast_1d(axes)[0],
                    note=" · andel af porteføljens dagsværdi som GP'en opgør den"
                         + (" · seneste rapport med fordelingen er ældre end rapportdatoen"
                            if min(datoer.values()) < self.as_of else ""))

    def graf_branche_tid(self):
        """Brancheeksponeringen over tid (eller den første dimension, GP'en har historik for)."""
        b = getattr(self, "BREAKDOWN", None)
        if b is None:
            b = data.breakdown(self.kode)
            b = b[(b["report_date"] <= self.as_of) & b["dimension"].isin(DIMENSION_DK)]
        dim = next((d for d in ("INDUSTRY", "SEGMENT", "GEOGRAPHY")
                    if b.loc[b["dimension"] == d, "report_date"].nunique() >= 4), None)
        if not self._kraever(dim, "fordeling med historik på mindst fire rapportdatoer"):
            return
        # GP'en staver kategorierne forskelligt fra rapport til rapport ("Building products" /
        # "Building Products", "defence" / "Defense") - de samles, før der pivoteres
        d = b[b["dimension"] == dim].copy()
        d["category"] = (d["category"].str.strip().str.replace("defence", "defense", case=False)
                         .str.title().str.replace(" It", " IT").str.replace("&", "&"))
        p = d.pivot_table(index="report_date", columns="category", values="share_pct",
                          aggfunc="sum").fillna(0.0)
        p = p[p.sum(axis=1) > 80]          # en rapport med en halv fordeling er ikke en fordeling
        smaa = p.columns[p.max() < MIN_ANDEL_TID]
        if len(smaa) > 1:
            p["Øvrige"] = p.get("Øvrige", 0) + p[[c for c in smaa if c != "Øvrige"]].sum(axis=1)
            p = p.drop(columns=[c for c in smaa if c != "Øvrige"])
        orden = list(p.iloc[-1].drop(labels=["Øvrige"], errors="ignore").sort_values(ascending=False).index)
        orden += ["Øvrige"] if "Øvrige" in p else []
        p = p[orden]
        farver = (GRUPPE_PALET + [PPIM_RED_MUTED, "#9AA08C", "#BFB5A3"])[:len(orden)]

        fig, ax = plt.subplots(figsize=SLIDE)
        style_ax(ax)
        xs = np.arange(len(p))
        bund = np.zeros(len(p))
        for kat, farve in zip(orden, farver):
            v = p[kat].to_numpy()
            ax.bar(xs, v, bottom=bund, width=0.78, color=farve, zorder=2)
            bund += v
        ax.set_ylim(0, max(bund.max(), 100) * 1.0)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: _dk(v, 0) + " %"))
        self._kvartalsakse(ax, list(p.index))
        ax.grid(False)
        legend_swatches(ax, [(f, f"{k}  {_dk(p[k].iloc[-1], 0)} %") for k, f in zip(orden, farver)],
                        loc="center left", bbox_to_anchor=(1.01, 0.5), fontsize=10)
        stoerst = orden[0]
        self.afslut(fig, f"{DIMENSION_DK[dim]}fordelingen over tid",
                    f"{len(p)} rapporter fra {p.index[0]:%d.%m.%Y} · {stoerst} er gået fra "
                    f"{_dk(p[stoerst].iloc[0], 0)} % til {_dk(p[stoerst].iloc[-1], 0)} % af dagsværdien",
                    "branche_tid", ax=ax, rect=[0.055, 0.075, 0.80, None],
                    note=" · GP'ens egen opgørelse; rapporter, hvor fordelingen kun står som "
                         "billede, mangler · kategorier under "
                         f"{_dk(MIN_ANDEL_TID, 0)} % er samlet i Øvrige")

    # ------------------------------------------------------------------ selskabernes egne nøgletal

    def graf_selskabs_kpi(self):
        """Gearing nu mod ved investering pr. selskab, og de vægtede nøgletal over tid."""
        k = data.portfolio_company(self.kode)
        k = k[k["report_date"] <= self.as_of]
        if not self._kraever(len(k) and k["net_leverage"].notna().sum() >= 5,
                             "selskabsnøgletal (gearing, EBITDA, EV)"):
            return
        dato = k["report_date"].max()
        nu = k[(k["report_date"] == dato) & k["net_leverage"].notna()
               & (k["invested_amount"] > 0)].copy()
        nu["inv"] = nu["invested_amount"] / 1e6

        def vaegtet(d, kol):
            m = d[kol].notna() & (d["invested_amount"] > 0)
            return np.average(d.loc[m, kol], weights=d.loc[m, "invested_amount"]) if m.any() else np.nan
        tid = k.groupby("report_date").apply(lambda d: pd.Series({
            "gearing": vaegtet(d, "net_leverage"), "ev": vaegtet(d, "ev_to_ebitda"),
            "margin": vaegtet(d, "ebitda_margin_pct"), "n": d["net_leverage"].notna().sum()}))
        tid = tid[tid["n"] >= 5]
        self.KPI_NU, self.KPI_TID = nu, tid

        fig, axes = plt.subplots(1, 2, figsize=SLIDE, gridspec_kw={"width_ratios": [1.15, 1]})
        ax = axes[0]
        _vandret(ax)
        vis = nu.nlargest(16, "inv").sort_values("net_leverage")
        ys = np.arange(len(vis))
        for y, r in zip(ys, vis.itertuples()):
            foer = r.leverage_at_investment
            if pd.notna(foer):
                op = r.net_leverage > foer
                ax.plot([foer, r.net_leverage], [y, y], color=PPIM_RED_MUTED if op else PPIM_SAGE_LIGHT,
                        linewidth=5, solid_capstyle="butt", zorder=2)
                ax.plot([foer], [y], marker="|", markersize=14, markeredgewidth=2.2, color=MUTED,
                        zorder=3)
            ax.plot([r.net_leverage], [y], marker="o", markersize=7, color=PPIM_SAGE_DARK, zorder=4)
            ax.text(max(r.net_leverage, foer if pd.notna(foer) else 0) + 0.45, y,
                    f"{_x(r.net_leverage)}" + (f"  (fra {_x(foer)})" if pd.notna(foer) else ""),
                    va="center", fontsize=9, color=INK)
        ax.set_yticks(ys)
        ax.set_yticklabels(vis["company"], fontsize=9.5)
        ax.set_xlim(0, max(vis["net_leverage"].max(), vis["leverage_at_investment"].max()) * 1.30)
        ax.set_ylim(-1.6, len(vis) - 0.3)
        ax.xaxis.set_major_formatter(MULT)
        ax.set_xlabel("Nettogæld / EBITDA")
        legend_swatches(ax, [(PPIM_SAGE_DARK, "Nu (punkt)"), (MUTED, "Ved investering (streg)"),
                             (PPIM_SAGE_LIGHT, "Nedbragt"), (PPIM_RED_MUTED, "Øget")],
                        loc="lower right", fontsize=9, ncol=4)
        _titel(ax, f"Gearing i de {len(vis)} største selskaber, målt på fondens investering")

        ax2 = axes[1]
        style_ax(ax2)
        ax2.plot(tid.index, tid["ev"], color=PPIM_TAUPE, linewidth=2.2, marker="o", markersize=3.5)
        ax2.plot(tid.index, tid["gearing"], color=PPIM_SAGE_DARK, linewidth=2.2, marker="o",
                 markersize=3.5)
        ax2.fill_between(tid.index, tid["gearing"], tid["ev"], color=PPIM_SAGE_LIGHT, alpha=0.35)
        ax2.set_ylim(0, tid["ev"].max() * 1.18)
        ax2.yaxis.set_major_formatter(MULT)
        self._tidsakse(ax2, list(tid.index))
        sidst = tid.iloc[-1]
        pude = 1 - sidst["gearing"] / sidst["ev"]
        legend_swatches(ax2, [(PPIM_TAUPE, f"EV / EBITDA  {_x(sidst['ev'])}"),
                              (PPIM_SAGE_DARK, f"Nettogæld / EBITDA  {_x(sidst['gearing'])}"),
                              (PPIM_SAGE_LIGHT, f"Egenkapitalpude  {pct(pude, 0)} af EV")],
                        loc="lower left", fontsize=10)
        _titel(ax2, "Vægtet med fondens investerede beløb")

        begge = nu[nu["leverage_at_investment"].notna()]
        ned = int((begge["net_leverage"] < begge["leverage_at_investment"]).sum())
        self.afslut(fig, "Selskabernes gearing og værdiansættelse",
                    f"{len(nu)} selskaber pr. {dato:%d.%m.%Y} · vægtet nettogæld "
                    f"{_x(vaegtet(nu, 'net_leverage'))} EBITDA mod {_x(vaegtet(begge, 'leverage_at_investment'))} "
                    f"ved investering · {ned} af {len(begge)} har nedbragt gearingen · vægtet "
                    f"EBITDA-margin {_dk(vaegtet(nu, 'ebitda_margin_pct'), 0)} %",
                    "selskabs_kpi", ax=axes[0],
                    note=" · selskabernes egne tal fra GP'ens rapport (LTM/FY, typisk 1-2 kvartaler "
                         "før rapportdatoen) · GP'en sætter EV som et fast multiplum af EBITDA")
