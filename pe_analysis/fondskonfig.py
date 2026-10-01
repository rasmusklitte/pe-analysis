"""Det, der er forskelligt fra forvalter til forvalter i porteføljeanalysen.

Analysen selv er drevet af, hvilke kolonner en fond har (se portefoelje/kerne.py). Her står
kun det, kolonnerne ikke siger: hvordan en GP's beholdningslinjer skal læses, og hvilken
gruppering der giver mening. `for_fond()` vælger på manager_code; en ny forvalter uden egen
indgang får standardopsætningen.
"""
import re
from dataclasses import dataclass, field

import pandas as pd

# ---------------------------------------------------------------------------- tærskler
# Beløb i mio. af fondens valuta. Samme værdier som i return-data/pscp/pscp.ipynb.
MIN_INVESTED    = 1.0    # under dette er en multipel afrundingsstøj (ude af forholdsgrafer)
MIN_LABEL       = 25.0   # kun positioner over dette navngives i scatterplots
MIN_MOVE        = 0.05   # under dette er en ændring afrundingsstøj
MIN_AFKASTBASE  = 2.0    # under dette er en procentsats afrundingsstøj
MIN_RESTATEMENT = 0.15   # beløb er rapporteret med én decimal; et fald på 0,1 er afrunding
DIETZ_VAEGT     = 0.5    # ingen datoer inde i kvartalet - indbetalinger vægtes midt i
N_TOP           = 15     # positioner i top-lister
N_MOVERS        = 9      # positioner navngivet i hver ende af bevægelsesgrafen
UR_KOSTPRIS     = (0.95, 1.05)   # bånd omkring 1,0x: her er der endnu ingen værdiskabelse
UR_MODEN        = 2.0    # år - under dette er en position til kostpris J-kurve
MAKS_GRUPPER    = 8      # flere grupper end dette er ikke en gruppering, men en liste
MAKS_RESTATERET = 0.25   # er mere end dette af dagsværdien restateret, vises ingen procentafkast

VALUTATEGN = {"EUR": "€", "USD": "$", "GBP": "£"}


@dataclass
class Konfig:
    gruppe_navn: str = "Segment"            # hvad grupperingen hedder i titler og tabeller
    gruppe_omtale: str = "segment"          # ... og i løbende tekst
    gruppe_flertal: str = "segmenter"
    titel_gruppe: str = "Afkast og risiko pr. segment"
    vintage_navn: str = "Handelsår (vintage)"          # aksetitel
    vintage_omtale: str = "handelsåret for den enkelte investering"
    under_navn: str = "Instrumenttype"      # den finere dimension under gruppen (PSCP)
    enhed: str = "selskaber"                # hvad en beholdning er, i flertal ...
    enhed_ental: str = "selskab"            # ... og ental
    sektion_struktur: str = "Struktur"      # deckets sektion 2
    gruppe_orden: list = field(default_factory=list)     # tom = efter investeret kapital
    kraev_kendt_gruppe: bool = False        # fejl, hvis en linje ikke kan placeres i en gruppe
    afviklet_ved_nul: bool = False          # ingen realiseret-markering: dagsværdi 0 = afviklet
    delboege: dict = field(default_factory=dict)   # {navn: {"match": ord i instrument, "slug": ..}}
    ustabile_navne: bool = False            # GP'en omdøber beholdninger mellem rapporter

    def rens(self, h):
        """Tilføj investment / instrument / gruppe / tranche_tekst til beholdningslinjerne."""
        h["investment"] = h["name"].str.strip()
        h["instrument"] = None
        h["tranche_tekst"] = ""
        h["gruppe"] = h["segment"].where(h["segment"].notna(), "Øvrige")
        return h


# ---------------------------------------------------------------------------- PSCP

# Instrumenttype -> kapitalgruppe. Inddelingen er analytisk og kan justeres her.
KAPITALGRUPPER = {
    "Senior/sikret gæld":      ["2L", "DD 2L", "TL", "FRN", "UniT", "ACF", "BB Tranche"],
    "PIK / junior gæld":       ["PIK", "PIK ACF", "DD PIK", "PIK-AD"],
    "Egenkapital & preferred": ["Equity", "Pref", "Jr Pref", "Sr Pref", "DD Pref"],
}
INSTR_TIL_GRUPPE = {i: g for g, lst in KAPITALGRUPPER.items() for i in lst}

# Track record-tabellen er læst som "<selskab> <instrument>", men grænsen mellem de to er sat
# efter sidste ord, så "Kroll Second" + "Lien" og "Mitratech Pref" + "Equity" forekommer.
# Linjen samles derfor igen og deles på den længste kendte instrumentbetegnelse i enden.
# Rækkefølgen er væsentlig: de lange før de korte.
_PREF = r"Pre(?:f|ferred|ffered)"
INSTRUMENT_MOENSTRE = [
    (r"PIK ACF", "PIK ACF"),
    (r"Delayed Draw PIK|DD[ -]PIK", "DD PIK"),
    (r"PIK-AD", "PIK-AD"),
    (r"PIK", "PIK"),
    (r"DD 2L", "DD 2L"),
    (r"Second Lien|2L", "2L"),
    (r"TL", "TL"), (r"FRN", "FRN"), (r"UniT", "UniT"), (r"ACF", "ACF"),
    (r"BB Tranches?(?: CLOs)?", "BB Tranche"),
    (rf"(?:Junior|Jr) {_PREF}(?: Equity)?", "Jr Pref"),
    (rf"(?:Senior|Sr) {_PREF}(?: Equity)?", "Sr Pref"),
    (rf"DD {_PREF}", "DD Pref"),
    (rf"{_PREF}(?: Equity)?(?: Add-on)?", "Pref"),
    (r"(?:Common )?Equity|Common", "Equity"),
]
_INSTR_RE = [(re.compile(rf"^(?P<navn>.*?)\s*\b(?:{m})$", re.IGNORECASE), kanon)
             for m, kanon in INSTRUMENT_MOENSTRE]
_FODNOTE = re.compile(r"(?:\(\d+\))+$")       # "Anticimex(4)(14)"
_LOT = re.compile(r"\s+\d$")                  # "Cleanova Jr Pref 2": andet lot af samme tranche

# Navne, GP'en har skiftet mellem to rapporter, og som portfolio.company_alias ikke dækker
# (aliastabellen lægges på bagefter i kerne.py, uden hensyn til store og små bogstaver)
PSCP_OMDOEBT = {"CLO": "Tymon Park", "CLO BB Tranches": "Tymon Park", "Diversitech": "DiversiTech"}


def pscp_del(navn, instrument):
    """("Mitratech Pref", "Equity") -> ("Mitratech", "Pref"). Uden kendt instrument: (navn, None)."""
    fuld = _FODNOTE.sub("", str(navn)).strip()
    if isinstance(instrument, str) and instrument.strip():
        fuld = f"{fuld} {instrument.strip()}"
    fuld = _LOT.sub("", fuld)
    for moenster, kanon in _INSTR_RE:
        m = moenster.match(fuld)
        if m and m.group("navn"):
            return m.group("navn").strip(), kanon
    return fuld, None


@dataclass
class PscpKonfig(Konfig):
    gruppe_navn: str = "Kapitalgruppe"
    gruppe_omtale: str = "kapitalgruppe"
    gruppe_flertal: str = "kapitalgrupper"
    titel_gruppe: str = "Hvad betaler kapitalstrukturen sig i"
    sektion_struktur: str = "Kapitalstruktur"
    gruppe_orden: list = field(default_factory=lambda: list(KAPITALGRUPPER))
    kraev_kendt_gruppe: bool = True
    delboege: dict = field(default_factory=lambda: {
        "PIK": {"match": "PIK", "slug": "pik"},
        "Preferred": {"match": "Pref", "slug": "pref"}})

    def rens(self, h):
        dele = [pscp_del(n, i) for n, i in zip(h["name"], h["instrument"])]
        h["investment"] = pd.Series([d[0] for d in dele], index=h.index).replace(PSCP_OMDOEBT)
        h["instrument"] = [d[1] for d in dele]
        h["tranche_tekst"] = ""
        # Før tranchedetaljen kom med i rapporten, er der én linje pr. selskab uden instrument
        h["gruppe"] = h["instrument"].map(INSTR_TIL_GRUPPE).where(h["instrument"].notna(), None)
        h.loc[h["instrument"].notna() & h["gruppe"].isna(), "gruppe"] = "Øvrige"
        return h


# ---------------------------------------------------------------------------- NEP

NEP_SEKTION = {"SECONDARY": "Sekundære", "PRIMARY": "Primære", "CO_INVESTMENT": "Co-investeringer"}


@dataclass
class NepKonfig(Konfig):
    gruppe_navn: str = "Investeringstype"
    gruppe_omtale: str = "investeringstype"
    gruppe_flertal: str = "investeringstyper"
    titel_gruppe: str = "Sekundære, primære og co-investeringer"
    # NEP's "vintage" er den underliggende fonds årgang, ikke året NEP købte ind
    vintage_navn: str = "Den underliggende fonds årgang"
    vintage_omtale: str = "den underliggende fonds årgang"
    enhed: str = "fonde"
    enhed_ental: str = "fond"
    sektion_struktur: str = "Investeringstyper"
    gruppe_orden: list = field(default_factory=lambda: list(NEP_SEKTION.values()))
    afviklet_ved_nul: bool = True
    ustabile_navne: bool = True

    def rens(self, h):
        h["investment"] = h["name"].str.strip()
        h["instrument"] = None
        # En sekundær handel ("Project X") rummer flere fonde, og samme fond kan indgå i flere
        h["tranche_tekst"] = h["transaction_ref"].fillna("")
        h["gruppe"] = h["section"].map(NEP_SEKTION).fillna("Øvrige")
        return h


# ---------------------------------------------------------------------------- Navigare (MIF)

_MIF_SELSKAB = re.compile(r"^(MIF III No\. \d+ K/S)")


@dataclass
class NavigareKonfig(Konfig):
    gruppe_omtale: str = "skibstype"
    gruppe_navn: str = "Skibstype"
    gruppe_flertal: str = "skibstyper"
    titel_gruppe: str = "Afkast og risiko pr. skibstype"
    enhed: str = "beholdninger"
    enhed_ental: str = "beholdning"

    def rens(self, h):
        # Skibsselskaberne skifter tilnavn mellem rapporter ("No. 1 K/S tbn Norwind Maestro*
        # Offshore wind" -> "No. 1 K/S Maestro"). Selskabsnummeret er nøglen; det nyeste navn vises.
        noegle = h["name"].str.strip().str.extract(_MIF_SELSKAB)[0].fillna(h["name"].str.strip())
        nyeste = h.assign(noegle=noegle).sort_values("report_date").groupby("noegle")["name"].last()
        h["investment"] = noegle.map(nyeste).str.strip()
        h["instrument"] = None
        h["tranche_tekst"] = ""
        # typen følger selskabet, også i de rapporter, hvor den ikke står på linjen
        seg = h.assign(noegle=noegle).dropna(subset=["segment"]).groupby("noegle")["segment"].last()
        h["gruppe"] = noegle.map(seg).fillna("Øvrige")
        return h


KONFIG = {"PSCP": PscpKonfig, "NEP": NepKonfig, "NAVIGARE": NavigareKonfig}


def for_fond(fond):
    """fond: rækken fra data.fond(). En forvalter uden egen indgang får standardopsætningen."""
    return KONFIG.get(fond["manager_code"], Konfig)()
