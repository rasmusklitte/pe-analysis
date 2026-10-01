"""Udviklingen mellem rapportdatoer: seneste kvartal og år til dato.

To ting måles, og de holdes adskilt:
- Ændring i MERVÆRDI (samlet værdi minus investeret kapital), i mio. Et kapitalkald løfter
  begge sider lige meget og er ikke værdiskabelse, så samlet værdi alene duer ikke.
- PERIODEAFKAST i procent (Modified Dietz), kædet kvartal for kvartal.
Det absolutte periodeafkast er pr. konstruktion lig ændringen i merværdi; det afstemmes.

En position er (selskab, tranche). Rapporten har ingen unik rækkenøgle - samme selskab og
tranche kan stå på flere linjer (geninvesteringer, separate lots) - så de lægges sammen.
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch
from matplotlib.transforms import blended_transform_factory

from ..fondskonfig import (DIETZ_VAEGT, MAKS_RESTATERET, MIN_AFKASTBASE, MIN_MOVE,
                           MIN_RESTATEMENT, N_MOVERS)
from ..style import (PPIM_SAGE_DARK, PPIM_SAGE_LIGHT, PPIM_OLIVE, PPIM_BROWN, PPIM_TAUPE,
                     PPIM_TAUPE_LIGHT, PPIM_TERRACOTTA, SLIDE, BG, INK, MUTED, LINE, style_ax, money,
                     mult)
from .bog import _titel, _vandret
from .kerne import (F_NEG, F_NEG_LYS, F_POS, F_POS_LYS, NUM, PROC, brudt, dmoney, dpct, pct,
                    soejlelabel)

POS_KEY = ["investment", "tranche"]


class Tid:
    # ------------------------------------------------------------------ positionspanel

    def _byg_perioder(self):
        """Positionspanelet for seneste kvartal og år til dato. Kaldes fra __init__."""
        self.HAR_KVT = self.FORRIGE is not None
        if not self.HAR_KVT:
            return
        # de to perioder er ens, når forrige rapport også er årets første
        self.AAR_SOM_KVT = self.PRIMO_AAR == self.FORRIGE
        self.TO_PERIODER = not self.AAR_SOM_KVT
        snap = {"nu": self.raw, "kvt": self.prev,
                "aar": self.prev if self.AAR_SOM_KVT else self.snapshot(self.PRIMO_AAR)}
        self._snap = snap

        pos = None
        for tag, s in snap.items():
            g = s.groupby(POS_KEY)[NUM].sum().add_suffix(f"_{tag}")
            pos = g if pos is None else pos.join(g, how="outer")
        pos = pos.fillna(0.0)
        for tag in snap:
            pos[f"merv_{tag}"] = pos[f"total_value_{tag}"] - pos[f"invested_{tag}"]
            pos[f"mom_{tag}"] = pos[f"total_value_{tag}"] / pos[f"invested_{tag}"].replace(0, np.nan)
        pos["d_merv_kvt"] = pos["merv_nu"] - pos["merv_kvt"]
        pos["d_merv_ytd"] = pos["merv_nu"] - pos["merv_aar"]
        pos["d_udloddet_ytd"] = pos["proceeds_nu"] - pos["proceeds_aar"]

        # En position, der ikke fandtes ved referencedatoen, tæller som 0 der - dens ændring er
        # det, den har tjent siden indtræden. Det er ikke værdiskabelse på en eksisterende
        # position, så begge yderpunkter mærkes i stedet for at gå ubemærket ind.
        saet = {t: set(map(tuple, s[POS_KEY].values)) for t, s in snap.items()}
        pos["note"] = ["udgået" if k not in saet["nu"] else
                       ("ny position" if k not in saet["aar"] else "") for k in pos.index]
        meta = (pd.concat([s[POS_KEY + ["instrument", "gruppe", "valuta", "label"]]
                           for s in snap.values()]).drop_duplicates(POS_KEY).set_index(POS_KEY))
        self.pos = pos.join(meta)

        def delta(tag, kol):
            t0 = snap[tag][NUM].sum()
            return pd.Series({
                "Investeret\nkapital": self.tot["invested"] - t0["invested"],
                "Udlodninger": self.tot["proceeds"] - t0["proceeds"],
                "Dagsværdi": self.tot["fair_value"] - t0["fair_value"],
                "Samlet\nværdi": self.tot["total_value"] - t0["total_value"],
                "Merværdi": self.pos[kol].sum()})
        self.D_KVT, self.D_YTD = delta("kvt", "d_merv_kvt"), delta("aar", "d_merv_ytd")

        # Selskabsniveau: kun beløb summeres - MoM regnes bagefter på summerne
        kol = [f"{b}_{t}" for t in snap for b in NUM + ["merv"]] + [
            "d_merv_kvt", "d_merv_ytd", "d_udloddet_ytd"]
        self.sel_udv = self.pos.groupby(level="investment")[kol].sum()
        for tag in snap:
            self.sel_udv[f"mom_{tag}"] = (self.sel_udv[f"total_value_{tag}"]
                                          / self.sel_udv[f"invested_{tag}"].replace(0, np.nan))

        # Afstemning: positionerne skal summere til fondens egen ændring, ellers er en nøgle tabt
        for tag, k in (("kvt", "d_merv_kvt"), ("aar", "d_merv_ytd")):
            fond = (self.tot["total_value"] - self.tot["invested"]) - (
                snap[tag]["total_value"].sum() - snap[tag]["invested"].sum())
            assert abs(self.pos[k].sum() - fond) < 0.01, f"positioner summerer ikke til fonden ({tag})"

        # Kumulative tal kan ikke falde - gør de det alligevel, er tidligere rapportering korrigeret
        perioder = [self.D_KVT] + ([self.D_YTD] if self.TO_PERIODER else [])
        self.FALDNE = sorted({n for d in perioder
                              for n, k in (("investeret kapital", "Investeret\nkapital"),
                                           ("udlodninger", "Udlodninger")) if d[k] < -MIN_MOVE})
        self.AAR_NOTE = ("" if self.AAR_ER_AARSSKIFTE else
                         " · ingen årsultimo-opgørelse i databasen: år til dato er sammenfaldende "
                         "med kvartalet" if self.AAR_SOM_KVT else
                         f" · år til dato er målt fra {self.AAR_DK} (ældste rapport)")
        self._rangkol = "d_merv_ytd"
        self.udgaaede = list(self.pos.index[self.pos["note"] == "udgået"])
        self.nye = list(self.pos.index[self.pos["note"] == "ny position"])
        print(f"  Seneste kvartal {self.FORRIGE_DK} → {self.REPORT_DK}: "
              f"{dmoney(self.D_KVT['Merværdi'])} merværdi · år til dato fra {self.AAR_DK}: "
              f"{dmoney(self.D_YTD['Merværdi'])} · {len(self.pos)} positioner, "
              f"{len(self.nye)} nye, {len(self.udgaaede)} udgåede")
        # En reelt afhændet position bliver stående i rapporten med dagsværdi ~0 - forsvinder
        # nøglen helt, er det som regel et navneskift
        if self.udgaaede and not self.cfg.ustabile_navne:
            print("  udgåede (kontrollér for navneskift): "
                  + ", ".join(self.pos.loc[self.udgaaede, "label"]))
        self._byg_afkast()

    def periode_barh(self, ax, etiketter, ytd, kvt, xlabel, fs=9.0, fmt=None, formatter=None,
                     gulv=None):
        """Vandrette bjælker med to perioder oven på hinanden.

        Den brede lyse bjælke er år til dato, den smalle mørke er seneste kvartal - lagt oven
        i hinanden, fordi 18 positioner x 2 grupperede bjælker ikke kan læses på ét slide.
        Farven bærer fortegnet, tonen bærer perioden. fmt/formatter/gulv gør den
        enhedsuafhængig, så samme figur tegner både mio. og procent."""
        fmt = dmoney if fmt is None else fmt
        formatter = self.BELOB if formatter is None else formatter
        gulv = MIN_MOVE if gulv is None else gulv
        kvt = np.asarray(kvt, dtype=float)
        ys = np.arange(len(etiketter))
        vis_ytd = ytd is not None
        bred = np.asarray(ytd, dtype=float) if vis_ytd else kvt
        if vis_ytd:
            ax.barh(ys, bred, color=[F_POS_LYS if v >= 0 else F_NEG_LYS for v in bred],
                    height=0.74, zorder=2)
            ax.barh(ys, kvt, color=[F_POS if v >= 0 else F_NEG for v in kvt], height=0.34, zorder=3)
        else:
            ax.barh(ys, kvt, color=[F_POS if v >= 0 else F_NEG for v in kvt], height=0.68, zorder=2)
        spand = max(np.nanmax(np.abs(np.concatenate([bred, kvt]))) if len(bred) else 0, gulv)
        for y, v in zip(ys, bred):
            ax.text(v + np.sign(v) * spand * 0.04, y, fmt(v), va="center",
                    ha="left" if v >= 0 else "right", fontsize=fs, color=INK, zorder=4)
        ax.set_yticks(ys)
        ax.set_yticklabels([e if len(e) <= 40 else e[:38] + "…" for e in map(str, etiketter)],
                           fontsize=fs)
        ax.axvline(0, color=LINE, linewidth=1.0)
        ax.set_xlim(-spand * 1.6, spand * 1.6)
        ax.set_ylim(-0.7, len(etiketter) - 0.3)
        ax.xaxis.set_major_formatter(formatter)
        ax.set_xlabel(xlabel)

    def periode_legend(self, ax, **kw):
        """Forklarer både tone (periode) og farve (fortegn) i ét."""
        h = [Patch(facecolor=F_POS_LYS, edgecolor="none",
                   label=f"År til dato ({self.AAR_DK} → {self.REPORT_DK})"),
             Patch(facecolor=F_POS, edgecolor="none",
                   label=f"Seneste kvartal ({self.FORRIGE_DK} → {self.REPORT_DK})"),
             Patch(facecolor=F_NEG, edgecolor="none", label="Fald")]
        if not self.TO_PERIODER:
            h = h[1:]
        lg = ax.legend(handles=h, frameon=False, handlelength=1.1, handleheight=1.1,
                       borderpad=0.4, labelspacing=0.5, fontsize=9, **kw)
        for t in lg.get_texts():
            t.set_color(INK)
        return lg

    def _to_soejler(self, ax, xs, ytd, kvt, fs=8.5):
        """Lodrette søjler for de to perioder side om side (eller kun kvartalet)."""
        if self.TO_PERIODER:
            ax.bar(xs - 0.19, ytd, width=0.36, zorder=2,
                   color=[F_POS_LYS if v >= 0 else F_NEG_LYS for v in ytd])
            ax.bar(xs + 0.19, kvt, width=0.36, zorder=2,
                   color=[F_POS if v >= 0 else F_NEG for v in kvt])
            alle = pd.concat([ytd, kvt])
        else:
            ax.bar(xs, kvt, width=0.6, color=[F_POS if v >= 0 else F_NEG for v in kvt], zorder=2)
            alle = kvt
        ax.axhline(0, color=LINE, linewidth=1.0)
        lo, hi = min(alle.min(), 0), max(alle.max(), 0)
        spaend = max(hi - lo, 1e-9)
        # plads under de negative søjlers tekst, og over den højeste søjle til signaturen
        ax.set_ylim(lo - spaend * 0.14 if lo < 0 else 0, hi + spaend * 0.46)
        if self.TO_PERIODER:
            soejlelabel(ax, xs - 0.19, ytd, [dmoney(v) for v in ytd], fs=fs)
            soejlelabel(ax, xs + 0.19, kvt, [dmoney(v) for v in kvt], fs=fs)
        else:
            soejlelabel(ax, xs, kvt, [dmoney(v) for v in kvt], fs=fs + 1.5)

    # ------------------------------------------------------------------ grafer: merværdi

    def graf_kvartal(self):
        """Udvikling i seneste kvartal og år til dato: fondsniveau og største bevægelser."""
        if not self._kraever(self.HAR_PERIODE, "tidligere rapportdato at måle mod"):
            return
        kv = self.sel_udv
        movers = kv[kv[self._rangkol].abs() > MIN_MOVE].sort_values(self._rangkol)
        n = 7 if self.TO_PERIODER else 8
        vis = pd.concat([movers.head(n), movers.tail(n)])
        vis = vis[~vis.index.duplicated()].sort_values(self._rangkol)

        fig, axes = plt.subplots(1, 2, figsize=SLIDE, gridspec_kw={"width_ratios": [1, 1.2]})
        ax = axes[0]
        style_ax(ax)
        xs = np.arange(len(self.D_KVT))
        self._to_soejler(ax, xs, self.D_YTD, self.D_KVT)
        ax.set_xticks(xs)
        ax.set_xticklabels(self.D_KVT.index, fontsize=9.5)
        ax.set_xlim(-0.6, len(xs) - 0.4)
        ax.yaxis.set_major_formatter(self.BELOB)
        ax.set_ylabel(f"Ændring ({self.MIO})")
        self.periode_legend(ax, loc="upper left")
        _titel(ax, "Hele fonden")

        ax2 = axes[1]
        _vandret(ax2)
        self.periode_barh(ax2, vis.index, vis["d_merv_ytd"] if self.TO_PERIODER else None,
                          vis["d_merv_kvt"], f"Ændring i merværdi ({self.MIO})", fs=9.5)
        _titel(ax2, f"Største bevægelser pr. {self.cfg.enhed_ental}")

        restat = (" · " + " og ".join(self.FALDNE) + " er korrigeret ned af GP'en siden "
                  "referencedatoen") if self.FALDNE else ""
        sub = ("Merværdi = samlet værdi minus investeret kapital · seneste kvartal "
               f"{dmoney(self.D_KVT['Merværdi'], enhed=True)}")
        if self.TO_PERIODER:
            sub += f" · år til dato {dmoney(self.D_YTD['Merværdi'], enhed=True)}"
        self.afslut(fig, "Udvikling: seneste kvartal og år til dato"
                    if self.TO_PERIODER else "Udvikling: seneste kvartal", sub, "kvartal", ax=axes[0],
                    note=self.note_belob() + self.AAR_NOTE + restat)

    def graf_positioner(self):
        """Udvikling pr. position, og hvor i strukturen bevægelsen sidder."""
        if not self._kraever(self.HAR_PERIODE and (self.HAR_TRANCHE or self.HAR_GRUPPE),
                             "positioner under selskabsniveau eller grupper at fordele på"):
            return
        pos, rk = self.pos, self._rangkol
        p_movers = pos[pos[rk].abs() > MIN_MOVE].sort_values(rk)
        p_vis = pd.concat([p_movers.head(N_MOVERS), p_movers.tail(N_MOVERS)])
        p_vis = p_vis[~p_vis.index.duplicated()].sort_values(rk)

        fig, axes = plt.subplots(1, 2, figsize=SLIDE, gridspec_kw={"width_ratios": [1.45, 1]})
        ax = axes[0]
        _vandret(ax)
        self.periode_barh(ax, p_vis["label"], p_vis["d_merv_ytd"] if self.TO_PERIODER else None,
                          p_vis["d_merv_kvt"], f"Ændring i merværdi ({self.MIO})", fs=8.5)
        # Etiketten farves efter gruppe, så to trancher i samme selskab, der trækker hver sin
        # vej, kan kendes fra hinanden uden at læse tranchenavnet
        if self.HAR_GRUPPE:
            for t, g in zip(ax.get_yticklabels(), p_vis["gruppe"]):
                t.set_color(self.GRUPPE_FARVE.get(g, INK))
        _titel(ax, f"Største bevægelser pr. position (top/bund {N_MOVERS})")

        ax2 = axes[1]
        style_ax(ax2)
        grp = (pos.groupby("gruppe")[["d_merv_kvt", "d_merv_ytd"]].sum()
               .reindex(self.GRUPPE_ORDEN).fillna(0.0))
        xs = np.arange(len(grp))
        self._to_soejler(ax2, xs, grp["d_merv_ytd"], grp["d_merv_kvt"])
        ax2.set_xticks(xs)
        ax2.set_xticklabels([brudt(g) for g in grp.index], fontsize=9.5 if len(grp) <= 3 else 8.5)
        ax2.set_xlim(-0.6, len(grp) - 0.4)
        ax2.yaxis.set_major_formatter(self.BELOB)
        ax2.set_ylabel(f"Ændring i merværdi ({self.MIO})")
        _titel(ax2, f"Bevægelsen pr. {self.cfg.gruppe_omtale}")
        self.periode_legend(ax2, loc="upper left")

        op = int((pos[rk] > MIN_MOVE).sum())
        ned = int((pos[rk] < -MIN_MOVE).sum())
        self.afslut(fig, "Udvikling pr. position",
                    f"{len(pos)} positioner: {op} op, {ned} ned, {len(pos) - op - ned} uændret · "
                    f"{'år til dato' if self.TO_PERIODER else 'seneste kvartal'} "
                    f"{self.AAR_DK if self.TO_PERIODER else self.FORRIGE_DK} → {self.REPORT_DK}",
                    "positioner", ax=axes[0],
                    note=self.note_belob()
                         + (f" · etikettens farve er {self.cfg.gruppe_omtale}" if self.HAR_GRUPPE else "")
                         + self.AAR_NOTE
                         + (" · et navneskift mellem rapporter ses som udgået + ny"
                            if self.cfg.ustabile_navne else ""))

    # ------------------------------------------------------------------ periodeafkast

    def _byg_afkast(self):
        """Modified Dietz pr. kvartalsskift, kædet til år til dato."""
        datoer = [d for d in self.DATOER if d >= self.PRIMO_AAR]
        skift = list(zip(datoer[:-1], datoer[1:]))
        self.PERIODE_SKIFT = {"kvt": [(a, b) for a, b in skift if a >= self.FORRIGE], "ytd": skift}
        SNAP = {d: self.snapshot(d) for d in datoer}
        for d in SNAP.values():
            d["delbog"] = [self._delbog(i) for i in d["instrument"]]
        self._SNAP = SNAP

        # Kumulative tal kan ikke falde. Gør de det, er tidligere rapportering korrigeret, og
        # "indbetalingen" er ikke en pengestrøm - den forvrider Dietz-nævneren. Positionerne
        # beholdes i alle absolutte tal, men udelades af de relative.
        self.RESTATERET = set()
        for a, b in skift:
            A = SNAP[a].groupby(POS_KEY)[["invested", "proceeds"]].sum()
            B = SNAP[b].groupby(POS_KEY)[["invested", "proceeds"]].sum()
            f = A.index.intersection(B.index)
            d = B.loc[f] - A.loc[f]
            self.RESTATERET |= set(d.index[(d["invested"] < -MIN_RESTATEMENT)
                                           | (d["proceeds"] < -MIN_RESTATEMENT)])

        # Er en stor del af bogen restateret, opgør GP'en ikke investeret kapital kumulativt
        # (MIF trækker tilbagebetalt kapital fra), og så er ændringen ikke en pengestrøm.
        # Procentafkastet ville hvile på resten alene - det vises ikke.
        nu = self.raw.groupby(POS_KEY)["fair_value"].sum()
        self.RESTATERET_ANDEL = (nu.reindex(list(self.RESTATERET)).sum() / nu.sum()
                                 if self.RESTATERET else 0.0)
        self.HAR_PCT_AFKAST = self.RESTATERET_ANDEL <= MAKS_RESTATERET
        if not self.HAR_PCT_AFKAST:
            self.advarsler.append(
                f"Investeret kapital eller udlodninger er faldet for positioner med "
                f"{pct(self.RESTATERET_ANDEL, 0)} af dagsværdien. GP'en opgør dem altså ikke "
                "kumulativt, og der beregnes derfor ikke periodeafkast i procent - kun ændring i "
                "merværdi.")

        alle = pd.concat(SNAP.values())
        meta = alle.drop_duplicates(POS_KEY).set_index(POS_KEY)[
            ["instrument", "gruppe", "valuta", "delbog", "label"]]
        self.AFK_DIM = self.UNDER if self.HAR_GRUPPE else "investment"
        self.AFKAST_POS, self.AFKAST_DIM, self.AFKAST_DELBOG, self.AFKAST_FOND = {}, {}, {}, {}
        for p, s in self.PERIODE_SKIFT.items():
            self.AFKAST_POS[p] = self._afkast(POS_KEY, s).join(meta)
            self.AFKAST_DIM[p] = self._afkast(self.AFK_DIM, s)
            self.AFKAST_DELBOG[p] = self._afkast("delbog", s)
            self.AFKAST_FOND[p] = self._afkast("_alt", s).loc["I alt"]
            # Det absolutte periodeafkast ER ændringen i merværdi. Stemmer de ikke, er
            # flow-regnestykket forkert.
            k = "d_merv_kvt" if p == "kvt" else "d_merv_ytd"
            assert abs(self.AFKAST_POS[p]["abs"].sum() - self.pos[k].sum()) < 0.01, \
                f"periodeafkast ({p}) stemmer ikke med ændringen i merværdi"
            assert abs(self.AFKAST_FOND[p]["abs"] - self.AFKAST_POS[p]["abs"].sum()) < 0.01

        if self.HAR_VALUTA:
            # Én farve pr. valuta, tildelt efter kapital, så tonerne er ens på tværs af slides
            orden = self.raw.groupby("valuta")["invested"].sum().sort_values(ascending=False).index
            self.VALUTA_FARVE = dict(zip(orden, [PPIM_SAGE_DARK, PPIM_TERRACOTTA, PPIM_TAUPE,
                                                 PPIM_OLIVE, PPIM_BROWN, PPIM_SAGE_LIGHT,
                                                 PPIM_TAUPE_LIGHT]))
        f = self.AFKAST_FOND
        if self.HAR_PCT_AFKAST:
            print(f"  Periodeafkast (Modified Dietz): kvartalet {dpct(f['kvt']['r'], 2)} · år til "
                  f"dato {dpct(f['ytd']['r'], 2)} · {len(self.RESTATERET)} restaterede positioner "
                  "udeladt af de relative tal")

    def _delbog(self, instrument):
        """Delbøgerne udledes af instrumentnavnet, ikke af gruppen: preferred ligger i samme
        kapitalgruppe som almindelig equity og skal skilles derfra."""
        for navn, cfg in self.cfg.delboege.items():
            if isinstance(instrument, str) and cfg["match"] in instrument:
                return navn
        return "Øvrige"

    def _dietz(self, dim, a, b, rene):
        """Modified Dietz for ét kvartalsskift.

        invested og proceeds er kumulative, så indbetalinger = Δinvested og udbetalinger =
        Δproceeds. Absolut afkast = (V1 − V0) + udbetalinger − indbetalinger, hvilket er præcis
        ændringen i merværdi. Nævneren er kapitalen i arbejde: dagsværdien ved periodens start
        plus de indbetalinger, der kom til undervejs, vægtet med DIETZ_VAEGT."""
        kol = ["fair_value", "invested", "proceeds"]
        ram = []
        for d in (a, b):
            f = self._SNAP[d]
            if rene and self.RESTATERET:
                f = f[~pd.MultiIndex.from_frame(f[POS_KEY]).isin(self.RESTATERET)]
            ram.append(f.assign(_alt="I alt"))
        A, B = [f.groupby(dim, dropna=False)[kol].sum() for f in ram]
        j = A.join(B, how="outer", rsuffix="_b").fillna(0.0)
        ud = pd.DataFrame(index=j.index)
        ud["V0"], ud["V1"] = j["fair_value"], j["fair_value_b"]
        ud["indbet"] = j["invested_b"] - j["invested"]
        ud["udbet"] = j["proceeds_b"] - j["proceeds"]
        ud["abs"] = (ud["V1"] - ud["V0"]) + ud["udbet"] - ud["indbet"]
        ud["base"] = ud["V0"] + DIETZ_VAEGT * ud["indbet"]
        ud["r"] = ud["abs"] / ud["base"].where(ud["base"] > MIN_AFKASTBASE)
        return ud

    def _kaedet(self, dim, skift, rene):
        """Kæder kvartalsafkastene: ∏(1+r) − 1. Store flows midt i året ville vægtes forkert i
        én lang Dietz-periode. Absolutte tal summeres."""
        dele = [self._dietz(dim, a, b, rene) for a, b in skift]
        idx = dele[0].index
        for d in dele[1:]:
            idx = idx.union(d.index)
        ud = pd.DataFrame(index=idx)
        ud["V0"] = dele[0]["V0"].reindex(idx).fillna(0.0)
        ud["V1"] = dele[-1]["V1"].reindex(idx).fillna(0.0)
        for k in ("indbet", "udbet", "abs"):
            ud[k] = sum(d[k].reindex(idx).fillna(0.0) for d in dele)
        ud["base"] = dele[0]["base"].reindex(idx)
        f = None
        for d in dele:
            led = 1 + d["r"].reindex(idx)
            f = led if f is None else f * led
        ud["r"] = f - 1
        return ud

    def _afkast(self, dim, skift):
        """Absolutte tal på hele bogen, relative tal kun på de ikke-restaterede positioner."""
        fuld = self._kaedet(dim, skift, rene=False)
        ren = self._kaedet(dim, skift, rene=True).reindex(fuld.index)
        ud = fuld.copy()
        ud["restateret"] = (fuld["base"] - ren["base"].fillna(0.0)).abs() > MIN_RESTATEMENT
        for k in ("r", "base"):
            ud[k] = ren[k]
        if not self.HAR_PCT_AFKAST:
            ud["r"] = np.nan
        return ud

    def _fondslinje(self, ax, r, tekst, farve):
        ax.axvline(r, color=farve, linewidth=1.4, zorder=5)
        tr = blended_transform_factory(ax.transData, ax.transAxes)
        ax.text(r, 0.012, f"  {tekst} {dpct(r, 2)}", transform=tr, ha="left", va="bottom",
                fontsize=9.5, color=farve, fontweight="bold", zorder=6,
                bbox=dict(boxstyle="round,pad=0.22", fc=BG, ec="none", alpha=0.9))

    def graf_periodeafkast(self):
        """Afkast pr. instrumenttype/gruppe - i mio. og i procent.

        De to paneler svarer på hver sit spørgsmål. Beløb fortæller, hvor resultatet blev
        skabt; procent fortæller, hvor godt kapitalen arbejdede."""
        if not self._kraever(self.HAR_PERIODE and self.HAR_PCT_AFKAST,
                             "kumulativt opgjort kapital at beregne periodeafkast på"):
            return
        y, k = self.AFKAST_DIM["ytd"], self.AFKAST_DIM["kvt"]
        ordn = y.sort_values("abs")
        if len(ordn) > 2 * N_MOVERS:          # pr. beholdning: kun de største i hver ende
            ordn = pd.concat([ordn.head(N_MOVERS), ordn.tail(N_MOVERS)])
        navn = (self.UNDER_NAVN if self.HAR_GRUPPE else self.cfg.enhed_ental).lower()

        fig, axes = plt.subplots(1, 2, figsize=SLIDE)
        ax = axes[0]
        _vandret(ax)
        self.periode_barh(ax, ordn.index, ordn["abs"] if self.TO_PERIODER else None,
                          k["abs"].reindex(ordn.index).fillna(0.0), f"Absolut afkast ({self.MIO})")
        _titel(ax, "Absolut afkast")

        # Kun linjer med en meningsfuld nævner - og uden restatements - får en procentsats
        ax2 = axes[1]
        _vandret(ax2)
        rel = ordn[ordn["r"].notna()].sort_values("r")
        self.periode_barh(ax2, rel.index, rel["r"] if self.TO_PERIODER else None,
                          k["r"].reindex(rel.index).fillna(0.0), "Periodeafkast (Modified Dietz)",
                          fmt=dpct, formatter=PROC, gulv=0.005)
        f = self.AFKAST_FOND["ytd" if self.TO_PERIODER else "kvt"]
        self._fondslinje(ax2, f["r"], "Fonden", PPIM_TERRACOTTA)
        _titel(ax2, "Relativt afkast")
        # sorteret stigende: øverst står de største gevinster, så øverste venstre hjørne er tomt.
        # Med kun én periode er der intet at forklare - undertitlen siger hvilken.
        if self.TO_PERIODER:
            self.periode_legend(ax, loc="upper left")

        ude = sorted(set(ordn.index) - set(rel.index))
        fk, fy = self.AFKAST_FOND["kvt"], self.AFKAST_FOND["ytd"]
        self.afslut(fig, f"Afkast pr. {navn}",
                    f"Fonden: {dmoney(fk['abs'], enhed=True)} / {dpct(fk['r'], 2)} i kvartalet"
                    + (f" · {dmoney(fy['abs'], enhed=True)} / {dpct(fy['r'], 2)} år til dato"
                       if self.TO_PERIODER else "")
                    + " · afkast = ændring i dagsværdi + udbetalinger − indbetalinger",
                    "periodeafkast", ax=axes[0],
                    note=self.note_belob() + " · Modified Dietz på kapitalen i arbejde, kædet "
                         "kvartal for kvartal"
                         + (f" · {len(ude)} uden procentsats: for lille base eller restatement"
                            if ude else ""))

    def graf_delboeger(self):
        """Ét slide pr. delbog (PSCP: PIK og Preferred), position for position."""
        if not self._kraever(self.HAR_PERIODE and self.cfg.delboege, "delbøger defineret for fonden"):
            return
        for bog in self.cfg.delboege:
            self._graf_delbog(bog)

    def _graf_delbog(self, bog):
        # PIK udbetaler stort set ingen kontanter mellem kvartalerne - renten tilskrives
        # dagsværdien - mens preferred står foran egenkapitalen, men bag gælden. Begge er
        # hybrider mellem kredit og equity, og begge måles derfor på samme måde.
        slug = self.cfg.delboege[bog]["slug"]
        per = {p: d[d["delbog"] == bog] for p, d in self.AFKAST_POS.items()}
        nu = self.raw[[self._delbog(i) == bog for i in self.raw["instrument"]]]
        if not self._kraever(len(nu) and len(per["ytd"]), f"positioner i {bog}-bogen"):
            return
        # Positioner der var afviklet før perioden begyndte, står med nul overalt og fylder
        # kun aksen op - de udelades af grafen, men bliver i tabellen og i Excel
        aktive = ((per["ytd"]["abs"].abs() > MIN_MOVE) | (per["ytd"]["V0"] > MIN_MOVE)
                  | (per["ytd"]["V1"] > MIN_MOVE))
        d = per["ytd"][aktive].sort_values("abs")
        m = nu["irr"].notna()
        irr = np.average(nu.loc[m, "irr"], weights=nu.loc[m, "invested"]) if m.any() else np.nan
        fs = 8.0 if len(d) > 16 else 9.0

        fig, axes = plt.subplots(1, 2, figsize=SLIDE)
        ax = axes[0]
        _vandret(ax)
        self.periode_barh(ax, d["label"], d["abs"] if self.TO_PERIODER else None,
                          per["kvt"]["abs"].reindex(d.index).fillna(0.0),
                          f"Absolut afkast ({self.MIO})", fs=fs)
        _titel(ax, "Absolut afkast")

        ax2 = axes[1]
        _vandret(ax2)
        rel = d[d["r"].notna()].sort_values("r")
        self.periode_barh(ax2, rel["label"], rel["r"] if self.TO_PERIODER else None,
                          per["kvt"]["r"].reindex(rel.index).fillna(0.0),
                          "Periodeafkast (Modified Dietz)", fs=fs, fmt=dpct, formatter=PROC,
                          gulv=0.005)
        g = self.AFKAST_DELBOG["ytd" if self.TO_PERIODER else "kvt"].loc[bog]
        self._fondslinje(ax2, g["r"], f"{bog} i alt", INK)
        _titel(ax2, "Relativt afkast")
        if self.HAR_VALUTA:
            for akse, ramme in ((ax, d), (ax2, rel)):
                for t, v in zip(akse.get_yticklabels(), ramme["valuta"]):
                    t.set_color(self.VALUTA_FARVE.get(v, INK))
            h = [Patch(facecolor=self.VALUTA_FARVE[v], edgecolor="none", label=v)
                 for v in d["valuta"].dropna().unique()]
            lg = ax.legend(handles=h, frameon=False, fontsize=9, loc="lower right", ncol=len(h),
                           handlelength=1.1, title="Valuta")
            lg.get_title().set_color(MUTED)
            lg.get_title().set_fontsize(9)

        gk = self.AFKAST_DELBOG["kvt"].loc[bog]
        self.afslut(fig, f"{bog}-bogen position for position",
                    f"{nu.groupby(POS_KEY).ngroups} positioner · {money(nu['invested'].sum(), 0)} "
                    f"investeret · MoM {mult(nu['total_value'].sum() / nu['invested'].sum())} · "
                    f"GP-IRR {pct(irr, 1)} · kvartalet {dmoney(gk['abs'])} / {dpct(gk['r'], 2)}"
                    + (f" · år til dato {dmoney(g['abs'])} / {dpct(g['r'], 2)}"
                       if self.TO_PERIODER else ""),
                    f"{slug}_positioner", ax=axes[0],
                    note=self.note_belob()
                         + (" · etikettens farve er tranchens valuta" if self.HAR_VALUTA else "")
                         + f" · {int((~aktive).sum())} positioner var afviklet før perioden og er "
                           "udeladt")
