"""
BlenderJPS Addon Preferences
Handles addon preferences and dependency installation.
"""

import os
import subprocess
import sys

import bpy
from bpy.types import AddonPreferences
from bpy.props import BoolProperty

# Add addon-local modules dir to path so pedpy (and shapely) are found when
# installed via "Install Dependencies". This avoids needing Administrator/root
# and keeps addon + deps in the same user Blender config.
_addon_dir = os.path.dirname(os.path.abspath(__file__))
_MODULES_DIR = os.path.join(_addon_dir, "modules")
if _MODULES_DIR not in sys.path:
    sys.path.insert(0, _MODULES_DIR)


def is_pedpy_installed():
    """Check if pedpy is installed and importable."""
    try:
        import pedpy
        return True
    except ImportError:
        return False


def dependencies_installed():
    """True if pedpy is importable or was just installed into the addon modules dir.
    Used to grey out the install button and show restart prompt without requiring a restart.
    """
    if is_pedpy_installed():
        return True
    pedpy_dir = os.path.join(_MODULES_DIR, "pedpy")
    return os.path.isdir(pedpy_dir)


def get_python_executable():
    """Get the path to Blender's Python executable."""
    return str(sys.executable)


class JUPEDSIM_OT_install_dependencies(bpy.types.Operator):
    """Install required Python packages for BlenderJPS addon."""
    
    bl_idname = "jupedsim.install_dependencies"
    bl_label = "Install Dependencies"
    bl_description = "Install pedpy and dependencies into this addon (no admin required)"
    bl_options = {'REGISTER'}
    
    @classmethod
    def poll(cls, context):
        return not dependencies_installed()
    
    def execute(self, context):
        py_exec = get_python_executable()
        
        try:
            os.makedirs(_MODULES_DIR, exist_ok=True)
            # Ensure pip is available
            self.report({'INFO'}, "Ensuring pip is installed...")
            subprocess.check_call([py_exec, "-m", "ensurepip", "--upgrade"], timeout=120)
            subprocess.check_call([py_exec, "-m", "pip", "install", "--upgrade", "pip"], timeout=120)
            # Install into addon folder so the same user always sees addon + deps (no root needed)
            self.report({'INFO'}, "Installing pedpy and dependencies...")
            subprocess.check_call(
                [
                    py_exec, "-m", "pip", "install",
                    "--target", _MODULES_DIR,
                    "--upgrade",
                    "--no-user",
                    "pedpy",
                    "numpy<2.0",
                ],
                timeout=300,
            )
            self.report({'INFO'}, "Dependencies installed. Close and reopen Blender.")
            return {'FINISHED'}
        except subprocess.CalledProcessError as e:
            self.report({'ERROR'}, f"Failed to install dependencies: {e}")
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
        
        if dependencies_installed():
            row = box.row()
            row.label(text="pedpy: Installed", icon='CHECKMARK')
            if not is_pedpy_installed():
                box.separator()
                box.alert = True
                box.label(text="Close and reopen Blender to use the addon.", icon='INFO')
        else:
            row = box.row()
            row.label(text="pedpy: Not Installed", icon='ERROR')
            
            box.separator()
            box.label(text="Install into this addon (no admin required):", icon='INFO')
            row = box.row()
            row.scale_y = 1.5
            row.operator("jupedsim.install_dependencies", icon='IMPORT')
            box.separator()


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

