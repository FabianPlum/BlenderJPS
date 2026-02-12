"""
BlenderJPS Operators
Operators for loading JuPedSim trajectory and geometry data.
"""

import os
import pathlib
import sqlite3
import threading
import time
import traceback
from array import array

import bmesh
import bpy
from bpy.props import StringProperty
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper

from . import install_utils

STREAM_STATE = {
    "db_path": None,
    "conn": None,
    "min_frame": 0,
    "max_frame": 0,
    "frame_step": 1,
    "agent_ids": [],
    "id_to_index": {},
    "mode": None,  # "default" or "big"
    "objects": [],
    "object_name": None,
    "handler_installed": False,
}

ADDON_DIR = os.path.dirname(os.path.realpath(__file__))


def _stream_frame_handler(scene):
    """Stream positions from sqlite for the current frame."""
    state = STREAM_STATE
    if not state["db_path"] or not state["agent_ids"]:
        return
    blender_frame = scene.frame_current
    # When frame_step > 1, Blender frame F shows SQLite frame F * frame_step (e.g. Blender 1 → SQLite 10).
    step = state["frame_step"]
    db_frame = blender_frame if step <= 1 else blender_frame * step
    if db_frame < state["min_frame"] or db_frame > state["max_frame"]:
        return

    if state["conn"] is None:
        state["conn"] = sqlite3.connect(state["db_path"], isolation_level=None)

    cur = state["conn"].cursor()
    res = cur.execute(
        "SELECT id, pos_x, pos_y FROM trajectory_data WHERE frame == (?) ORDER BY id ASC",
        (db_frame,),
    )
    rows = res.fetchall()

    if state["mode"] == "big":
        obj = bpy.data.objects.get(state["object_name"])
        if not obj or obj.type != "MESH":
            return
        total = len(state["agent_ids"])
        hide_z = -1.0e6
        coords = array("f", [0.0] * (total * 3))
        for i in range(2, len(coords), 3):
            coords[i] = hide_z
        for agent_id, x, y in rows:
            idx = state["id_to_index"].get(agent_id)
            if idx is None:
                continue
            base = idx * 3
            coords[base] = float(x)
            coords[base + 1] = float(y)
            coords[base + 2] = 0.5
        obj.data.vertices.foreach_set("co", coords)
        obj.data.update()
        return

    # Default mode: update agent objects directly.
    for obj in state["objects"]:
        obj.hide_viewport = True
        obj.hide_render = True
    for agent_id, x, y in rows:
        idx = state["id_to_index"].get(agent_id)
        if idx is None:
            continue
        obj = state["objects"][idx]
        obj.location = (float(x), float(y), 0.5)
        obj.hide_viewport = False
        obj.hide_render = False


def check_dependencies():
    """Check if required dependencies are installed."""
    import importlib.util

    install_utils.ensure_deps_in_path(ADDON_DIR)
    if importlib.util.find_spec("shapely") is None:
        return False, "shapely not found"
    return True, None


class JUPEDSIM_OT_select_file(Operator, ImportHelper):
    """Select a JuPedSim SQLite trajectory file."""

    bl_idname = "jupedsim.select_file"
    bl_label = "Select SQLite File"
    bl_description = "Browse for a JuPedSim trajectory SQLite file"

    filter_glob: StringProperty(
        default="*.sqlite;*.db",
        options={"HIDDEN"},
    )

    def execute(self, context):
        """Store the selected SQLite file path in the scene properties."""
        context.scene.jupedsim_props.sqlite_file = self.filepath
        self.report({"INFO"}, f"Selected file: {self.filepath}")
        return {"FINISHED"}


class JUPEDSIM_OT_load_simulation(Operator):
    """Load simulation data from the selected SQLite file."""

    bl_idname = "jupedsim.load_simulation"
    bl_label = "Load Simulation"
    bl_description = "Load agent trajectories and geometry from the SQLite file"
    bl_options = {"REGISTER", "UNDO"}

    _timer = None
    _worker_thread = None
    _worker_done = False
    _worker_error = None
    _worker_data = None
    _worker_timings = None
    _worker_traceback = None
    _cancel_event = None
    _cancelled = False
    _timings = None
    _agent_groups = None
    _agent_index = 0
    _path_index = 0
    _frame_step = 1
    _min_frame = 0
    _max_frame = 0
    _sampled_frames = None
    _agents_collection = None
    _geometry_collection = None
    _total_agents = 0
    _stage = None
    _big_data_mode = False
    _load_full_paths = False
    _path_groups = None
    _materials = None

    def execute(self, context):
        """Start a modal load that keeps the UI responsive."""
        # Check dependencies first
        deps_ok, error = check_dependencies()
        if not deps_ok:
            self.report({"ERROR"}, f"Missing dependencies: {error}")
            self.report({"ERROR"}, "Please install dependencies in addon preferences.")
            return {"CANCELLED"}

        props = context.scene.jupedsim_props
        if props.loading_in_progress:
            self.report({"WARNING"}, "A load is already in progress")
            return {"CANCELLED"}

        # Get file path
        filepath = props.sqlite_file
        if not filepath:
            self.report({"ERROR"}, "No SQLite file selected")
            return {"CANCELLED"}

        filepath = bpy.path.abspath(filepath)
        path = pathlib.Path(filepath)

        if not path.exists():
            self.report({"ERROR"}, f"File not found: {filepath}")
            return {"CANCELLED"}

        self._reset_state()
        self._frame_step = props.frame_step
        self._big_data_mode = props.big_data_mode
        self._load_full_paths = props.load_full_paths
        self._cancel_event = threading.Event()
        props.loading_in_progress = True
        props.loading_progress = 0.0
        props.loading_message = "Starting load..."
        self._stage = "loading_sqlite"

        # Start worker thread for SQLite loading
        self._worker_thread = threading.Thread(
            target=self._load_sqlite_worker,
            args=(path, self._frame_step, self._cancel_event),
            daemon=True,
        )
        self._worker_thread.start()

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        """Advance loading stages and update progress."""
        props = context.scene.jupedsim_props

        if event.type == "ESC":
            self._cancelled = True
            if self._cancel_event:
                self._cancel_event.set()
            props.loading_message = "Cancelling..."
            return self._finish_cancel(context)

        if event.type != "TIMER":
            return {"RUNNING_MODAL"}

        if self._cancelled:
            return self._finish_cancel(context)

        # Update progress while waiting for worker
        if self._stage == "loading_sqlite":
            props.loading_message = "Loading trajectory data..."
            props.loading_progress = 5.0
            if self._worker_done:
                if self._worker_error:
                    self.report({"ERROR"}, f"Failed to load simulation: {self._worker_error}")
                    self._print_worker_traceback()
                    return self._finish_cancel(context)
                self._apply_worker_data(context)
                props.loading_message = "Trajectory loaded"
                props.loading_progress = 20.0
                self._stage = "create_collections"

        if self._stage == "create_collections":
            self._timed_start("create_collections")
            self._agents_collection = self._get_or_create_collection("JuPedSim_Agents")
            self._geometry_collection = self._get_or_create_collection("JuPedSim_Geometry")
            self._timed_end("create_collections")
            props.loading_message = "Preparing scene..."
            props.loading_progress = 10.0
            self._stage = "create_geometry"

        if self._stage == "create_geometry":
            self._timed_start("create_geometry")
            self._create_geometry(context, self._worker_data["geometry"], self._geometry_collection)
            self._timed_end("create_geometry")
            props.loading_message = "Creating geometry..."
            props.loading_progress = 25.0
            self._stage = "create_big_data" if self._big_data_mode else "create_agents"

        if self._stage == "create_agents":
            props.loading_message = "Creating agents..."
            if self._step_create_agents(context):
                self._timed_end("create_agents")
                self._stage = "create_paths" if self._load_full_paths else "finalize"

        if self._stage == "create_big_data":
            props.loading_message = "Building frame buffers..."
            props.loading_progress = 60.0
            self._timed_start("create_big_data")
            self._create_big_data_points(context)
            self._timed_end("create_big_data")
            props.loading_message = "Creating particle points..."
            props.loading_progress = 90.0
            self._stage = "finalize"

        if self._stage == "create_paths":
            props.loading_message = "Creating agent paths..."
            if self._step_create_paths(context):
                self._timed_end("create_paths")
                self._stage = "finalize"

        if self._stage == "finalize":
            self._timed_start("finalize")
            show_paths = props.show_paths
            self._update_path_visibility(self._agents_collection, show_paths)
            if not self._big_data_mode:
                objects = []
                for agent_id in self._agent_groups:
                    obj = bpy.data.objects.get(f"Agent_{agent_id}")
                    if obj:
                        objects.append(obj)
                self._start_streaming("default", objects=objects)
            context.scene.frame_set(1)
            self._timed_end("finalize")
            props.loading_progress = 100.0
            props.loading_message = "Load complete"
            self._log_timings()
            self.report({"INFO"}, "Simulation loaded successfully!")
            return self._finish_success(context)

        return {"RUNNING_MODAL"}

    def _reset_state(self):
        """Reset modal state for a new load."""
        self._worker_thread = None
        self._worker_done = False
        self._worker_error = None
        self._worker_data = None
        self._worker_timings = None
        self._worker_traceback = None
        self._cancel_event = None
        self._cancelled = False
        self._timings = {}
        self._agent_groups = None
        self._agent_index = 0
        self._path_index = 0
        self._frame_step = 1
        self._min_frame = 0
        self._max_frame = 0
        self._sampled_frames = None
        self._agents_collection = None
        self._geometry_collection = None
        self._total_agents = 0
        self._stage = None
        self._big_data_mode = False
        self._load_full_paths = False
        self._path_groups = None
        self._materials = None
        self._clear_stream_state()

    def _finish_success(self, context):
        """Finalize a successful load."""
        self._cleanup_timer(context)
        props = context.scene.jupedsim_props
        props.loading_in_progress = False
        return {"FINISHED"}

    def _finish_cancel(self, context):
        """Finalize a cancelled load while keeping partial data."""
        self._cleanup_timer(context)
        self._finalize_timings_on_cancel()
        self._log_timings()
        props = context.scene.jupedsim_props
        props.loading_in_progress = False
        props.loading_message = "Load cancelled (partial data kept)"
        return {"CANCELLED"}

    def _cleanup_timer(self, context):
        """Remove the modal timer."""
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None

    def _finalize_timings_on_cancel(self):
        for key, value in (self._worker_timings or {}).items():
            if key not in self._timings:
                self._timings[key] = value
        for key, value in list(self._timings.items()):
            if value < 0:
                self._timings[key] = time.perf_counter() + value
                print(f"[BlenderJPS] {key} took {self._timings[key]:.3f}s (cancelled)")

    def _load_sqlite_worker(self, path, frame_step, cancel_event):
        """Load metadata and geometry in a worker thread to keep UI responsive."""
        import shapely

        conn = None
        try:
            timings = {}
            start_total = time.perf_counter()

            start = time.perf_counter()
            conn = sqlite3.connect(str(path), isolation_level=None)
            timings["open_sqlite"] = time.perf_counter() - start
            if cancel_event.is_set():
                self._worker_timings = timings
                self._worker_done = True
                return

            start = time.perf_counter()
            cur = conn.cursor()
            res = cur.execute("SELECT wkt FROM geometry")
            geometries = [shapely.from_wkt(s[0]) for s in res.fetchall()]
            geometry = shapely.union_all(geometries)
            timings["load_geometry_sqlite"] = time.perf_counter() - start
            if cancel_event.is_set():
                self._worker_timings = timings
                self._worker_done = True
                return

            start = time.perf_counter()
            res = cur.execute("SELECT MIN(frame), MAX(frame) FROM trajectory_data")
            min_frame, max_frame = res.fetchone()
            min_frame = int(min_frame) if min_frame is not None else 0
            max_frame = int(max_frame) if max_frame is not None else 0
            timings["read_frame_range"] = time.perf_counter() - start
            if cancel_event.is_set():
                self._worker_timings = timings
                self._worker_done = True
                return

            start = time.perf_counter()
            res = cur.execute("SELECT DISTINCT id FROM trajectory_data ORDER BY id ASC")
            agent_ids = [row[0] for row in res.fetchall()]
            timings["read_agent_ids"] = time.perf_counter() - start
            if cancel_event.is_set():
                self._worker_timings = timings
                self._worker_done = True
                return

            path_groups = None
            if self._load_full_paths:
                start = time.perf_counter()
                path_groups = self._load_full_path_groups(cur, frame_step)
                timings["load_full_paths"] = time.perf_counter() - start

            start = time.perf_counter()
            res = cur.execute("SELECT value FROM metadata WHERE key == 'fps'")
            fps = float(res.fetchone()[0])
            res = cur.execute("SELECT count(*) FROM frame_data")
            num_frames = int(res.fetchone()[0])
            timings["read_metadata"] = time.perf_counter() - start

            timings["load_sqlite_total"] = time.perf_counter() - start_total

            self._worker_data = {
                "geometry": geometry,
                "agent_ids": agent_ids,
                "min_frame": min_frame,
                "max_frame": max_frame,
                "fps": fps,
                "num_frames": num_frames,
                "db_path": str(path),
                "path_groups": path_groups,
            }
            self._worker_timings = timings
            self._worker_done = True
        except Exception as e:
            self._worker_error = str(e)
            self._worker_traceback = traceback.format_exc()
            self._worker_done = True
        finally:
            if conn is not None:
                conn.close()

    def _apply_worker_data(self, context):
        """Apply worker results to the modal state."""
        self._agent_groups = self._worker_data["agent_ids"]
        self._total_agents = len(self._agent_groups)
        self._min_frame = self._worker_data["min_frame"]
        self._max_frame = self._worker_data["max_frame"]
        self._sampled_frames = set()
        self._path_groups = self._worker_data.get("path_groups")
        context.scene.jupedsim_props.loaded_agent_count = self._total_agents
        # When frame_step > 1, map Blender timeline so frame F shows SQLite frame F*step (e.g. 1→10, 2→20).
        step = self._frame_step
        if step > 1:
            context.scene.frame_start = 1
            context.scene.frame_end = max(1, self._max_frame // step)
        else:
            context.scene.frame_start = self._min_frame
            context.scene.frame_end = self._max_frame
        for key, value in (self._worker_timings or {}).items():
            self._timings[key] = value
        if not self._big_data_mode:
            self._timed_start("create_agents")

    def _get_or_create_material(self, name, rgba):
        """Get or create a simple material with a viewport color."""
        if self._materials is None:
            self._materials = {}
        if name in self._materials:
            return self._materials[name]
        mat = bpy.data.materials.get(name)
        if mat is None:
            mat = bpy.data.materials.new(name=name)
        mat.use_nodes = False
        mat.diffuse_color = rgba
        self._materials[name] = mat
        return mat

    def _assign_material(self, obj, material):
        """Assign a single material to an object's data."""
        if not obj or not material:
            return
        if hasattr(obj.data, "materials"):
            obj.data.materials.clear()
            obj.data.materials.append(material)

    def _step_create_agents(self, context):
        """Create a small batch of agent objects per tick."""
        if self._agent_groups is None:
            return True
        if self._agent_index == 0:
            self.report(
                {"INFO"},
                f"Creating {self._total_agents} agents (every {self._frame_step} frame(s))...",
            )
        chunk_size = 10
        start = self._agent_index
        end = min(self._total_agents, start + chunk_size)
        for idx in range(start, end):
            agent_id = self._agent_groups[idx]
            self._create_agent(context, agent_id, self._agents_collection)
        self._agent_index = end
        progress = 25.0 + (self._agent_index / max(1, self._total_agents)) * 45.0
        context.scene.jupedsim_props.loading_progress = min(progress, 70.0)
        if self._agent_index >= self._total_agents:
            return True
        return False

    def _step_create_paths(self, context):
        """Create a small batch of agent path curves per tick."""
        if not self._path_groups:
            return True
        if self._path_index == 0:
            self._timed_start("create_paths")
        chunk_size = 10
        start = self._path_index
        end = min(len(self._path_groups), start + chunk_size)
        for idx in range(start, end):
            agent_id, coords = self._path_groups[idx]
            self._create_agent_path(context, agent_id, coords, self._agents_collection)
        self._path_index = end
        progress = 70.0 + (self._path_index / max(1, len(self._path_groups))) * 25.0
        context.scene.jupedsim_props.loading_progress = min(progress, 95.0)
        if self._path_index >= len(self._path_groups):
            return True
        return False

    def _timed_start(self, name):
        """Start a named timing section."""
        self._timings[name] = -time.perf_counter()

    def _timed_end(self, name):
        """Stop a named timing section and log it."""
        if name in self._timings:
            self._timings[name] = time.perf_counter() + self._timings[name]
            print(f"[BlenderJPS] {name} took {self._timings[name]:.3f}s")

    def _log_timings(self):
        """Print the timing summary."""
        print("[BlenderJPS] Timing summary:")
        for key, value in self._timings.items():
            print(f"  - {key}: {value:.3f}s")

    def _print_worker_traceback(self):
        """Print worker thread traceback if available."""
        trace = getattr(self, "_worker_traceback", None)
        if trace:
            print(trace)

    def _start_streaming(self, mode, objects=None, object_name=None):
        """Register streaming handler and state."""
        STREAM_STATE["db_path"] = self._worker_data["db_path"]
        STREAM_STATE["min_frame"] = self._min_frame
        STREAM_STATE["max_frame"] = self._max_frame
        STREAM_STATE["frame_step"] = self._frame_step
        STREAM_STATE["agent_ids"] = list(self._agent_groups)
        STREAM_STATE["id_to_index"] = {
            agent_id: idx for idx, agent_id in enumerate(self._agent_groups)
        }
        STREAM_STATE["mode"] = mode
        STREAM_STATE["objects"] = objects or []
        STREAM_STATE["object_name"] = object_name
        if not STREAM_STATE["handler_installed"]:
            bpy.app.handlers.frame_change_pre.append(_stream_frame_handler)
            STREAM_STATE["handler_installed"] = True

    def _load_full_path_groups(self, cursor, frame_step):
        """Load full path coordinates per agent using SQLite cursor."""
        res = cursor.execute(
            "SELECT id, frame, pos_x, pos_y FROM trajectory_data ORDER BY id ASC, frame ASC"
        )
        paths = {}
        for agent_id, frame, x, y in res.fetchall():
            if frame_step > 1 and frame % frame_step != 0:
                continue
            paths.setdefault(agent_id, []).append((float(x), float(y), 0.0))
        return [(agent_id, coords) for agent_id, coords in paths.items()]

    def _clear_stream_state(self):
        """Remove frame handlers and clear streaming buffers."""
        if STREAM_STATE["handler_installed"]:
            if _stream_frame_handler in bpy.app.handlers.frame_change_pre:
                bpy.app.handlers.frame_change_pre.remove(_stream_frame_handler)
        if STREAM_STATE["conn"] is not None:
            STREAM_STATE["conn"].close()
        STREAM_STATE["db_path"] = None
        STREAM_STATE["conn"] = None
        STREAM_STATE["min_frame"] = 0
        STREAM_STATE["max_frame"] = 0
        STREAM_STATE["agent_ids"] = []
        STREAM_STATE["id_to_index"] = {}
        STREAM_STATE["mode"] = None
        STREAM_STATE["objects"] = []
        STREAM_STATE["object_name"] = None
        STREAM_STATE["handler_installed"] = False

    def _get_or_create_collection(self, name):
        """Get or create a collection with the given name."""
        if name in bpy.data.collections:
            collection = bpy.data.collections[name]
            # Clear existing objects
            for obj in list(collection.objects):
                bpy.data.objects.remove(obj, do_unlink=True)
        else:
            collection = bpy.data.collections.new(name)
            bpy.context.scene.collection.children.link(collection)
        return collection

    def _create_agent(self, context, agent_id, collection):
        """Create an icosphere object for a single agent (streamed positions)."""
        mesh = bpy.data.meshes.new(f"Agent_{agent_id}_Mesh")
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=2, radius=0.5)
        bm.to_mesh(mesh)
        bm.free()
        mesh.polygons.foreach_set("use_smooth", [True] * len(mesh.polygons))
        mesh.update()

        agent_obj = bpy.data.objects.new(f"Agent_{agent_id}", mesh)
        agent_material = self._get_or_create_material(
            "JuPedSim_Agent_Material", (0.95, 0.7, 0.1, 1.0)
        )
        self._assign_material(agent_obj, agent_material)
        agent_obj.scale = (
            context.scene.jupedsim_props.agent_scale,
            context.scene.jupedsim_props.agent_scale,
            context.scene.jupedsim_props.agent_scale,
        )

        # Add to collection
        collection.objects.link(agent_obj)

        # Initial state; positions are streamed per frame.
        agent_obj.hide_viewport = True
        agent_obj.hide_render = True

    def _create_geometry(self, context, geometry, collection):
        """Create curves from the walkable area geometry."""
        # Support both pedpy geometry and raw shapely geometry
        polygon = geometry.polygon if hasattr(geometry, "polygon") else geometry

        # Ensure viewport clip distance covers the geometry extent
        bounds = polygon.bounds  # (minx, miny, maxx, maxy)
        max_dim = max(bounds[2] - bounds[0], bounds[3] - bounds[1])
        if max_dim > 0:
            for window in context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type != "VIEW_3D":
                        continue
                    for space in area.spaces:
                        if space.type == "VIEW_3D" and space.clip_end < max_dim:
                            space.clip_end = max_dim * 4

        # Create a ground plane at origin, expanded 10% beyond geometry bounds.
        span_x = max(bounds[2] - bounds[0], 0.0)
        span_y = max(bounds[3] - bounds[1], 0.0)
        if span_x > 0.0 and span_y > 0.0:
            pad_x = span_x * 0.1
            pad_y = span_y * 0.1
            min_x = bounds[0] - pad_x
            max_x = bounds[2] + pad_x
            min_y = bounds[1] - pad_y
            max_y = bounds[3] + pad_y

            plane_mesh = bpy.data.meshes.new("JuPedSim_Ground_Plane_Mesh")
            bm = bmesh.new()
            verts = [
                bm.verts.new((min_x, min_y, 0.0)),
                bm.verts.new((max_x, min_y, 0.0)),
                bm.verts.new((max_x, max_y, 0.0)),
                bm.verts.new((min_x, max_y, 0.0)),
            ]
            bm.faces.new(verts)
            bm.to_mesh(plane_mesh)
            bm.free()
            plane_obj = bpy.data.objects.new("JuPedSim_Ground_Plane", plane_mesh)
            plane_obj.location = (0.0, 0.0, 0.0)
            plane_material = self._get_or_create_material(
                "JuPedSim_Ground_Plane_Material", (0.85, 0.85, 0.85, 1.0)
            )
            self._assign_material(plane_obj, plane_material)
            collection.objects.link(plane_obj)

        # Create curves for exterior boundary
        self._create_curve_from_coords(
            context,
            "Walkable_Area_Boundary",
            list(polygon.exterior.coords),
            collection,
            closed=True,
        )

        # Create curves for any interior holes (obstacles)
        for i, interior in enumerate(polygon.interiors):
            self._create_curve_from_coords(
                context, f"Obstacle_{i}", list(interior.coords), collection, closed=True
            )

        self.report(
            {"INFO"}, f"Created geometry with {1 + len(list(polygon.interiors))} boundary curves"
        )

    def _create_curve_from_coords(self, context, name, coords, collection, closed=False):
        """Create a curve object from a list of coordinates."""
        # Create curve data
        curve_data = bpy.data.curves.new(name=name, type="CURVE")
        curve_data.dimensions = "3D"
        curve_data.resolution_u = 2

        # Create spline
        spline = curve_data.splines.new("POLY")
        spline.points.add(len(coords) - 1)  # One point already exists

        # Set point coordinates (x, y, z, w)
        for i, coord in enumerate(coords):
            x, y = coord[0], coord[1]
            z = 0.0  # Ground level for geometry
            spline.points[i].co = (x, y, z, 1.0)

        if closed:
            spline.use_cyclic_u = True

        # Create curve object
        curve_obj = bpy.data.objects.new(name, curve_data)
        curve_material = self._get_or_create_material(
            "JuPedSim_Geometry_Material", (0.2, 0.2, 0.2, 1.0)
        )
        self._assign_material(curve_obj, curve_material)

        # Add to collection
        collection.objects.link(curve_obj)

        # Add some visual thickness to the curve
        curve_data.bevel_depth = context.scene.jupedsim_props.geometry_thickness
        curve_data.bevel_resolution = 2

        return curve_obj

    def _create_agent_path(self, context, agent_id, coords, collection):
        """Create a curve representing the path of an agent."""

        if len(coords) < 2:
            return  # Need at least 2 points for a curve

        # Create curve data
        curve_data = bpy.data.curves.new(name=f"Path_Agent_{agent_id}", type="CURVE")
        curve_data.dimensions = "3D"
        curve_data.resolution_u = 2

        # Create spline
        spline = curve_data.splines.new("POLY")
        spline.points.add(len(coords) - 1)  # One point already exists

        # Set point coordinates (x, y, z, w)
        for i, coord in enumerate(coords):
            spline.points[i].co = (*coord, 1.0)

        # Path is not closed
        spline.use_cyclic_u = False

        # Create curve object
        curve_obj = bpy.data.objects.new(f"Path_Agent_{agent_id}", curve_data)

        # Add to collection
        collection.objects.link(curve_obj)

        # Add visual thickness to the path curve (thinner than geometry)
        curve_data.bevel_depth = 0.02
        curve_data.bevel_resolution = 2

        # Set material color (optional - can be customized)
        # For now, just make it visible but will be controlled by toggle

        return curve_obj

    def _create_big_data_points(self, context):
        """Create a single mesh driven by frame-change handler."""
        if not self._worker_data:
            return
        agent_ids = self._agent_groups or []
        if not agent_ids:
            return

        mesh = bpy.data.meshes.new("JuPedSim_Particles")
        mesh.vertices.add(len(agent_ids))
        hide_z = -1.0e6
        coords = array("f", [0.0] * (len(agent_ids) * 3))
        for i in range(2, len(coords), 3):
            coords[i] = hide_z
        mesh.vertices.foreach_set("co", coords)
        mesh.update()

        obj = bpy.data.objects.new("JuPedSim_Particles", mesh)
        obj.display_type = "WIRE"
        obj.show_in_front = True
        self._agents_collection.objects.link(obj)

        instance_mesh = bpy.data.meshes.new("JuPedSim_ParticleInstanceMesh")
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=1, radius=0.5)
        bm.to_mesh(instance_mesh)
        bm.free()
        instance_mesh.polygons.foreach_set("use_smooth", [True] * len(instance_mesh.polygons))
        instance_mesh.update()

        instance_obj = bpy.data.objects.new("JuPedSim_ParticleInstance", instance_mesh)
        plane_obj = bpy.data.objects.get("JuPedSim_Ground_Plane")
        if plane_obj:
            bb = plane_obj.bound_box
            center_x = (bb[0][0] + bb[6][0]) * 0.5
            center_y = (bb[0][1] + bb[6][1]) * 0.5
            instance_obj.location = (
                center_x + plane_obj.location.x,
                center_y + plane_obj.location.y,
                -1.0,
            )
        else:
            instance_obj.location = (0.0, 0.0, -1.0)
        agent_material = self._get_or_create_material(
            "JuPedSim_Agent_Material", (0.95, 0.7, 0.1, 1.0)
        )
        self._assign_material(instance_obj, agent_material)
        instance_obj.scale = (
            context.scene.jupedsim_props.agent_scale,
            context.scene.jupedsim_props.agent_scale,
            context.scene.jupedsim_props.agent_scale,
        )
        instance_obj.hide_viewport = False
        instance_obj.hide_render = False
        instance_obj.display_type = "SOLID"
        self._agents_collection.objects.link(instance_obj)

        ps_settings = bpy.data.particles.new("JuPedSim_Particles_Settings")
        ps_settings.type = "HAIR"
        ps_settings.count = len(agent_ids)
        ps_settings.emit_from = "VERT"
        ps_settings.use_emit_random = False
        ps_settings.render_type = "OBJECT"
        ps_settings.instance_object = instance_obj
        ps_settings.particle_size = (
            0.25  # magic number, ensures particles are same size as reference sphere
        )
        ps_settings.display_method = "RENDER"
        ps_settings.display_percentage = 100

        ps_mod = obj.modifiers.new("JuPedSimParticles", type="PARTICLE_SYSTEM")
        ps_mod.particle_system.settings = ps_settings

        self._start_streaming("big", object_name=obj.name)

    def _update_path_visibility(self, collection, visible):
        """Update visibility of all agent path curves in the collection."""
        for obj in collection.objects:
            if obj.name.startswith("Path_Agent_"):
                obj.hide_viewport = not visible
                obj.hide_render = not visible


classes = [
    JUPEDSIM_OT_select_file,
    JUPEDSIM_OT_load_simulation,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
