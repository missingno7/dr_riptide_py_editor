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
    MESSAGES,
    entity_sprite_name,
    shootable_sprite_name,
    shootable_drop_name,
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
SPECIAL_TRIGGER_SLOTS = list(range(0, 10)) + list(range(10, 38))
MESSAGE_POSITION_TO_CONTENT = {30: 31, 32: 33, 34: 35, 36: 37}
MESSAGE_CONTENT_TO_POSITION = {v: k for k, v in MESSAGE_POSITION_TO_CONTENT.items()}
MESSAGE_CONTENT_SLOTS = set(MESSAGE_CONTENT_TO_POSITION)
ERASE_TILE_ID = 256


def object_display_name(kind: str, object_id: int, name: str) -> str:
    drop = shootable_drop_name(object_id) if kind == "shootable" else ""
    return f"{name} -> {drop}" if drop else name


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
        self.pending_trigger_index: int | None = None

        self.scale_var = tk.IntVar(value=3)
        self.tool_var = tk.StringVar(value="select")
        self.active_layer_var = tk.StringVar(value="tile")
        self.special_status_var = tk.StringVar(value="Select a special point")
        self.message_id_var = tk.StringVar(value="0: You need a key for this door.")
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
        self.asset_tile_atlas_photo: ImageTk.PhotoImage | None = None
        self.rendered_map: Image.Image | None = None
        self.map_base_image: Image.Image | None = None
        self.map_base_key: tuple[int, int] | None = None
        self.sprite_cache: dict[tuple[str, int], Image.Image] = {}
        self._sprite_sheet_refs: list[ImageTk.PhotoImage] = []
        self._atlas_refs: list[ImageTk.PhotoImage] = []
        self._preview_photo: ImageTk.PhotoImage | None = None
        self._preview_items: list[int] = []
        self._drag_seen: set[tuple] = set()
        self._refresh_after_id: str | None = None
        self._metadata_after_id: str | None = None
        self._atlas_resize_after_id: str | None = None
        self.map_entries = []

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
        ttk.Button(top, text="Export PNG", command=self.export_png).pack(side="left", padx=(6, 14))
        ttk.Label(top, text="Level").pack(side="left")
        self.map_combo = ttk.Combobox(top, state="readonly", width=34)
        self.map_combo.pack(side="left", padx=(4, 14))
        self.map_combo.bind("<<ComboboxSelected>>", self._on_map_select)
        ttk.Label(top, text="Mode").pack(side="left")
        for text, value in [
            ("Select", "select"), ("Move", "move"), ("Brush", "brush"), ("Pick", "pick"),
        ]:
            ttk.Radiobutton(top, text=text, variable=self.tool_var, value=value).pack(side="left", padx=(4, 0))
        ttk.Label(top, text="Layer").pack(side="left", padx=(18, 4))
        ttk.Label(top, textvariable=self.active_layer_var, width=10).pack(side="left")
        ttk.Label(top, text="Zoom").pack(side="left", padx=(10, 4))
        ttk.Spinbox(top, from_=1, to=8, textvariable=self.scale_var, width=4, command=self.refresh_map).pack(side="left")

        main = ttk.Notebook(self)
        main.grid(row=1, column=0, sticky="nsew")
        self.workspace = main

        self.map_info_label = ttk.Label(self, text="No map loaded")

        self._build_build_workspace(main)
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
        notebook.add(tab, text="LEVEL EDITOR")

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
        self.map_canvas.bind("<B3-Motion>", self._on_map_right_drag)
        self.map_canvas.bind("<ButtonRelease-1>", self._on_map_release)
        self.map_canvas.bind("<ButtonRelease-3>", self._on_map_release)
        self.map_canvas.bind("<Button-3>", self._on_map_right_click)
        self.map_canvas.bind("<Motion>", self._on_map_motion)
        self.map_canvas.bind("<Leave>", self._clear_preview)

        side = ttk.Notebook(split)
        split.add(side, weight=0)
        self.editor_side_notebook = side
        side.bind("<<NotebookTabChanged>>", self._on_editor_side_tab_changed)

        tile_tab = ttk.Frame(side)
        tile_tab.columnconfigure(0, weight=1)
        tile_tab.rowconfigure(0, weight=1)
        side.add(tile_tab, text="Tiles")
        self.tile_canvas = tk.Canvas(tile_tab, background="#282828", width=390)
        tile_ybar = ttk.Scrollbar(tile_tab, orient="vertical", command=self.tile_canvas.yview)
        self.tile_canvas.configure(yscrollcommand=tile_ybar.set)
        self.tile_canvas.grid(row=0, column=0, sticky="nsew")
        tile_ybar.grid(row=0, column=1, sticky="ns")
        self.tile_canvas.bind("<Button-1>", self._on_tile_atlas_click)
        self.tile_canvas.bind("<Configure>", self._on_atlas_canvas_configure)

        shootable_tab = ttk.Frame(side)
        shootable_tab.columnconfigure(0, weight=1)
        shootable_tab.rowconfigure(0, weight=1)
        side.add(shootable_tab, text="Shootables")
        self.shootable_canvas = tk.Canvas(shootable_tab, background="#282828", width=390)
        shootable_ybar = ttk.Scrollbar(shootable_tab, orient="vertical", command=self.shootable_canvas.yview)
        self.shootable_canvas.configure(yscrollcommand=shootable_ybar.set)
        self.shootable_canvas.grid(row=0, column=0, sticky="nsew")
        shootable_ybar.grid(row=0, column=1, sticky="ns")
        self.shootable_canvas.bind("<Button-1>", self._on_shootable_atlas_click)
        self.shootable_canvas.bind("<Configure>", self._on_atlas_canvas_configure)

        entity_tab = ttk.Frame(side)
        entity_tab.columnconfigure(0, weight=1)
        entity_tab.rowconfigure(0, weight=1)
        side.add(entity_tab, text="Entities")
        self.entity_canvas = tk.Canvas(entity_tab, background="#282828", width=390)
        entity_ybar = ttk.Scrollbar(entity_tab, orient="vertical", command=self.entity_canvas.yview)
        self.entity_canvas.configure(yscrollcommand=entity_ybar.set)
        self.entity_canvas.grid(row=0, column=0, sticky="nsew")
        entity_ybar.grid(row=0, column=1, sticky="ns")
        self.entity_canvas.bind("<Button-1>", self._on_entity_atlas_click)
        self.entity_canvas.bind("<Configure>", self._on_atlas_canvas_configure)

        layers = ttk.Frame(side, padding=6)
        side.add(layers, text="Layers")
        self._build_layers_panel(layers)

        logic = ttk.Frame(side, padding=6)
        side.add(logic, text="Logic")
        self._build_logic_panel(logic)

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
        controls = ttk.Frame(specials)
        controls.pack(fill="x", pady=(8, 0))
        ttk.Button(controls, text="Place selected by map click", command=self._arm_selected_trigger_placement).pack(fill="x")
        ttk.Button(controls, text="Move selected to selected cell", command=self._move_selected_trigger_to_cell).pack(fill="x", pady=(4, 0))
        ttk.Button(controls, text="Clear selected special point", command=self._clear_selected_trigger).pack(fill="x", pady=(4, 0))
        msg_frame = ttk.LabelFrame(specials, text="Message content", padding=6)
        msg_frame.pack(fill="x", pady=(8, 0))
        self.message_combo = ttk.Combobox(msg_frame, state="readonly", textvariable=self.message_id_var, values=self._message_combo_values())
        self.message_combo.pack(fill="x")
        self.message_combo.bind("<<ComboboxSelected>>", self._on_message_content_select)
        ttk.Label(specials, textvariable=self.special_status_var, wraplength=360).pack(fill="x", pady=(8, 0))

    def _build_layers_panel(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        checks = [
            ("Sprite overlay", self.show_sprite_overlay_var),
            ("Object labels", self.show_entities_var),
            ("Special points", self.show_triggers_var),
            ("Teleport + message links", self.show_event_links_var),
            ("Switch to door links", self.show_door_links_var),
            ("Solid mask", self.show_solids_var),
            ("Grid", self.show_grid_var),
            ("Only highlighted", self.show_highlight_only_var),
        ]
        for row, (text, var) in enumerate(checks):
            ttk.Checkbutton(parent, text=text, variable=var, command=self.refresh_map).grid(row=row, column=0, sticky="w", pady=2)
        ttk.Separator(parent).grid(row=len(checks), column=0, sticky="ew", pady=8)
        ttk.Button(parent, text="Clear highlight", command=self.clear_highlight).grid(row=len(checks) + 1, column=0, sticky="ew")

    def _build_logic_panel(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        self.logic_summary = tk.Text(parent, height=6, wrap="word")
        self.logic_summary.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        split = ttk.PanedWindow(parent, orient="vertical")
        split.grid(row=1, column=0, sticky="nsew")
        graph_frame = ttk.LabelFrame(split, text="Level logic", padding=6)
        problem_frame = ttk.LabelFrame(split, text="Warnings", padding=6)
        split.add(graph_frame, weight=2)
        split.add(problem_frame, weight=1)

        self.logic_tree = ttk.Treeview(graph_frame, columns=("type", "detail"), show="tree headings", height=14)
        self.logic_tree.heading("#0", text="Item")
        self.logic_tree.heading("type", text="Type")
        self.logic_tree.heading("detail", text="Detail")
        self.logic_tree.column("#0", width=170)
        self.logic_tree.column("type", width=90)
        self.logic_tree.column("detail", width=260, stretch=True)
        self.logic_tree.pack(fill="both", expand=True)
        self.logic_tree.bind("<<TreeviewSelect>>", self._on_logic_select)

        self.problem_tree = ttk.Treeview(problem_frame, columns=("severity", "detail"), show="headings", height=7)
        self.problem_tree.heading("severity", text="Level")
        self.problem_tree.heading("detail", text="Detail")
        self.problem_tree.column("severity", width=70)
        self.problem_tree.column("detail", width=320, stretch=True)
        self.problem_tree.pack(fill="both", expand=True)

    def _build_logic_workspace(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=6)
        notebook.add(tab, text="LOGIC")
        self._build_logic_panel(tab)

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
        self.asset_tile_canvas = tk.Canvas(tile_tab, background="#282828")
        taxbar = ttk.Scrollbar(tile_tab, orient="horizontal", command=self.asset_tile_canvas.xview)
        taybar = ttk.Scrollbar(tile_tab, orient="vertical", command=self.asset_tile_canvas.yview)
        self.asset_tile_canvas.configure(xscrollcommand=taxbar.set, yscrollcommand=taybar.set)
        self.asset_tile_canvas.grid(row=0, column=0, sticky="nsew")
        self.asset_tile_canvas.bind("<Configure>", self._on_atlas_canvas_configure)
        taybar.grid(row=0, column=1, sticky="ns")
        taxbar.grid(row=1, column=0, sticky="ew")

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

    def _message_combo_values(self) -> list[str]:
        return [f"{message_id}: {text}" for message_id, text in sorted(MESSAGES.items())]

    def _brush_status_var(self) -> tk.StringVar:
        self.brush_status = tk.StringVar(value="Brush layer: tile; tile=0, entity=0, shootable=0")
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
        self.map_entries = self.dat.maps()
        combo_values = []
        for entry in self.map_entries:
            info = map_info(entry.filename)
            combo_values.append(f"{entry.filename:<8}  {info.title}")
        self.map_combo.configure(values=combo_values)
        self.sprite_list.delete(0, tk.END)
        for entry in self.dat.sprites():
            self.sprite_list.insert(tk.END, entry.filename)
        self.refresh_object_browser()
        self.refresh_archive_browser()
        self.status_var.set(f"Loaded {path} ({len(self.dat.entries)} files, {len(self.occurrences)} object/event occurrences)")
        if self.map_entries:
            self.map_combo.current(0)
            self._on_map_select(None)

    def _prime_object_db_from_occurrences(self) -> None:
        for occ in self.occurrences:
            self.object_db.get(occ.kind, occ.object_id, value=occ.value)
        self.object_db.save()

    def _on_map_select(self, _event) -> None:
        if not self.dat:
            return
        index = self.map_combo.current()
        if index < 0 or index >= len(self.map_entries):
            return
        entry = self.map_entries[index]
        try:
            self.current_map = RiptideMap(entry)
            self.current_entry = entry
            self.dirty = False
            self.last_selected_cell = None
            self.selected_trigger_index = None
            self.pending_trigger_index = None
            self.map_base_image = None
            self.map_base_key = None
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
        self.refresh_object_atlases()
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
            py = cy * tile + tile - spr.height - max(1, scale * 3)
        img.alpha_composite(spr, (px, py))

    def refresh_map(self) -> None:
        rmap = self.current_map
        if not rmap or not hasattr(self, "map_canvas"):
            return
        scale = max(1, int(self.scale_var.get()))
        base_key = (id(rmap), scale)
        if self.map_base_image is None or self.map_base_key != base_key:
            self.map_base_image = rmap.render(scale=scale).convert("RGBA")
            self.map_base_key = base_key
        img = self.map_base_image.copy()
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
                if index in MESSAGE_CONTENT_SLOTS:
                    continue
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
        img = self._build_tile_atlas_image(self.tile_canvas)
        self.tile_atlas_photo = ImageTk.PhotoImage(img)
        self.tile_canvas.delete("all")
        self.tile_canvas.create_image(0, 0, image=self.tile_atlas_photo, anchor="nw")
        self.tile_canvas.config(scrollregion=(0, 0, img.width, img.height))
        if hasattr(self, "asset_tile_canvas"):
            asset_img = self._build_tile_atlas_image(self.asset_tile_canvas)
            self.asset_tile_atlas_photo = ImageTk.PhotoImage(asset_img)
            self.asset_tile_canvas.delete("all")
            self.asset_tile_canvas.create_image(0, 0, image=self.asset_tile_atlas_photo, anchor="nw")
            self.asset_tile_canvas.config(scrollregion=(0, 0, asset_img.width, asset_img.height))

    def _canvas_content_width(self, canvas: tk.Canvas, fallback: int) -> int:
        width = canvas.winfo_width()
        return width if width > 1 else fallback

    def _atlas_cols_for_width(self, canvas: tk.Canvas, item_w: int) -> int:
        return max(1, self._canvas_content_width(canvas, item_w) // item_w)

    def _build_tile_atlas_image(self, canvas: tk.Canvas) -> Image.Image:
        rmap = self.current_map
        if not rmap:
            return Image.new("RGBA", (1, 1), (40, 40, 40, 255))
        scale = 4
        tile = 8 * scale
        cols = self._atlas_cols_for_width(canvas, tile)
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
        return img

    def refresh_object_atlases(self) -> None:
        self._atlas_refs.clear()
        self._draw_object_atlas("shootable")
        self._draw_object_atlas("entity")

    def _on_atlas_canvas_configure(self, _event=None) -> None:
        if not self.current_map or self._atlas_resize_after_id is not None:
            return
        self._atlas_resize_after_id = self.after(80, self._refresh_atlases_after_resize)

    def _refresh_atlases_after_resize(self) -> None:
        self._atlas_resize_after_id = None
        self.refresh_tile_atlas()
        self.refresh_object_atlases()

    def _object_ids_for_atlas(self, kind: str) -> list[int]:
        ids = {o.object_id for o in self.occurrences if o.kind == kind}
        ids.update(rec.object_id for rec in self.object_db.records.values() if rec.kind == kind)
        if kind == "shootable":
            ids.update(DOOR_SWITCH_TO_ENTITY.keys())
        return sorted(i for i in ids if i > 0)

    def _draw_object_atlas(self, kind: str) -> None:
        canvas = getattr(self, f"{kind}_canvas", None)
        if canvas is None:
            return
        canvas.delete("all")
        rmap = self.current_map
        if not rmap:
            return
        card_w = 122
        card_h = 104
        pad = 8
        cols = self._atlas_cols_for_width(canvas, card_w)
        selected_id = self.selected_shootable_var.get() if kind == "shootable" else self.selected_entity_var.get()
        object_ids = self._object_ids_for_atlas(kind)
        for idx, object_id in enumerate(object_ids):
            col = idx % cols
            row = idx // cols
            x = pad + col * card_w
            y = pad + row * card_h
            tag = f"atlas:{kind}:{object_id}"
            is_selected = object_id == selected_id and self.active_layer_var.get() == kind
            outline = "#f7d04a" if is_selected else "#5b6470"
            canvas.create_rectangle(x, y, x + card_w - pad, y + card_h - pad, fill="#1f2328", outline=outline, width=2, tags=(tag,))
            rec = self.object_db.get(kind, object_id)
            sprite_name = rec.sprite or (shootable_sprite_name(object_id, True) if kind == "shootable" else entity_sprite_name(object_id, True))
            sprite = self._sprite_first_frame(sprite_name)
            if sprite:
                max_w, max_h = 54, 48
                scale = max(1, min(max_w // max(1, sprite.width), max_h // max(1, sprite.height)))
                preview = sprite.resize((sprite.width * scale, sprite.height * scale), Image.Resampling.NEAREST)
                photo = ImageTk.PhotoImage(preview)
                self._atlas_refs.append(photo)
                canvas.create_image(x + 14 + max_w // 2, y + 8 + max_h // 2, image=photo, anchor="center", tags=(tag,))
            else:
                prefix = "S" if kind == "shootable" else "E"
                canvas.create_rectangle(x + 18, y + 14, x + 66, y + 54, fill="#39414d", outline="#77808d", tags=(tag,))
                canvas.create_text(x + 42, y + 34, text=f"{prefix}{object_id}", fill="white", tags=(tag,))
            name = rec.name or f"{kind.title()} {object_id}"
            drop = shootable_drop_name(object_id) if kind == "shootable" else ""
            display_name = f"Drop: {drop}" if drop else name
            short_name = display_name if len(display_name) <= 18 else display_name[:17] + "..."
            prefix = "S" if kind == "shootable" else "E"
            canvas.create_text(x + 8, y + 64, text=f"{prefix}{object_id}", fill="#f7d04a", anchor="nw", tags=(tag,))
            canvas.create_text(x + 8, y + 82, text=short_name, fill="#e6edf3", anchor="nw", tags=(tag,))
        rows = (len(object_ids) + cols - 1) // cols
        canvas.config(scrollregion=(0, 0, cols * card_w + pad, max(1, rows) * card_h + pad))

    def refresh_triggers(self) -> None:
        for item in self.trigger_tree.get_children():
            self.trigger_tree.delete(item)
        rmap = self.current_map
        if not rmap:
            return
        for index in SPECIAL_TRIGGER_SLOTS:
            if index >= len(rmap.triggers):
                continue
            value = rmap.triggers[index]
            if index in MESSAGE_CONTENT_SLOTS:
                x_text = "-"
                y_text = "-"
                label = trigger_name(index, value)
            elif value:
                x, y = rmap.trigger_xy(value)
                x_text = str(x)
                y_text = str(y)
                label = trigger_name(index, value)
            else:
                x_text = ""
                y_text = ""
                label = trigger_name(index, value)
            value_text = str(value) if value else ""
            self.trigger_tree.insert("", "end", iid=f"trigger:{index}", values=(index, value_text, x_text, y_text, label))
            if self.selected_trigger_index == index:
                self.trigger_tree.selection_set(f"trigger:{index}")

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
                self.quick_object_tree.insert("", "end", iid=f"quick:{kind}:{object_id}", values=(kind, object_id, object_display_name(kind, object_id, rec.name)))
                seen.add((kind, object_id))
        for sid in sorted(DOOR_SWITCH_TO_ENTITY):
            if ("shootable", sid) not in seen:
                rec = self.object_db.get("shootable", sid)
                self.quick_object_tree.insert("", "end", iid=f"quick:shootable:{sid}", values=("shootable", sid, object_display_name("shootable", sid, rec.name)))

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
            self.object_tree.insert("", "end", iid=f"{kind}:{object_id}", values=(kind, object_id, count, rec.category, rec.sprite, object_display_name(kind, object_id, rec.name)))

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
                self.logic_tree.insert(obj_parent, "end", iid=f"logic:counts:{kind}:{object_id}", text=f"{kind[0].upper()}{object_id}", values=(rec.category, f"{count}x {object_display_name(kind, object_id, rec.name)}"))

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
            if index in MESSAGE_CONTENT_SLOTS:
                continue
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
        if self.tool_var.get() == "move":
            self.map_canvas.scan_mark(event.x, event.y)
            return
        self._drag_seen.clear()
        cell_xy = self._canvas_to_cell(event)
        if cell_xy and self.pending_trigger_index is not None:
            self._place_pending_trigger(*cell_xy)
            return
        if cell_xy:
            self._handle_cell_action(*cell_xy)

    def _on_map_drag(self, event) -> None:
        if self.tool_var.get() == "move":
            self.map_canvas.scan_dragto(event.x, event.y, gain=1)
            return
        if self.tool_var.get() in ("brush", "pick"):
            cell_xy = self._canvas_to_cell(event)
            if cell_xy:
                self._handle_cell_action(*cell_xy)

    def _on_map_release(self, _event) -> None:
        self._drag_seen.clear()

    def _on_map_right_click(self, event) -> None:
        self._drag_seen.clear()
        cell_xy = self._canvas_to_cell(event)
        if cell_xy:
            self._erase_cell_layer(*cell_xy)

    def _on_map_right_drag(self, event) -> None:
        cell_xy = self._canvas_to_cell(event)
        if cell_xy:
            self._erase_cell_layer(*cell_xy)

    def _on_map_motion(self, event) -> None:
        cell_xy = self._canvas_to_cell(event)
        if cell_xy and self.pending_trigger_index is not None:
            self._show_special_preview(*cell_xy)
        elif cell_xy and self.tool_var.get() == "brush":
            self._show_brush_preview(*cell_xy)
        else:
            self._clear_preview()

    def _handle_cell_action(self, x: int, y: int) -> None:
        rmap = self.current_map
        if not rmap:
            return
        tool = self.tool_var.get()
        layer = self.active_layer_var.get()
        if tool == "brush":
            key = (layer, x, y)
            if key in self._drag_seen:
                return
            self._drag_seen.add(key)
            if layer == "tile":
                rmap.set_cell(x, y, tile_id=self.selected_tile_var.get())
                self._mark_level_changed(tile_changed=True, tile_cell=(x, y))
            elif layer == "entity":
                rmap.set_cell(x, y, entity_id=self.selected_entity_var.get())
                self._mark_level_changed()
            elif layer == "shootable":
                rmap.set_cell(x, y, shootable_id=self.selected_shootable_var.get())
                self._mark_level_changed()
        elif tool == "pick":
            cell = rmap.cell(x, y)
            self.selected_tile_var.set(cell.tile_id)
            self.selected_entity_var.set(cell.entity_id)
            self.selected_shootable_var.set(cell.shootable_id)
            self.refresh_tile_atlas()
            self.refresh_object_atlases()
        if tool in ("select", "pick", "brush"):
            self.select_cell(x, y)
        if tool in ("select", "pick"):
            self.refresh_map()
        self._update_brush_status()

    def _erase_cell_layer(self, x: int, y: int) -> None:
        rmap = self.current_map
        if not rmap:
            return
        layer = self.active_layer_var.get()
        key = ("erase", layer, x, y)
        if key in self._drag_seen:
            return
        self._drag_seen.add(key)
        if layer == "tile":
            rmap.set_cell(x, y, tile_id=ERASE_TILE_ID)
            self._mark_level_changed(tile_changed=True, tile_cell=(x, y))
        elif layer == "entity":
            rmap.set_cell(x, y, entity_id=0)
            self._mark_level_changed()
        elif layer == "shootable":
            rmap.set_cell(x, y, shootable_id=0)
            self._mark_level_changed()
        self.select_cell(x, y)
        self._update_brush_status()

    def _mark_level_changed(self, *, tile_changed: bool = False, tile_cell: tuple[int, int] | None = None) -> None:
        self.dirty = True
        if tile_changed:
            if tile_cell is None:
                self.map_base_image = None
                self.map_base_key = None
            else:
                self._update_base_tile(*tile_cell)
        self._schedule_map_refresh()
        if not tile_changed:
            self._schedule_metadata_refresh()

    def _update_base_tile(self, x: int, y: int) -> None:
        rmap = self.current_map
        if not rmap or self.map_base_image is None:
            return
        scale = max(1, int(self.scale_var.get()))
        if self.map_base_key != (id(rmap), scale):
            return
        tile = 8 * scale
        tile_img = rmap.tile_image(rmap.cell(x, y).tile_id, scale=scale).convert("RGBA")
        self.map_base_image.paste(tile_img, (x * tile, y * tile))

    def _mark_specials_changed(self) -> None:
        self.dirty = True
        self.occurrences = scan_archive(self.dat) if self.dat else []
        self.refresh_triggers()
        self.refresh_logic_workspace()
        self.refresh_object_browser()
        self.refresh_map()

    def _schedule_map_refresh(self) -> None:
        if self._refresh_after_id:
            return
        self._refresh_after_id = self.after(25, self._run_scheduled_map_refresh)

    def _run_scheduled_map_refresh(self) -> None:
        self._refresh_after_id = None
        self.refresh_map()

    def _schedule_metadata_refresh(self) -> None:
        if self._metadata_after_id:
            self.after_cancel(self._metadata_after_id)
        self._metadata_after_id = self.after(250, self._run_scheduled_metadata_refresh)

    def _run_scheduled_metadata_refresh(self) -> None:
        self._metadata_after_id = None
        self.occurrences = scan_archive(self.dat) if self.dat else []
        self.refresh_object_browser()
        self.refresh_quick_objects()
        self.refresh_logic_workspace()
        self.refresh_object_atlases()

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
        trigger_hits = [
            f"T{idx}: {trigger_name(idx, value)}"
            for idx, value, tx, ty, _even in rmap.nonzero_triggers()
            if idx not in MESSAGE_CONTENT_SLOTS and tx == x and ty == y
        ]
        lines = [
            f"Cell: x={x}, y={y}",
            f"Tile: {cell.tile_id} ({'solid' if cell.is_solid else 'passable/background'})",
            f"Shootable: S{cell.shootable_id}" + (f" — {shootable_sprite}" if shootable_sprite else ""),
            f"Entity: E{cell.entity_id}" + (f" — {entity_sprite}" if entity_sprite else ""),
        ]
        if cell.shootable_id in SHOOTABLE_INFO:
            lines.append(f"Shootable info: {SHOOTABLE_INFO[cell.shootable_id]}")
        drop = shootable_drop_name(cell.shootable_id)
        if drop:
            lines.append(f"Shootable drop: {drop}")
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
        self.map_base_image = None
        self.map_base_key = None
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
            self.brush_status.set(
                f"Brush layer: {self.active_layer_var.get()}; "
                f"tile={self.selected_tile_var.get()}, "
                f"entity={self.selected_entity_var.get()}, "
                f"shootable={self.selected_shootable_var.get()}"
            )

    def _on_tile_atlas_click(self, event) -> None:
        scale = 4
        tile = 8 * scale
        cols = self._atlas_cols_for_width(self.tile_canvas, tile)
        label_h = 16
        y_canvas = int(self.tile_canvas.canvasy(event.y)) - 24
        if y_canvas < 0:
            return
        x = int(self.tile_canvas.canvasx(event.x) // tile)
        y = int(y_canvas // (tile + label_h))
        tile_id = y * cols + x
        if 0 <= tile_id < 512:
            self.selected_tile_var.set(tile_id)
            self.active_layer_var.set("tile")
            self.tool_var.set("brush")
            self.refresh_tile_atlas()
            self.refresh_object_atlases()
            self._update_brush_status()
            self.status_var.set(f"Selected tile {tile_id} for tile brush")

    def _on_shootable_atlas_click(self, event) -> None:
        self._select_object_from_atlas(event, "shootable")

    def _on_entity_atlas_click(self, event) -> None:
        self._select_object_from_atlas(event, "entity")

    def _select_object_from_atlas(self, event, kind: str) -> None:
        canvas = event.widget
        current = canvas.find_withtag("current")
        if not current:
            return
        tags = canvas.gettags(current[0])
        tag = next((t for t in tags if t.startswith(f"atlas:{kind}:")), "")
        if not tag:
            return
        object_id = int(tag.rsplit(":", 1)[1])
        self._select_atlas_object(kind, object_id)

    def _select_atlas_object(self, kind: str, object_id: int) -> None:
        self.active_layer_var.set(kind)
        self.tool_var.set("brush")
        if kind == "shootable":
            self.selected_shootable_var.set(object_id)
        elif kind == "entity":
            self.selected_entity_var.set(object_id)
        self.highlight = (kind, object_id)
        self.refresh_object_atlases()
        self.refresh_map()
        self._update_brush_status()
        rec = self.object_db.get(kind, object_id)
        prefix = "S" if kind == "shootable" else "E"
        self.status_var.set(f"Brush: {prefix}{object_id} {object_display_name(kind, object_id, rec.name)}")

    def _on_editor_side_tab_changed(self, _event) -> None:
        if not hasattr(self, "editor_side_notebook"):
            return
        tab_text = self.editor_side_notebook.tab(self.editor_side_notebook.select(), "text")
        if tab_text == "Tiles":
            self.active_layer_var.set("tile")
        elif tab_text == "Shootables":
            self.active_layer_var.set("shootable")
        elif tab_text == "Entities":
            self.active_layer_var.set("entity")
        elif tab_text == "Specials":
            self.active_layer_var.set("special")
        self._update_brush_status()

    def _clear_preview(self, _event=None) -> None:
        if hasattr(self, "map_canvas"):
            self.map_canvas.delete("brush_preview")
        self._preview_items.clear()
        self._preview_photo = None

    def _show_brush_preview(self, x: int, y: int) -> None:
        rmap = self.current_map
        if not rmap:
            return
        self._clear_preview()
        scale = max(1, int(self.scale_var.get()))
        tile = 8 * scale
        px, py = x * tile, y * tile
        layer = self.active_layer_var.get()
        img = self._brush_preview_image(layer, x, y, scale)
        if img:
            self._preview_photo = ImageTk.PhotoImage(img)
            offset_x = px
            offset_y = py
            if layer == "entity":
                offset_x = px + tile // 2 - img.width // 2
                offset_y = py + tile - img.height
            elif layer == "shootable":
                offset_x = px + tile // 2 - img.width // 2
                offset_y = py + tile - img.height - max(1, scale * 3)
            self.map_canvas.create_image(offset_x, offset_y, image=self._preview_photo, anchor="nw", tags=("brush_preview",))
        self.map_canvas.create_rectangle(px, py, px + tile - 1, py + tile - 1, outline="#f7d04a", width=max(2, scale), tags=("brush_preview",))

    def _show_special_preview(self, x: int, y: int) -> None:
        self._clear_preview()
        scale = max(1, int(self.scale_var.get()))
        tile = 8 * scale
        px, py = x * tile, y * tile
        index = self.pending_trigger_index
        label = f"T{index}" if index is not None else "T"
        self.map_canvas.create_oval(px + 2, py + 2, px + tile - 3, py + tile - 3, outline="#f7d04a", width=max(2, scale), tags=("brush_preview",))
        self.map_canvas.create_text(px + tile // 2, py + tile // 2, text=label, fill="#ffffff", tags=("brush_preview",))

    def _brush_preview_image(self, layer: str, x: int, y: int, scale: int) -> Image.Image | None:
        rmap = self.current_map
        if not rmap:
            return None
        if layer == "tile":
            img = rmap.tile_image(self.selected_tile_var.get(), scale=scale).convert("RGBA")
        else:
            even = ((y * rmap.width + x) % 2) == 0
            if layer == "shootable":
                sprite_name = shootable_sprite_name(self.selected_shootable_var.get(), even)
            elif layer == "entity":
                sprite_name = entity_sprite_name(self.selected_entity_var.get(), even)
            else:
                return None
            sprite = self._sprite_first_frame(sprite_name)
            if not sprite:
                return None
            img = sprite.resize((sprite.width * scale, sprite.height * scale), Image.Resampling.NEAREST).convert("RGBA")
        alpha = img.getchannel("A").point(lambda value: min(value, 145))
        img.putalpha(alpha)
        return img

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
        drop = shootable_drop_name(object_id) if kind == "shootable" else ""
        drop_line = f"Drop: {drop}\n" if drop else ""
        self.object_detail.delete("1.0", tk.END)
        self.object_detail.insert(tk.END, f"{kind} {object_id}\nName: {rec.name}\n{drop_line}Category: {rec.category}\nSprite: {rec.sprite or '-'}\nInfo: {rec.info or '-'}\nNotes: {rec.notes or '-'}\nConfidence: {rec.confidence}\n")
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
            self.active_layer_var.set("entity")
        elif kind == "shootable":
            self.selected_shootable_var.set(object_id)
            self.active_layer_var.set("shootable")
        self.tool_var.set("brush")
        self.refresh_object_atlases()
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
            self.highlight = ("trigger", self.selected_trigger_index)
            self._sync_message_combo_from_trigger()
            if self.selected_trigger_index not in MESSAGE_CONTENT_SLOTS and value:
                x, y = self.current_map.trigger_xy(value)
                if 0 <= x < self.current_map.width and 0 <= y < self.current_map.height:
                    self.select_cell(x, y)
                    self._scroll_to_cell(x, y)
            self.special_status_var.set(f"Selected T{self.selected_trigger_index}: {trigger_name(self.selected_trigger_index, value)}")
            self.refresh_map()

    def _selected_trigger_index_from_tree(self) -> int | None:
        selected = self.trigger_tree.selection()
        if not selected:
            return self.selected_trigger_index
        iid = selected[0]
        if iid.startswith("trigger:"):
            return int(iid.split(":", 1)[1])
        return None

    def _arm_selected_trigger_placement(self) -> None:
        index = self._selected_trigger_index_from_tree()
        if index is None:
            self.special_status_var.set("Select a special point first")
            return
        if index in MESSAGE_CONTENT_SLOTS:
            self.special_status_var.set("This row stores message text, not a map position")
            return
        self.pending_trigger_index = index
        self.highlight = ("trigger", index)
        self.tool_var.set("select")
        self.workspace.select(0)
        self.special_status_var.set(f"Click the map to place T{index}: {trigger_name(index, self.current_map.triggers[index] if self.current_map else 0)}")
        self.refresh_map()

    def _move_selected_trigger_to_cell(self) -> None:
        if not self.last_selected_cell:
            self.special_status_var.set("Select a map cell first")
            return
        index = self._selected_trigger_index_from_tree()
        if index is None:
            self.special_status_var.set("Select a special point first")
            return
        if index in MESSAGE_CONTENT_SLOTS:
            self.special_status_var.set("This row stores message text, not a map position")
            return
        self._set_trigger_xy(index, *self.last_selected_cell)

    def _clear_selected_trigger(self) -> None:
        if not self.current_map:
            return
        index = self._selected_trigger_index_from_tree()
        if index is None:
            self.special_status_var.set("Select a special point first")
            return
        self.current_map.set_trigger(index, 0)
        self.pending_trigger_index = None
        self.highlight = ("trigger", index)
        self.special_status_var.set(f"Cleared T{index}")
        self._mark_specials_changed()

    def _place_pending_trigger(self, x: int, y: int) -> None:
        index = self.pending_trigger_index
        if index is None:
            return
        self.pending_trigger_index = None
        self._set_trigger_xy(index, x, y)

    def _set_trigger_xy(self, index: int, x: int, y: int) -> None:
        if not self.current_map:
            return
        self.current_map.set_trigger_xy(index, x, y)
        self.selected_trigger_index = index
        self.highlight = ("trigger", index)
        self.select_cell(x, y)
        self.special_status_var.set(f"Moved T{index} to {x},{y}: {trigger_name(index, self.current_map.triggers[index])}")
        self._mark_specials_changed()

    def _sync_message_combo_from_trigger(self) -> None:
        if not self.current_map:
            return
        content_index = self._message_content_index_for_selected()
        if content_index is None:
            return
        value = self.current_map.triggers[content_index]
        self.message_id_var.set(f"{value}: {message_by_id(value)}")

    def _message_content_index_for_selected(self) -> int | None:
        index = self.selected_trigger_index
        if index is None:
            return None
        if index in MESSAGE_CONTENT_SLOTS:
            return index
        return MESSAGE_POSITION_TO_CONTENT.get(index)

    def _on_message_content_select(self, _event) -> None:
        if not self.current_map:
            return
        content_index = self._message_content_index_for_selected()
        if content_index is None:
            self.special_status_var.set("Select a message position/content row first")
            return
        raw = self.message_id_var.get().split(":", 1)[0].strip()
        try:
            message_id = int(raw)
        except ValueError:
            return
        self.current_map.set_trigger(content_index, message_id)
        self.selected_trigger_index = content_index
        self.highlight = ("trigger", content_index)
        self.special_status_var.set(f"Set T{content_index} message to {message_id}: {message_by_id(message_id)}")
        self._mark_specials_changed()

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
        for idx, entry in enumerate(self.map_entries or self.dat.maps()):
            if entry.filename == map_name:
                self.map_combo.current(idx)
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
        self.workspace.select(0)
        if hasattr(self, "editor_side_notebook"):
            for idx in range(self.editor_side_notebook.index("end")):
                if self.editor_side_notebook.tab(idx, "text") == "Logic":
                    self.editor_side_notebook.select(idx)
                    break
        self.status_var.set("Validation refreshed in the Logic panel")

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
