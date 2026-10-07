// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice
import { type RefObject } from "react";
export declare function useExitTransition(nodeRef: RefObject<HTMLElement | null>, open: boolean, active: boolean, fallbackMs: number, onExitComplete?: () => void): void;
