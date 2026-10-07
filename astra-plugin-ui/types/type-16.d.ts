// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice

export interface PopoverProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    trigger: React.ReactNode;
    children: React.ReactNode;
    placement?: "bottom-start" | "bottom-end" | "top-start" | "top-end";
    matchTriggerWidth?: boolean;
    className?: string;
}
export declare function Popover({ open, onOpenChange, trigger, children, placement, matchTriggerWidth, className, }: PopoverProps): import("react/jsx-runtime").JSX.Element;
