// SPDX-License-Identifier: MPL-2.0
try { await astra.loadUi({apiVersion:1}); await import('./App.js'); }
catch(error) { document.getElementById('app').textContent='Update Astra to use this interface. '+error.message; }
