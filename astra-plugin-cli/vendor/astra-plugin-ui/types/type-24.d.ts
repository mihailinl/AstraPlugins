// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice

export interface SelectTriggerProps {
    open: boolean;
    onToggle: () => void;
    children?: React.ReactNode;
    placeholder?: React.ReactNode;
    icon?: React.ReactNode;
    size?: "sm" | "md";
    disabled?: boolean;
    id?: string;
    className?: string;
    bare?: boolean;
    title?: string;
    popup?: "listbox" | "menu" | "dialog";
    onMouseDown?: React.MouseEventHandler<HTMLButtonElement>;
}
export declare const SelectTrigger: import("react").ForwardRefExoticComponent<SelectTriggerProps & import("react").RefAttributes<HTMLButtonElement>>;
