// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice
import { type RefObject } from "react";
export interface ClearBehindOptions {
    fadeTop?: number;
    fadeBottom?: number;
    enabled?: boolean;
}
export declare function useClearBehindMask(hostRef: RefObject<HTMLElement | null>, options?: ClearBehindOptions): void;
