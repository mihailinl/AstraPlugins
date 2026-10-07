// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice
import { type ReactNode } from "react";

export interface AdvancedProps {
    variant?: "knobs" | "whole";
    label?: string;
    children: ReactNode;
}
export declare function Advanced({ variant, label, children }: AdvancedProps): import("react/jsx-runtime").JSX.Element;
