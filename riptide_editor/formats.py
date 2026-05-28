from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import struct
from datetime import datetime
from typing import Iterable

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover
    raise SystemExit("This editor needs Pillow. Install it with: python -m pip install pillow") from exc


@dataclass
class DatEntry:
    index: int
    filename: str
    size: int
    modified: int
    offset: int
    data: bytearray

    @property
    def extension(self) -> str:
        return Path(self.filename).suffix.lower()


class RiptideDat:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.entries: list[DatEntry] = []
        self.load()

    def load(self) -> None:
        raw = self.path.read_bytes()
        if len(raw) < 2:
            raise ValueError("DAT file is too short")
        count = struct.unpack_from("<H", raw, 0)[0]
        header_size = 2 + count * 25
        if len(raw) < header_size:
            raise ValueError("DAT header is truncated")
        self.entries.clear()
        pos = 2
        for index in range(count):
            size, modified, offset = struct.unpack_from("<iii", raw, pos)
            pos += 12
            name_raw = raw[pos:pos + 13]
            pos += 13
            filename = name_raw.split(b"\0", 1)[0].decode("ascii", errors="replace")
            if offset < 0 or size < 0 or offset + size > len(raw):
                raise ValueError(f"Invalid DAT entry bounds for {filename!r}")
            self.entries.append(DatEntry(index, filename, size, modified, offset, bytearray(raw[offset:offset + size])))

    def get(self, filename: str) -> DatEntry | None:
        target = filename.lower()
        for entry in self.entries:
            if entry.filename.lower() == target:
                return entry
        return None

    def maps(self) -> list[DatEntry]:
        return sorted((e for e in self.entries if e.extension == ".m"), key=lambda e: e.filename.lower())

    def sprites(self) -> list[DatEntry]:
        return sorted((e for e in self.entries if e.extension == ".l"), key=lambda e: e.filename.lower())

    def save(self, backup: bool = True) -> Path | None:
        backup_path = None
        if backup and self.path.exists():
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = self.path.with_suffix(self.path.suffix + f".{stamp}.bak")
            shutil.copy2(self.path, backup_path)

        header_size = 2 + len(self.entries) * 25
        offset = header_size
        for entry in self.entries:
            entry.size = len(entry.data)
            entry.offset = offset
            offset += entry.size

        out = bytearray()
        out += struct.pack("<H", len(self.entries))
        for entry in self.entries:
            out += struct.pack("<iii", entry.size, entry.modified, entry.offset)
            name_bytes = entry.filename.encode("ascii", errors="replace")[:13]
            out += name_bytes + bytes(13 - len(name_bytes))
        for entry in self.entries:
            out += entry.data
        self.path.write_bytes(out)
        return backup_path


@dataclass
class MapCell:
    tile_id: int
    shootable_id: int
    entity_id: int

    @property
    def is_solid(self) -> bool:
        return self.tile_id < 256


@dataclass
class PaletteRotation:
    start: int
    end: int
    speed: int
    unknown: int


class RiptideMap:
    TILE_SIZE = 8
    TILE_COUNT = 512
    TRIGGER_COUNT = 50

    def __init__(self, entry: DatEntry):
        self.entry = entry
        self.filename = entry.filename
        self.raw = entry.data
        self.width = 0
        self.height = 0
        self.cells: list[MapCell] = []
        self.palette: list[tuple[int, int, int]] = []
        self.tile_pixels: list[bytes] = []
        self.triggers: list[int] = []
        self.palette_rotation = PaletteRotation(0, 0, 0, 0)
        self._parse()

    def _parse(self) -> None:
        data = self.raw
        if len(data) < 4 + self.TILE_COUNT * 64 + 768 + 100 + 4:
            raise ValueError(f"Map {self.filename} is too small")
        self.width = struct.unpack_from("<H", data, 0)[0]
        self.height = struct.unpack_from("<H", data, 2)[0]
        if self.width <= 0 or self.height <= 0:
            raise ValueError(f"Map {self.filename} has invalid dimensions")
        num_cells = self.width * self.height
        cell_start = 4
        tile_start = cell_start + num_cells * 4
        palette_start = len(data) - 872
        trigger_start = len(data) - 104
        rotation_start = len(data) - 4
        expected_min_tile_end = tile_start + self.TILE_COUNT * 64
        if expected_min_tile_end > palette_start:
            raise ValueError(f"Map {self.filename} layout does not fit expected Riptide map structure")

        self.cells.clear()
        pos = cell_start
        for _ in range(num_cells):
            tile_id = struct.unpack_from("<H", data, pos)[0]
            shootable_id = data[pos + 2]
            entity_id = data[pos + 3]
            self.cells.append(MapCell(tile_id, shootable_id, entity_id))
            pos += 4

        self.palette.clear()
        pos = palette_start
        for _ in range(256):
            r6, g6, b6 = data[pos], data[pos + 1], data[pos + 2]
            self.palette.append((int(r6 * 255 / 63), int(g6 * 255 / 63), int(b6 * 255 / 63)))
            pos += 3

        self.tile_pixels = [bytes(data[tile_start + i * 64: tile_start + (i + 1) * 64]) for i in range(self.TILE_COUNT)]
        self.triggers = [struct.unpack_from("<H", data, trigger_start + i * 2)[0] for i in range(self.TRIGGER_COUNT)]
        self.palette_rotation = PaletteRotation(data[rotation_start], data[rotation_start + 1], data[rotation_start + 2], data[rotation_start + 3])

    def cell_index(self, x: int, y: int) -> int:
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise IndexError(f"Cell out of bounds: {x}, {y}")
        return y * self.width + x

    def cell(self, x: int, y: int) -> MapCell:
        return self.cells[self.cell_index(x, y)]

    def set_cell(self, x: int, y: int, *, tile_id: int | None = None, shootable_id: int | None = None, entity_id: int | None = None) -> None:
        index = self.cell_index(x, y)
        cell = self.cells[index]
        if tile_id is not None:
            if not 0 <= tile_id <= 511:
                raise ValueError("tile_id must be 0..511")
            cell.tile_id = tile_id
        if shootable_id is not None:
            if not 0 <= shootable_id <= 255:
                raise ValueError("shootable_id must be 0..255")
            cell.shootable_id = shootable_id
        if entity_id is not None:
            if not 0 <= entity_id <= 255:
                raise ValueError("entity_id must be 0..255")
            cell.entity_id = entity_id
        pos = 4 + index * 4
        struct.pack_into("<HBB", self.raw, pos, cell.tile_id, cell.shootable_id, cell.entity_id)

    def tile_image(self, tile_id: int, scale: int = 1) -> Image.Image:
        if not 0 <= tile_id < self.TILE_COUNT:
            tile_id = 0
        img = Image.new("RGB", (8, 8))
        img.putdata([self.palette[p] for p in self.tile_pixels[tile_id]])
        if scale != 1:
            img = img.resize((8 * scale, 8 * scale), Image.Resampling.NEAREST)
        return img

    def render(self, scale: int = 2) -> Image.Image:
        img = Image.new("RGB", (self.width * 8, self.height * 8))
        for y in range(self.height):
            for x in range(self.width):
                img.paste(self.tile_image(self.cell(x, y).tile_id), (x * 8, y * 8))
        if scale != 1:
            img = img.resize((img.width * scale, img.height * scale), Image.Resampling.NEAREST)
        return img

    def trigger_xy(self, value: int) -> tuple[int, int]:
        # Notes say trigger values use tile-number-positioning, top-left origin.
        return value % self.width, value // self.width

    def nonzero_triggers(self) -> Iterable[tuple[int, int, int, int, int]]:
        for index, value in enumerate(self.triggers):
            if value:
                x, y = self.trigger_xy(value)
                yield index, value, x, y, value % 2
