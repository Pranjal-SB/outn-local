"""Image -> Pokémon name, using OutN's 64x64 Keras model."""

import os
import threading
from pathlib import Path

import numpy as np
from PIL import Image

from core import pokedex

INPUT_SIZE = (64, 64)
IMAGE_SUFFIXES = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'}


def to_image(clip):
  """Normalise whatever ImageGrab.grabclipboard() or a file dialog returns.

  Copying a file in Explorer puts a list of paths on the clipboard, not pixels.
  Returns a loaded PIL image, or None if there is nothing usable.
  """
  if isinstance(clip, Image.Image):
    return clip
  if isinstance(clip, (list, tuple)):
    clip = next((p for p in clip if Path(p).suffix.lower() in IMAGE_SUFFIXES), None)
  if not isinstance(clip, (str, Path)):
    return None
  try:
    with Image.open(clip) as img:
      img.load()
      return img.copy()
  except (OSError, Image.DecompressionBombError):  # includes UnidentifiedImageError,
    return None                                    # missing files, and huge (>178MP) images


def preprocess(image):
  # convert('RGB') flattens alpha/palette/greyscale; the model takes 3 channels.
  rgb = image.convert('RGB').resize(INPUT_SIZE)
  return np.expand_dims(np.asarray(rgb, dtype=np.float32) / 255.0, axis=0)


def top_k(scores, k):
  scores = np.asarray(scores, dtype=np.float64).ravel()
  if scores.min() < 0 or not np.isclose(scores.sum(), 1.0, atol=1e-3):
    exp = np.exp(scores - scores.max())
    scores = exp / exp.sum()
  order = np.argsort(scores)[::-1][:k]
  return [(pokedex.index_to_name[int(i)], float(scores[i])) for i in order]


class Recognizer:
  def __init__(self, model_path=pokedex.DATA / 'model.h5'):
    # 2 = filter INFO and WARNING; silences TF's absl/oneDNN/Keras launch noise.
    os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '2')
    # Imported here: tensorflow takes seconds to import and the GUI calls this
    # from a worker thread so the window can paint first.
    from tensorflow.keras.models import load_model
    self._model = load_model(str(model_path), compile=False)
    # Pastes can overlap; never run two predictions on the model at once.
    self._lock = threading.Lock()

  def predict(self, image, k=3):
    batch = preprocess(image)
    with self._lock:
      scores = self._model.predict(batch, verbose=0)[0]
    return top_k(scores, k)
