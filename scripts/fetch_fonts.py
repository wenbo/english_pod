"""Download Noto Sans CJK fonts (SIL Open Font License) and cut static Regular/Bold instances.

Google ships these only as variable fonts, which reportlab renders at their default weight,
so the two weights the layout needs are instanced here once into build/fonts/.
"""
import urllib.request
from pathlib import Path

from fontTools import ttLib
from fontTools.varLib import instancer

ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "build" / "fonts"

# family -> (variable-font URL, {output filename: weight})
FAMILIES = {
    "NotoSansJP": (
        "https://github.com/google/fonts/raw/main/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf",
        {"NotoSansJP-Regular.ttf": 400, "NotoSansJP-Bold.ttf": 700},
    ),
    "NotoSansSC": (
        "https://github.com/google/fonts/raw/main/ofl/notosanssc/NotoSansSC%5Bwght%5D.ttf",
        {"NotoSansSC-Regular.ttf": 400, "NotoSansSC-Bold.ttf": 700},
    ),
}


def ensure(family="NotoSansJP"):
    """Make sure the static weights of one family exist in build/fonts/, and return the dir."""
    source, weights = FAMILIES[family]
    if all((FONT_DIR / name).exists() for name in weights):
        return FONT_DIR
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    variable = FONT_DIR / f"{family}-variable.ttf"
    if not variable.exists():
        print(f"downloading {source}")
        urllib.request.urlretrieve(source, variable)
    for name, weight in weights.items():
        font = ttLib.TTFont(variable)
        instancer.instantiateVariableFont(font, {"wght": weight}, updateFontNames=True)
        font.save(FONT_DIR / name)
        print(f"wrote {FONT_DIR / name}")
    variable.unlink()
    return FONT_DIR


if __name__ == "__main__":
    for name in FAMILIES:
        ensure(name)
