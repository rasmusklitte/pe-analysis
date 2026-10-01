"""Nøgletal på investorniveau: XIRR, kvartalsserie (indbetalt/DPI/RVPI/TVPI/IRR) og NAV-bro.

Definitionerne følger analysis-data-guide.md:
- Indbetalt = -SUM(CONTRIBUTION), udloddet = SUM(DISTRIBUTION) (brutto).
- EQUALISATION ligger uden for tilsagnet og indgår hverken i indbetalt eller udloddet.
- WITHHOLDING_TAX trækkes ikke fra DPI og indgår ikke i XIRR.
- XIRR: alle pengestrømme undtagen WITHHOLDING_TAX til og med datoen, plus NAV som sidste
  positive strøm (faktisk/365).
"""
import numpy as np
import pandas as pd

MIN_IRR_DAGE = 365   # en annualiseret IRR på under et års historik er støj og vises ikke


def xirr(stroemme):
    """stroemme: liste af (dato, beløb). Bisektion på faktisk/365. NaN uden fortegnsskifte."""
    stroemme = [(pd.Timestamp(d), float(a)) for d, a in stroemme if a]
    if not stroemme or min(a for _, a in stroemme) >= 0 or max(a for _, a in stroemme) <= 0:
        return np.nan
    t0 = min(d for d, _ in stroemme)
    f = lambda r: sum(a / (1 + r) ** ((d - t0).days / 365) for d, a in stroemme)
    lo, hi = -0.99, 10.0
    if f(lo) * f(hi) > 0:
        return np.nan
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if f(lo) * f(mid) > 0 else (lo, mid)
    return (lo + hi) / 2


def kvartalsserie(cf, nav, nav_kolonne="restated_nav"):
    """Én række pr. NAV-dato med akkumulerede tal til og med datoen.

    cf er rpt.v_cash_flow, nav er rpt.v_nav (begge for én fond). Har fonden flere af vores
    investorer, lægges de sammen pr. dato.
    """
    navs = nav.groupby("period_end").agg(
        nav=(nav_kolonne, "sum"), nav_dkk=(f"{nav_kolonne}_dkk", "sum"),
        commitment=("commitment", "sum"))
    irr_cf = cf[cf["flow_class"] != "WITHHOLDING_TAX"]
    foerste = cf["value_date"].min()

    raekker = []
    for dato, r in navs.iterrows():
        c = cf[cf["value_date"] <= dato]
        ic = irr_cf[irr_cf["value_date"] <= dato]
        bidrag = c[c["flow_class"] == "CONTRIBUTION"]
        udl = c[c["flow_class"] == "DISTRIBUTION"]
        indbetalt = -bidrag["amount"].sum()
        udloddet = udl["amount"].sum()
        gammel_nok = pd.notna(foerste) and (dato - foerste).days >= MIN_IRR_DAGE
        irr = xirr(list(zip(ic["value_date"], ic["amount"])) + [(dato, r["nav"])]) \
            if gammel_nok else np.nan
        raekker.append(dict(
            period_end=dato, commitment=r["commitment"], indbetalt=indbetalt, udloddet=udloddet,
            genindkaldelig=udl.loc[udl["is_recallable"] == 1, "amount"].sum(),
            nav=r["nav"], netto_cash=ic["amount"].sum(),
            indbetalt_dkk=-bidrag["amount_dkk"].sum(), udloddet_dkk=udl["amount_dkk"].sum(),
            nav_dkk=r["nav_dkk"], irr=irr))
    s = pd.DataFrame(raekker).set_index("period_end")
    ib = s["indbetalt"].replace(0, np.nan)
    s["dpi"] = s["udloddet"] / ib
    s["rvpi"] = s["nav"] / ib
    s["tvpi"] = s["dpi"] + s["rvpi"]
    s["resttilsagn"] = s["commitment"] - s["indbetalt"] + s["genindkaldelig"]
    s["mervaerdi"] = s["nav"] + s["udloddet"] - s["indbetalt"]
    s["nettovaerdi"] = s["netto_cash"] + s["nav"]      # J-kurven: hvad vi har fået + hvad der står
    return s


def manglende_kvartaler(datoer):
    """Kvartalsultimoer mellem første og sidste dato, som ikke findes i serien."""
    datoer = pd.DatetimeIndex(datoer)
    if len(datoer) < 2:
        return []
    alle = pd.date_range(datoer.min(), datoer.max(), freq="QE")
    return [d for d in alle if d not in datoer]


def periodeserie(serie, cf):
    """Én række pr. opgørelsesperiode: værdiskabelse og Modified Dietz-afkast.

    serie er kvartalsserie(), cf de samme pengestrømme. Værdiskabelsen er ændringen i
    nettoværdi (NAV + akkumuleret nettopengestrøm), så perioderne summerer til totalen.
    Afkastet er værdiskabelsen over primo-NAV plus periodens nettoindbetalinger, vægtet med
    den del af perioden de har været inde (faktiske valørdatoer). Første periode løber fra
    første pengestrøm med primo-NAV 0. `indeks` kæder afkastene (start = 100), og
    `afkast_12m` er indeksets ændring over præcis ét år, hvor den opgørelse findes.
    """
    stroem = cf[cf["flow_class"] != "WITHHOLDING_TAX"].groupby("value_date")["amount"].sum()
    start = cf["value_date"].min()
    raekker, t0, nav0, nv0 = [], None, 0.0, 0.0
    for dato, r in serie.iterrows():
        fra = start if t0 is None else t0
        s = stroem[(stroem.index <= dato) & ((stroem.index > t0) if t0 is not None else True)]
        dage = max((dato - fra).days, 1)
        vaegt = np.array([(dato - d).days / dage for d in s.index])
        kapital = nav0 - float((s.values * vaegt).sum())
        skabt = r["nettovaerdi"] - nv0
        raekker.append(dict(
            period_end=dato, start=fra, dage=dage, nav_primo=nav0, nav_ultimo=r["nav"],
            netto_indbetalt=-float(s.sum()), vaerdiskabelse=skabt, kapital=kapital,
            afkast=skabt / kapital if kapital > 0 else np.nan))
        t0, nav0, nv0 = dato, r["nav"], r["nettovaerdi"]
    p = pd.DataFrame(raekker).set_index("period_end")
    p["indeks"] = 100 * (1 + p["afkast"].fillna(0)).cumprod()
    p["nettovaerdi"] = p["vaerdiskabelse"].cumsum()
    idx0 = pd.concat([pd.Series({start: 100.0}), p["indeks"]])
    idx0 = idx0[~idx0.index.duplicated(keep="last")]
    nv = pd.concat([pd.Series({start: 0.0}), p["nettovaerdi"]])
    nv = nv[~nv.index.duplicated(keep="last")]
    for dato in p.index:
        foer = dato - pd.DateOffset(years=1) + pd.offsets.MonthEnd(0)
        if foer in p.index:
            p.loc[dato, "afkast_12m"] = p.loc[dato, "indeks"] / idx0[foer] - 1
            p.loc[dato, "vaerdiskabelse_12m"] = p.loc[dato, "nettovaerdi"] - nv[foer]
    if "afkast_12m" not in p:
        p["afkast_12m"], p["vaerdiskabelse_12m"] = np.nan, np.nan
    return p


def kilder_serie(ca, cf, datoer):
    """Kapitalkontoens bevægelser akkumuleret siden start, én række pr. opgørelsesdato.

    Kolonnerne er kontokoderne (CA110, CA210 ...) plus RESTAT (GP'ens efterregulering af et
    årsultimo) og HUL (resultat i perioder uden opgørelse). Pr. dato bruges opgørelsens egen
    ITD; ellers YTD lagt oven på en tidligere dato: samme års YTD-forskel, forrige årsultimo
    plus efterregulering, eller - hvis årsultimoet mangler - den seneste kendte dato, hvor
    pengestrømmene i hullet trækkes ud, så kun resultatet står i HUL. Rækkerne summerer til
    NAV som rapporteret; en efterregulering ses først i RESTAT, når GP'en ændrer årets primo
    (typisk fra Q2), og ligger i Q1 i opgørelsens egne linjer.

    Returnerer (akkumuleret DataFrame, ultimo-NAV som rapporteret pr. dato).
    """
    d = ca[(ca["account_group"] == "CAPACC") & (ca["basis"] != "POINT")]

    def hent(dato, basis):
        x = d[(d["period_end"] == dato) & (d["basis"] == basis)]
        return _bro_paa_dato(d, dato, basis) if (x["account_code"] == "CA900").any() else None

    def plus(k, kode, v):
        k[kode] = k.get(kode, 0.0) + v

    kum, ultimo = {}, {}
    for dato in sorted(pd.DatetimeIndex(datoer)):
        itd, ytd = hent(dato, "ITD"), hent(dato, "YTD")
        if itd is not None:
            primo, ult, bev = itd
            k = bev.copy()
            if abs(primo) > 0.5:
                plus(k, "HUL", primo)
        elif ytd is not None:
            primo, ult, bev = ytd
            aarsskifte = pd.Timestamp(year=dato.year - 1, month=12, day=31)
            samme = [e for e in kum if e.year == dato.year and hent(e, "YTD") is not None]
            if samme:
                e = max(samme)
                primo_e, _, bev_e = hent(e, "YTD")
                k = kum[e].add(bev, fill_value=0).sub(bev_e, fill_value=0)
                # Q1 åbner i den først rapporterede årsultimo, Q2 i den efterregulerede
                plus(k, "RESTAT", primo - primo_e)
            elif aarsskifte in kum:
                k = kum[aarsskifte].add(bev, fill_value=0)
                plus(k, "RESTAT", primo - ultimo[aarsskifte])
            else:
                e = max(kum) if kum else None
                k = kum[e].add(bev, fill_value=0) if e is not None else bev.copy()
                g = cf[(cf["value_date"] <= aarsskifte)
                       & ((cf["value_date"] > e) if e is not None else True)]
                ind = -g.loc[g["flow_class"] == "CONTRIBUTION", "amount"].sum()
                udl = -g.loc[g["flow_class"] == "DISTRIBUTION", "amount"].sum()
                plus(k, "CA110", ind)
                plus(k, "CA120", udl)
                plus(k, "HUL", primo - (ultimo[e] if e is not None else 0.0) - ind - udl)
        else:
            continue
        kum[dato], ultimo[dato] = k, ult
    if not kum:
        return pd.DataFrame(), pd.Series(dtype=float)
    df = pd.DataFrame(kum).T.fillna(0.0)
    df = df.loc[:, df.abs().max() > 0.5]
    df.index.name = "period_end"
    return df, pd.Series(ultimo)


def _bro_paa_dato(d, dato, basis):
    d = d[(d["period_end"] == dato) & (d["basis"] == basis)]
    bev = d[d["in_nav_rollforward"]].groupby("account_code")["amount"].sum()
    return (d.loc[d["account_code"] == "CA100", "amount"].sum(),
            d.loc[d["account_code"] == "CA900", "amount"].sum(), bev)


def nav_bro(ca, dato=None):
    """Kapitalkontoens bro på dato: primo-NAV + bevægelser = ultimo-NAV (CA900).

    Helst siden start: opgørelsens egen ITD, ellers YTD-opgørelserne kædet år for år (kræver
    at hvert årsskifte findes, og at første år starter i 0). Forskellen mellem et års ultimo
    og næste års primo er GP'ens efterregulering og får sin egen linje, "RESTAT". Kan der
    ikke kædes, vises kun år til dato. Returnerer None uden kapitalkontolinjer.

    'rest' er det, GP'ens linjer ikke forklarer; den skal være ~0 (afrunding).
    """
    d = ca[(ca["account_group"] == "CAPACC") & (ca["basis"] != "POINT")]
    if dato is not None:
        d = d[d["period_end"] <= pd.Timestamp(dato)]
    d = d[d["period_end"].isin(d.loc[d["account_code"] == "CA900", "period_end"])]
    if d.empty:
        return None
    dato = d["period_end"].max()
    baser = set(d.loc[d["period_end"] == dato, "basis"])

    if "ITD" in baser:
        basis = "ITD"
        primo, ultimo, bev = _bro_paa_dato(d, dato, "ITD")
    elif "YTD" in baser:
        ytd_datoer = set(d.loc[d["basis"] == "YTD", "period_end"])
        aar = [pd.Timestamp(year=y, month=12, day=31)
               for y in range(min(ytd_datoer).year, dato.year)]
        led = [_bro_paa_dato(d, x, "YTD") for x in aar + [dato]]             if all(x in ytd_datoer for x in aar) else []
        if led and abs(led[0][0]) < 0.5:
            basis = "ITD (kædet YTD)"
            primo, ultimo = 0.0, led[-1][1]
            bev = pd.concat([b for _, _, b in led]).groupby(level=0).sum()
            bev["RESTAT"] = sum(nu[0] - foer[1] for foer, nu in zip(led, led[1:]))
        else:
            basis = "YTD"
            primo, ultimo, bev = _bro_paa_dato(d, dato, "YTD")
    else:
        basis = "QTD"
        primo, ultimo, bev = _bro_paa_dato(d, dato, "QTD")

    bev = bev[bev.abs() > 0.005].rename("amount").rename_axis("account_code").reset_index()
    return dict(dato=dato, basis=basis, primo=primo, ultimo=ultimo, bevaegelser=bev,
                rest=ultimo - primo - bev["amount"].sum())
