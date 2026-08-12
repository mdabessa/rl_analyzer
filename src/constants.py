import json
from pathlib import Path

# Resolve o caminho do JSON a partir deste módulo, não do diretório de trabalho
# (cwd). Isso permite importar `src.constants` de qualquer lugar (ex.: numa VPS).
_CONSTANTS_PATH = Path(__file__).resolve().parent / "constants.json"


def get_constants():
    with open(_CONSTANTS_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_constants(constants):
    with open(_CONSTANTS_PATH, "w", encoding="utf-8") as f:
        json.dump(constants, f, indent=4)


CONSTANTS = get_constants()

RANKS = CONSTANTS["ranks"]
