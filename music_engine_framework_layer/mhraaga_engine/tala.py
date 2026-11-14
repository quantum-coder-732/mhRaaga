"""Talas: beat count, vibhag (sections) and a tabla bol per beat. Bol classes the browser synth knows:
dha/dhin/dhi (both drums), na/ti/tin/ta (right drum), ge/ka/kat (left drum), 'x' = khali (open, softer)."""

TALAS = {
    "teental": dict(beats=16, vibhag=[4, 4, 4, 4], sam=0, khali=[8],
                    bols="Dha Dhin Dhin Dha Dha Dhin Dhin Dha Na Tin Tin Na Ta Dhin Dhin Dha".split()),
    "keherwa": dict(beats=8, vibhag=[4, 4], sam=0, khali=[4], bols="Dha Ge Na Ti Na Ka Dhi Na".split()),
    "dadra": dict(beats=6, vibhag=[3, 3], sam=0, khali=[3], bols="Dha Dhi Na Dha Ti Na".split()),
    "rupak": dict(beats=7, vibhag=[3, 2, 2], sam=0, khali=[0], bols="Tin Tin Na Dhi Na Dhi Na".split()),
    "jhaptal": dict(beats=10, vibhag=[2, 3, 2, 3], sam=0, khali=[5], bols="Dhi Na Dhi Dhi Na Ti Na Dhi Dhi Na".split()),
    "ektal": dict(beats=12, vibhag=[2, 2, 2, 2, 2, 2], sam=0, khali=[2, 6],
                  bols="Dhin Dhin Dha Ge Ti Ra Ki Ta Tu Na Kat Ta".split()[:12]),
    "adi": dict(beats=8, vibhag=[4, 2, 2], sam=0, khali=[4], bols="Dha Dhin Dhin Dha Dha Dhin Dhin Dha".split()),
}

BOL_CLASS = {"dha": "both", "dhin": "both", "dhi": "both", "na": "right", "ti": "right", "tin": "right", "ta": "right",
             "ra": "right", "ki": "right", "tu": "right", "ge": "left", "ka": "left", "kat": "left"}


def bol_class(b: str) -> str:
    return BOL_CLASS.get(b.lower(), "right")
