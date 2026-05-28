# Dr. Riptide Python Level Editor

A Python/Tkinter reverse-engineering level editor for *In Search of Dr. Riptide*.

The editor reads the original `RIPTIDE.DAT` archive, renders maps with the embedded tiles and palettes, and layers known object, sprite, and trigger information on top of the raw map data. It is currently a research/editor hybrid: tile, entity, and shootable-cell editing exists, while trigger/event editing is still intentionally read-only.

## Status

This is an early reverse-engineering tool, not a finished safe WYSIWYG authoring workflow. It can write modified maps back into `RIPTIDE.DAT`, so keep backups of your game data and treat edits as experimental.

Original game files are not included in this repository.

## Requirements

- Python 3.10 or newer
- Pillow
- A local copy of `RIPTIDE.DAT` from *In Search of Dr. Riptide*

Install dependencies with:

```bash
python -m pip install -r requirements.txt
```

## Quick Start

1. Clone the repository.
2. Create a `game_data/` directory in the project root.
3. Copy your original `RIPTIDE.DAT` into `game_data/`.
4. Run the editor:

   ```bash
   python riptide_level_editor.py
   ```

On Windows, `run_editor.bat` runs the same command and leaves the console open.

Optional original files such as `RIPTIDE.EXE`, `README.TXT`, and other shareware distribution files can also live in `game_data/` for local research. The directory is ignored by Git.

## Features

### Map Editing

- Loads `game_data/RIPTIDE.DAT` automatically.
- Parses the DAT archive index.
- Lists `.M` maps.
- Renders maps from embedded 8x8 tiles and VGA palettes.
- Shows map metadata: title, password, music, and palette cycle.
- Provides a tile atlas for the current map.
- Provides a cell inspector with tile ID, solidity, shootable ID, and entity ID.
- Supports tile painting and eyedropper workflows.
- Supports direct editing of tile, shootable, and entity IDs for the selected cell.
- Saves modified maps back into `RIPTIDE.DAT` and creates timestamped backups.
- Exports the current visual map as PNG.

### Object And Event Research

- Maintains `object_db.json` as an external metadata layer for observed objects.
- Scans all maps and builds occurrence counts for entities, shootables, and triggers.
- Includes an Object Browser for kind, ID, count, category, sprite, and name.
- Highlights all current-map occurrences of the selected object.
- Can jump from an occurrence list to the matching map and cell.
- Draws known entity and shootable sprites over the map using `.L` files.
- Keeps raw labels such as `E28`, `S64`, and `T10` visible next to sprite overlays.
- Visualizes POINTS table entries and special positions.
- Draws teleport input/output pairs as cyan links.
- Marks message trigger positions.
- Shows triggers located on the selected cell.
- Imports hardcoded object and sprite mappings from DrRiptideDissected-derived research notes.

## Project Structure

```text
game_data/                  local original game files; ignored by Git
riptide_level_editor.py      Tkinter GUI entry point
riptide_editor/formats.py    DAT, .M, tile, palette, and map rendering logic
riptide_editor/game_info.py  known map/object metadata
riptide_editor/object_db.py  occurrence scanner and editable object DB layer
riptide_editor/sprites.py    .L sprite reader
object_db.json               checked-in object metadata seed
docs/                        reverse-engineering and UX notes
tools/                       helper scripts
```

## Reverse-Engineering Notes

- [Object/event notes](docs/object_event_re_notes.md)
- [UX v0.3 notes](docs/ux_v3_notes.md)

## Repository Policy

Do not commit or redistribute original game assets. The `.gitignore` excludes `game_data/`, generated PNG exports, logs, and DAT backup files.

No open-source license has been selected yet; see [LICENSE.md](LICENSE.md).
