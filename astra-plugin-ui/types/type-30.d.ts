// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice
import { type CSSProperties } from "react";

export declare function forgetTooltipWarmth_for_test(): void;
export declare function tooltipDwell(delay?: number): number;
export declare function noteTooltipClosed(): void;
export type TooltipPlacement = "top" | "bottom" | "left" | "right";
export declare function tooltipPosition(anchor: DOMRect, size: {
    width: number;
    height: number;
}, placement: TooltipPlacement): CSSProperties;
export interface TooltipProps {
    anchorRef?: React.RefObject<HTMLElement | null>;
    content: React.ReactNode;
    placement?: TooltipPlacement;
    delay?: number;
    children: React.ReactNode;
    className?: string;
    open?: boolean;
    spotlightId?: string;
}
export declare function Tooltip({ content, placement, delay, children, className, open, spotlightId, anchorRef }: TooltipProps): import("react/jsx-runtime").JSX.Element;
