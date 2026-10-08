// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice
export type ControlTone = "success" | "danger" | "warning" | "info";
export declare function toneClasses(tone: ControlTone | undefined, base: string): string[];
