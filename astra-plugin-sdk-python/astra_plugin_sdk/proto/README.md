# DO NOT EDIT `plugin.proto` in this directory

`astra_plugin_sdk/proto/plugin.proto` is a **generated, byte-identical copy** of the
repository's canonical protocol file, `proto/plugin.proto` (which is itself generated
in the Astra repo by `astra-rs/tools/proto-slice`).

It exists for one reason: setuptools packages data from inside the package directory
only, so an sdist/wheel cannot carry `../../proto/plugin.proto`. This copy is the input
for regenerating `plugin_pb2.py` / `plugin_pb2_grpc.py` — see `__init__.py` for that
command.

**To change the protocol:** edit `astra-proto/src/astra.proto` (or
`astra-proto/plugin-surface.toml`) in the Astra repo, regenerate `proto/plugin.proto`,
then run from this repo's root:

```sh
tools/sync-proto.sh
```

`tools/check-proto.sh` fails the build if this copy is not byte-identical to
`proto/plugin.proto`, or if its sha256 is not the one pinned in `proto/PROTO_VERSION`.
