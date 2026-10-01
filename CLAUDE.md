# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Overview

Analyses of the private equity funds in the `PE` database for **Petersen & Partners (PPIM)**. Each analysis is a Jupyter notebook that reads from the database, draws branded 16:9 slides with matplotlib (PNG), exports the tables behind them to Excel and assembles a PowerPoint deck on `ppim_slidemaster.pptx`.

The working pattern, house style and many chart ideas come from the sibling repo `../return-data` (`nep/nep.ipynb`, `pscp/pscp.ipynb`). When in doubt about how something should look or be structured, look there. Two differences: data comes from the database instead of Excel files, and analyses are organised **fund → analysis**.

`analysis-data-guide.md` describes the database (views, signs, units, currencies, pitfalls). Read it before writing a query.

```
pe-analysis/
├── analysis-data-guide.md      the database, as seen from an analysis repo
├── ppim_slidemaster.pptx       PPIM PowerPoint master (template for all decks)
├── pyproject.toml              package pe_analysis; install with `pip install -e .`
├── pe_analysis/                shared code
│   ├── db.py                   read-only connection (SELECT/WITH only)
│   ├── data.py                 one loader per rpt view, per fund_code
│   ├── metrics.py              xirr, kvartalsserie, nav_bro, manglende_kvartaler
│   ├── style.py                house style: palette, 16:9 helpers, render_table
│   ├── deck.py                 byg_deck: PNG slides -> pptx on the master
│   ├── analyse.py              base class Analyse: file names, slide frame, deck selection
│   ├── fondskonfig.py          what differs per manager in the portfolio analysis + thresholds
│   ├── overblik.py             the overview analysis (class Overblik) - investor level + fund level
│   ├── afkast/                 the return analysis (class Afkast) - investor level only
│   │                           kerne.py, perioder.py, kilder.py, valuta.py, eksport.py
│   └── portefoelje/            the portfolio analysis (class Portefoelje) - fund level only
│       ├── kerne.py            loading, enrichment, aggregates, reconciliation, HAR_* flags
│       ├── bog.py              latest date: overview, structure, spread/losses/concentration, IRR, vintage
│       ├── tid.py              latest quarter and YTD: merværdi and period return (Modified Dietz)
│       ├── idag.py             the unrealised book, currency, largest positions
│       ├── ekstra.py           history, industry/geography, company KPIs
│       └── eksport.py          tables, Excel, deck text, the deck, SLIDES (order)
├── scripts/
│   ├── ny_analyse.py           create funds/<fond>/<analyse>/ from a template
│   ├── koer.py                 execute an analysis' notebooks for one or all funds
│   └── byg_skabeloner.py       regenerate templates/*.ipynb (templates are kept as code)
├── templates/                  overblik.ipynb, portefoelje.ipynb, afkast.ipynb, analyse.ipynb
│                               (placeholders __FUND_CODE__, __ANALYSE__)
└── funds/
    └── <fund_code lower>/      nep5, nep6, pscp4, pscp5, mif3, atppep9, catacap3, seed4, cap3, cap4
        └── <analyse>/          overblik (all funds), portefoelje (funds with holdings values),
                                afkast (funds we are invested in)
            ├── <analyse>.ipynb
            ├── charts/         <fond>_<analyse>_*.png
            └── exports/        <fond>_<analyse>_<ddmmyyyy>.{xlsx,pptx}
```

## Environment

```powershell
pip install -e .                                  # once; makes `import pe_analysis` work from any notebook folder
python scripts/koer.py overblik                   # run the overview for every fund
python scripts/koer.py overblik NEP5 PSCP4        # or for selected funds
python scripts/koer.py portefoelje                # run the portfolio analysis for every fund that has it
python scripts/koer.py afkast                     # run the return analysis for every fund we are invested in
python scripts/ny_analyse.py PSCP4 watchlist      # new analysis folder from templates/analyse.ipynb
python scripts/ny_analyse.py alle overblik        # overview folder for funds added to the database
python scripts/ny_analyse.py alle portefoelje     # ... only for funds the analysis has data for
python scripts/byg_skabeloner.py                  # after changing a template (needs the package installed)
```

`exports/` folders are gitignored (regenerate with `koer.py`); `charts/` and the executed notebooks are not.

Database: `sql1\ppim`, database `PE`, Windows authentication, **ODBC Driver 18** with `Encrypt=no`. Override with `PE_DB_SERVER` / `PE_DB_DATABASE` / `PE_DB_DRIVER`. The repo only reads: `db.read_sql` refuses anything but `SELECT`/`WITH`. All writes to the database go through the `pefund` CLI in `../pe-external-fund-data`.

Notebooks use paths relative to their own folder (`charts/`, `exports/`), so run them from there; `scripts/koer.py` does that. There is no test suite; the checks are the reconciliation in each analysis and looking at the slides.

Chart fonts are Gill Sans MT (falls back to Segoe UI with a printed warning).

## Shared modules

### `data.py`

One function per view, filtered on `fund_code`: `fonde()`, `fond(code)`, `cash_flows`, `nav`, `fund_summary`, `capital_account`, `fund_metrics`, `holdings`, `breakdown`, `dkk_kurser(dato)`. `Decimal` becomes float and dates become `datetime64` here. For DKK funds the views have no FX rate, so `amount_dkk` / `nav_dkk` are filled with the amount itself. `capital_account` reads the base table with the `APPROVED` + `is_active = 1` filters from the guide.

**Two levels that are never added together:** investor level (`cash_flows`, `nav`, `fund_summary`, `capital_account` – our share) and fund level (`fund_metrics`, `holdings`, `breakdown` – the whole fund).

### `metrics.py`

- `xirr(stroemme)`: actual/365 bisection; NaN without a sign change.
- `kvartalsserie(cf, nav, nav_kolonne)`: one row per NAV date with cumulative `indbetalt`, `udloddet`, `nav`, `dpi`/`rvpi`/`tvpi`, `irr`, `mervaerdi`, `nettovaerdi`, `resttilsagn`. `EQUALISATION` is left out of paid-in/distributions, `WITHHOLDING_TAX` out of DPI and XIRR. IRR is NaN until `MIN_IRR_DAGE` (365) days after the first cash flow.
- `periodeserie(serie, cf)`: one row per statement period with value creation, Modified Dietz return (real value dates), chained index and 12-month figures.
- `kilder_serie(ca, cf, datoer)`: the capital account's movements cumulative since inception per statement date, per account, plus `RESTAT` and `HUL` (see the return analysis).
- `nav_bro(ca, dato)`: opening NAV + capital-account movements = closing NAV. Uses the statement's own ITD if it has one; otherwise chains the YTD statements year by year (only if every year-end exists and the first year opens at 0), with the gap between one year's closing and the next year's opening as its own line `RESTAT` (the GP's year-end restatement); otherwise YTD only. `rest` is what the GP's lines don't explain.

### `style.py` and `deck.py`

Moved from `return-data` (`ppim_style.py`, `ppim_pptx.py`) and kept close to the originals so fixes can be carried across. Changes: `style.VALUTA` drives `money()` (`€12,3m`, `$12,3m`, otherwise `12,3 mio. DKK`) and `style.KILDE` the source line. `FUND`, `REPORT_DK`, `VALUTA`, `KILDE` are **module attributes** set by the notebook/analysis after loading, because `add_header()` / `source_line()` read them without parameters.

Slides are whole 16:9 pictures (kicker, title, subtitle, rule, source line, signature all drawn by matplotlib; `save()` deliberately without `bbox_inches="tight"`), and `byg_deck` places them edge to edge. It adds cover, agenda with up to three key figures, one divider per section, text slides and the closing slide. The agenda layout has **seven rows**: more than seven sections raises. Keep the cover title on one line.

`rcParams["text.parse_math"]` is off: two `$` in one string ("$1,2m ... $3,4m") are amounts, not a formula.

### `analyse.py`

`class Analyse(fund_code, analyse)`: the part every analysis shares. Fund master data, `charts/` and `exports/` with the `<fond>_<analyse>` prefix (old PNGs of the analysis are deleted at start, so skipped slides don't linger), `_figur`/`_gem` (slide frame), `_kraever` (print why and skip), `_slides` (the PNGs that exist, incl. a table's `_side1`, `_side2` …), axis helpers. An analysis is a subclass with **one method per slide**; each method checks its own data needs.

## The overview analysis (`overblik`)

`pe_analysis/overblik.py`, class `Overblik(fund_code, as_of=None, nav_kolonne="restated_nav")`. The notebook in `funds/<fond>/overblik/` only picks the fund and calls one method per slide, so the logic exists once. Changing a chart means editing `overblik.py` and re-running `scripts/koer.py overblik`; changing the notebook's cells means editing `scripts/byg_skabeloner.py` (existing notebooks are never overwritten by `ny_analyse.py`).

Flags `HAR_LP` (we have investor-level data) and `HAR_FOND` (fund reports exist). A method whose data is missing prints why and returns; the deck is built from the PNGs that exist. The constructor deletes the analysis' old PNGs first so skipped slides don't linger.

| Method | Slide |
|---|---|
| `graf_noegletal` | key-figure cards: tilsagn, indbetalt, udloddet, NAV, TVPI, IRR, merværdi, resttilsagn |
| `graf_kapitalforloeb` | cumulative paid-in and distributions (daily steps) against NAV |
| `graf_pengestroemme` | calls and distributions per quarter, net as a dot |
| `graf_tvpi` | TVPI per NAV date split into DPI + RVPI |
| `graf_jkurve` | cumulative net cash flow and net value (net cash + NAV) |
| `graf_irr` | our XIRR over time against the GP's reported net IRR; early extremes are clipped and noted |
| `graf_nav_bro` | waterfall from the capital account (since inception where possible) |
| `graf_fond_noegletal` | whole fund: the first four of `FOND_METRICS` that reach the latest report |
| `graf_fond_beholdninger` | whole fund: largest holdings and concentration (fair value; commitment if the GP gives no fair value, as ATP) |
| `tabel_noegletal`, `tabel_kvartaler`, `tabel_pengestroemme` | tables, auto-paginated |
| `excel`, `deck` | Excel with every table plus `Afstemning`; deck with computed Hovedpunkter and Metode/forbehold |

Things the code handles on purpose:

- **Reconciliation before charts.** Paid-in, distributions and unfunded are asserted against `rpt.v_fund_summary`. Our cash flows are also compared with the GP's own cumulative contributions/distributions in the capital account. If the net differs by more than 1 %, notices are probably missing in the database and a warning becomes the first bullet under Metode og forbehold (today: SEED4, where draw downs 14 and 16 are missing, so paid-in is understated and TVPI/IRR overstated). If only the gross differs, the GP nets recallable distributions (MIF3) and the bullet says so.
- **NAV column.** `restated_nav` by default (audited year-ends); the reconciliation against `v_fund_summary` uses cash flows only, so it holds for both.
- **Cash flows after the latest NAV date are ignored**, like `v_fund_summary`.
- **IRR under one year is not shown** (card says "under ét års historik").
- **Gaps in the NAV series** (CATACAP3, SEED4) are detected and listed in the forbehold bullets.
- **Fund-level metrics differ per GP.** `FOND_METRICS` is a priority list with units; add a metric there rather than special-casing a fund. Check `unit` (PICC is PCT for some GPs and X for MIF3).
- **Several of our investors in one fund** are summed per date. That is only right if they report on the same dates; today every fund has one investor.

## The portfolio analysis (`portefoelje`)

`pe_analysis/portefoelje/`, class `Portefoelje(fund_code, as_of=None)`. Where does the fund's return come from, what does it cost in risk, and how safe is it. It is the investment-committee deck from `return-data/pscp/pscp.ipynb` (Del 2) rebuilt on `rpt.v_portfolio_holding`, minus the two "margin over base rate" slides (hand-typed fixings), plus what the database adds. **Fund level only**: the whole fund, gross of fees and carry. Amounts are converted to mio. of the fund currency at load.

Runs for PSCP4, PSCP5, NEP5, NEP6, CAP3, CAP4, MIF3. ATPPEP9, CATACAP3 and SEED4 have no per-holding values (`portefoelje.har_data()` is False).

**Capability-driven, not fund-driven.** `kerne._flag()` sets `HAR_GRUPPE`, `HAR_INSTRUMENT`, `HAR_IRR`, `HAR_REAL`, `HAR_EXIT`, `HAR_VINTAGE`, `HAR_VALUTA`, `HAR_ALDER`, `HAR_PERIODE` from the latest report's columns, and every slide method asks them. PSCP gets all slides; NEP has no IRR, exit dates or deal currency; Capidea has no grouping (its `segment` is unique per company); MIF has no realised book.

What a manager needs beyond its columns is in `fondskonfig.py` (`KONFIG` by `manager_code`):
- **PSCP**: `KAPITALGRUPPER` (instrument → Senior/sikret gæld · PIK / junior gæld · Egenkapital & preferred); a **normaliser** for name/instrument, because the track-record table is split after the last word (`"Kroll Second"` + `"Lien"`, `"Mitratech Pref"` + `"Equity"`): the line is re-joined and split on the longest known instrument term (`INSTRUMENT_MOENSTRE`, long before short); renames (`PSCP_OMDOEBT`, plus `portfolio.company_alias` applied case-insensitively); sub-books `DELBOGE` (PIK, Preferred) matched on the instrument name. An unknown instrument raises.
- **NEP**: group = `section` (Sekundære / Primære / Co-investeringer); position = fund + `transaction_ref`; no realised flag, so fair value 0 with distributions counts as realised; `vintage` is the *underlying fund's* vintage; names are unstable between reports (`ustabile_navne`), which shows as one exit plus one new position in mover charts.
- **Navigare (MIF)**: ship companies are keyed on `MIF III No. N K/S`, since the rest of the name changes between reports.
- Thresholds (`MIN_INVESTED`, `MIN_MOVE`, `MIN_RESTATEMENT`, `DIETZ_VAEGT`, `UR_KOSTPRIS`, `UR_MODEN`, `MAKS_RESTATERET` …) are at the top of the file.

`eksport.SLIDES` is the one list of slide methods in deck order; `koer_alt()` and the notebook template both follow it. Seven deck sections: overblik og værdibro · struktur · afkastspredning, tab og koncentration · afkast mod tid · vintage og realiseringstakt · porteføljen i dag · nøgletal i tabelform. Konklusion / Metode / Forbehold are computed.

Things the code handles on purpose:

- **Total value is computed as distributions + fair value.** The GP's own column is rounded separately (up to 0,1 per line) and kept as `total_value_gp` only for a check; using it breaks the identity below.
- **Reconciliation before charts**: every dimension sums to the snapshot totals; positions sum to the fund's own change; the absolute period return equals the change in merværdi. All asserted.
- **Development is measured on merværdi** (total value − invested), never on total value: a capital call lifts both sides and is not value creation. A position absent at the reference date counts as 0 there and is labelled "ny position" / "udgået".
- **Period return is Modified Dietz**, chain-linked quarter by quarter from the latest year-end (`PRIMO_AAR`; the oldest report if there is no year-end). **Restatements** (a cumulative figure that falls by more than `MIN_RESTATEMENT`) stay in every absolute sum but are left out of relative returns. If restated positions hold more than `MAKS_RESTATERET` of fair value, the GP isn't reporting invested capital cumulatively (MIF deducts returned capital) and no percentage return is shown at all.
- **"Er markene levende"** measures the change in fair value **net of flows** (Δfair value − Δinvested + Δdistributions) since year-end; the old notebook used raw Δfair value, which reads a repayment as a write-down.
- **PSCP tranche detail starts 30.09.2024** (`DETALJE_FRA`). Earlier dates have one line per company, so instrument/currency history starts there; totals go back to the first report.
- **Labels in sentences** use `lille()` so acronyms survive ("PIK / junior gæld", "CSOV"). `dmoney()` drops the unit for currencies without a symbol ("+12,3", axis says mio. DKK) unless `enhed=True`.
- PSCP4 at 30.06.2026 reproduces the original deck: TVPI 1,40x, 48 companies / 105 lines / 86 positions, realised book 1,45x, loss rate 0,9 % (all in equity), top 5 = 38 % of gain, quarter +€38,6m (+2,07 %), YTD +€74,7m (+4,03 %). Use these as a regression check after touching the loader or the normaliser.

## The return analysis (`afkast`)

`pe_analysis/afkast/`, class `Afkast(fund_code, as_of=None, nav_kolonne="restated_nav")`. What has our investment returned per period, where does the result come from, what does the management cost, and what is the return in DKK. **Investor level only** (our cash flows, our NAV, our capital account; net). Runs for the eight funds with investor data; CAP3/CAP4 have none (`afkast.har_data()` is False).

Parts: `kerne.py` (loading, series, `HAR_*` flags, reconciliation), `perioder.py`, `kilder.py`, `valuta.py`, `eksport.py` (`SLIDES`, tables, Excel, deck text). Five deck sections: periodeafkast · afkastets kilder og omkostninger · kapitalens anvendelse · valuta · tabeller.

| Method | Slide | Needs |
|---|---|---|
| `graf_noegletal` | cards: latest quarter, 12 months, IRR, net result, gross result, costs, currency effect | – |
| `graf_kvartalsafkast` | value creation per statement period, Modified Dietz % as label | 2 statements |
| `graf_rullende` | rolling 12 months: value creation and return | more than a year |
| `graf_horisont` | IRR over 1, 3, 5 years and since inception (opening NAV as an outflow) | more than a year |
| `graf_kilder_tid`, `graf_kilder_aar` | the capital account's result lines, cumulative per date and per calendar year | `HAR_KILDER` |
| `graf_brutto_netto` | waterfall gross result → fee → expenses → financial items → carry → net | `HAR_KILDER` |
| `graf_omkostninger` | costs per year; fee in % of commitment and running costs in % of average NAV | `HAR_HONORAR` |
| `graf_formaal` | calls by purpose and distributions by type (from the notices) | `HAR_CF_SPLIT` |
| `graf_tilsagn` | commitment drawn / unfunded over time against NAV | – |
| `graf_valutabro`, `graf_valuta_tid` | DKK value = paid-in + return in fund currency + FX effect; TVPI in both currencies, rate at each call | `HAR_VALUTA` |
| `tabel_perioder`, `tabel_kilder`, `tabel_omkostninger` | tables | as the charts |

Things the code handles on purpose:

- **Value creation is the change in `nettovaerdi`** (NAV + cumulative net cash), so periods sum to the total (asserted). **Modified Dietz uses the real value dates** as weights (unlike `portefoelje`, which has no dated flows). The percentage is only shown once the capital at work exceeds `MIN_KAPITAL` (5 %) of the commitment; before that it is a large percentage of a small amount (NEP6's first period is +615 %). There is deliberately **no since-inception time-weighted index**: those early periods would dominate it.
- **`metrics.kilder_serie`** builds the capital account cumulatively per date: the statement's own ITD, else YTD on top of an earlier date. NEP opens Q1 at the year-end NAV as first reported and Q2 onwards at the restated one, so the change in opening within a year is booked as `RESTAT`. A missing year-end (CATACAP3 H2 2023) becomes `HUL`: ΔNAV minus the cash flows in the gap.
- **Restatements are folded into the line the GP books them in** (`urealiseret` if the statement has CA310, else `resultat`), because they sit inside the GP's own lines in Q1 and as a changed opening from Q2; kept separate, the category would flicker.
- **`HAR_HONORAR` requires CA210 in the latest statement.** If the GP stopped splitting the result (NEP6 from 2025-12, `SAMLET`), the whole history is shown unsplit rather than split up to a date. `CA290` means different things per GP (everything for NEP, operating costs for CataCap, investment result for ATP) and is always labelled "Resultat, ikke opdelt".
- **Costs in % p.a. need `MIN_AAR_OMK` (2) years**: the first statement often carries fees from before our entry (MIF3, ATP). % of NAV is hidden for years where average NAV is under `MIN_NAV_ANDEL` of its peak.
- **Reconciliation**: periods = net value; capital-account lines = NAV (within `BRO_TOLERANCE`); FX bridge = DKK value. The capital account's net result is compared with the merværdi of our cash flows; over 1 % of paid-in becomes the first forbehold (SEED4, missing draw downs).
- Regression: PSCP4 at 30.06.2026 – net result €6.072.056 = merværdi, gross €8,93m, fee €1,08m, expenses €0,28m, financial items €1,49m, 12-month return +8,1 %, IRR 10,7 %. NEP5 net result $29.525.608.

## Conventions

- All user-facing text (titles, labels, prints, deck text) is Danish, with Danish number format (`_dk`). Code identifiers are ASCII (`vaerdi`, `stoerst`), comments Danish.
- Positive values `PPIM_SAGE_DARK`/`PPIM_SAGE_LIGHT`, negative `PPIM_RED_MUTED`; flows that are neither gain nor loss (calls, distributions in the bridge) taupe.
- Amounts are shown in mio. of the fund currency; DKK equivalents only in tables.
- Every number in a deck's text is computed from the data, never typed.
- Slides and text that show whole-fund figures say "hele fonden".
- One slide = one PNG named `<fond>_<analyse>_<navn>.png`; a paginated table becomes `..._side1.png`, `..._side2.png`.
- New fund-specific analyses go in `funds/<fond>/<analyse>/`. Put code in `pe_analysis/` only when a second fund needs it.
