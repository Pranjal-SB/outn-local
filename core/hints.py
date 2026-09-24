"""Pokétwo hint solver, ported from outn lib/hint_helper.py.

Deliberately not regex: the input is whatever the user pasted.
"""

from core.pokedex import DATA

HINT_PREFIX = 'the pokémon is '

with open(DATA / 'pokes' / 'pokemon', encoding='utf8') as f:
  pokemon_list = [line.strip() for line in f if line.strip()]


def extract_pattern(text):
  """Accept a full Pokétwo hint or a bare pattern like 'p_k_chu'.

  Pokétwo escapes blanks as '\\_' and ends the sentence with a period.
  """
  text = text.replace('\\', '').strip().lower()
  _, sep, rest = text.partition(HINT_PREFIX)
  if sep:
    text = rest
  return text.strip().rstrip('.').strip()


def solve(text):
  """Every Pokémon matching the pattern, '_' being a single wildcard char."""
  pattern = extract_pattern(text)
  if not pattern:
    return []
  return [name for name in pokemon_list
          if len(name) == len(pattern)
          and all(p == '_' or p == c for p, c in zip(pattern, name))]
