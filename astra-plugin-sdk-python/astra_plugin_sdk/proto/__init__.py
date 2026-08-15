# Proto stubs — generated from plugin.proto.
#
# To regenerate, from `astra-plugin-sdk-python/`:
#
#   python -m grpc_tools.protoc -I astra_plugin_sdk/proto \
#     --python_out=astra_plugin_sdk/proto \
#     --grpc_python_out=astra_plugin_sdk/proto \
#     astra_plugin_sdk/proto/plugin.proto
#   sed -i 's|^import plugin_pb2 as plugin__pb2$|from . import plugin_pb2 as plugin__pb2|' \
#     astra_plugin_sdk/proto/plugin_pb2_grpc.py
#
# BOTH lines. protoc emits `import plugin_pb2`, a top-level import that only
# resolves when the proto directory is itself on `sys.path` — inside a package
# it raises `ModuleNotFoundError: No module named 'plugin_pb2'` the moment
# anything imports the grpc stub. The recipe here used to stop after protoc, so
# following it exactly produced a package that could not import itself, and the
# failure surfaced in eight CI jobs rather than at the command that caused it.
# An incomplete instruction is worse than none: it is run in confidence.
#
# **Use the grpcio-tools version the checked-in stubs were generated with**
# (`GRPC_GENERATED_VERSION` at the top of plugin_pb2_grpc.py, currently
# 1.75.1). A newer one is not wrong, but it rewrites unrelated lines — class
# declarations, string formatting — and raises the version floor the stub
# asserts at import against the installed grpcio. Moving that floor is a
# decision about the package's minimum runtime, not a side effect of syncing a
# proto, so it belongs in its own commit with its own reason.
#
# After regenerating, `python -m pytest` from this directory is the check: the
# suite imports the stubs, so a broken import fails at collection.
