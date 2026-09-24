"""Class index map and tier lookup, ported from outn lib/pokedex.py.

Tier files are exact-match sets. Substring matching is how 'eternatus' once
registered as legendary (it contains 'natu').
"""

import json
import re
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / 'data'
REGIONAL_MARKERS = ('galar', 'alola', 'hisui')
UNSURE_BELOW = 0.60

GOLD = '#E8B923'
ICE = '#9FD3E0'

# tier -> (badge text, badge colour). Common spawns get no badge.
# BMP-only symbols: Tk on Windows renders astral-plane emoji unreliably.
BADGES = {
    'mythic': ('✨ A mythical!', GOLD),
    'legendary': ('★ A legendary!', GOLD),
    'ub': ('⚡ An Ultra Beast!', GOLD),
    'regional': ('✦ A regional form!', ICE),
}


def _load_set(name):
  with open(DATA / 'pokes' / name, encoding='utf8') as f:
    return {line.strip() for line in f if line.strip()}


with open(DATA / 'classes.json', encoding='utf8') as f:
  classes = json.load(f)

index_to_name = {index: name for name, index in classes.items()}

MYTHICAL = _load_set('mythical')
LEGENDARY = _load_set('legendary')
ULTRA_BEAST = _load_set('ultrabeast')
REGIONAL = _load_set('regional')


def tier_of(name):
  """Return one of: 'mythic', 'legendary', 'ub', 'regional', 'common'."""
  if name in MYTHICAL:
    return 'mythic'
  if name in LEGENDARY:
    return 'legendary'
  if name in ULTRA_BEAST:
    return 'ub'
  if name in REGIONAL or any(m in name for m in REGIONAL_MARKERS):
    return 'regional'
  return 'common'


def display_name(name):
  # str.title() mangles apostrophes ("farfetch'd" -> "Farfetch'D"); capitalise
  # only the first letter after the start, a space, or a hyphen instead.
  return re.sub(r"(^|[\s-])(\w)", lambda m: m[1] + m[2].upper(), name)


def headline(name, confidence):
  pretty = display_name(name)
  return f"It's {pretty}!" if confidence >= UNSURE_BELOW else f"Probably {pretty}?"
