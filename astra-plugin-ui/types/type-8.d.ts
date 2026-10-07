// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice
import { type ReactNode } from "react";

export interface CollapseProps {
    open: boolean;
    className?: string;
    openClassName?: string;
    innerClassName?: string;
    children: ReactNode;
}
export declare function Collapse({ open, className, openClassName, innerClassName, children, }: CollapseProps): import("react/jsx-runtime").JSX.Element;
