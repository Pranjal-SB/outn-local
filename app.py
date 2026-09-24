"""outn-local: paste a Pokétwo spawn, find out who's that Pokémon."""

import ctypes
import hashlib
import queue
import threading
import tkinter
import traceback
from tkinter import filedialog

import customtkinter as ctk
from PIL import ImageGrab

from core import hints, pokedex
from core.recognizer import Recognizer, to_image

PREVIEW = 300          # px, square box the spawn image is fitted into
DRAIN_MS = 50          # how often the UI checks for worker results
FLASH_MS = 1200        # how long "Copied!" stays up
WATCH_MS = 700         # clipboard poll interval while "Watch clipboard" is on
MAX_HINT_MATCHES = 20
HINT_COLUMNS = 5
ACCENT = '#EF5350'     # pokéball red
ACCENT_HOVER = '#D84340'
FILETYPES = [('Images', '*.png *.jpg *.jpeg *.webp *.gif *.bmp'), ('All files', '*.*')]


def _grab():
  """Clipboard contents, or None. Windows raises OSError while another app holds it."""
  try:
    return ImageGrab.grabclipboard()
  except OSError:
    return None


def _digest(clip):
  """Cheap identity for clipboard contents, so the same image isn't identified twice."""
  if clip is None:
    return None
  data = clip.tobytes() if hasattr(clip, 'tobytes') else repr(clip).encode()
  return hashlib.md5(data).hexdigest()


def _clipboard_seq():
  """Changes whenever anything is copied. None where the API doesn't exist."""
  try:
    return ctypes.windll.user32.GetClipboardSequenceNumber()
  except AttributeError:
    return None


class App(ctk.CTk):
  def __init__(self):
    super().__init__()
    self.title('outn-local')
    self.geometry('920x760')
    self.minsize(780, 620)

    self.results = queue.Queue()
    self._recognizer = None
    self._request = 0      # newest identification wins; older results are dropped
    self._name = None      # currently shown Pokémon, for "Copy name"
    self._last_clip = None
    self._last_seq = None
    self._poll_id = None

    self._big = ctk.CTkFont(size=34, weight='bold')
    self._medium = ctk.CTkFont(size=20, weight='bold')

    self.grid_columnconfigure((0, 1), weight=1, uniform='col')
    self.grid_rowconfigure(0, weight=1)
    self._build_image_card()
    self._build_result_card()
    self._build_hint_card()

    self.bind('<Control-v>', self._on_ctrl_v)
    self.bind('<Control-V>', self._on_ctrl_v)

    self._set_inputs(False)
    self._show_message('Waking up the Pokédex…')
    threading.Thread(target=self._load_model, daemon=True).start()
    self.after(DRAIN_MS, self._drain)

  # ---- layout -------------------------------------------------------------

  def _build_image_card(self):
    self.left = ctk.CTkFrame(self, corner_radius=18)
    self.left.grid(row=0, column=0, padx=(20, 10), pady=20, sticky='nsew')

    # Switch and buttons are packed first (from the bottom) so a short window
    # clips the preview, never the controls.
    self.watch = ctk.CTkSwitch(self.left, text='Watch clipboard', command=self._toggle_watch,
                               progress_color=ACCENT)
    self.watch.pack(side='bottom', pady=(0, 22))

    buttons = ctk.CTkFrame(self.left, fg_color='transparent')
    buttons.pack(side='bottom', pady=(0, 12))
    self.paste_btn = ctk.CTkButton(buttons, text='Paste', width=120, command=self.paste,
                                   fg_color=ACCENT, hover_color=ACCENT_HOVER)
    self.paste_btn.pack(side='left', padx=6)
    self.open_btn = ctk.CTkButton(buttons, text='Open…', width=120, command=self.open_file)
    self.open_btn.pack(side='left', padx=6)

    self.preview = ctk.CTkLabel(
        self.left, width=PREVIEW, height=PREVIEW, font=self._medium,
        text="Who's that Pokémon?\n\nCopy a spawn image\nand press Ctrl+V")
    self.preview.pack(padx=20, pady=(24, 12), expand=True)
    # Buttons/frames never take focus on click, so once the hint entry is
    # focused it stays focused all session; clicking the card takes it back.
    self.left.bind('<Button-1>', lambda _e: self.focus_set())

  def _build_result_card(self):
    right = ctk.CTkFrame(self, corner_radius=18)
    right.grid(row=0, column=1, padx=(10, 20), pady=20, sticky='nsew')

    self.headline = ctk.CTkLabel(right, text='', font=self._big, wraplength=360)
    self.headline.pack(padx=24, pady=(48, 10))

    self.badge = ctk.CTkLabel(right, text='', corner_radius=12, text_color='#1A1A1A',
                              font=ctk.CTkFont(size=15, weight='bold'))
    self.badge.pack(pady=6)

    self.bar = ctk.CTkProgressBar(right, width=300, height=14, progress_color=ACCENT)
    self.bar.pack(pady=(18, 4))
    self.confidence = ctk.CTkLabel(right, text='')
    self.confidence.pack()

    self.runners = ctk.CTkLabel(right, text='', text_color='gray60')
    self.runners.pack(pady=(12, 0))

    self.copy_btn = ctk.CTkButton(right, text='Copy name', width=160,
                                  command=lambda: self._copy(self._name, self.copy_btn))
    self.copy_btn.pack(pady=(24, 30))

  def _build_hint_card(self):
    bottom = ctk.CTkFrame(self, corner_radius=18)
    bottom.grid(row=1, column=0, columnspan=2, padx=20, pady=(0, 20), sticky='ew')
    ctk.CTkLabel(bottom, text='Hint solver', font=ctk.CTkFont(size=16, weight='bold')
                 ).pack(anchor='w', padx=20, pady=(14, 4))
    self.hint_entry = ctk.CTkEntry(bottom, placeholder_text='Paste a Pokétwo hint, or type p_k_chu')
    self.hint_entry.pack(fill='x', padx=20)
    self.hint_entry.bind('<KeyRelease>', lambda _e: self._solve_hint())
    self.hint_matches = ctk.CTkFrame(bottom, fg_color='transparent')
    self.hint_matches.pack(fill='x', padx=20, pady=(6, 14))
    # Always keep one child: an empty CTkFrame requests its default 200px height.
    self.hint_header = ctk.CTkLabel(self.hint_matches, text='', text_color='gray60', height=0)
    self.hint_header.grid(row=0, column=0, columnspan=HINT_COLUMNS, sticky='w')

  # ---- inputs -------------------------------------------------------------

  def _on_ctrl_v(self, _event):
    # Typing in an entry (the hint box): let Tk paste the text as normal, but
    # only when there's actually text to paste -- otherwise this entry keeps
    # focus all session (see _build_image_card) and would silently eat every
    # image paste too.
    if isinstance(self.focus_get(), tkinter.Entry):
      try:
        self.clipboard_get()
        return None   # text on the clipboard: let the entry paste it
      except tkinter.TclError:
        pass          # no text, so it's an image: identify it
    self.paste()
    return 'break'

  def paste(self):
    if self._recognizer is None:
      return
    image = to_image(_grab())
    if image is None:
      self._show_message('Nothing to identify. Copy an image first.')
      return
    self._identify(image)

  def open_file(self):
    if self._recognizer is None:
      return
    path = filedialog.askopenfilename(filetypes=FILETYPES)
    if not path:
      return
    image = to_image(path)
    if image is None:
      self._show_message("Couldn't read that image.")
      return
    self._identify(image)

  def _toggle_watch(self):
    if self.watch.get():
      # Only images copied from now on count; whatever is already there is old.
      self._last_clip = _digest(_grab())
      self._last_seq = _clipboard_seq()
      self._poll_id = self.after(WATCH_MS, self._poll_clipboard)
    elif self._poll_id is not None:
      self.after_cancel(self._poll_id)
      self._poll_id = None

  def _poll_clipboard(self):
    try:
      # Decoding + hashing the whole clipboard is ~90ms on a 4K screenshot; skip
      # it unless the OS says the clipboard actually changed since last poll.
      seq = _clipboard_seq()
      if seq is None or seq != self._last_seq:  # None: no seq API, always check
        self._last_seq = seq
        clip = _grab()
        digest = _digest(clip)
        if digest is not None and digest != self._last_clip:
          self._last_clip = digest
          image = to_image(clip)
          if image is not None:  # text on the clipboard is not an error while watching
            self._identify(image)
    except Exception:  # a bad clip must not silently kill the poll loop
      traceback.print_exc()
      self._show_message("Couldn't read that image.")
    finally:
      self._poll_id = self.after(WATCH_MS, self._poll_clipboard)

  def _solve_hint(self):
    for child in self.hint_matches.winfo_children():
      if child is not self.hint_header:
        child.destroy()
    text = self.hint_entry.get()
    if not text.strip():
      self.hint_header.configure(text='')
      return
    matches = hints.solve(text)
    shown = matches[:MAX_HINT_MATCHES]
    header = 'No matches' if not matches else \
        f"{len(matches)} match{'es' if len(matches) != 1 else ''}"
    if len(matches) > len(shown):
      header += f', showing {len(shown)}'
    self.hint_header.configure(text=header)
    for i, name in enumerate(shown):
      button = ctk.CTkButton(self.hint_matches, text=pokedex.display_name(name), width=150,
                             height=28, fg_color='transparent', border_width=1)
      button.configure(command=lambda n=name, b=button: self._copy(n, b))
      button.grid(row=1 + i // HINT_COLUMNS, column=i % HINT_COLUMNS, padx=4, pady=3, sticky='w')

  def _set_inputs(self, enabled):
    state = 'normal' if enabled else 'disabled'
    self.paste_btn.configure(state=state)
    self.open_btn.configure(state=state)
    self.watch.configure(state=state)

  # ---- work ---------------------------------------------------------------

  def _load_model(self):
    try:
      self.results.put(('ready', Recognizer()))
    except Exception as exc:  # anything here must reach the UI, not die with the thread
      traceback.print_exc()
      self.results.put(('load_failed', exc))

  def _identify(self, image):
    self._request += 1
    self._show_image(image)
    self._show_message('Hmm…')
    threading.Thread(target=self._predict, args=(self._request, image), daemon=True).start()

  def _predict(self, request, image):
    try:
      self.results.put(('result', request, self._recognizer.predict(image)))
    except Exception:
      traceback.print_exc()
      self.results.put(('error', request, "Couldn't read that image."))

  def _drain(self):
    try:
      while not self.results.empty():
        kind, *payload = self.results.get_nowait()
        try:
          if kind == 'ready':
            self._recognizer = payload[0]
            self._set_inputs(True)
            self._show_message('Ready! Paste a spawn.')
          elif kind == 'load_failed':
            self._show_message(f"Couldn't load the model: {payload[0]}")
          elif payload[0] == self._request:  # 'result' / 'error' for the newest request only
            if kind == 'result':
              self._show_result(payload[1])
            else:
              self._show_message(payload[1])
        except Exception:  # one bad item must not stop the rest or the reschedule
          traceback.print_exc()
    finally:
      self.after(DRAIN_MS, self._drain)

  # ---- output -------------------------------------------------------------

  def _show_image(self, image):
    w, h = image.size
    scale = min(PREVIEW / w, PREVIEW / h)
    size = (max(1, round(w * scale)), max(1, round(h * scale)))
    rgba = image.convert('RGBA')
    self._preview_image = ctk.CTkImage(light_image=rgba, dark_image=rgba, size=size)
    self.preview.configure(image=self._preview_image, text='')

  def _show_message(self, text):
    self._name = None
    self.headline.configure(text=text, font=self._medium)
    self.badge.configure(text='', fg_color='transparent')
    self.bar.set(0)
    self.confidence.configure(text='')
    self.runners.configure(text='')
    self.copy_btn.configure(state='disabled')

  def _show_result(self, results):
    (name, conf), rest = results[0], results[1:]
    self._name = name
    self.headline.configure(text=pokedex.headline(name, conf), font=self._big)
    badge = pokedex.BADGES.get(pokedex.tier_of(name))
    if badge:
      self.badge.configure(text=f'  {badge[0]}  ', fg_color=badge[1])
    else:
      self.badge.configure(text='', fg_color='transparent')
    self.bar.set(conf)
    self.confidence.configure(text=f'{conf:.0%} sure')
    self.runners.configure(
        text='  ·  '.join(f'{pokedex.display_name(n)} {c:.0%}' for n, c in rest))
    self.copy_btn.configure(state='normal')

  def _copy(self, text, button=None):
    if not text:
      return
    self.clipboard_clear()
    self.clipboard_append(text)
    if button is not None:
      label = getattr(button, 'rest_label', None) or button.cget('text')
      button.rest_label = label
      button.configure(text='Copied!')
      self.after(FLASH_MS, lambda: button.winfo_exists() and button.configure(text=label))


if __name__ == '__main__':
  ctk.set_appearance_mode('dark')
  App().mainloop()
