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
- Special point editing is supported for named POINTS slots. Unknown trigger slots should stay research-only until their behavior is confirmed.
- Full path/AI logic likely needs deeper EXE work if we want accurate behavior simulation.

## DrRiptideDissected follow-up

DrRiptideDissected confirms that the map logic is mostly hardcoded by numeric IDs and fixed POINTS slots, not a free-form event graph.

- Shootable switches are fixed: `S64 -> E1`, `S128 -> E2`, `S192 -> E3`.
- Teleports are fixed POINTS pairs: `10/11`, `12/13`, ..., `28/29`.
- Message position/content pairs are fixed: `30/31`, `32/33`, `34/35`, `36/37`.
- Message content slots are message IDs, not map positions, so the editor should not draw `31/33/35/37` as points on the map.
- DrRiptideDissected's map view marks entities/shootables with overlays instead of drawing exact game sprites, so exact sprite origin offsets still need in-game/EXE confirmation.

The editor now treats special points as editable named slots. Select a special point, arm placement, then click the map to write that slot's position.
