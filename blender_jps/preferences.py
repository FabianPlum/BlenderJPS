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
import subprocess
import sys
import os

# Get the addon's directory and deps path
ADDON_DIR = os.path.dirname(os.path.realpath(__file__))
DEPS_DIR = os.path.join(ADDON_DIR, "deps")


def ensure_deps_in_path():
    """Add the local deps directory to sys.path if it exists."""
    if os.path.exists(DEPS_DIR) and DEPS_DIR not in sys.path:
        sys.path.insert(0, DEPS_DIR)


def is_pedpy_installed():
    """Check if pedpy is installed and importable."""
    ensure_deps_in_path()
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
    pedpy_dir = os.path.join(DEPS_DIR, "pedpy")
    return os.path.isdir(pedpy_dir)


def get_python_executable():
    """Get the path to Blender's Python executable."""
    return str(sys.executable)


class JUPEDSIM_OT_install_dependencies(bpy.types.Operator):
    """Install required Python packages for BlenderJPS addon."""

    bl_idname = "jupedsim.install_dependencies"
    bl_label = "Install Dependencies"
    bl_description = "Install pedpy and required packages to addon's local directory"
    bl_options = {"REGISTER"}

    def execute(self, context):
        py_exec = get_python_executable()

        try:
            # Create deps directory if it doesn't exist
            os.makedirs(DEPS_DIR, exist_ok=True)

            # Ensure pip is available
            self.report({"INFO"}, "Ensuring pip is available...")
            subprocess.check_call([py_exec, "-m", "ensurepip", "--upgrade"])

            # Upgrade pip
            self.report({"INFO"}, "Upgrading pip...")
            subprocess.check_call([py_exec, "-m", "pip", "install", "--upgrade", "pip"])

            # Install pedpy and numpy to the local deps directory
            self.report({"INFO"}, f"Installing pedpy to {DEPS_DIR}...")
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

            # Add to path immediately so it works without restart
            ensure_deps_in_path()

            # Verify installation
            if is_pedpy_installed():
                self.report({"INFO"}, "Dependencies installed successfully!")
                self.report(
                    {"INFO"}, "You may need to restart Blender if imports still fail."
                )
            else:
                self.report(
                    {"WARNING"},
                    "Installation completed but import still failing. Please restart Blender.",
                )

            return {"FINISHED"}

        except subprocess.CalledProcessError as e:
            self.report({"ERROR"}, f"Failed to install dependencies: {e}")
            self.report(
                {"ERROR"},
                "Try running Blender as administrator if permission errors occur.",
            )
            return {"CANCELLED"}
        except Exception as e:
            self.report({"ERROR"}, f"Unexpected error: {e}")
            return {"CANCELLED"}


class JUPEDSIM_OT_uninstall_dependencies(bpy.types.Operator):
    """Remove installed dependencies."""

    bl_idname = "jupedsim.uninstall_dependencies"
    bl_label = "Uninstall Dependencies"
    bl_description = "Remove the local deps folder"
    bl_options = {"REGISTER"}

    def execute(self, context):
        import shutil

        if os.path.exists(DEPS_DIR):
            try:
                # Remove from sys.path first
                if DEPS_DIR in sys.path:
                    sys.path.remove(DEPS_DIR)

                shutil.rmtree(DEPS_DIR)
                self.report({"INFO"}, "Dependencies uninstalled successfully.")
            except Exception as e:
                self.report({"ERROR"}, f"Failed to remove deps folder: {e}")
                return {"CANCELLED"}
        else:
            self.report({"INFO"}, "No dependencies to uninstall.")

        return {"FINISHED"}


class JuPedSimAddonPreferences(AddonPreferences):
    """Addon preferences for BlenderJPS."""

    bl_idname = __package__

    def draw(self, context):
        layout = self.layout

        # Dependency status
        box = layout.box()
        box.label(text="Dependencies", icon="PACKAGE")

        # Show deps directory location
        col = box.column(align=True)
        col.label(text=f"Install location: {DEPS_DIR}", icon="FILE_FOLDER")
        col.separator()

        if is_pedpy_installed():
            row = box.row()
            row.label(text="pedpy: Installed", icon="CHECKMARK")

            # Show version if possible
            try:
                ensure_deps_in_path()
                import pedpy

                version = getattr(pedpy, "__version__", "unknown")
                row = box.row()
                row.label(text=f"Version: {version}")
            except:
                pass

            box.separator()
            row = box.row()
            row.operator("jupedsim.uninstall_dependencies", icon="TRASH")
        else:
            row = box.row()
            row.label(text="pedpy: Not Installed", icon="ERROR")

            box.separator()
            box.label(text="Click below to install dependencies:", icon="INFO")
            box.label(text="(No admin privileges required)")
            box.separator()

            row = box.row()
            row.scale_y = 1.5
            row.operator("jupedsim.install_dependencies", icon="IMPORT")


classes = [
    JUPEDSIM_OT_install_dependencies,
    JUPEDSIM_OT_uninstall_dependencies,
    JuPedSimAddonPreferences,
]


def register():
    # Ensure deps are in path on addon load
    ensure_deps_in_path()

    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
