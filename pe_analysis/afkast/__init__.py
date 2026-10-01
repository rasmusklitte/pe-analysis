"""Afkastanalysen: hvad har vores investering givet pr. periode, hvor kommer resultatet fra,
hvad koster forvaltningen, og hvad er afkastet i DKK. Investorniveau (vores andel, netto).

    af = Afkast("PSCP4")           # indlæser, bygger serierne og afstemmer
    af.graf_kvartalsafkast()       # én metode pr. slide; springer over, hvis data mangler
    af.excel(); af.deck()

Bygget op af dele, der hver dækker et afsnit af decket:
    kerne     indlæsning, periode-, kilde- og valutaserier, HAR_*-flagene og afstemning
    perioder  nøgletal, værdiskabelse pr. kvartal, rullende 12 måneder, IRR pr. horisont
    kilder    kapitalkontoen: resultatets kilder, brutto til netto, omkostninger - og
              meddelelserne: indkald efter formål, tilsagnets udnyttelse
    valuta    afkastet i DKK delt i fondens afkast og valutaeffekt
    eksport   tabeller, Excel, deckets tekst og selve decket
"""
from .eksport import Eksport
from .kerne import Kerne, har_data
from .kilder import Kilder
from .perioder import Perioder
from .valuta import Valuta


class Afkast(Perioder, Kilder, Valuta, Eksport, Kerne):
    pass
