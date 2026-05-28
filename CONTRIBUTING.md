# Contributing

Thanks for helping improve the Dr. Riptide Python Level Editor.

## Local setup

1. Use Python 3.10 or newer.
2. Install dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

3. Put your own copy of `RIPTIDE.DAT` in `game_data/`.
4. Run the editor:

   ```bash
   python riptide_level_editor.py
   ```

## Repository hygiene

- Do not commit files from `game_data/`.
- Do not commit generated map PNG exports or DAT backup files.
- Keep reverse-engineering notes factual and distinguish confirmed behavior from guesses.
- Prefer small, focused changes so map-format work is easy to review.

## Smoke checks

Before opening a pull request, run:

```bash
python -m compileall riptide_level_editor.py riptide_editor tools
```

If you have local game data available, also launch the editor and verify that maps load.
