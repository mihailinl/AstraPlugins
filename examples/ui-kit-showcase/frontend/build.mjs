// SPDX-License-Identifier: MPL-2.0
import {buildUi} from '@astra/plugin-ui/build';
import {copyFileSync} from 'node:fs';
import {resolve} from 'node:path';
await buildUi(resolve('App.tsx'),resolve('../ui'));
copyFileSync(resolve('index.html'),resolve('../ui/react.html'));
copyFileSync(resolve("bootstrap.js"),resolve("../ui/bootstrap.js"));
