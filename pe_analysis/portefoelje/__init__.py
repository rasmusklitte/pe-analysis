"""Porteføljeanalysen: hvor kommer fondens afkast fra, hvad koster det i risiko, og hvor
sikkert er det. Fondsniveau (hele fonden, brutto), fra rpt.v_portfolio_holding.

    pf = Portefoelje("PSCP4")      # indlæser, beriger og afstemmer
    pf.graf_vaerdibro()            # én metode pr. slide; springer over, hvis data mangler
    pf.excel(); pf.deck()

Bygget op af dele, der hver dækker et afsnit af decket:
    kerne    indlæsning, berigelse, aggregater, afstemning og HAR_*-flagene
    bog      seneste rapportdato: overblik, struktur, spredning/tab/koncentration, IRR, vintage
    tid      seneste kvartal og år til dato: merværdi og periodeafkast (Modified Dietz)
    idag     den urealiserede bog, valuta og de største positioner
    ekstra   det, databasen kan ud over det oprindelige regneark: historik, branche, selskabs-KPI
    eksport  tabeller, Excel, deckets tekst og selve decket
Det forvalterspecifikke står i pe_analysis/fondskonfig.py.
"""
from .bog import Bog
from .eksport import Eksport
from .ekstra import Ekstra
from .idag import Idag
from .kerne import Kerne, har_data
from .tid import Tid


class Portefoelje(Bog, Tid, Idag, Ekstra, Eksport, Kerne):
    def __init__(self, fund_code, as_of=None, charts="charts", exports="exports"):
        super().__init__(fund_code, as_of=as_of, charts=charts, exports=exports)
        self._byg_perioder()
        self._byg_urealiseret()
