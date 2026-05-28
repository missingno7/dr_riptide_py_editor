# GitHub first-commit checklist

Use this checklist before publishing the repository.

## Must be excluded

- `game_data/`
- `game_data.zip`
- `RIPTIDE.DAT`
- `RIPTIDE.EXE`
- Generated PNG map exports
- DAT backup files such as `RIPTIDE.DAT.20260528_120000.bak`

## Suggested local verification

```bash
python -m pip install -r requirements.txt
python -m compileall riptide_level_editor.py riptide_editor tools
python riptide_level_editor.py
```

The final launch check requires a local `game_data/RIPTIDE.DAT`.

## Initial Git commands

Because this repository may live on a drive shared by multiple Windows accounts, Git can report a dubious-ownership warning. If that happens, either run commands with a one-off safe-directory override:

```bash
git -c safe.directory=D:/Games/DOS/dr_riptide_py_editor status
```

Or mark this checkout as safe for your current Windows user:

```bash
git config --global --add safe.directory D:/Games/DOS/dr_riptide_py_editor
```

Then create the first commit:

```bash
git add .gitattributes .gitignore CONTRIBUTING.md LICENSE.md README.md requirements.txt docs object_db.json riptide_editor riptide_level_editor.py run_editor.bat tools
git status --short
git commit -m "Initial Dr. Riptide level editor"
```

Only add a remote and push after confirming the status output does not include original game files.
