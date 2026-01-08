"""
BlenderJPS Addon Preferences
Handles addon preferences and dependency installation.
"""

import bpy
from bpy.types import AddonPreferences
from bpy.props import BoolProperty
import subprocess
import sys


def is_pedpy_installed():
    """Check if pedpy is installed and importable."""
    try:
        import pedpy
        return True
    except ImportError:
        return False


def get_python_executable():
    """Get the path to Blender's Python executable."""
    return str(sys.executable)


class JUPEDSIM_OT_install_dependencies(bpy.types.Operator):
    """Install required Python packages for BlenderJPS addon."""
    
    bl_idname = "jupedsim.install_dependencies"
    bl_label = "Install Dependencies"
    bl_description = "Install pedpy and required packages (requires admin/elevated privileges)"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        py_exec = get_python_executable()
        
        try:
            # Ensure pip is available and up-to-date
            self.report({'INFO'}, "Ensuring pip is installed...")
            subprocess.check_call([py_exec, "-m", "ensurepip", "--user"])
            subprocess.check_call([py_exec, "-m", "pip", "install", "--upgrade", "pip"])
            
            # Install pedpy with numpy version constraint
            self.report({'INFO'}, "Installing pedpy and dependencies...")
            subprocess.check_call([py_exec, "-m", "pip", "install", "pedpy", "numpy<2.0"])
            
            self.report({'INFO'}, "Dependencies installed successfully! Please restart Blender.")
            return {'FINISHED'}
            
        except subprocess.CalledProcessError as e:
            self.report({'ERROR'}, f"Failed to install dependencies: {e}")
            self.report({'ERROR'}, "Make sure Blender is running with administrator privileges.")
            return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"Unexpected error: {e}")
            return {'CANCELLED'}


class JuPedSimAddonPreferences(AddonPreferences):
    """Addon preferences for BlenderJPS."""
    
    bl_idname = __package__
    
    def draw(self, context):
        layout = self.layout
        
        # Dependency status
        box = layout.box()
        box.label(text="Dependencies", icon='PACKAGE')
        
        if is_pedpy_installed():
            row = box.row()
            row.label(text="pedpy: Installed", icon='CHECKMARK')
        else:
            row = box.row()
            row.label(text="pedpy: Not Installed", icon='ERROR')
            
            box.separator()
            box.label(text="To install dependencies:", icon='INFO')
            box.label(text="1. Close Blender")
            box.label(text="2. Run Blender as Administrator")
            box.label(text="3. Click the button below")
            box.separator()
            
            row = box.row()
            row.scale_y = 1.5
            row.operator("jupedsim.install_dependencies", icon='IMPORT')


classes = [
    JUPEDSIM_OT_install_dependencies,
    JuPedSimAddonPreferences,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

