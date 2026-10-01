// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice

export interface TooltipProps {
    content: React.ReactNode;
    placement?: "top" | "bottom" | "left" | "right";
    delay?: number;
    children: React.ReactNode;
    className?: string;
    open?: boolean;
    spotlightId?: string;
}
export declare function Tooltip({ content, placement, delay, children, className, open, spotlightId }: TooltipProps): import("react/jsx-runtime").JSX.Element;
