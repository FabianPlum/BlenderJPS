"""
BlenderJPS Operators
Operators for loading JuPedSim trajectory and geometry data.
"""

import bpy
from bpy.types import Operator
from bpy.props import StringProperty
from bpy_extras.io_utils import ImportHelper
import pathlib


def check_dependencies():
    """Check if required dependencies are installed."""
    try:
        import pedpy
        return True, None
    except ImportError as e:
        return False, str(e)


class JUPEDSIM_OT_select_file(Operator, ImportHelper):
    """Select a JuPedSim SQLite trajectory file."""
    
    bl_idname = "jupedsim.select_file"
    bl_label = "Select SQLite File"
    bl_description = "Browse for a JuPedSim trajectory SQLite file"
    
    filter_glob: StringProperty(
        default="*.sqlite;*.db",
        options={'HIDDEN'},
    )
    
    def execute(self, context):
        context.scene.jupedsim_props.sqlite_file = self.filepath
        self.report({'INFO'}, f"Selected file: {self.filepath}")
        return {'FINISHED'}


class JUPEDSIM_OT_load_simulation(Operator):
    """Load simulation data from the selected SQLite file."""
    
    bl_idname = "jupedsim.load_simulation"
    bl_label = "Load Simulation"
    bl_description = "Load agent trajectories and geometry from the SQLite file"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        # Check dependencies first
        deps_ok, error = check_dependencies()
        if not deps_ok:
            self.report({'ERROR'}, f"Missing dependencies: {error}")
            self.report({'ERROR'}, "Please install dependencies in addon preferences.")
            return {'CANCELLED'}
        
        # Import pedpy here after checking
        from pedpy import (
            load_trajectory_from_jupedsim_sqlite,
            load_walkable_area_from_jupedsim_sqlite,
        )
        
        # Get file path
        filepath = context.scene.jupedsim_props.sqlite_file
        if not filepath:
            self.report({'ERROR'}, "No SQLite file selected")
            return {'CANCELLED'}
        
        filepath = bpy.path.abspath(filepath)
        path = pathlib.Path(filepath)
        
        if not path.exists():
            self.report({'ERROR'}, f"File not found: {filepath}")
            return {'CANCELLED'}
        
        try:
            # Load trajectory data
            self.report({'INFO'}, "Loading trajectory data...")
            traj_data = load_trajectory_from_jupedsim_sqlite(trajectory_file=path)
            
            # Load geometry data
            self.report({'INFO'}, "Loading geometry data...")
            geometry = load_walkable_area_from_jupedsim_sqlite(trajectory_file=path)
            
            # Create agents collection
            agents_collection = self._get_or_create_collection("JuPedSim_Agents")
            geometry_collection = self._get_or_create_collection("JuPedSim_Geometry")
            
            # Get frame step setting
            frame_step = context.scene.jupedsim_props.frame_step
            
            # Create agents with animated trajectories
            self._create_agents(context, traj_data, agents_collection, frame_step)
            
            # Create geometry curves
            self._create_geometry(context, geometry, geometry_collection)
            
            self.report({'INFO'}, "Simulation loaded successfully!")
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Failed to load simulation: {e}")
            return {'CANCELLED'}
    
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
    
    def _create_agents(self, context, traj_data, collection, frame_step=1):
        """Create animated empty objects for each agent."""
        # Get the trajectory DataFrame
        df = traj_data.data
        
        # Get unique agent IDs
        agent_ids = df['id'].unique()
        
        # Get frame rate info - pedpy uses 'frame' column
        frames = sorted(df['frame'].unique())
        min_frame = int(frames[0])
        max_frame = int(frames[-1])
        
        # Apply frame step to get sampled frames
        sampled_frames = set(frames[::frame_step])
        
        # Set scene frame range
        context.scene.frame_start = min_frame
        context.scene.frame_end = max_frame
        
        self.report({'INFO'}, f"Creating {len(agent_ids)} agents (every {frame_step} frame(s))...")
        
        for agent_id in agent_ids:
            # Filter data for this agent
            agent_data = df[df['id'] == agent_id]
            
            # Create an empty object for the agent (much faster than mesh)
            empty_obj = bpy.data.objects.new(f"Agent_{agent_id}", None)
            empty_obj.empty_display_type = 'SPHERE'
            empty_obj.empty_display_size = 0.5  # Radius 0.5 = diameter 1
            
            # Add to collection
            collection.objects.link(empty_obj)
            
            # Track the last frame this agent appears in
            last_agent_frame = None
            
            # Add keyframes for sampled frames only
            for _, row in agent_data.iterrows():
                frame = int(row['frame'])
                
                # Skip frames not in our sampled set
                if frame not in sampled_frames:
                    continue
                
                x = float(row['x'])
                y = float(row['y'])

                # JuPedSim is 2D, so we set z to 0.5 (sphere center above ground)
                z = 0.5
                
                empty_obj.location = (x, y, z)
                empty_obj.keyframe_insert(data_path="location", frame=frame)
                
                # Track last frame
                if last_agent_frame is None or frame > last_agent_frame:
                    last_agent_frame = frame
            
            # Set interpolation to linear for smooth movement.
            # This is not clean for curves, but if you need less interpolation and
            # more precision, simply decrease the iteration step in the for loop above.
            if empty_obj.animation_data and empty_obj.animation_data.action:
                for fcurve in empty_obj.animation_data.action.fcurves:
                    for keyframe in fcurve.keyframe_points:
                        keyframe.interpolation = 'LINEAR'
            
            # Add visibility keyframes: visible until last frame, then hidden
            if last_agent_frame is not None and last_agent_frame < max_frame:
                # Visible at last valid frame
                empty_obj.hide_viewport = False
                empty_obj.hide_render = False
                empty_obj.keyframe_insert(data_path="hide_viewport", frame=last_agent_frame)
                empty_obj.keyframe_insert(data_path="hide_render", frame=last_agent_frame)
                
                # Hidden on next frame
                empty_obj.hide_viewport = True
                empty_obj.hide_render = True
                empty_obj.keyframe_insert(data_path="hide_viewport", frame=last_agent_frame + 1)
                empty_obj.keyframe_insert(data_path="hide_render", frame=last_agent_frame + 1)
                
                # Reset to visible for viewport (current state)
                empty_obj.hide_viewport = False
                empty_obj.hide_render = False
        
        self.report({'INFO'}, f"Created {len(agent_ids)} agents with animations")
    
    def _create_geometry(self, context, geometry, collection):
        """Create curves from the walkable area geometry."""
        # Get the shapely polygon from the walkable area
        polygon = geometry.polygon
        
        # Create curves for exterior boundary
        self._create_curve_from_coords(
            context,
            "Walkable_Area_Boundary",
            list(polygon.exterior.coords),
            collection,
            closed=True
        )
        
        # Create curves for any interior holes (obstacles)
        for i, interior in enumerate(polygon.interiors):
            self._create_curve_from_coords(
                context,
                f"Obstacle_{i}",
                list(interior.coords),
                collection,
                closed=True
            )
        
        self.report({'INFO'}, f"Created geometry with {1 + len(list(polygon.interiors))} boundary curves")
    
    def _create_curve_from_coords(self, context, name, coords, collection, closed=False):
        """Create a curve object from a list of coordinates."""
        # Create curve data
        curve_data = bpy.data.curves.new(name=name, type='CURVE')
        curve_data.dimensions = '3D'
        curve_data.resolution_u = 2
        
        # Create spline
        spline = curve_data.splines.new('POLY')
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
        
        # Add to collection
        collection.objects.link(curve_obj)
        
        # Add some visual thickness to the curve
        curve_data.bevel_depth = 0.05
        curve_data.bevel_resolution = 2
        
        return curve_obj


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

