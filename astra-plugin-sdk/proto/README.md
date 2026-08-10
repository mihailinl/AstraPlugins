# DO NOT EDIT `plugin.proto` in this directory

`astra-plugin-sdk/proto/plugin.proto` is a **generated, byte-identical copy** of the
repository's canonical protocol file, `proto/plugin.proto` (which is itself generated
in the Astra repo by `astra-rs/tools/proto-slice`).

It exists for one reason: `cargo package` refuses to include files outside the crate
root, so `build.rs` cannot compile `../proto/plugin.proto` from a published `.crate`.

**To change the protocol:** edit `astra-proto/src/astra.proto` (or
`astra-proto/plugin-surface.toml`) in the Astra repo, regenerate `proto/plugin.proto`,
then run from this repo's root:

```sh
tools/sync-proto.sh
```

`tools/check-proto.sh` fails the build if this copy is not byte-identical to
`proto/plugin.proto`, or if its sha256 is not the one pinned in `proto/PROTO_VERSION`.
