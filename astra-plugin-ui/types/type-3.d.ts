// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice
import { type RefObject } from "react";

export declare function isInsideAnchoredMenu(target: EventTarget | null): boolean;
export interface AnchoredMenuProps {
    anchorRef: RefObject<HTMLElement | null>;
    open: boolean;
    children: React.ReactNode;
    menuRef?: RefObject<HTMLDivElement | null>;
    className?: string;
    role?: string;
    ariaLabel?: string;
    maxHeight?: number;
    matchAnchorWidth?: boolean;
    align?: "start" | "end";
    side?: "bottom" | "top";
    onDismiss?: () => void;
    onMouseDown?: React.MouseEventHandler<HTMLDivElement>;
    onAnimationEnd?: React.AnimationEventHandler<HTMLDivElement>;
}
export declare function AnchoredMenu({ anchorRef, open, children, menuRef, className, role, ariaLabel, maxHeight, matchAnchorWidth, align, side, onDismiss, onMouseDown, onAnimationEnd, }: AnchoredMenuProps): import("react").ReactPortal;
