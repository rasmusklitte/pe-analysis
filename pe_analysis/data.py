"""Indlæsning fra rpt-viewene, én funktion pr. view, filtreret på fund_code.

Konventionerne står i analysis-data-guide.md. De vigtigste:
- Investorniveau (cash_flows, nav, fund_summary, capital_account) er VORES andel.
  Fondsniveau (fund_metrics, holdings, breakdown) er HELE fonden. De lægges aldrig sammen.
- Pengestrømme har LP-fortegn: betalt til fonden < 0, modtaget > 0.
- Beløb er hele enheder i fondens valuta.

Decimal og dato-objekter omsættes her til float og datetime64, så analyserne ikke skal.
"""
import pandas as pd

from .db import read_sql


def _datoer(df, *kolonner):
    for k in kolonner:
        df[k] = pd.to_datetime(df[k])
    return df


def _tal(df, *kolonner):
    for k in kolonner:
        df[k] = pd.to_numeric(df[k], errors="coerce").astype(float)
    return df


def fonde():
    """Alle fonde med forvalter og vores investorer (tom streng = kun fondsniveau)."""
    return read_sql("""
        SELECT f.fund_code, f.name AS fund_name, m.manager_code, f.strategy, f.currency,
               f.vintage_year,
               COALESCE((SELECT STRING_AGG(i.investor_code, ', ')
                         FROM fund.investment x
                         JOIN fund.investor i ON i.investor_id = x.investor_id
                         WHERE x.fund_id = f.fund_id), '') AS investorer
        FROM fund.fund f
        JOIN fund.manager m ON m.manager_id = f.manager_id
        ORDER BY f.fund_code""")


def fond(fund_code):
    """Én fonds stamdata som Series; fejler med de gyldige koder, hvis koden ikke findes."""
    alle = fonde()
    hit = alle[alle["fund_code"].str.upper() == fund_code.upper()]
    if hit.empty:
        raise KeyError(f"Ukendt fund_code '{fund_code}' - gyldige: {', '.join(alle['fund_code'])}")
    return hit.iloc[0]


def cash_flows(fund_code):
    """rpt.v_cash_flow. For DKK-fonde har viewet ingen kurs, så amount_dkk sættes til amount."""
    df = read_sql("SELECT * FROM rpt.v_cash_flow WHERE fund_code = :f "
                  "ORDER BY value_date, cash_flow_id", f=fund_code)
    _datoer(df, "value_date", "notice_date")
    _tal(df, "amount", "fx_rate", "amount_dkk")
    dkk = df["currency"] == "DKK"
    df.loc[dkk, "amount_dkk"] = df.loc[dkk, "amount"]
    df.loc[dkk, "fx_rate"] = 1.0
    return df


def nav(fund_code):
    """rpt.v_nav: vores NAV pr. opgørelsesdato, som rapporteret (nav) og revideret (restated_nav)."""
    df = read_sql("SELECT * FROM rpt.v_nav WHERE fund_code = :f ORDER BY period_end, investment_id",
                  f=fund_code)
    _datoer(df, "period_end")
    _tal(df, "nav", "restatement", "restated_nav", "commitment", "fx_rate", "nav_dkk",
         "restated_nav_dkk")
    dkk = df["currency"] == "DKK"
    df.loc[dkk, "fx_rate"] = 1.0
    df.loc[dkk, "nav_dkk"] = df.loc[dkk, "nav"]
    df.loc[dkk, "restated_nav_dkk"] = df.loc[dkk, "restated_nav"]
    return df


def fund_summary(fund_code):
    """rpt.v_fund_summary: nøgletal pr. investering på seneste NAV-dato. Bruges til afstemning."""
    df = read_sql("SELECT * FROM rpt.v_fund_summary WHERE fund_code = :f", f=fund_code)
    _datoer(df, "as_of", "first_cash_flow")
    return df


def capital_account(fund_code):
    """Kapitalkontoens linjer (fund.capital_account) med gyldighedsfiltrene fra guidens afsnit 2.

    Fortegn som de påvirker kapitalkontoen: indbetalinger +, udlodninger -, tab -.
    """
    df = read_sql("""
        SELECT f.fund_code, x.investment_id, ca.period_end, ca.basis, a.account_code,
               a.name AS account_name, a.account_group, a.in_nav_rollforward, a.sort_order,
               ca.amount, ca.currency, ca.document_id
        FROM fund.capital_account ca
        JOIN fund.document d ON d.document_id = ca.document_id AND d.status = 'APPROVED'
        JOIN fund.account a ON a.account_id = ca.account_id
        JOIN fund.investment x ON x.investment_id = ca.investment_id
        JOIN fund.fund f ON f.fund_id = x.fund_id
        WHERE ca.is_active = 1 AND f.fund_code = :f
        ORDER BY ca.period_end, ca.basis, a.sort_order""", f=fund_code)
    _datoer(df, "period_end")
    _tal(df, "amount")
    df["in_nav_rollforward"] = df["in_nav_rollforward"].astype(bool)
    return df


def fund_metrics(fund_code):
    """rpt.v_fund_metric i langt format. Hele fonden - tjek altid unit (PCT / X / CCY / COUNT)."""
    df = read_sql("SELECT * FROM rpt.v_fund_metric WHERE fund_code = :f "
                  "ORDER BY report_date, metric_code", f=fund_code)
    _datoer(df, "report_date")
    _tal(df, "value")
    return df


HOLDING_TAL = ["total_capitalization", "commitment", "invested", "distributions", "fair_value",
               "total_value", "unfunded", "gain_loss", "paid_in_pct", "dpi", "multiple", "irr_pct"]


def holdings(fund_code):
    """rpt.v_portfolio_holding: fondens beholdninger pr. rapportdato (hele fonden)."""
    df = read_sql("SELECT * FROM rpt.v_portfolio_holding WHERE fund_code = :f "
                  "ORDER BY report_date, section, name", f=fund_code)
    _datoer(df, "report_date", "trade_date", "exit_date")
    _tal(df, *HOLDING_TAL)
    return df


def breakdown(fund_code):
    """rpt.v_portfolio_breakdown: fordelinger (branche, geografi, valuta ...) pr. rapportdato."""
    df = read_sql("SELECT * FROM rpt.v_portfolio_breakdown WHERE fund_code = :f "
                  "ORDER BY report_date, dimension, share_pct DESC", f=fund_code)
    _datoer(df, "report_date")
    _tal(df, "share_pct", "amount")
    return df


def dkk_kurser(dato):
    """DKK pr. 1 enhed af hver valuta, seneste kurs på eller før dato (Nationalbanken). DKK = 1."""
    df = read_sql("""
        SELECT r.currency, r.dkk_per_1
        FROM dbo.fx_rates_nationalbanken r
        JOIN (SELECT currency, MAX(rate_date) AS d FROM dbo.fx_rates_nationalbanken
              WHERE rate_date <= :d GROUP BY currency) s
          ON s.currency = r.currency AND s.d = r.rate_date""", d=pd.Timestamp(dato).date())
    kurser = dict(zip(df["currency"], pd.to_numeric(df["dkk_per_1"]).astype(float)))
    kurser["DKK"] = 1.0
    return kurser


def portfolio_company(fund_code):
    """rpt.v_portfolio_company: selskabernes egne nøgletal pr. rapport (PSCP).

    Omsætning, EBITDA og EV er i selskabets egen valuta (kpi_currency) - brug forholdstallene,
    eller omregn før der lægges sammen. Gruppér over tid på `company`, ikke `company_name`.
    """
    df = read_sql("SELECT * FROM rpt.v_portfolio_company WHERE fund_code = :f "
                  "ORDER BY report_date, company", f=fund_code)
    _datoer(df, "report_date", "kpi_period_end")
    _tal(df, "invested_amount", "revenue", "ebitda", "enterprise_value", "ebitda_margin_pct",
         "ev_to_ebitda", "net_leverage", "net_senior_leverage", "leverage_at_investment")
    return df


def company_alias():
    """portfolio.company_alias som {alias med små bogstaver: selskabets ene navn}."""
    df = read_sql("SELECT alias_name, company_name FROM portfolio.company_alias")
    return {a.lower(): c for a, c in zip(df["alias_name"], df["company_name"])}
