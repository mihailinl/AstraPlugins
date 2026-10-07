// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice
import { type RefObject } from "react";
export interface EscapeLayerOptions {
    priority?: number;
    element?: RefObject<HTMLElement | null>;
    floor?: boolean;
}
export declare function useEscapeLayer(active: boolean, onEscape: () => void, options?: EscapeLayerOptions): void;
