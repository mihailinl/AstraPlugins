// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice
import { type ReactNode } from "react";

export declare const SECTION_NAVIGATE_EVENT = "astra-section-navigate";
export interface AdvancedProps {
    variant?: "knobs" | "whole";
    label?: string;
    alwaysCollapsible?: boolean;
    children: ReactNode;
}
export declare function Advanced({ variant, label, alwaysCollapsible, children }: AdvancedProps): import("react/jsx-runtime").JSX.Element;
