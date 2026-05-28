# Dr. Riptide editor v0.3 UX notes

This build reorganizes the editor around actual Dr. Riptide concepts rather than generic raw bytes.

## Workspaces

- **BUILD**: main map canvas, current cell inspector, safe brushes for tiles/entities/shootables, quick object list, and special point list.
- **LOGIC**: human-readable level graph: spawn, exits, key gate, teleport pairs, message pairs, switch-to-door systems, and object counts.
- **ASSETS**: tile atlas, sprite atlas, and `RIPTIDE.DAT` archive browser.
- **RESEARCH**: global object database, all observed occurrences across all maps, notes, confidence and raw mappings.

## Safe modes

The toolbar separates click behavior into explicit modes:

- Inspect: default, non-destructive.
- Tiles: paints only tile IDs.
- Entities: paints only entity IDs.
- Shootables: paints only shootable IDs.
- Eyedropper: copies tile/entity/shootable from map into the current brush.
- Raw: reserved for future low-level editing.

This avoids the common old-editor problem where clicking the level accidentally places or overwrites something.

## Riptide-specific logic model

The LOGIC workspace interprets known hardcoded systems:

- `S64 -> E1`, `S128 -> E2`, `S192 -> E3` for switch/door links.
- Teleport pairs are trigger slots `10/11`, `12/13`, ..., `28/29`.
- Message pairs are `30/31`, `32/33`, `34/35`, `36/37`.
- Tile solidity is still the known rule `tile_id < 256`.

Editing triggers remains read-only in this build. The goal is to make the level understandable first, then add safer prefab editors later.
