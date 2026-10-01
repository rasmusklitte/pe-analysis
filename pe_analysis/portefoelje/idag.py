"""Porteføljen i dag: de urealiserede positioner, valuta og den urealiserede bogs kvalitet.

Den urealiserede del af track record'et hviler på GP'ens egne dagsværdier. Slidene her
spørger, om bogen ligner den, afkastet er tjent på, om markene bliver revurderet, om gamle
positioner er strandet, og hvor værdiskabelsen endnu ikke er sket.
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.transforms import blended_transform_factory

from ..fondskonfig import MIN_INVESTED, MIN_MOVE, N_TOP, UR_KOSTPRIS, UR_MODEN
from ..style import (PPIM_SAGE_DARK, PPIM_SAGE_LIGHT, PPIM_OLIVE, PPIM_TAUPE, PPIM_TAUPE_LIGHT,
                     PPIM_TERRACOTTA, PPIM_BEIGE, SLIDE, BG, INK, MUTED, LINE, GRID, style_ax,
                     legend_swatches, _dk, money, mult)
from .bog import _legend, _titel, _vandret
from .kerne import (F_NEG, F_POS, F_RVPI, MULT, PROC, brudt, dmoney, lille, opsummer, pct,
                    reflabel, soejlelabel)
from .tid import POS_KEY


def _kort(tekst, n=40):
    return tekst if len(tekst) <= n else tekst[:n - 2] + "…"


def _tvilling(ax):
    """Sekundær y-akse uden egne rammer og gitter."""
    b = ax.twinx()
    b.set_facecolor("none")
    for s in b.spines.values():
        s.set_visible(False)
    b.grid(False)
    b.tick_params(length=0, colors=MUTED)
    return b


class Idag:
    def _byg_urealiseret(self):
        """Aggregaterne bag slidene om den urealiserede bog. Kaldes fra __init__."""
        UREAL, tot = self.UREAL, self.tot
        self.UREAL_ALDER = (np.average(UREAL.loc[UREAL["holdeperiode"].notna(), "holdeperiode"],
                                       weights=UREAL.loc[UREAL["holdeperiode"].notna(), "invested"])
                            if self.HAR_ALDER and UREAL["invested"].sum() > 0 else np.nan)
        self.ANDEL_UREAL_VAERDI = tot["fair_value"] / tot["total_value"]

        # Koncentration i dagsværdien
        s = (UREAL.groupby("investment")[["invested", "proceeds", "fair_value", "total_value"]].sum()
             .sort_values("fair_value", ascending=False))
        s["mom"] = s["total_value"] / s["invested"].replace(0, np.nan)
        s["merv"] = s["total_value"] - s["invested"]
        self.UR_SELSKAB = s
        kum = s["fair_value"].cumsum() / s["fair_value"].sum()
        self.UR_TOP5 = kum.iloc[min(4, len(kum) - 1)] if len(kum) else np.nan
        self.UR_TOP10 = kum.iloc[min(9, len(kum) - 1)] if len(kum) else np.nan

        # Positioner uden værdiskabelse: til kostpris og under kostpris
        p = UREAL.groupby(POS_KEY).agg(invested=("invested", "sum"), fair_value=("fair_value", "sum"),
                                       total_value=("total_value", "sum"),
                                       holdeperiode=("holdeperiode", "max"),
                                       gruppe=("gruppe", "first"), label=("label", "first"))
        p["mom"] = p["total_value"] / p["invested"].replace(0, np.nan)
        self.UR_POS = p[p["invested"] >= MIN_INVESTED]
        self.TIL_KOSTPRIS = self.UR_POS[self.UR_POS["mom"].between(*UR_KOSTPRIS)].sort_values("invested")
        self.UNDER_KOSTPRIS = self.UR_POS[self.UR_POS["mom"] < UR_KOSTPRIS[0]].sort_values(
            "mom", ascending=False)

        if not self.HAR_PERIODE:
            return
        # Bevæger markene sig? Dagsværdien pr. position gennem opgørelserne siden årsskiftet.
        # En bog med marks på autopilot ville stå stille - det er den vigtigste kontrol af, om
        # den urealiserede værdi overhovedet bliver revurderet.
        datoer = [d for d in self.DATOER if d >= self.PRIMO_AAR]
        self.MARK_DATOER = datoer
        snaps = {d: self.snapshot(d) for d in datoer}
        fv = pd.concat([snaps[d].groupby(POS_KEY)["fair_value"].sum().rename(d) for d in datoer],
                       axis=1)
        # Dagsværdien flytter sig også, når kapital kommer ind eller går ud. Det er ikke en
        # revurdering, så ændringen renses for flows: Δdagsværdi − Δinvesteret + Δudlodninger.
        netto = pd.concat([(s.groupby(POS_KEY)["fair_value"].sum() - s.groupby(POS_KEY)["invested"].sum()
                            + s.groupby(POS_KEY)["proceeds"].sum()).rename(d)
                           for d, s in snaps.items()], axis=1)
        M = fv[fv[self.as_of].fillna(0) > MIN_MOVE].copy()
        # En position, der ikke fandtes ved den første opgørelse, er kommet til i perioden. Dens
        # dagsværdi er en indtræden og ikke en revurdering, så den holdes for sig - ellers ville
        # den optræde som porteføljens største opskrivning.
        ny = M[datoer[0]].isna()
        M[datoer] = M[datoer].fillna(0.0)
        netto = netto.reindex(M.index).fillna(0.0)
        M["d_fv"] = netto[self.as_of] - netto[datoer[0]]
        # "Uændret" betyder uændret i hvert eneste skridt, ikke bare fra start til slut
        M["bevaeget"] = (netto[datoer].diff(axis=1).abs() > MIN_MOVE).any(axis=1)
        M["retning"] = np.where(ny, "Ny i perioden",
                                np.where(~M["bevaeget"], "Uændret",
                                         np.where(M["d_fv"] > 0, "Skrevet op", "Skrevet ned")))
        labels = (pd.concat(snaps.values()).drop_duplicates(POS_KEY).set_index(POS_KEY)["label"])
        M["label"] = labels.reindex(M.index)
        self.MARKS = M
        self.RETNINGER = [r for r in ("Skrevet op", "Skrevet ned", "Uændret", "Ny i perioden")
                          if (M["retning"] == r).any()]
        self.MARK_OPS = (M.groupby("retning").agg(antal=("d_fv", "size"),
                                                  dagsvaerdi=(self.as_of, "sum"))
                         .reindex(self.RETNINGER).fillna(0))
        self.REVURDERET = M[~ny]
        self.RVPI_SERIE = pd.Series({
            d: s["fair_value"].sum() / max(s.loc[~s["realiseret"], "invested"].sum(), 1e-9)
            for d, s in snaps.items()})

    # ------------------------------------------------------------------ grafer

    def graf_urealiseret_top(self):
        """De største urealiserede positioner: investeret kapital mod dagsværdi."""
        ur = self.UR_SELSKAB
        if not self._kraever(len(ur) >= 2, "urealiserede beholdninger"):
            return
        top = ur.nlargest(N_TOP, "fair_value").sort_values("fair_value")
        fig, ax = plt.subplots(figsize=SLIDE)
        _vandret(ax)
        ys = np.arange(len(top))
        ax.barh(ys, top["invested"], height=0.34, color=PPIM_TAUPE, zorder=2, label="Investeret kapital")
        ax.barh(ys + 0.36, top["fair_value"], height=0.34, color=F_RVPI, zorder=2, label="Dagsværdi")
        for y, r in zip(ys, top.itertuples()):
            ax.text(max(r.invested, r.fair_value) + top["fair_value"].max() * 0.02, y + 0.18,
                    f"{mult(r.mom)}   ({money(r.merv, 0)})", va="center", fontsize=9.5, color=INK)
        ax.set_yticks(ys + 0.18)
        ax.set_yticklabels([_kort(n) for n in top.index], fontsize=9.5)
        ax.set_xlim(0, max(top["fair_value"].max(), top["invested"].max()) * 1.42)
        ax.xaxis.set_major_formatter(self.BELOB)
        ax.set_xlabel(self.MIO_STOR)
        _legend(ax, loc="lower right", handlelength=1.2)
        self.afslut(fig, "De største urealiserede positioner",
                    f"Top {len(top)} af {len(ur)} urealiserede {self.cfg.enhed} · "
                    f"{pct(top['fair_value'].sum() / self.tot['fair_value'], 0)} af den samlede "
                    f"dagsværdi · pr. {self.REPORT_DK}", "urealiseret_top", ax=ax,
                    note=self.note_belob() + " · multiplen er udlodninger plus dagsværdi i forhold "
                         "til investeret kapital · kun urealiserede linjer indgår")

    def graf_valuta(self):
        """Valutaeksponering på de urealiserede marks."""
        if not self._kraever(self.HAR_VALUTA, "handelsvaluta pr. linje"):
            return
        val = opsummer(self.UREAL, "valuta", med_irr=False).sort_values("dagsvaerdi", ascending=False)
        val = val[val["dagsvaerdi"] > 0]
        alle = self.g_valuta
        farve = self.VALUTA_FARVE if hasattr(self, "VALUTA_FARVE") else dict(zip(
            alle.index, [PPIM_SAGE_DARK, PPIM_OLIVE, PPIM_TAUPE, PPIM_TERRACOTTA, PPIM_SAGE_LIGHT,
                         PPIM_TAUPE_LIGHT]))

        fig, axes = plt.subplots(1, 2, figsize=SLIDE, gridspec_kw={"width_ratios": [1, 1.1]})
        ax = axes[0]
        ax.set_axis_off()
        kiler, _ = ax.pie(val["dagsvaerdi"], startangle=90, counterclock=False,
                          colors=[farve[v] for v in val.index],
                          wedgeprops=dict(width=0.42, edgecolor=BG, linewidth=2))
        ax.text(0, 0.08, money(val["dagsvaerdi"].sum(), 0), ha="center", va="center", fontsize=21,
                fontweight="bold", color=INK)
        ax.text(0, -0.14, "urealiseret dagsværdi", ha="center", va="center", fontsize=10.5, color=MUTED)
        lg = ax.legend(kiler, [f"{v}   {money(k, 0)}   ({pct(a, 0)})" for v, k, a in
                               zip(val.index, val["dagsvaerdi"],
                                   val["dagsvaerdi"] / val["dagsvaerdi"].sum())],
                       frameon=False, loc="center left", bbox_to_anchor=(0.98, 0.5), handlelength=1.1)
        for t in lg.get_texts():
            t.set_color(INK)
        _titel(ax, "Dagsværdi pr. valuta")

        ax2 = axes[1]
        style_ax(ax2)
        xs = np.arange(len(alle))
        ax2.bar(xs, alle["tvpi"], width=0.6, color=[farve[v] for v in alle.index], zorder=2)
        ax2.axhline(1.0, color=LINE, linestyle=(0, (4, 3)), linewidth=1.0, zorder=3)
        ax2.axhline(self.pool_tvpi, color=PPIM_SAGE_DARK, linewidth=1.5, zorder=3)
        ax2.set_xticks(xs)
        ax2.set_xticklabels(alle.index)
        ax2.set_xlim(-0.6, len(alle) - 0.4)
        ax2.set_ylim(0, alle["tvpi"].max() * 1.28)
        ax2.yaxis.set_major_formatter(MULT)
        ax2.set_ylabel("TVPI")
        ax2.set_xlabel("Handelsvaluta")
        soejlelabel(ax2, xs, alle["tvpi"], [f"{mult(t)}\n{money(k, 0)}" for t, k in
                                            zip(alle["tvpi"], alle["investeret"])], fs=10)
        reflabel(ax2, self.pool_tvpi, f"Poolet {mult(self.pool_tvpi)}", PPIM_SAGE_DARK)
        _titel(ax2, "TVPI og investeret kapital pr. valuta")
        self.afslut(fig, "Valutaeksponering på de urealiserede marks",
                    f"Beløbene er rapporteret i {self.valuta}; valutaen er handlens egen · "
                    f"pr. {self.REPORT_DK}", "valuta", ax=axes[0],
                    note=self.note_belob() + " · afdækning er ikke oplyst")

    def graf_ureal_struktur(self):
        """Den realiserede bog mod den urealiserede: ligner resten det, afkastet er tjent på?"""
        if not self._kraever(self.HAR_REAL and self.HAR_GRUPPE,
                             f"realiseret/urealiseret fordelt på {self.cfg.gruppe_omtale}"):
            return
        boeger = (("Realiseret", self.REAL), ("Urealiseret", self.UREAL))
        BOG = {}
        for navn, f in boeger:
            g = opsummer(f, "gruppe", med_irr=False).reindex(self.GRUPPE_ORDEN)
            g["investeret"] = g["investeret"].fillna(0.0)
            g["andel"] = g["investeret"] / f["invested"].sum()
            BOG[navn] = g
        BOG_TVPI = {k: f["total_value"].sum() / f["invested"].sum() for k, f in boeger}
        tone = {"Realiseret": PPIM_SAGE_DARK, "Urealiseret": PPIM_TAUPE_LIGHT}

        fig, axes = plt.subplots(1, 2, figsize=SLIDE, gridspec_kw={"width_ratios": [1.15, 1]})
        ax = axes[0]
        _vandret(ax)
        ys = np.arange(len(self.GRUPPE_ORDEN))[::-1]
        h = 0.34
        for k, b in enumerate(BOG):
            off = (0.5 - k) * h
            v = BOG[b]["andel"].to_numpy(float)
            ax.barh(ys + off, v, height=h * 0.88, color=tone[b], zorder=2)
            # Bogens navn skrives på den øverste gruppes to søjler i stedet for i en signatur -
            # så er der ingen boks, der kan lande oven i en værditekst
            for j, (y, val, kap) in enumerate(zip(ys, v, BOG[b]["investeret"])):
                navn = f"{b}:  " if j == 0 else ""
                ax.text(val + 0.008, y + off, f"{navn}{pct(val, 0)}  ({money(kap, 0)})", va="center",
                        ha="left", fontsize=9.5, color=INK,
                        fontweight="bold" if j == 0 else "normal", zorder=4)
        ax.set_yticks(ys)
        ax.set_yticklabels([brudt(g, 16) for g in self.GRUPPE_ORDEN], fontsize=10.5)
        ax.set_xlim(0, max(BOG[b]["andel"].max() for b in BOG) * 1.62)
        ax.xaxis.set_major_formatter(PROC)
        ax.set_xlabel("Andel af bogens investerede kapital")
        _titel(ax, f"Sammensætning · realiseret {money(self.REAL['invested'].sum(), 0)} mod "
                   f"urealiseret {money(self.UREAL['invested'].sum(), 0)}")

        # Højre panel: multiplen pr. gruppe, med bogens samlede multipel som en ekstra gruppe -
        # to referencelinjer tæt på hinanden kan ikke mærkes læseligt
        ax2 = axes[1]
        style_ax(ax2)
        xs = np.arange(len(self.GRUPPE_ORDEN) + 1)
        b2 = 0.34
        maks = 0.0
        for k, b in enumerate(BOG):
            v = np.array(list(BOG[b]["tvpi"]) + [BOG_TVPI[b]], dtype=float)
            ax2.bar(xs + (k - 0.5) * b2, np.nan_to_num(v), width=b2 * 0.88, color=tone[b], zorder=2)
            maks = max(maks, np.nanmax(v))
            ax2.set_ylim(0, maks * 1.22)
            soejlelabel(ax2, xs + (k - 0.5) * b2, v, [mult(x) for x in v], fs=9.5)
        ax2.axvline(len(self.GRUPPE_ORDEN) - 0.5, color=GRID, linewidth=1.2, zorder=1)
        ax2.set_xticks(xs)
        ax2.set_xticklabels([brudt(g) for g in self.GRUPPE_ORDEN] + ["Hele\nbogen"], fontsize=9.5)
        ax2.set_xlim(-0.6, len(xs) - 0.4)
        ax2.yaxis.set_major_formatter(MULT)
        ax2.set_ylabel("MoM")
        _titel(ax2, "Multipel: hjemtaget kasse mod GP's marks")
        legend_swatches(ax2, [(tone[b], b) for b in BOG], loc="upper left")

        # Undertitlen nævner den gruppe, hvis vægt flytter sig mest mellem de to bøger
        skift = (BOG["Urealiseret"]["andel"] - BOG["Realiseret"]["andel"]).abs().idxmax()
        self.afslut(fig, "Den realiserede bog mod den urealiserede",
                    f"{pct(self.ANDEL_UREAL_VAERDI, 0)} af værdien er endnu ikke afgjort · "
                    f"{lille(skift)} er {pct(BOG['Realiseret'].loc[skift, 'andel'], 0)} af den "
                    f"realiserede kapital og {pct(BOG['Urealiseret'].loc[skift, 'andel'], 0)} af den "
                    f"urealiserede · pr. {self.REPORT_DK}", "ureal_struktur", ax=axes[0],
                    note=self.note_belob() + " · multiplen på den urealiserede bog er GP's egne "
                                             "marks, den realiserede er hjemtaget kasse")
        self.BOG, self.BOG_TVPI, self.BOG_SKIFT = BOG, BOG_TVPI, skift

    def graf_ureal_marks(self):
        """Bevæger markene sig overhovedet?

        En urealiseret bog er kun så meget værd som den revurdering, der ligger bag. Står
        dagsværdien stille kvartal efter kvartal, er tallet en bogføring, ikke en vurdering."""
        if not self._kraever(self.HAR_PERIODE and len(getattr(self, "MARKS", [])) >= 3,
                             "flere opgørelser af de aktive positioner"):
            return
        M, datoer = self.MARKS, self.MARK_DATOER
        farve = {"Skrevet op": F_POS, "Skrevet ned": F_NEG, "Uændret": PPIM_TAUPE_LIGHT,
                 "Ny i perioden": PPIM_TERRACOTTA}
        fig, axes = plt.subplots(1, 2, figsize=SLIDE, gridspec_kw={"width_ratios": [1.35, 1]})
        ax = axes[0]
        style_ax(ax)
        d = M.sort_values("d_fv")
        xs = np.arange(len(d))
        ax.bar(xs, d["d_fv"], width=0.82, zorder=2, color=[farve[r] for r in d["retning"]])
        ax.axhline(0, color=LINE, linewidth=1.0)
        spand = max(np.abs(d["d_fv"]).max(), MIN_MOVE)
        ax.set_ylim(-spand * 1.28, spand * 1.28)
        ax.set_xlim(-1, len(d))
        ax.set_xticks([])
        ax.yaxis.set_major_formatter(self.BELOB)
        ax.set_ylabel(f"Værdiregulering ({self.MIO})")
        ax.set_xlabel(f"{len(d)} aktive positioner, sorteret efter ændring")
        # De største bevægelser i hver ende navngives i to tekstblokke i stedet for som roterede
        # etiketter på søjlerne: mange smalle søjler har ikke plads til et navn. Blokkene lægges
        # i de to tomme hjørner.
        rangeret = d[d["retning"].isin(["Skrevet op", "Skrevet ned"])]
        ned, op = rangeret[rangeret["d_fv"] < 0].head(4), rangeret[rangeret["d_fv"] > 0].tail(4)
        for x0, y0, ha, rows, titel, kant in (
                (0.015, 0.97, "left", ned, "Største nedskrivninger", F_NEG),
                (0.985, 0.40, "right", op.iloc[::-1], "Største opskrivninger", F_POS)):
            if len(rows):
                linjer = [titel.upper()] + [f"{_kort(r['label'], 34)}   {dmoney(r['d_fv'])}"
                                            for _, r in rows.iterrows()]
                ax.text(x0, y0, "\n".join(linjer), transform=ax.transAxes, ha=ha, va="top",
                        multialignment=ha, fontsize=9, color=INK, linespacing=1.6, zorder=6,
                        bbox=dict(boxstyle="round,pad=0.45", fc=BG, ec=kant, linewidth=1.2))
        _titel(ax, f"Værdiregulering {datoer[0]:%d.%m.%Y} → {self.REPORT_DK}")

        ax2 = axes[1]
        _vandret(ax2)
        ops = self.MARK_OPS
        rader = [("Antal positioner", ops["antal"] / ops["antal"].sum(), ops["antal"],
                  lambda v: f"{int(v)}"),
                 ("Andel af dagsværdien", ops["dagsvaerdi"] / ops["dagsvaerdi"].sum(),
                  ops["dagsvaerdi"], lambda v: money(v, 0))]
        ys2 = np.arange(len(rader))[::-1]
        for y, (navn, andele, raa, fmt) in zip(ys2, rader):
            venstre = 0.0
            for r in self.RETNINGER:
                a = float(andele[r])
                ax2.barh(y, a, left=venstre, height=0.42, color=farve[r], zorder=2, edgecolor=BG,
                         linewidth=1.0)
                if a > 0.075:
                    ax2.text(venstre + a / 2, y, f"{fmt(raa[r])}\n{pct(a, 0)}", va="center",
                             ha="center", fontsize=9.5, fontweight="bold", zorder=4,
                             color="white" if r != "Uændret" else INK)
                venstre += a
        ax2.set_yticks(ys2)
        ax2.set_yticklabels([r[0] for r in rader], fontsize=10.5)
        ax2.set_xlim(0, 1)
        ax2.set_ylim(-0.8, len(rader) - 0.2)
        ax2.xaxis.set_major_formatter(PROC)
        _titel(ax2, "Hvor mange marks er revurderet")
        legend_swatches(ax2, [(farve[r], r) for r in self.RETNINGER], loc="lower center",
                        bbox_to_anchor=(0.5, -0.02), ncol=3)

        uaendret = ops["antal"].get("Uændret", 0)
        uaendret_andel = ops["dagsvaerdi"].get("Uændret", 0) / M[self.as_of].sum()
        nye = int(ops["antal"].get("Ny i perioden", 0))
        self.afslut(fig, "Er markene levende",
                    "RVPI " + " → ".join(mult(v) for v in self.RVPI_SERIE)
                    + f" over {len(datoer)} opgørelser · {int(uaendret)} af {len(self.REVURDERET)} "
                    f"positioner står uændret gennem hele perioden ({pct(uaendret_andel, 0)} af "
                    "dagsværdien)"
                    + (f" · {nye} position{'er' if nye != 1 else ''} kommet til undervejs" if nye else ""),
                    "ureal_marks", ax=axes[0],
                    note=self.note_belob() + " · værdiregulering = ændring i dagsværdi renset for "
                         "ind- og udbetalinger · \"uændret\" = uændret i hvert eneste skridt")

    def graf_ureal_modenhed(self):
        """Modenhed: er de gamle positioner strandet?

        En lav multipel på en ung position er J-kurve. Den samme multipel efter fem år er en
        position, der ikke er kommet videre."""
        if not self._kraever(self.HAR_ALDER, "handelsdato pr. linje"):
            return
        baand_navne = ["under 2 år", "2-3 år", "3-4 år", "4-5 år", "5 år og mere"]
        U = self.UREAL[self.UREAL["holdeperiode"].notna()].copy()
        U["aldersbaand"] = pd.cut(U["holdeperiode"], [0, 2, 3, 4, 5, np.inf], labels=baand_navne,
                                  right=False)
        A = opsummer(U, "aldersbaand", med_irr=False).reindex(baand_navne)
        A["investeret"] = A["investeret"].fillna(0.0)
        self.UR_ALDER = A

        fig, axes = plt.subplots(1, 2, figsize=SLIDE, gridspec_kw={"width_ratios": [1, 1.2]})
        ax = axes[0]
        style_ax(ax)
        xs = np.arange(len(A))
        ax.bar(xs, A["investeret"], width=0.62, color=PPIM_TAUPE_LIGHT, zorder=2)
        ax.set_ylim(0, A["investeret"].max() * 1.30)
        soejlelabel(ax, xs, A["investeret"], [money(v, 0) if v > 0 else "" for v in A["investeret"]],
                    fs=9.5)
        ax.set_xticks(xs)
        ax.set_xticklabels([n.replace(" og ", "\nog ").replace("under ", "under\n")
                            for n in baand_navne], fontsize=9.5)
        ax.set_xlim(-0.6, len(A) - 0.4)
        ax.yaxis.set_major_formatter(self.BELOB)
        ax.set_ylabel(f"Urealiseret kapital ({self.MIO})")
        ax.set_xlabel("Holdeperiode")
        axb = _tvilling(ax)
        # Punktstørrelsen følger kapitalen i båndet: uden den ser et lille bånd lige så tungt
        # ud som et stort, og linjens toppunkt bliver misvisende
        gyldig = A["tvpi"].notna()
        axb.plot(xs[gyldig], A.loc[gyldig, "tvpi"], color=PPIM_SAGE_DARK, linewidth=2.0, zorder=5)
        axb.scatter(xs[gyldig], A.loc[gyldig, "tvpi"], zorder=6, color=PPIM_SAGE_DARK,
                    s=40 + 360 * A.loc[gyldig, "investeret"] / A["investeret"].max())
        for x_i, v in zip(xs, A["tvpi"]):
            if pd.notna(v):
                axb.annotate(mult(v), xy=(x_i, v), xytext=(0, 9), textcoords="offset points",
                             ha="center", va="bottom", fontsize=9.5, fontweight="bold",
                             color=PPIM_SAGE_DARK, zorder=6)
        axb.set_ylim(0, float(A["tvpi"].max()) * 1.45)
        axb.yaxis.set_major_formatter(MULT)
        axb.set_ylabel("MoM (linje)", color=MUTED)
        _titel(ax, "Kapital og multipel pr. aldersbånd")

        ax2 = axes[1]
        style_ax(ax2)
        ax2.grid(axis="x", color=GRID, linewidth=0.8)
        skala = 2400 / self.raw["invested"].max()
        u = U[U["invested"] >= MIN_INVESTED]
        if self.HAR_EXIT:
            r = self.REAL[(self.REAL["invested"] >= MIN_INVESTED) & self.REAL["holdeperiode"].notna()]
            ax2.scatter(r["holdeperiode"], r["mom"], s=r["invested"] * skala, facecolor=PPIM_BEIGE,
                        edgecolor=PPIM_TAUPE_LIGHT, linewidth=0.8, zorder=2)
        for g in self.GRUPPE_ORDEN:
            m = u["gruppe"] == g
            ax2.scatter(u.loc[m, "holdeperiode"], u.loc[m, "mom"], s=u.loc[m, "invested"] * skala,
                        facecolor=self.GRUPPE_FARVE[g], edgecolor=BG, linewidth=1.0, alpha=0.88,
                        zorder=4)
        ax2.axhline(1.0, color=LINE, linestyle=(0, (4, 3)), linewidth=1.0, zorder=3)
        ax2.set_xlim(0, u["holdeperiode"].max() * 1.08)
        ax2.set_ylim(-0.2, min(float(u["mom"].max()) * 1.12, 6.0))
        ax2.yaxis.set_major_formatter(MULT)
        ax2.set_xlabel("Holdeperiode (år)")
        ax2.set_ylabel("MoM")
        if pd.notna(self.REAL_LEVETID):
            ax2.axvline(self.REAL_LEVETID, color=PPIM_TERRACOTTA, linewidth=1.4, zorder=3)
            tr = blended_transform_factory(ax2.transData, ax2.transAxes)
            ax2.text(self.REAL_LEVETID + 0.08, 0.015,
                     f"Realiseret levetid {_dk(self.REAL_LEVETID, 1)} år", transform=tr, ha="left",
                     va="bottom", fontsize=9.5, color=PPIM_TERRACOTTA, fontweight="bold", zorder=6,
                     bbox=dict(boxstyle="round,pad=0.22", fc=BG, ec="none", alpha=0.9))
        reflabel(ax2, 1.0, "1,0x")
        h = [Patch(facecolor=self.GRUPPE_FARVE[g], edgecolor="none",
                   label=f"Urealiseret · {g}" if self.HAR_GRUPPE else "Urealiseret")
             for g in self.GRUPPE_ORDEN]
        if self.HAR_EXIT:
            h.append(Line2D([0], [0], marker="o", linestyle="none", markersize=9,
                            markerfacecolor=PPIM_BEIGE, markeredgecolor=PPIM_TAUPE_LIGHT,
                            label="Realiseret (til exit)"))
        lg = ax2.legend(handles=h, frameon=False, fontsize=9, loc="upper right", labelspacing=0.5,
                        handlelength=1.2)
        for t in lg.get_texts():
            t.set_color(INK)
        _titel(ax2, "Holdeperiode mod multipel")

        gamle = A.loc["5 år og mere"]
        sub = f"Kapitalvægtet alder {_dk(self.UREAL_ALDER, 1)} år"
        if pd.notna(self.REAL_LEVETID):
            sub += f" mod en realiseret levetid på {_dk(self.REAL_LEVETID, 1)} år"
        if gamle["investeret"] > 0:
            sub += (f" · {money(gamle['investeret'], 0)} har siddet 5 år eller mere og står i "
                    f"{mult(gamle['tvpi'])}")
        # Et smalt bånd kan vise en ekstrem multipel på ganske lidt kapital - sig hvem det er
        note = " · punkt- og boblestørrelse = investeret kapital"
        fyldte = A[A["investeret"] > 0]
        lille = fyldte["investeret"].idxmin()
        if fyldte.loc[lille, "investeret"] < 0.1 * fyldte["investeret"].sum() and \
                fyldte.loc[lille, "tvpi"] > 1.5 * self.pool_tvpi:
            l = U[U["aldersbaand"] == lille].nlargest(1, "fair_value").iloc[0]
            note += (f" · {lille}-båndet er kun {money(fyldte.loc[lille, 'investeret'], 0)} og "
                     f"trækkes af {l['label']} i {mult(l['mom'])}")
        self.afslut(fig, "Modenhed i den urealiserede bog", sub + f" · pr. {self.REPORT_DK}",
                    "ureal_modenhed", ax=axes[0], note=note)

    def graf_ureal_kostpris(self):
        """Hvor er der ingen værdiskabelse endnu - og hvor koncentreret er dagsværdien?"""
        if not self._kraever(len(self.UR_SELSKAB) >= 3, "urealiserede beholdninger"):
            return
        fig, axes = plt.subplots(1, 2, figsize=SLIDE, gridspec_kw={"width_ratios": [1.15, 1]})
        ax = axes[0]
        _vandret(ax)
        d = pd.concat([self.UNDER_KOSTPRIS.sort_values("mom"), self.TIL_KOSTPRIS.sort_values("mom")])
        udeladt = max(len(d) - 16, 0)
        d = d.sort_values("invested").tail(16).sort_values("mom")     # de største, hvis listen er lang
        ys = np.arange(len(d))
        moden = d["holdeperiode"] >= UR_MODEN
        ax.barh(ys, d["mom"], height=0.66, zorder=2,
                color=[PPIM_TERRACOTTA if m else PPIM_TAUPE_LIGHT for m in moden]
                if self.HAR_ALDER else PPIM_TAUPE_LIGHT)
        for y, (_, r) in zip(ys, d.iterrows()):
            alder = f" · {_dk(r['holdeperiode'], 1)} år" if pd.notna(r["holdeperiode"]) else ""
            ax.text(r["mom"] + 0.022, y, f"{mult(r['mom'])}   {money(r['invested'], 1)}{alder}",
                    va="center", ha="left", fontsize=9, color=INK, zorder=4)
        ax.axvline(1.0, color=LINE, linestyle=(0, (4, 3)), linewidth=1.0, zorder=3)
        ax.set_yticks(ys)
        ax.set_yticklabels([_kort(l) for l in d["label"]], fontsize=9)
        # Ekstra tom række i bunden, så signaturen har sin egen plads
        ax.set_ylim(-2.0, max(len(d), 6) - 0.3)
        ax.set_xlim(0, 1.55)
        ax.xaxis.set_major_formatter(MULT)
        ax.set_xlabel("MoM")
        if not len(d):
            ax.text(0.5, 0.55, "Ingen urealiseret position står\npå eller under kostpris",
                    transform=ax.transAxes, ha="center", va="center", fontsize=12, color=MUTED)
        _titel(ax, f"Positioner under og til kostpris ({_dk(UR_KOSTPRIS[0], 2)}-"
                   f"{_dk(UR_KOSTPRIS[1], 2)}x)")
        if self.HAR_ALDER and len(d):
            legend_swatches(ax, [(PPIM_TERRACOTTA, f"Holdt {UR_MODEN:.0f} år eller mere - står stille"),
                                 (PPIM_TAUPE_LIGHT, f"Holdt under {UR_MODEN:.0f} år - J-kurve")],
                            loc="lower right")

        ax2 = axes[1]
        style_ax(ax2)
        S = self.UR_SELSKAB
        top = S.head(N_TOP)
        xs = np.arange(len(top))
        ax2.bar(xs, top["fair_value"], width=0.66, color=PPIM_SAGE_LIGHT, zorder=2)
        ax2.set_xticks(xs)
        ax2.set_xticklabels([_kort(n, 26) for n in top.index], rotation=90, fontsize=8.5)
        ax2.set_xlim(-0.7, len(top) - 0.3)
        ax2.set_ylim(0, top["fair_value"].max() * 1.30)
        ax2.yaxis.set_major_formatter(self.BELOB)
        ax2.set_ylabel(f"Urealiseret dagsværdi ({self.MIO})")
        ax2b = _tvilling(ax2)
        kum_top = (S["fair_value"].cumsum() / S["fair_value"].sum()).head(N_TOP)
        ax2b.plot(xs, kum_top, color=PPIM_SAGE_DARK, linewidth=2.2, marker="o", markersize=4, zorder=5)
        ax2b.set_ylim(0, 1.06)
        ax2b.yaxis.set_major_formatter(PROC)
        ax2b.set_ylabel("Kumulativ andel (linje)", color=MUTED)
        for i, t in ((4, f"top 5\n{pct(self.UR_TOP5, 0)}"), (9, f"top 10\n{pct(self.UR_TOP10, 0)}")):
            if i < len(kum_top) - 1:
                ax2b.annotate(t, xy=(i, kum_top.iloc[i]), xytext=(6, -4), textcoords="offset points",
                              ha="left", va="top", fontsize=9.5, fontweight="bold",
                              color=PPIM_SAGE_DARK, zorder=6)
        _titel(ax2, f"Koncentration - de {len(top)} største af {len(S)} {self.cfg.enhed}")

        kap = self.TIL_KOSTPRIS["invested"].sum() + self.UNDER_KOSTPRIS["invested"].sum()
        moden_kost = self.TIL_KOSTPRIS[self.TIL_KOSTPRIS["holdeperiode"] >= UR_MODEN]
        sub = f"{money(kap, 0)} af den urealiserede kapital står på eller under kostpris"
        if self.HAR_ALDER and len(self.TIL_KOSTPRIS):
            sub += (" · modne til kostpris: " + ", ".join(_kort(l, 28) for l in moden_kost["label"][:3])
                    + (" m.fl." if len(moden_kost) > 3 else "")
                    if len(moden_kost) else " · alle positioner til kostpris er unge og dermed J-kurve")
        self.afslut(fig, "Hvor er værdiskabelsen endnu ikke sket", sub, "ureal_kostpris", ax=axes[0],
                    note=self.note_belob() + f" · kun positioner over {money(MIN_INVESTED, 0)}"
                         + (f" · de {udeladt} mindste er udeladt af listen" if udeladt else ""))
