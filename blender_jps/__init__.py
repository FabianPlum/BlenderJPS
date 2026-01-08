"""
BlenderJPS - JuPedSim Trajectory Importer for Blender
A Blender addon for importing JuPedSim simulation SQLite files.
"""

bl_info = {
    "name": "BlenderJPS - JuPedSim Importer",
    "author": "Fabian Plum",
    "version": (0, 1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > JuPedSim",
    "description": "Import JuPedSim trajectory SQLite files with agent animations and geometry",
    "warning": "Requires external Python packages (pedpy). See documentation for installation.",
    "doc_url": "",
    "category": "Import-Export",
}

import bpy
from bpy.props import StringProperty, PointerProperty, IntProperty
from bpy.types import PropertyGroup

# Import submodules
from . import operators
from . import panels
from . import preferences


class JuPedSimProperties(PropertyGroup):
    """Property group for JuPedSim addon settings."""
    
    sqlite_file: StringProperty(
        name="SQLite File",
        description="Path to the JuPedSim trajectory SQLite file",
        default="",
        subtype='FILE_PATH',
    )
    
    frame_step: IntProperty(
        name="Frame Step",
        description="Load every Nth frame (1 = all frames, 2 = every 2nd frame, etc.)",
        default=1,
        min=1,
        max=99999,
        soft_max=1000,
    )


# List of classes to register
classes = [
    JuPedSimProperties,
]


def register():
    """Register the addon."""
    # Register classes from submodules first
    preferences.register()
    operators.register()
    panels.register()
    
    # Register main classes
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Add properties to scene
    bpy.types.Scene.jupedsim_props = PointerProperty(type=JuPedSimProperties)
    
    print("BlenderJPS addon registered successfully")


def unregister():
    """Unregister the addon."""
    # Remove properties from scene
    del bpy.types.Scene.jupedsim_props
    
    # Unregister main classes
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    # Unregister submodule classes
    panels.unregister()
    operators.unregister()
    preferences.unregister()
    
    print("BlenderJPS addon unregistered")


if __name__ == "__main__":
    register()

