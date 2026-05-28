from __future__ import annotations

from pathlib import Path
from collections import Counter, defaultdict
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

try:
    from PIL import Image, ImageDraw, ImageTk
except ImportError as exc:
    raise SystemExit("This editor needs Pillow. Install it with: python -m pip install pillow") from exc

from riptide_editor.formats import RiptideDat, RiptideMap
from riptide_editor.game_info import (
    map_info,
    trigger_name,
    message_by_id,
    entity_sprite_name,
    shootable_sprite_name,
    ENTITY_INFO,
    SHOOTABLE_INFO,
)
from riptide_editor.sprites import read_sprite_frames
from riptide_editor.object_db import (
    ObjectDatabase,
    scan_archive,
    occurrence_counts,
    occurrences_for_current_map,
)

PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_GAME_DATA = PROJECT_DIR / "game_data"
DEFAULT_DAT = DEFAULT_GAME_DATA / "RIPTIDE.DAT"
OBJECT_DB_PATH = PROJECT_DIR / "object_db.json"

DOOR_SWITCH_TO_ENTITY = {64: 1, 128: 2, 192: 3}


class DrRiptideEditor(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Dr. Riptide Level Editor - v0.3 UX / Logic Workspace")
        self.geometry("1680x980")
        self.minsize(1180, 720)

        self.dat: RiptideDat | None = None
        self.current_map: RiptideMap | None = None
        self.current_entry = None
        self.object_db = ObjectDatabase(OBJECT_DB_PATH)
        self.occurrences = []
        self.highlight: tuple[str, int] | None = None
        self.selected_trigger_index: int | None = None

        self.scale_var = tk.IntVar(value=3)
        self.tool_var = tk.StringVar(value="inspect")
        self.selected_tile_var = tk.IntVar(value=0)
        self.selected_entity_var = tk.IntVar(value=0)
        self.selected_shootable_var = tk.IntVar(value=0)

        self.show_grid_var = tk.BooleanVar(value=True)
        self.show_solids_var = tk.BooleanVar(value=False)
        self.show_entities_var = tk.BooleanVar(value=True)
        self.show_sprite_overlay_var = tk.BooleanVar(value=True)
        self.show_triggers_var = tk.BooleanVar(value=True)
        self.show_event_links_var = tk.BooleanVar(value=True)
        self.show_door_links_var = tk.BooleanVar(value=True)
        self.show_highlight_only_var = tk.BooleanVar(value=False)

        self.dirty = False
        self.last_selected_cell: tuple[int, int] | None = None
        self.map_photo: ImageTk.PhotoImage | None = None
        self.tile_atlas_photo: ImageTk.PhotoImage | None = None
        self.rendered_map: Image.Image | None = None
        self.sprite_cache: dict[tuple[str, int], Image.Image] = {}
        self._sprite_sheet_refs: list[ImageTk.PhotoImage] = []

        self._build_ui()
        self._load_default_dat()

    # ---------------------------------------------------------------------
    # UI
    # ---------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        top = ttk.Frame(self, padding=(8, 6))
        top.grid(row=0, column=0, sticky="ew")
        ttk.Button(top, text="Open game_data / RIPTIDE.DAT", command=self.open_dat).pack(side="left")
        ttk.Button(top, text="Save", command=self.save_dat).pack(side="left", padx=(6, 0))
        ttk.Button(top, text="Validate level", command=self.validate_current_level).pack(side="left", padx=(6, 0))
        ttk.Button(top, text="Export PNG", command=self.export_png).pack(side="left", padx=(6, 16))
        ttk.Label(top, text="Mode:").pack(side="left")
        for text, value in [
            ("Inspect", "inspect"), ("Tiles", "paint_tile"), ("Entities", "paint_entity"),
            ("Shootables", "paint_shootable"), ("Eyedropper", "pick"), ("Raw", "raw"),
        ]:
            ttk.Radiobutton(top, text=text, variable=self.tool_var, value=value).pack(side="left", padx=(4, 0))
        ttk.Label(top, text="Zoom").pack(side="left", padx=(18, 4))
        ttk.Spinbox(top, from_=1, to=8, textvariable=self.scale_var, width=4, command=self.refresh_map).pack(side="left")

        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.grid(row=1, column=0, sticky="nsew")

        left = ttk.Frame(paned, padding=6)
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)
        paned.add(left, weight=0)

        ttk.Label(left, text="Levels", font=("TkDefaultFont", 10, "bold")).grid(row=0, column=0, sticky="w")
        self.map_list = tk.Listbox(left, width=30, exportselection=False)
        self.map_list.grid(row=1, column=0, sticky="nsew", pady=(4, 8))
        self.map_list.bind("<<ListboxSelect>>", self._on_map_select)
        self.map_info_label = ttk.Label(left, text="No map loaded", justify="left", wraplength=260)
        self.map_info_label.grid(row=2, column=0, sticky="ew")

        layer_box = ttk.LabelFrame(left, text="Layers", padding=6)
        layer_box.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        for text, var in [
            ("Game-like object sprites", self.show_sprite_overlay_var),
            ("Object labels E/S", self.show_entities_var),
            ("Special / trigger markers", self.show_triggers_var),
            ("Teleport + message links", self.show_event_links_var),
            ("Switch → door links", self.show_door_links_var),
            ("Solid mask", self.show_solids_var),
            ("Grid", self.show_grid_var),
            ("Only highlighted object", self.show_highlight_only_var),
        ]:
            ttk.Checkbutton(layer_box, text=text, variable=var, command=self.refresh_map).pack(anchor="w")
        ttk.Button(layer_box, text="Clear highlight", command=self.clear_highlight).pack(fill="x", pady=(8, 0))

        main = ttk.Notebook(paned)
        paned.add(main, weight=1)
        self.workspace = main

        self._build_build_workspace(main)
        self._build_logic_workspace(main)
        self._build_assets_workspace(main)
        self._build_research_workspace(main)

        status = ttk.Frame(self, padding=(8, 3))
        status.grid(row=2, column=0, sticky="ew")
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(status, textvariable=self.status_var).pack(anchor="w")

    def _build_build_workspace(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=6)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        notebook.add(tab, text="BUILD")

        split = ttk.PanedWindow(tab, orient="horizontal")
        split.grid(row=0, column=0, sticky="nsew")

        map_frame = ttk.Frame(split)
        map_frame.columnconfigure(0, weight=1)
        map_frame.rowconfigure(0, weight=1)
        split.add(map_frame, weight=1)
        self.map_canvas = tk.Canvas(map_frame, background="#202020")
        xbar = ttk.Scrollbar(map_frame, orient="horizontal", command=self.map_canvas.xview)
        ybar = ttk.Scrollbar(map_frame, orient="vertical", command=self.map_canvas.yview)
        self.map_canvas.configure(xscrollcommand=xbar.set, yscrollcommand=ybar.set)
        self.map_canvas.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        self.map_canvas.bind("<Button-1>", self._on_map_click)
        self.map_canvas.bind("<B1-Motion>", self._on_map_drag)

        side = ttk.Notebook(split)
        split.add(side, weight=0)

        inspect = ttk.Frame(side, padding=6)
        side.add(inspect, text="Inspect")
        selected = ttk.LabelFrame(inspect, text="Selected cell", padding=6)
        selected.pack(fill="x")
        self.cell_info_label = ttk.Label(selected, text="Click a cell", justify="left", wraplength=360)
        self.cell_info_label.pack(anchor="w")

        edit = ttk.LabelFrame(inspect, text="Cell edit / brush", padding=6)
        edit.pack(fill="x", pady=(8, 0))
        self.tile_id_var = tk.IntVar(value=0)
        self.shootable_id_var = tk.IntVar(value=0)
        self.entity_id_var = tk.IntVar(value=0)
        self._spin_row(edit, "Tile ID", self.tile_id_var, 0, 511)
        self._spin_row(edit, "Shootable ID", self.shootable_id_var, 0, 255)
        self._spin_row(edit, "Entity ID", self.entity_id_var, 0, 255)
        ttk.Button(edit, text="Apply to selected cell", command=self.apply_cell_values).pack(fill="x", pady=(8, 0))
        ttk.Button(edit, text="Brush = selected cell values", command=self._brush_from_cell).pack(fill="x", pady=(4, 0))
        ttk.Label(edit, textvariable=self._brush_status_var()).pack(anchor="w", pady=(8, 0))

        objects = ttk.Frame(side, padding=6)
        side.add(objects, text="Objects")
        self.quick_object_tree = ttk.Treeview(objects, columns=("kind", "id", "name"), show="headings", height=16)
        for col, width in [("kind", 82), ("id", 44), ("name", 230)]:
            self.quick_object_tree.heading(col, text=col)
            self.quick_object_tree.column(col, width=width, stretch=(col == "name"))
        self.quick_object_tree.pack(fill="both", expand=True)
        self.quick_object_tree.bind("<<TreeviewSelect>>", self._on_quick_object_select)
        ttk.Button(objects, text="Use selected object as brush", command=self._use_quick_object_as_brush).pack(fill="x", pady=(6, 0))

        specials = ttk.Frame(side, padding=6)
        side.add(specials, text="Specials")
        self.trigger_tree = ttk.Treeview(specials, columns=("idx", "value", "x", "y", "type"), show="headings", height=18)
        for col, width in [("idx", 38), ("value", 55), ("x", 38), ("y", 38), ("type", 230)]:
            self.trigger_tree.heading(col, text=col)
            self.trigger_tree.column(col, width=width, stretch=(col == "type"))
        self.trigger_tree.pack(fill="both", expand=True)
        self.trigger_tree.bind("<<TreeviewSelect>>", self._on_trigger_select)

    def _build_logic_workspace(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=6)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)
        notebook.add(tab, text="LOGIC")
        self.logic_summary = tk.Text(tab, height=7, wrap="word")
        self.logic_summary.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        split = ttk.PanedWindow(tab, orient="horizontal")
        split.grid(row=1, column=0, sticky="nsew")
        graph_frame = ttk.LabelFrame(split, text="Level logic graph", padding=6)
        problem_frame = ttk.LabelFrame(split, text="Problems / warnings", padding=6)
        split.add(graph_frame, weight=2)
        split.add(problem_frame, weight=1)

        self.logic_tree = ttk.Treeview(graph_frame, columns=("type", "detail"), show="tree headings")
        self.logic_tree.heading("#0", text="Node")
        self.logic_tree.heading("type", text="Type")
        self.logic_tree.heading("detail", text="Detail")
        self.logic_tree.column("#0", width=260)
        self.logic_tree.column("type", width=130)
        self.logic_tree.column("detail", width=420, stretch=True)
        self.logic_tree.pack(fill="both", expand=True)
        self.logic_tree.bind("<<TreeviewSelect>>", self._on_logic_select)

        self.problem_tree = ttk.Treeview(problem_frame, columns=("severity", "detail"), show="headings")
        self.problem_tree.heading("severity", text="Severity")
        self.problem_tree.heading("detail", text="Detail")
        self.problem_tree.column("severity", width=85)
        self.problem_tree.column("detail", width=400, stretch=True)
        self.problem_tree.pack(fill="both", expand=True)

    def _build_assets_workspace(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=6)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        notebook.add(tab, text="ASSETS")
        nb = ttk.Notebook(tab)
        nb.grid(row=0, column=0, sticky="nsew")

        tile_tab = ttk.Frame(nb)
        tile_tab.columnconfigure(0, weight=1)
        tile_tab.rowconfigure(0, weight=1)
        nb.add(tile_tab, text="Map Tiles")
        self.tile_canvas = tk.Canvas(tile_tab, background="#282828")
        taxbar = ttk.Scrollbar(tile_tab, orient="horizontal", command=self.tile_canvas.xview)
        taybar = ttk.Scrollbar(tile_tab, orient="vertical", command=self.tile_canvas.yview)
        self.tile_canvas.configure(xscrollcommand=taxbar.set, yscrollcommand=taybar.set)
        self.tile_canvas.grid(row=0, column=0, sticky="nsew")
        taybar.grid(row=0, column=1, sticky="ns")
        taxbar.grid(row=1, column=0, sticky="ew")
        self.tile_canvas.bind("<Button-1>", self._on_tile_atlas_click)

        sprite_tab = ttk.Frame(nb)
        sprite_tab.columnconfigure(1, weight=1)
        sprite_tab.rowconfigure(0, weight=1)
        nb.add(sprite_tab, text="Sprites .L")
        self.sprite_list = tk.Listbox(sprite_tab, width=32, exportselection=False)
        self.sprite_list.grid(row=0, column=0, sticky="ns")
        self.sprite_list.bind("<<ListboxSelect>>", self._on_sprite_select)
        self.sprite_canvas = tk.Canvas(sprite_tab, background="#282828")
        self.sprite_canvas.grid(row=0, column=1, sticky="nsew")

        archive_tab = ttk.Frame(nb, padding=6)
        archive_tab.columnconfigure(0, weight=1)
        archive_tab.rowconfigure(0, weight=1)
        nb.add(archive_tab, text="Archive")
        self.archive_tree = ttk.Treeview(archive_tab, columns=("idx", "name", "type", "size", "role"), show="headings")
        for col, width in [("idx", 50), ("name", 120), ("type", 70), ("size", 80), ("role", 260)]:
            self.archive_tree.heading(col, text=col)
            self.archive_tree.column(col, width=width, stretch=(col == "role"))
        self.archive_tree.grid(row=0, column=0, sticky="nsew")
        ttk.Scrollbar(archive_tab, orient="vertical", command=self.archive_tree.yview).grid(row=0, column=1, sticky="ns")

    def _build_research_workspace(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=6)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        notebook.add(tab, text="RESEARCH")

        split = ttk.PanedWindow(tab, orient="vertical")
        split.grid(row=0, column=0, sticky="nsew")
        top = ttk.Frame(split)
        top.columnconfigure(0, weight=1)
        top.rowconfigure(0, weight=1)
        split.add(top, weight=2)
        self.object_tree = ttk.Treeview(top, columns=("kind", "id", "count", "category", "sprite", "name"), show="headings")
        for col, width in [("kind", 80), ("id", 50), ("count", 70), ("category", 130), ("sprite", 120), ("name", 320)]:
            self.object_tree.heading(col, text=col)
            self.object_tree.column(col, width=width, stretch=(col == "name"))
        self.object_tree.grid(row=0, column=0, sticky="nsew")
        self.object_tree.bind("<<TreeviewSelect>>", self._on_object_select)
        ttk.Scrollbar(top, orient="vertical", command=self.object_tree.yview).grid(row=0, column=1, sticky="ns")

        bottom = ttk.PanedWindow(split, orient="horizontal")
        split.add(bottom, weight=1)
        detail_frame = ttk.LabelFrame(bottom, text="Selected object detail", padding=6)
        occ_frame = ttk.LabelFrame(bottom, text="Occurrences", padding=6)
        bottom.add(detail_frame, weight=1)
        bottom.add(occ_frame, weight=2)
        self.object_detail = tk.Text(detail_frame, height=7, width=55, wrap="word")
        self.object_detail.pack(fill="both", expand=True)
        self.occ_tree = ttk.Treeview(occ_frame, columns=("map", "x", "y", "value", "note"), show="headings", height=7)
        for col, width in [("map", 80), ("x", 45), ("y", 45), ("value", 70), ("note", 280)]:
            self.occ_tree.heading(col, text=col)
            self.occ_tree.column(col, width=width, stretch=(col == "note"))
        self.occ_tree.pack(fill="both", expand=True)
        self.occ_tree.bind("<<TreeviewSelect>>", self._on_occurrence_select)

    def _spin_row(self, parent: ttk.Frame, label: str, var: tk.IntVar, start: int, end: int) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=label, width=13).pack(side="left")
        ttk.Spinbox(row, from_=start, to=end, textvariable=var, width=8).pack(side="left")

    def _brush_status_var(self) -> tk.StringVar:
        self.brush_status = tk.StringVar(value="Brush: tile=0, entity=0, shootable=0")
        return self.brush_status

    # ---------------------------------------------------------------------
    # Loading / saving
    # ---------------------------------------------------------------------
    def _load_default_dat(self) -> None:
        if DEFAULT_DAT.exists():
            self.load_dat(DEFAULT_DAT)
        else:
            self.status_var.set(f"Put RIPTIDE.DAT into {DEFAULT_GAME_DATA}")

    def open_dat(self) -> None:
        path = filedialog.askopenfilename(
            title="Open RIPTIDE.DAT",
            filetypes=[("Riptide DAT", "*.DAT"), ("All files", "*.*")],
            initialdir=str(DEFAULT_GAME_DATA),
        )
        if path:
            self.load_dat(Path(path))

    def load_dat(self, path: Path) -> None:
        try:
            self.dat = RiptideDat(path)
            self.occurrences = scan_archive(self.dat)
            self._prime_object_db_from_occurrences()
        except Exception as exc:
            messagebox.showerror("Load failed", str(exc))
            return
        self.map_list.delete(0, tk.END)
        for entry in self.dat.maps():
            info = map_info(entry.filename)
            self.map_list.insert(tk.END, f"{entry.filename:<8}  {info.title}")
        self.sprite_list.delete(0, tk.END)
        for entry in self.dat.sprites():
            self.sprite_list.insert(tk.END, entry.filename)
        self.refresh_object_browser()
        self.refresh_archive_browser()
        self.status_var.set(f"Loaded {path} ({len(self.dat.entries)} files, {len(self.occurrences)} object/event occurrences)")
        if self.dat.maps():
            self.map_list.selection_set(0)
            self._on_map_select(None)

    def _prime_object_db_from_occurrences(self) -> None:
        for occ in self.occurrences:
            self.object_db.get(occ.kind, occ.object_id, value=occ.value)
        self.object_db.save()

    def _on_map_select(self, _event) -> None:
        if not self.dat:
            return
        selected = self.map_list.curselection()
        if not selected:
            return
        entry = self.dat.maps()[selected[0]]
        try:
            self.current_map = RiptideMap(entry)
            self.current_entry = entry
            self.dirty = False
            self.last_selected_cell = None
            self.selected_trigger_index = None
        except Exception as exc:
            messagebox.showerror("Map load failed", str(exc))
            return
        info = map_info(entry.filename)
        rot = self.current_map.palette_rotation
        self.map_info_label.config(text=(
            f"{entry.filename} — {info.title}\n"
            f"Size: {self.current_map.width} x {self.current_map.height}\n"
            f"Password: {info.password or '-'}\nMusic: {info.music or '-'}\n"
            f"Palette cycle: {rot.start:02X}-{rot.end:02X}, speed={rot.speed}, unk={rot.unknown}"
        ))
        self.sprite_cache.clear()
        self.refresh_map()
        self.refresh_tile_atlas()
        self.refresh_triggers()
        self.refresh_logic_workspace()
        self.refresh_quick_objects()
        self.cell_info_label.config(text="Click a cell")

    def save_dat(self) -> None:
        if not self.dat:
            return
        try:
            backup = self.dat.save(backup=True)
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc))
            return
        self.dirty = False
        self.status_var.set(f"Saved DAT. Backup: {backup.name if backup else 'none'}")
        messagebox.showinfo("Saved", f"RIPTIDE.DAT saved.\nBackup created:\n{backup}" if backup else "RIPTIDE.DAT saved.")

    # ---------------------------------------------------------------------
    # Rendering
    # ---------------------------------------------------------------------
    def _sprite_first_frame(self, filename: str) -> Image.Image | None:
        if not self.dat or not self.current_map or not filename:
            return None
        key = (filename.lower(), id(self.current_map))
        if key in self.sprite_cache:
            return self.sprite_cache[key]
        entry = self.dat.get(filename)
        if not entry:
            return None
        frames = read_sprite_frames(entry, self.current_map.palette)
        if not frames:
            return None
        self.sprite_cache[key] = frames[0]
        return frames[0]

    def _paste_sprite_on_map(self, img: Image.Image, sprite: Image.Image, cx: int, cy: int, scale: int, *, kind: str) -> None:
        tile = 8 * scale
        spr = sprite.resize((sprite.width * scale, sprite.height * scale), Image.Resampling.NEAREST)
        px = cx * tile + tile // 2 - spr.width // 2
        py = cy * tile + tile - spr.height
        if kind == "shootable":
            py = cy * tile + tile // 2 - spr.height // 2
        img.alpha_composite(spr, (px, py))

    def refresh_map(self) -> None:
        rmap = self.current_map
        if not rmap or not hasattr(self, "map_canvas"):
            return
        scale = max(1, int(self.scale_var.get()))
        img = rmap.render(scale=scale).convert("RGBA")
        draw = ImageDraw.Draw(img, "RGBA")
        tile = 8 * scale

        if self.show_sprite_overlay_var.get():
            for y in range(rmap.height):
                for x in range(rmap.width):
                    cell = rmap.cell(x, y)
                    even = ((y * rmap.width + x) % 2) == 0
                    if cell.shootable_id and self._should_draw_object("shootable", cell.shootable_id):
                        sprite = self._sprite_first_frame(shootable_sprite_name(cell.shootable_id, even))
                        if sprite:
                            self._paste_sprite_on_map(img, sprite, x, y, scale, kind="shootable")
                    if cell.entity_id and self._should_draw_object("entity", cell.entity_id):
                        sprite = self._sprite_first_frame(entity_sprite_name(cell.entity_id, even))
                        if sprite:
                            self._paste_sprite_on_map(img, sprite, x, y, scale, kind="entity")
            draw = ImageDraw.Draw(img, "RGBA")

        if self.show_solids_var.get():
            for y in range(rmap.height):
                for x in range(rmap.width):
                    if rmap.cell(x, y).is_solid:
                        draw.rectangle([x * tile, y * tile, (x + 1) * tile - 1, (y + 1) * tile - 1], fill=(255, 0, 0, 46))

        if self.show_event_links_var.get():
            self._draw_trigger_links(draw, rmap, tile)
        if self.show_door_links_var.get():
            self._draw_door_switch_links(draw, rmap, tile)

        if self.show_grid_var.get() and scale >= 2:
            for x in range(rmap.width + 1):
                draw.line([(x * tile, 0), (x * tile, rmap.height * tile)], fill=(255, 255, 255, 45))
            for y in range(rmap.height + 1):
                draw.line([(0, y * tile), (rmap.width * tile, y * tile)], fill=(255, 255, 255, 45))

        if self.show_entities_var.get():
            for y in range(rmap.height):
                for x in range(rmap.width):
                    cell = rmap.cell(x, y)
                    labels = []
                    if cell.shootable_id and self._should_draw_object("shootable", cell.shootable_id):
                        labels.append(f"S{cell.shootable_id}")
                    if cell.entity_id and self._should_draw_object("entity", cell.entity_id):
                        labels.append(f"E{cell.entity_id}")
                    if labels:
                        self._draw_label(draw, x * tile + 2, y * tile + 2, "/".join(labels), tile)

        if self.show_triggers_var.get():
            for index, value, x, y, _even in rmap.nonzero_triggers():
                if 0 <= x < rmap.width and 0 <= y < rmap.height and self._should_draw_object("trigger", index):
                    px, py = x * tile, y * tile
                    outline = (0, 255, 255, 255)
                    width = max(1, scale)
                    if self.highlight == ("trigger", index) or self.selected_trigger_index == index:
                        outline = (255, 255, 255, 255)
                        width = max(2, scale + 1)
                    draw.rectangle([px + 1, py + 1, px + tile - 2, py + tile - 2], outline=outline, width=width)
                    self._draw_label(draw, px + 2, py + tile // 2, f"T{index}", tile, fill=outline)

        for occ in self._current_highlight_occurrences():
            if 0 <= occ.x < rmap.width and 0 <= occ.y < rmap.height:
                px, py = occ.x * tile, occ.y * tile
                draw.rectangle([px, py, px + tile - 1, py + tile - 1], outline=(255, 255, 255, 255), width=max(2, scale + 1))

        if self.last_selected_cell:
            x, y = self.last_selected_cell
            draw.rectangle([x * tile, y * tile, (x + 1) * tile - 1, (y + 1) * tile - 1], outline=(255, 255, 255, 255), width=max(2, scale))

        self.rendered_map = img
        self.map_photo = ImageTk.PhotoImage(img)
        self.map_canvas.delete("all")
        self.map_canvas.create_image(0, 0, image=self.map_photo, anchor="nw")
        self.map_canvas.config(scrollregion=(0, 0, img.width, img.height))

    def _draw_label(self, draw: ImageDraw.ImageDraw, x: int, y: int, text: str, tile: int, fill=(255, 255, 0, 255)) -> None:
        draw.rectangle([x - 1, y - 1, x + len(text) * 6 + 2, y + 10], fill=(0, 0, 0, 175))
        draw.text((x, y), text, fill=fill)

    def _should_draw_object(self, kind: str, object_id: int) -> bool:
        return not self.show_highlight_only_var.get() or self.highlight is None or self.highlight == (kind, object_id)

    def _current_highlight_occurrences(self):
        if not self.highlight or not self.current_map:
            return []
        kind, object_id = self.highlight
        return occurrences_for_current_map(self.occurrences, self.current_map.filename, kind, object_id)

    def _trigger_center(self, value: int, rmap: RiptideMap, tile: int) -> tuple[int, int]:
        x, y = rmap.trigger_xy(value)
        return x * tile + tile // 2, y * tile + tile // 2

    def _draw_trigger_links(self, draw: ImageDraw.ImageDraw, rmap: RiptideMap, tile: int) -> None:
        for index in range(10, 30, 2):
            if index + 1 >= len(rmap.triggers):
                continue
            a, b = rmap.triggers[index], rmap.triggers[index + 1]
            if not a or not b:
                continue
            ax, ay = self._trigger_center(a, rmap, tile)
            bx, by = self._trigger_center(b, rmap, tile)
            draw.line([(ax, ay), (bx, by)], fill=(0, 255, 255, 170), width=max(1, tile // 12))
            draw.ellipse([ax-4, ay-4, ax+4, ay+4], fill=(0, 255, 255, 220))
            draw.ellipse([bx-4, by-4, bx+4, by+4], fill=(0, 255, 255, 220))
        for pos_idx in (30, 32, 34, 36):
            if pos_idx < len(rmap.triggers) and rmap.triggers[pos_idx]:
                px, py = self._trigger_center(rmap.triggers[pos_idx], rmap, tile)
                draw.ellipse([px-6, py-6, px+6, py+6], outline=(255, 180, 0, 230), width=max(1, tile // 12))

    def _draw_door_switch_links(self, draw: ImageDraw.ImageDraw, rmap: RiptideMap, tile: int) -> None:
        switches = defaultdict(list)
        doors = defaultdict(list)
        for y in range(rmap.height):
            for x in range(rmap.width):
                cell = rmap.cell(x, y)
                if cell.shootable_id in DOOR_SWITCH_TO_ENTITY:
                    switches[cell.shootable_id].append((x, y))
                if cell.entity_id in (1, 2, 3):
                    doors[cell.entity_id].append((x, y))
        for switch_id, door_id in DOOR_SWITCH_TO_ENTITY.items():
            for sx, sy in switches.get(switch_id, []):
                for dx, dy in doors.get(door_id, []):
                    ax, ay = sx * tile + tile // 2, sy * tile + tile // 2
                    bx, by = dx * tile + tile // 2, dy * tile + tile // 2
                    draw.line([(ax, ay), (bx, by)], fill=(255, 100, 0, 115), width=max(1, tile // 18))

    # ---------------------------------------------------------------------
    # Refresh workspaces
    # ---------------------------------------------------------------------
    def refresh_tile_atlas(self) -> None:
        rmap = self.current_map
        if not rmap or not hasattr(self, "tile_canvas"):
            return
        scale = 4
        cols = 32
        tile = 8 * scale
        rows = (512 + cols - 1) // cols
        label_h = 16
        img = Image.new("RGBA", (cols * tile, rows * (tile + label_h) + 32), (40, 40, 40, 255))
        draw = ImageDraw.Draw(img, "RGBA")
        draw.text((4, 2), "Tiles 0-255 are solid / wall; tiles 256-511 are passable background.", fill=(230, 230, 230, 255))
        for tile_id in range(512):
            x = tile_id % cols
            y = tile_id // cols
            px, py = x * tile, 24 + y * (tile + label_h)
            img.paste(rmap.tile_image(tile_id, scale=scale).convert("RGBA"), (px, py))
            fill = (255, 150, 150, 255) if tile_id < 256 else (170, 220, 255, 255)
            draw.text((px + 1, py + tile), str(tile_id), fill=fill)
            if tile_id == self.selected_tile_var.get():
                draw.rectangle([px, py, px + tile - 1, py + tile - 1], outline=(255, 255, 0, 255), width=3)
        self.tile_atlas_photo = ImageTk.PhotoImage(img)
        self.tile_canvas.delete("all")
        self.tile_canvas.create_image(0, 0, image=self.tile_atlas_photo, anchor="nw")
        self.tile_canvas.config(scrollregion=(0, 0, img.width, img.height))

    def refresh_triggers(self) -> None:
        for item in self.trigger_tree.get_children():
            self.trigger_tree.delete(item)
        rmap = self.current_map
        if not rmap:
            return
        for index, value, x, y, _even in rmap.nonzero_triggers():
            self.trigger_tree.insert("", "end", iid=f"trigger:{index}", values=(index, value, x, y, trigger_name(index, value)))

    def refresh_quick_objects(self) -> None:
        for item in self.quick_object_tree.get_children():
            self.quick_object_tree.delete(item)
        if not self.current_map:
            return
        seen: set[tuple[str, int]] = set()
        for kind in ("entity", "shootable"):
            ids = sorted({getattr(cell, f"{kind}_id") for cell in self.current_map.cells if getattr(cell, f"{kind}_id")})
            for object_id in ids:
                rec = self.object_db.get(kind, object_id)
                self.quick_object_tree.insert("", "end", iid=f"quick:{kind}:{object_id}", values=(kind, object_id, rec.name))
                seen.add((kind, object_id))
        for sid in sorted(DOOR_SWITCH_TO_ENTITY):
            if ("shootable", sid) not in seen:
                rec = self.object_db.get("shootable", sid)
                self.quick_object_tree.insert("", "end", iid=f"quick:shootable:{sid}", values=("shootable", sid, rec.name))

    def refresh_object_browser(self) -> None:
        for item in self.object_tree.get_children():
            self.object_tree.delete(item)
        for item in self.occ_tree.get_children():
            self.occ_tree.delete(item)
        self.object_detail.delete("1.0", tk.END)
        if not self.dat:
            return
        counts = occurrence_counts(self.occurrences)
        for (kind, object_id), count in sorted(counts.items(), key=lambda kv: (kv[0][0], kv[0][1])):
            sample = next((o for o in self.occurrences if o.kind == kind and o.object_id == object_id), None)
            rec = self.object_db.get(kind, object_id, value=sample.value if sample else 0)
            self.object_tree.insert("", "end", iid=f"{kind}:{object_id}", values=(kind, object_id, count, rec.category, rec.sprite, rec.name))

    def refresh_archive_browser(self) -> None:
        for item in self.archive_tree.get_children():
            self.archive_tree.delete(item)
        if not self.dat:
            return
        role_by_ext = {".m": "Level map", ".l": "Animated sprite", ".cmf": "AdLib music", ".voc": "Sound effect", ".pcx": "Image", ".pcs": "Image/splash"}
        for e in self.dat.entries:
            ext = e.extension or "?"
            self.archive_tree.insert("", "end", values=(e.index, e.filename, ext, e.size, role_by_ext.get(ext, "Raw/unknown resource")))

    def refresh_logic_workspace(self) -> None:
        for tree in (self.logic_tree, self.problem_tree):
            for item in tree.get_children():
                tree.delete(item)
        self.logic_summary.delete("1.0", tk.END)
        rmap = self.current_map
        if not rmap:
            return
        stats = self._level_stats(rmap)
        self.logic_summary.insert(tk.END, self._make_logic_summary_text(rmap, stats))

        trig_parent = self.logic_tree.insert("", "end", text="Special points", values=("group", "player start, exits, key gate, teleports, messages"), open=True)
        for index in (0, 1, 2, 3, 4):
            if index < len(rmap.triggers) and rmap.triggers[index]:
                x, y = rmap.trigger_xy(rmap.triggers[index])
                self.logic_tree.insert(trig_parent, "end", iid=f"logic:special:trigger:{index}", text=f"T{index}", values=("special", f"{trigger_name(index, rmap.triggers[index])} at {x},{y}"))

        tele_parent = self.logic_tree.insert("", "end", text="Teleports", values=("group", "IN → OUT pairs"), open=True)
        for index in range(10, 30, 2):
            a = rmap.triggers[index] if index < len(rmap.triggers) else 0
            b = rmap.triggers[index + 1] if index + 1 < len(rmap.triggers) else 0
            if not a and not b:
                continue
            ax, ay = rmap.trigger_xy(a) if a else (None, None)
            bx, by = rmap.trigger_xy(b) if b else (None, None)
            status = "OK" if a and b else "incomplete"
            self.logic_tree.insert(tele_parent, "end", iid=f"logic:special:trigger:{index}", text=f"Teleport {(index - 10)//2 + 1}", values=(status, f"IN {ax},{ay} → OUT {bx},{by}"))

        msg_parent = self.logic_tree.insert("", "end", text="Messages", values=("group", "trigger position + message id"), open=True)
        for pos_idx, content_idx in [(30,31),(32,33),(34,35),(36,37)]:
            pos_val = rmap.triggers[pos_idx]
            content_val = rmap.triggers[content_idx]
            if not pos_val and not content_val:
                continue
            x, y = rmap.trigger_xy(pos_val) if pos_val else (None, None)
            self.logic_tree.insert(msg_parent, "end", iid=f"logic:messages:trigger:{pos_idx}", text=f"Message {(pos_idx-30)//2+1}", values=("message", f"at {x},{y}; content {content_val}: {message_by_id(content_val)}"))

        door_parent = self.logic_tree.insert("", "end", text="Doors & switches", values=("group", "hardcoded switch IDs open door entity IDs"), open=True)
        for sid, eid in DOOR_SWITCH_TO_ENTITY.items():
            sw = stats["switches"].get(sid, [])
            doors = stats["doors"].get(eid, [])
            node = self.logic_tree.insert(door_parent, "end", iid=f"logic:doors:shootable:{sid}", text=f"S{sid} → E{eid}", values=("door system", f"{len(sw)} switch(es), {len(doors)} door tile(s)"))
            for x, y in sw[:20]:
                self.logic_tree.insert(node, "end", iid=f"logiccell:shootable:{sid}:{x}:{y}", text=f"switch at {x},{y}", values=("switch", "click to jump"))
            for x, y in doors[:20]:
                self.logic_tree.insert(node, "end", iid=f"logiccell:entity:{eid}:{x}:{y}", text=f"door at {x},{y}", values=("door", "click to jump"))

        obj_parent = self.logic_tree.insert("", "end", text="Object counts", values=("group", "entities and shootables in this level"), open=False)
        for kind, counter in [("entity", stats["entity_counts"]), ("shootable", stats["shootable_counts"])]:
            for object_id, count in sorted(counter.items()):
                rec = self.object_db.get(kind, object_id)
                self.logic_tree.insert(obj_parent, "end", iid=f"logic:counts:{kind}:{object_id}", text=f"{kind[0].upper()}{object_id}", values=(rec.category, f"{count}× {rec.name}"))

        for sev, detail in self._validate_level(rmap, stats):
            self.problem_tree.insert("", "end", values=(sev, detail))

    def _level_stats(self, rmap: RiptideMap) -> dict:
        entity_counts = Counter()
        shootable_counts = Counter()
        doors = defaultdict(list)
        switches = defaultdict(list)
        for y in range(rmap.height):
            for x in range(rmap.width):
                cell = rmap.cell(x, y)
                if cell.entity_id:
                    entity_counts[cell.entity_id] += 1
                if cell.shootable_id:
                    shootable_counts[cell.shootable_id] += 1
                if cell.entity_id in (1, 2, 3):
                    doors[cell.entity_id].append((x, y))
                if cell.shootable_id in DOOR_SWITCH_TO_ENTITY:
                    switches[cell.shootable_id].append((x, y))
        return {"entity_counts": entity_counts, "shootable_counts": shootable_counts, "doors": doors, "switches": switches}

    def _make_logic_summary_text(self, rmap: RiptideMap, stats: dict) -> str:
        nonzero_triggers = list(rmap.nonzero_triggers())
        return (
            f"{rmap.filename}: {rmap.width}×{rmap.height} cells\n"
            f"Entities: {sum(stats['entity_counts'].values())} placements / {len(stats['entity_counts'])} unique IDs. "
            f"Shootables: {sum(stats['shootable_counts'].values())} placements / {len(stats['shootable_counts'])} unique IDs.\n"
            f"Special points: {len(nonzero_triggers)} non-empty trigger slots. "
            "This workspace interprets raw level bytes as human-readable systems: spawn, exits, teleports, messages, barrels, switches, doors and active enemies.\n"
            "Click a graph node to highlight or jump to the relevant map position."
        )

    def _validate_level(self, rmap: RiptideMap, stats: dict) -> list[tuple[str, str]]:
        problems: list[tuple[str, str]] = []
        if not rmap.triggers[0]:
            problems.append(("warning", "No player spawn trigger T0 is set."))
        for idx in range(10, 30, 2):
            a, b = rmap.triggers[idx], rmap.triggers[idx + 1]
            if bool(a) != bool(b):
                problems.append(("warning", f"Teleport {(idx - 10)//2 + 1} is incomplete: T{idx}={a}, T{idx+1}={b}."))
        for pos_idx, content_idx in [(30,31),(32,33),(34,35),(36,37)]:
            if bool(rmap.triggers[pos_idx]) != bool(rmap.triggers[content_idx]):
                problems.append(("info", f"Message pair T{pos_idx}/T{content_idx} is partial."))
        for sid, eid in DOOR_SWITCH_TO_ENTITY.items():
            if stats["switches"].get(sid) and not stats["doors"].get(eid):
                problems.append(("warning", f"Switch S{sid} exists but no Door E{eid} exists in this level."))
            if stats["doors"].get(eid) and not stats["switches"].get(sid):
                problems.append(("info", f"Door E{eid} exists but there is no matching switch S{sid}; it may be opened elsewhere or intentionally locked."))
        for index, value, x, y, _even in rmap.nonzero_triggers():
            if not (0 <= x < rmap.width and 0 <= y < rmap.height):
                problems.append(("error", f"Trigger T{index} points outside the map: value={value}, decoded={x},{y}."))
        if not problems:
            problems.append(("ok", "No obvious structural problems found."))
        return problems

    # ---------------------------------------------------------------------
    # Map interaction
    # ---------------------------------------------------------------------
    def _canvas_to_cell(self, event) -> tuple[int, int] | None:
        rmap = self.current_map
        if not rmap:
            return None
        scale = max(1, int(self.scale_var.get()))
        tile = 8 * scale
        x = int(self.map_canvas.canvasx(event.x) // tile)
        y = int(self.map_canvas.canvasy(event.y) // tile)
        if 0 <= x < rmap.width and 0 <= y < rmap.height:
            return x, y
        return None

    def _on_map_click(self, event) -> None:
        cell_xy = self._canvas_to_cell(event)
        if cell_xy:
            self._handle_cell_action(*cell_xy)

    def _on_map_drag(self, event) -> None:
        if self.tool_var.get() in ("paint_tile", "paint_entity", "paint_shootable"):
            cell_xy = self._canvas_to_cell(event)
            if cell_xy:
                self._handle_cell_action(*cell_xy)

    def _handle_cell_action(self, x: int, y: int) -> None:
        rmap = self.current_map
        if not rmap:
            return
        tool = self.tool_var.get()
        if tool == "paint_tile":
            rmap.set_cell(x, y, tile_id=self.selected_tile_var.get())
            self.dirty = True
        elif tool == "paint_entity":
            rmap.set_cell(x, y, entity_id=self.selected_entity_var.get())
            self.dirty = True
        elif tool == "paint_shootable":
            rmap.set_cell(x, y, shootable_id=self.selected_shootable_var.get())
            self.dirty = True
        elif tool == "pick":
            cell = rmap.cell(x, y)
            self.selected_tile_var.set(cell.tile_id)
            self.selected_entity_var.set(cell.entity_id)
            self.selected_shootable_var.set(cell.shootable_id)
            self.refresh_tile_atlas()
        self.select_cell(x, y)
        if self.dirty:
            self.occurrences = scan_archive(self.dat) if self.dat else []
            self.refresh_object_browser()
            self.refresh_quick_objects()
            self.refresh_logic_workspace()
        self.refresh_map()
        self._update_brush_status()

    def select_cell(self, x: int, y: int) -> None:
        rmap = self.current_map
        if not rmap:
            return
        cell = rmap.cell(x, y)
        even = ((y * rmap.width + x) % 2) == 0
        self.last_selected_cell = (x, y)
        self.tile_id_var.set(cell.tile_id)
        self.shootable_id_var.set(cell.shootable_id)
        self.entity_id_var.set(cell.entity_id)
        entity_sprite = entity_sprite_name(cell.entity_id, even)
        shootable_sprite = shootable_sprite_name(cell.shootable_id, even)
        trigger_hits = [f"T{idx}: {trigger_name(idx, value)}" for idx, value, tx, ty, _even in rmap.nonzero_triggers() if tx == x and ty == y]
        lines = [
            f"Cell: x={x}, y={y}",
            f"Tile: {cell.tile_id} ({'solid' if cell.is_solid else 'passable/background'})",
            f"Shootable: S{cell.shootable_id}" + (f" — {shootable_sprite}" if shootable_sprite else ""),
            f"Entity: E{cell.entity_id}" + (f" — {entity_sprite}" if entity_sprite else ""),
        ]
        if cell.shootable_id in SHOOTABLE_INFO:
            lines.append(f"Shootable info: {SHOOTABLE_INFO[cell.shootable_id]}")
        if cell.entity_id in ENTITY_INFO:
            lines.append(f"Entity info: {ENTITY_INFO[cell.entity_id]}")
        if trigger_hits:
            lines.append("Special points here:")
            lines.extend("  " + t for t in trigger_hits)
        self.cell_info_label.config(text="\n".join(lines))
        self.status_var.set(f"Selected cell ({x}, {y}); mode={self.tool_var.get()}")

    def apply_cell_values(self) -> None:
        if not self.current_map or not self.last_selected_cell:
            return
        x, y = self.last_selected_cell
        try:
            self.current_map.set_cell(x, y, tile_id=int(self.tile_id_var.get()), shootable_id=int(self.shootable_id_var.get()), entity_id=int(self.entity_id_var.get()))
        except Exception as exc:
            messagebox.showerror("Invalid cell values", str(exc))
            return
        self.dirty = True
        self.occurrences = scan_archive(self.dat) if self.dat else []
        self.select_cell(x, y)
        self.refresh_object_browser()
        self.refresh_quick_objects()
        self.refresh_logic_workspace()
        self.refresh_map()

    def _brush_from_cell(self) -> None:
        self.selected_tile_var.set(self.tile_id_var.get())
        self.selected_entity_var.set(self.entity_id_var.get())
        self.selected_shootable_var.set(self.shootable_id_var.get())
        self._update_brush_status()

    def _update_brush_status(self) -> None:
        if hasattr(self, "brush_status"):
            self.brush_status.set(f"Brush: tile={self.selected_tile_var.get()}, entity={self.selected_entity_var.get()}, shootable={self.selected_shootable_var.get()}")

    def _on_tile_atlas_click(self, event) -> None:
        scale = 4
        cols = 32
        tile = 8 * scale
        label_h = 16
        y_canvas = int(self.tile_canvas.canvasy(event.y)) - 24
        if y_canvas < 0:
            return
        x = int(self.tile_canvas.canvasx(event.x) // tile)
        y = int(y_canvas // (tile + label_h))
        tile_id = y * cols + x
        if 0 <= tile_id < 512:
            self.selected_tile_var.set(tile_id)
            self.refresh_tile_atlas()
            self._update_brush_status()
            self.status_var.set(f"Selected tile {tile_id} for tile brush")

    # ---------------------------------------------------------------------
    # Selection callbacks
    # ---------------------------------------------------------------------
    def _on_sprite_select(self, _event) -> None:
        if not self.dat or not self.current_map:
            return
        selection = self.sprite_list.curselection()
        if not selection:
            return
        entry = self.dat.sprites()[selection[0]]
        frames = read_sprite_frames(entry, self.current_map.palette)
        self.sprite_canvas.delete("all")
        self._sprite_sheet_refs.clear()
        if not frames:
            self.status_var.set(f"Could not parse sprite {entry.filename}")
            return
        scale = 3
        margin = 10
        x = margin
        y = margin
        max_h = 0
        for i, frame in enumerate(frames[:120]):
            preview = frame.resize((frame.width * scale, frame.height * scale), Image.Resampling.NEAREST)
            if x + preview.width + margin > 1200:
                x = margin
                y += max_h + 28
                max_h = 0
            photo = ImageTk.PhotoImage(preview)
            self._sprite_sheet_refs.append(photo)
            self.sprite_canvas.create_image(x, y, image=photo, anchor="nw")
            self.sprite_canvas.create_text(x, y + preview.height + 2, text=str(i), fill="white", anchor="nw")
            x += preview.width + margin
            max_h = max(max_h, preview.height)
        self.sprite_canvas.create_text(10, y + max_h + 24, text=f"{entry.filename}: {len(frames)} frame(s)", fill="white", anchor="nw")
        self.sprite_canvas.config(scrollregion=(0, 0, 1250, y + max_h + 60))
        self.status_var.set(f"Previewing {entry.filename}")

    def _on_object_select(self, _event) -> None:
        selected = self.object_tree.selection()
        if not selected:
            return
        iid = selected[0]
        kind, raw_id = iid.split(":")
        object_id = int(raw_id)
        self.highlight = (kind, object_id)
        sample = next((o for o in self.occurrences if o.kind == kind and o.object_id == object_id), None)
        rec = self.object_db.get(kind, object_id, value=sample.value if sample else 0)
        self.object_detail.delete("1.0", tk.END)
        self.object_detail.insert(tk.END, f"{kind} {object_id}\nName: {rec.name}\nCategory: {rec.category}\nSprite: {rec.sprite or '-'}\nInfo: {rec.info or '-'}\nNotes: {rec.notes or '-'}\nConfidence: {rec.confidence}\n")
        for item in self.occ_tree.get_children():
            self.occ_tree.delete(item)
        occs = [o for o in self.occurrences if o.kind == kind and o.object_id == object_id]
        for n, occ in enumerate(occs):
            self.occ_tree.insert("", "end", iid=f"occ:{n}", values=(occ.map_name, occ.x, occ.y, occ.value, occ.note))
        self.refresh_map()
        self.status_var.set(f"Highlighted {kind} {object_id}: {len(occs)} occurrence(s) in archive")

    def _on_quick_object_select(self, _event) -> None:
        selected = self.quick_object_tree.selection()
        if not selected:
            return
        _, kind, raw_id = selected[0].split(":")
        object_id = int(raw_id)
        self.highlight = (kind, object_id)
        self.refresh_map()

    def _use_quick_object_as_brush(self) -> None:
        selected = self.quick_object_tree.selection()
        if not selected:
            return
        _, kind, raw_id = selected[0].split(":")
        object_id = int(raw_id)
        if kind == "entity":
            self.selected_entity_var.set(object_id)
            self.tool_var.set("paint_entity")
        elif kind == "shootable":
            self.selected_shootable_var.set(object_id)
            self.tool_var.set("paint_shootable")
        self._update_brush_status()

    def _on_occurrence_select(self, _event) -> None:
        selected = self.occ_tree.selection()
        if not selected or not self.dat:
            return
        values = self.occ_tree.item(selected[0], "values")
        self._jump_to_map_cell(values[0], int(values[1]), int(values[2]))

    def _on_trigger_select(self, _event) -> None:
        selected = self.trigger_tree.selection()
        if not selected or not self.current_map:
            return
        iid = selected[0]
        if iid.startswith("trigger:"):
            self.selected_trigger_index = int(iid.split(":", 1)[1])
            value = self.current_map.triggers[self.selected_trigger_index]
            x, y = self.current_map.trigger_xy(value)
            self.highlight = ("trigger", self.selected_trigger_index)
            self.select_cell(x, y)
            self.refresh_map()

    def _on_logic_select(self, _event) -> None:
        selected = self.logic_tree.selection()
        if not selected or not self.current_map:
            return
        iid = selected[0]
        parts = iid.split(":")
        if parts and parts[0] == "logic":
            # IIDs are namespaced by tree section, because the same logical object
            # can appear both in e.g. "Doors & switches" and "Object counts".
            # Supported forms:
            #   logic:special:trigger:<index>
            #   logic:messages:trigger:<index>
            #   logic:doors:shootable:<id>
            #   logic:counts:<entity|shootable>:<id>
            if len(parts) >= 4 and parts[-2] == "trigger":
                trigger_index = int(parts[-1])
                self.highlight = ("trigger", trigger_index)
                self.selected_trigger_index = trigger_index
                value = self.current_map.triggers[trigger_index]
                x, y = self.current_map.trigger_xy(value)
                self.select_cell(x, y)
            elif len(parts) >= 4 and parts[-2] in ("entity", "shootable"):
                kind = parts[-2]
                object_id = int(parts[-1])
                self.highlight = (kind, object_id)
            self.refresh_map()
        elif len(parts) >= 5 and parts[0] == "logiccell":
            _, kind, object_id, x, y = parts[:5]
            self.highlight = (kind, int(object_id))
            self.select_cell(int(x), int(y))
            self._scroll_to_cell(int(x), int(y))
            self.refresh_map()

    def _jump_to_map_cell(self, map_name: str, x: int, y: int) -> None:
        if not self.dat:
            return
        for idx, entry in enumerate(self.dat.maps()):
            if entry.filename == map_name:
                self.map_list.selection_clear(0, tk.END)
                self.map_list.selection_set(idx)
                self.map_list.see(idx)
                self._on_map_select(None)
                self.select_cell(x, y)
                self._scroll_to_cell(x, y)
                self.refresh_map()
                return

    def _scroll_to_cell(self, x: int, y: int) -> None:
        scale = max(1, int(self.scale_var.get()))
        if self.rendered_map:
            self.map_canvas.xview_moveto(max(0, (x * 8 * scale - 220) / max(1, self.rendered_map.width)))
            self.map_canvas.yview_moveto(max(0, (y * 8 * scale - 160) / max(1, self.rendered_map.height)))

    # ---------------------------------------------------------------------
    # Actions
    # ---------------------------------------------------------------------
    def clear_highlight(self) -> None:
        self.highlight = None
        self.selected_trigger_index = None
        if hasattr(self, "object_tree"):
            self.object_tree.selection_remove(self.object_tree.selection())
        if hasattr(self, "quick_object_tree"):
            self.quick_object_tree.selection_remove(self.quick_object_tree.selection())
        self.refresh_map()

    def validate_current_level(self) -> None:
        if not self.current_map:
            return
        self.refresh_logic_workspace()
        self.workspace.select(1)
        self.status_var.set("Validation refreshed in LOGIC workspace")

    def export_png(self) -> None:
        if not self.current_map:
            return
        initial = f"{self.current_map.filename}.png"
        path = filedialog.asksaveasfilename(title="Export PNG", defaultextension=".png", initialfile=initial, filetypes=[("PNG", "*.png")])
        if not path:
            return
        image = self.rendered_map if self.rendered_map else self.current_map.render(scale=self.scale_var.get())
        image.save(path)
        self.status_var.set(f"Exported {path}")


def main() -> int:
    app = DrRiptideEditor()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
