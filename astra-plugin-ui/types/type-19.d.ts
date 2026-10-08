// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice
import { type HTMLAttributes } from "react";

export interface ScrollAreaProps extends HTMLAttributes<HTMLDivElement> {
    orientation?: "vertical" | "horizontal" | "both";
    scrollbar?: boolean;
}
export declare const ScrollArea: import("react").ForwardRefExoticComponent<ScrollAreaProps & import("react").RefAttributes<HTMLDivElement>>;
