from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from collections import defaultdict
import json
from typing import Iterable

from .formats import RiptideDat, RiptideMap
from .game_info import (
    ENTITY_INFO, SHOOTABLE_INFO,
    entity_sprite_name, shootable_sprite_name,
    trigger_name, message_by_id,
)


@dataclass(frozen=True)
class ObjectOccurrence:
    kind: str
    object_id: int
    map_name: str
    x: int
    y: int
    value: int = 0
    note: str = ""


@dataclass
class ObjectRecord:
    kind: str
    object_id: int
    name: str = ""
    category: str = "unknown"
    sprite: str = ""
    info: str = ""
    notes: str = ""
    confidence: str = "hardcoded-or-observed"

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.object_id}"


def default_entity_name(entity_id: int) -> str:
    names = {
        1: "Door 1", 2: "Door 2", 3: "Door 3", 4: "Coin", 8: "Mine",
        12: "Vertical zap/hazard", 16: "Pod pair", 20: "Fish", 24: "Seaweed",
        28: "Spitting tulip", 32: "Chest", 36: "Pirana", 40: "Gem",
        44: "Water duct / current", 48: "Water duct / current", 52: "Block",
        56: "Face shooter", 60: "Sea serpent", 64: "Crab", 68: "Pulse cannon piece",
        72: "Jellyfish", 76: "Shark", 80: "Bonus", 84: "Tentacle hole",
        88: "Up spikes", 92: "Statue", 96: "Fire pit", 100: "Rocket shutter",
        104: "Clam", 108: "Cannon", 112: "Face shooter", 116: "Bomb ship",
    }
    return names.get(entity_id, f"Unknown entity {entity_id}")


def default_shootable_name(shootable_id: int) -> str:
    if 1 <= shootable_id <= 9:
        return f"Pickup barrel {shootable_id}"
    if shootable_id == 16:
        return "Coin barrel"
    if shootable_id == 32:
        return "Pod barrel"
    if shootable_id in (64, 128, 192):
        return f"Door switch {shootable_id}"
    return f"Unknown shootable {shootable_id}"


def default_category(kind: str, object_id: int) -> str:
    if kind == "trigger":
        if object_id == 0: return "spawn"
        if object_id in (1, 4): return "exit"
        if object_id in (2, 30, 32, 34, 36): return "message-position"
        if object_id in (31, 33, 35, 37): return "message-content"
        if 10 <= object_id <= 29: return "teleport"
        if object_id == 3: return "key-gate"
        return "unknown-trigger"
    if kind == "shootable":
        if object_id in (64, 128, 192): return "switch"
        if object_id in (1,2,3,4,5,6,7,8,9,16,32): return "container"
    if kind == "entity":
        if object_id in (1,2,3): return "door"
        if object_id in (4,40,68,80): return "pickup"
        if object_id in (44,48): return "current"
        if object_id in (8,12,88,96): return "hazard"
        if object_id in (20,28,36,56,60,64,72,76,84,100,104,108,112,116): return "enemy-or-active"
        if object_id in (24,52,92): return "level-object"
    return "unknown"


def default_record(kind: str, object_id: int, even_pos: bool = True, value: int = 0) -> ObjectRecord:
    if kind == "entity":
        sprite = entity_sprite_name(object_id, even_pos)
        name = default_entity_name(object_id)
        info = ENTITY_INFO.get(object_id, "")
    elif kind == "shootable":
        sprite = shootable_sprite_name(object_id, even_pos)
        name = default_shootable_name(object_id)
        info = SHOOTABLE_INFO.get(object_id, "")
    else:
        sprite = ""
        name = trigger_name(object_id, value)
        info = message_by_id(value) if object_id in (31, 33, 35, 37) else ""
    return ObjectRecord(kind, object_id, name=name, category=default_category(kind, object_id), sprite=sprite or "", info=info)


class ObjectDatabase:
    """External knowledge layer over raw numeric Riptide map IDs."""

    def __init__(self, json_path: Path):
        self.json_path = Path(json_path)
        self.records: dict[str, ObjectRecord] = {}
        self.load()

    def load(self) -> None:
        self.records.clear()
        if not self.json_path.exists():
            return
        data = json.loads(self.json_path.read_text(encoding="utf-8"))
        for item in data.get("records", []):
            rec = ObjectRecord(**item)
            self.records[rec.key] = rec

    def save(self) -> None:
        self.json_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"records": [asdict(v) for v in sorted(self.records.values(), key=lambda r: (r.kind, r.object_id))]}
        self.json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def get(self, kind: str, object_id: int, *, even_pos: bool = True, value: int = 0) -> ObjectRecord:
        key = f"{kind}:{object_id}"
        if key not in self.records:
            self.records[key] = default_record(kind, object_id, even_pos=even_pos, value=value)
        return self.records[key]

    def set_notes(self, kind: str, object_id: int, notes: str) -> None:
        rec = self.get(kind, object_id)
        rec.notes = notes
        self.save()


def scan_map(entry) -> list[ObjectOccurrence]:
    rmap = RiptideMap(entry)
    out: list[ObjectOccurrence] = []
    for y in range(rmap.height):
        for x in range(rmap.width):
            cell = rmap.cell(x, y)
            if cell.shootable_id:
                out.append(ObjectOccurrence("shootable", cell.shootable_id, entry.filename, x, y, cell.shootable_id))
            if cell.entity_id:
                out.append(ObjectOccurrence("entity", cell.entity_id, entry.filename, x, y, cell.entity_id))
    for index, value, x, y, _even in rmap.nonzero_triggers():
        out.append(ObjectOccurrence("trigger", index, entry.filename, x, y, value, trigger_name(index, value)))
    return out


def scan_archive(dat: RiptideDat) -> list[ObjectOccurrence]:
    out: list[ObjectOccurrence] = []
    for entry in dat.maps():
        try:
            out.extend(scan_map(entry))
        except Exception:
            continue
    return out


def occurrence_counts(occurrences: Iterable[ObjectOccurrence]) -> dict[tuple[str, int], int]:
    counts: dict[tuple[str, int], int] = defaultdict(int)
    for occ in occurrences:
        counts[(occ.kind, occ.object_id)] += 1
    return counts


def occurrences_for_current_map(occurrences: Iterable[ObjectOccurrence], map_name: str, kind: str | None = None, object_id: int | None = None) -> list[ObjectOccurrence]:
    return [o for o in occurrences if o.map_name.lower() == map_name.lower() and (kind is None or o.kind == kind) and (object_id is None or o.object_id == object_id)]
