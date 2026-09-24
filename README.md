# outn-local

Desktop version of [OutN](https://github.com/Pranjal-SB/OutN). Copy a Pokétwo spawn
image, paste it in, and it tells you who's that Pokémon. No Discord bot needed.

- Ctrl+V or Open… to identify, or turn on **Watch clipboard** and just copy images
- shows how sure it is, and the next two guesses
- rare and regional spawns get a badge
- hint solver: paste the hint or type `p_k_chu`

## Run

Needs Python 3.10–3.13 (TensorFlow has no wheels for 3.14 yet).

```
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe app.py
```

The first launch takes ~15 s while the model loads.

## Self-check

```
.venv\Scripts\python.exe test_core.py
```
