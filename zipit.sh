 zip -r BlenderJPS.zip blender_jps \
      -x "blender_jps/deps/*" \
      -x "blender_jps/tests/*" \
      -x "blender_jps/__pycache__/*" \
      -x "blender_jps/**/__pycache__/*" \
      -x "*.pyc"
