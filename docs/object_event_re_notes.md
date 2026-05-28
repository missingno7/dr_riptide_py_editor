# Dr. Riptide object/event reverse-engineering notes

This build imports the usable hardcoded knowledge from DrRiptideDissected instead of treating the map as just raw bytes.

## Map cell layout

Each map cell is 4 bytes:

- `u16 tile_id`
- `u8 shootable_id` - barrels, switches and other shootable cell objects
- `u8 entity_id` - doors, enemies, pickups, hazards, currents, etc.

`tile_id < 256` behaves as solid; `tile_id >= 256` behaves as passable/background.

## POINTS table / triggers

Each map has a 50 word table near the end of the file. Values are tile-number positions:

- x = value % map_width
- y = value // map_width
- even values face right, odd values face left

Known entries:

- 0: player spawn
- 1: level exit
- 2: fixed key-door message position
- 3: green-key gate
- 4: secondary/left exit
- 10/11 ... 28/29: teleport input/output pairs
- 30/31, 32/33, 34/35, 36/37: message position/content pairs

The editor now draws teleport links as cyan lines and message points as amber circles.

## Object DB

`object_db.json` is intentionally external metadata. It starts from DrRiptideDissected's hardcoded sprite/function mappings, then grows as new IDs are observed in maps.

The goal is not to hide raw data. The goal is to make this a reverse-engineering IDE:

- raw IDs remain visible
- known sprite names are shown
- all occurrences across all maps can be selected/highlighted
- notes/categories can be stored outside the original DAT

## What is still suspicious / next

- Sprite offsets are approximate. The overlay centers/rises sprites over map cells, but exact in-game origin offsets probably live in the executable.
- Entity behavior is only named at the level already documented by DrRiptideDissected.
- Editing triggers is intentionally still read-only; visualizing first avoids corrupting maps.
- Full path/AI logic likely needs deeper EXE work if we want accurate behavior simulation.
