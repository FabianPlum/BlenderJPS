"""
BlenderJPS UI Panels
User interface panels for the JuPedSim importer.
"""

import bpy
from bpy.types import Panel

from .preferences import is_pedpy_installed


class JUPEDSIM_PT_main_panel(Panel):
    """Main panel for JuPedSim importer in the 3D Viewport sidebar."""
    
    bl_label = "JuPedSim Importer"
    bl_idname = "JUPEDSIM_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'JuPedSim'
    
    def draw(self, context):
        layout = self.layout
        props = context.scene.jupedsim_props
        
        # Check dependencies
        if not is_pedpy_installed():
            box = layout.box()
            box.alert = True
            box.label(text="Dependencies not installed!", icon='ERROR')
            box.label(text="Go to Edit > Preferences > Add-ons")
            box.label(text="Find 'BlenderJPS' and install dependencies")
            box.separator()
            box.operator("jupedsim.install_dependencies", 
                        text="Install Dependencies", 
                        icon='IMPORT')
            return
        
        # File selection section
        box = layout.box()
        box.label(text="Trajectory File", icon='FILE')
        
        # Display selected file or prompt
        if props.sqlite_file:
            import os
            filename = os.path.basename(props.sqlite_file)
            box.label(text=filename, icon='CHECKMARK')
        else:
            box.label(text="No file selected", icon='QUESTION')
        
        box.operator("jupedsim.select_file", text="Browse...", icon='FILEBROWSER')
        
        layout.separator()
        
        # Import options
        box = layout.box()
        box.label(text="Import Options", icon='SETTINGS')
        row = box.row()
        row.prop(props, "frame_step", text="Load Every Nth Frame")
        
        layout.separator()
        
        # Load button
        row = layout.row()
        row.scale_y = 1.5
        row.operator("jupedsim.load_simulation", 
                    text="Load Simulation", 
                    icon='IMPORT')
        
        # Info section
        layout.separator()
        box = layout.box()
        box.label(text="Info", icon='INFO')
        box.label(text="Agents → Animated spheres")
        box.label(text="Geometry → Curve boundaries")


class JUPEDSIM_PT_info_panel(Panel):
    """Info panel showing loaded simulation statistics."""
    
    bl_label = "Simulation Info"
    bl_idname = "JUPEDSIM_PT_info_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'JuPedSim'
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        
        # Count agents and geometry
        agents_count = 0
        geometry_count = 0
        
        if "JuPedSim_Agents" in bpy.data.collections:
            agents_count = len(bpy.data.collections["JuPedSim_Agents"].objects)
        
        if "JuPedSim_Geometry" in bpy.data.collections:
            geometry_count = len(bpy.data.collections["JuPedSim_Geometry"].objects)
        
        box = layout.box()
        box.label(text=f"Agents loaded: {agents_count}")
        box.label(text=f"Geometry curves: {geometry_count}")
        box.label(text=f"Frame range: {context.scene.frame_start} - {context.scene.frame_end}")


classes = [
    JUPEDSIM_PT_main_panel,
    JUPEDSIM_PT_info_panel,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

