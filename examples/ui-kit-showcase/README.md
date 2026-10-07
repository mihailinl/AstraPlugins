<!-- SPDX-License-Identifier: MPL-2.0 -->
# UI Kit showcase

Scaffolded with astra-plugin new --template ui --ui react --lang typescript.

1. Run bun install --frozen-lockfile in frontend/ and bun install at the backend root.
2. Run astra-plugin build . and astra-plugin dev . with the prepared Astra build.
3. Both Vanilla UI Kit and React UI Kit pages use the host Section, SettingRow, Select, Input, Toggle and Button, preserving local state while calling the ping backend. They use no CSS overriding controls.
4. In Astra enable localStorage.astra_ui_gallery = "1" and reload; choose Vanilla or React in Plugin comparison. Reset it to "0" afterwards.

Check narrow frames, palette changes in one theme, glass/material, language, Escape and focus in the actual installed shells. UI Kit requires the prepared Astra 0.2.7; it is not yet published.
