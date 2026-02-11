import argparse
import os
import sys
import traceback

import bpy
import addon_utils


def _script_args():
    """Return args passed after `--` (Blender convention)."""
    argv = sys.argv
    if "--" in argv:
        return argv[argv.index("--") + 1 :]
    return []


def _add_repo_root_to_syspath():
    """
    Ensure the repository root is on sys.path so the add-on can be imported
    directly from the checkout in CI.
    Assumes this file is at: <repo>/blender_jps/tests/test_plugin_loading.py
    """
    here = os.path.abspath(os.path.dirname(__file__))
    repo_root = os.path.abspath(os.path.join(here, "..", ".."))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    return repo_root


def _parse_args():
    p = argparse.ArgumentParser(description="Headless Blender add-on smoke test")
    p.add_argument("--addon", required=True, help="Blender add-on module name (folder/file name)")
    p.add_argument(
        "--require-module",
        action="append",
        default=[],
        help="Python module that must be importable after enabling (repeatable)",
    )
    p.add_argument(
        "--require-operator",
        action="append",
        default=[],
        help="Operator that must exist, e.g. 'import_scene.jupedsim' (repeatable)",
    )
    p.add_argument(
        "--factory-startup",
        action="store_true",
        help="Reset Blender to factory settings for deterministic CI runs",
    )
    return p.parse_args(_script_args())


def _operator_exists(op_id: str) -> bool:
    """
    Check if bpy.ops.<category>.<op> exists.
    Example: 'import_scene.obj' -> bpy.ops.import_scene.obj
    """
    if "." not in op_id:
        return False
    cat, op = op_id.split(".", 1)
    cat_obj = getattr(bpy.ops, cat, None)
    return cat_obj is not None and getattr(cat_obj, op, None) is not None


def main():
    args = _parse_args()

    print("\n" + "=" * 72)
    print(f"Blender: {bpy.app.version_string}")
    print(f"Addon module: {args.addon}")
    print("=" * 72)

    repo_root = _add_repo_root_to_syspath()
    print(f"Repo root on sys.path: {repo_root}")

    if args.factory_startup:
        # Ensures user prefs don't break CI runs
        bpy.ops.wm.read_factory_settings(use_empty=True)
        print("Loaded factory startup settings (empty).")

    enabled_ok = False

    try:
        # Enable using addon_utils (more direct than UI operators)
        addon_utils.enable(args.addon, default_set=True, persistent=False)
        enabled_ok = True
        print(f"✓ Enabled add-on '{args.addon}'")

        # Verify it shows up in preferences
        if args.addon not in bpy.context.preferences.addons.keys():
            raise RuntimeError(
                f"Add-on '{args.addon}' not present in bpy.context.preferences.addons"
            )

        print(f"✓ Add-on '{args.addon}' present in enabled add-ons list")

        # Require specific python modules (optional)
        for mod in args.require_module:
            __import__(mod)
            print(f"✓ Required module import ok: {mod}")

        # Require specific operators (optional)
        for op_id in args.require_operator:
            if not _operator_exists(op_id):
                raise RuntimeError(f"Required operator not found: {op_id}")
            print(f"✓ Required operator exists: {op_id}")

        print("\n" + "=" * 72)
        print("All tests passed!")
        print("=" * 72 + "\n")
        return 0

    except Exception as e:
        print("\n✗ TEST FAILED")
        print(f"Reason: {e}")
        traceback.print_exc()
        return 1

    finally:
        # Always attempt disable if we enabled
        if enabled_ok:
            try:
                addon_utils.disable(args.addon, default_set=True)
                print(f"✓ Disabled add-on '{args.addon}'")
            except Exception as e:
                print(f"⚠ Failed to disable add-on '{args.addon}': {e}")


if __name__ == "__main__":
    raise SystemExit(main())
