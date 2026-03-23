#!/usr/bin/env bash
set -euo pipefail

zip -r BlenderJPS.zip blender_jps \
    -x "blender_jps/deps/*" \
    -x "blender_jps/tests/*" \
    -x "blender_jps/examples/*" \
    -x "blender_jps/__pycache__/*" \
    -x "blender_jps/**/__pycache__/*" \
    -x "*.pyc" \
    -x "*~" \
    -x "*.~undo-tree~" \
    -x "*.sqlite" \
    -x "*.DS_Store"
