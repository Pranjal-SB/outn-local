"""Self-check for outn-local. Run from the repo root: .venv\\Scripts\\python.exe test_core.py"""

import importlib.util
import sys
import tempfile
from pathlib import Path

from PIL import Image

from core import hints, pokedex, recognizer


def test_tier_files_only_contain_real_class_names():
  for label, names in [('mythical', pokedex.MYTHICAL),
                       ('legendary', pokedex.LEGENDARY),
                       ('ultrabeast', pokedex.ULTRA_BEAST),
                       ('regional', pokedex.REGIONAL)]:
    unknown = sorted(names - set(pokedex.classes))
    assert not unknown, f"{label} lists names the model can never predict: {unknown}"


def test_index_lookup_round_trips():
  for name, index in pokedex.classes.items():
    assert pokedex.index_to_name[index] == name


def test_known_tiers():
  cases = {
      'mew': 'mythic',
      'deoxys-normal': 'mythic',
      'mewtwo': 'legendary',
      'giratina': 'legendary',
      'articuno galar': 'legendary',
      'ting-lu': 'legendary',
      'zygarde-10': 'legendary',
      'eternatus': 'legendary',
      'natu': 'common',
      'nihilego': 'ub',
      'meowth-galar': 'regional',
      'obstagoon': 'regional',
      'bulbasaur': 'common',
  }
  for name, expected in cases.items():
    assert name in pokedex.classes, f"{name} is not a model class"
    got = pokedex.tier_of(name)
    assert got == expected, f"{name}: expected {expected}, got {got}"


def test_every_non_common_tier_has_a_badge():
  for tier in ('mythic', 'legendary', 'ub', 'regional'):
    assert tier in pokedex.BADGES
  assert 'common' not in pokedex.BADGES


def test_headline():
  assert pokedex.headline('pikachu', 0.93) == "It's Pikachu!"
  assert pokedex.headline('pikachu', 0.60) == "It's Pikachu!"
  assert pokedex.headline('pikachu', 0.59) == "Probably Pikachu?"
  assert pokedex.headline('mr-rime', 0.9) == "It's Mr-Rime!"


def test_display_name():
  assert pokedex.display_name("farfetch'd") == "Farfetch'd"
  assert pokedex.display_name('mr-rime') == 'Mr-Rime'
  assert pokedex.display_name('articuno galar') == 'Articuno Galar'


def test_hint_solving():
  assert hints.solve('The pokémon is p\\_k\\_chu.') == ['pikachu']
  assert hints.solve('p_k_chu') == ['pikachu']
  assert hints.solve('The pokémon is \\_\\_\\_.') == \
      [n for n in hints.pokemon_list if len(n) == 3]
  assert hints.solve('') == []
  assert hints.solve('hello there') == []


def test_hint_normalisation():
  """Straight from Discord: escapes, capitals, trailing period, stray spaces."""
  assert hints.solve('  The Pokémon is P\\_K\\_chu.  ') == ['pikachu']
  assert hints.solve('P_K_CHU') == ['pikachu']


def test_hint_input_is_not_a_regex():
  assert hints.solve('(a+)+b') == []
  assert hints.solve('.*') == []


def test_top_k_softmaxes_logits():
  out = recognizer.top_k([0.0, 5.0, 1.0] + [0.0] * 1078, k=3)
  assert [name for name, _ in out][0] == pokedex.index_to_name[1]
  confs = [c for _, c in out]
  assert confs == sorted(confs, reverse=True)
  assert all(0.0 <= c <= 1.0 for c in confs)


def test_top_k_keeps_probabilities():
  probs = [0.0] * 1081
  probs[7], probs[3] = 0.7, 0.3
  out = recognizer.top_k(probs, k=2)
  assert out[0] == (pokedex.index_to_name[7], 0.7)
  assert abs(out[1][1] - 0.3) < 1e-9


def test_to_image_accepts_path_list():
  with tempfile.TemporaryDirectory() as tmp:
    png = Path(tmp) / 'spawn.png'
    Image.new('RGBA', (10, 10), (255, 0, 0, 0)).save(png)
    txt = Path(tmp) / 'notes.txt'
    txt.write_text('hi')
    assert recognizer.to_image([str(txt), str(png)]).size == (10, 10)
    assert recognizer.to_image(str(png)).size == (10, 10)
    assert recognizer.to_image([str(txt)]) is None
    assert recognizer.to_image(str(txt)) is None


def test_to_image_rejects_non_images():
  assert recognizer.to_image(None) is None
  assert recognizer.to_image(42) is None
  img = Image.new('RGB', (4, 4))
  assert recognizer.to_image(img) is img


def test_recognizer_smoke():
  if importlib.util.find_spec('tensorflow') is None:
    print("  (skipped: tensorflow not installed)")
    return
  model = recognizer.Recognizer()
  for mode in ('P', 'LA', 'RGBA'):
    out = model.predict(Image.new(mode, (120, 90)), k=3)
    assert len(out) == 3, mode
    confs = [c for _, c in out]
    assert confs == sorted(confs, reverse=True), mode
    assert all(0.0 <= c <= 1.0 for c in confs), mode
    assert all(name in pokedex.classes for name, _ in out), mode


if __name__ == '__main__':
  failures = 0
  for name, fn in sorted(globals().items()):
    if not name.startswith('test_'):
      continue
    try:
      fn()
      print(f"PASS {name}")
    except Exception as exc:  # a bad test must not abort the rest of the run
      failures += 1
      print(f"FAIL {name}: {type(exc).__name__}: {exc}")
  print(f"\n{failures} failure(s)")
  sys.exit(1 if failures else 0)
