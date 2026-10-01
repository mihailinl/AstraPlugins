// SPDX-License-Identifier: GPL-3.0-or-later
import {verifyUiBundle} from '../astra-plugin-cli/resources/ui/verify-bundle.mjs';
import contract from '../astra-plugin-ui/contract.json' with {type:'json'};
const count=verifyUiBundle(process.argv[2],contract);
console.log('UI bundle host-import validation PASS: '+count+' Kit modules inspected');
