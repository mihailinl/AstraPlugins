# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2026 Minice — https://minice.ai

"""Shared wire constants, generated from spec/wire.yaml.

AUTO-GENERATED — DO NOT EDIT.

Produced by `tools/gen-limits.mjs` from `spec/wire.yaml`.
Regenerate with `node tools/gen-limits.mjs` at the repo root.
These keys are shared with the Astra daemon; changing one here without
changing the spec is a silent protocol break, which is why this file is
generated and CI re-runs the generator with `--check`.
"""

#: SHA-256 of the ``spec/wire.yaml`` these constants were generated from.
SPEC_SHA256 = "a78339e40279f26f5d87c87fa33dedf63ba960bc8dea8e85aec2b931576d1178"

#: Metadata key the daemon carries a per-invocation LEASE under when it calls
#: into a plugin, and the key an SDK echoes it back on when that plugin fires a
#: trigger. Redeeming the lease is how the daemon recovers what caused the fire,
#: and therefore which conversation the resulting output belongs in.
#:
#: It is metadata and not a proto field for two reasons that are both about not
#: colliding with the plugin's own data. Inbound, a trigger's payload keys are
#: injected verbatim as workflow variables, so a reserved key would appear as
#: `{__astra_cause}` in the user's own variable picker. Outbound, `params_json`
#: is the plugin's typed argument document, where an extra field hard-fails any
#: plugin whose model uses `deny_unknown_fields` or `extra="forbid"`.
#:
#: Absent is legal and is the honest answer: a plugin that never heard of leases
#: — every published plugin today — fires without it and the daemon files the
#: result as a root event. An SDK must therefore never invent a value and never
#: send the key empty. `x_astra_cause` keeps the identifier the daemon-side
#: design names, without the `_header` suffix the two older keys carry.
X_ASTRA_CAUSE = "x-astra-cause"

#: Metadata key every host RPC but `Register` must present its session token
#: under. `Register` is the one exempt path — it is where a plugin trades its
#: spawn-time `--auth-token` for the session token — and everything after it
#: comes back `unauthenticated` without this.
SESSION_TOKEN_HEADER = "x-session-token"

#: Metadata key the daemon presents its copy of the plugin's spawn token under,
#: on every call INTO the plugin. The mirror image of the session token: it is
#: what lets a plugin's own capability server tell the daemon apart from any
#: other local process that found its loopback port.
PLUGIN_TOKEN_HEADER = "x-plugin-token"

__all__ = [
    "SPEC_SHA256",
    "X_ASTRA_CAUSE",
    "SESSION_TOKEN_HEADER",
    "PLUGIN_TOKEN_HEADER",
]
