// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice

export interface SelectOption<T extends string> {
    value: T;
    label: React.ReactNode;
    description?: React.ReactNode;
    tone?: "warning";
    icon?: React.ReactNode;
    badge?: React.ReactNode;
    disabled?: boolean;
}
export interface SelectProps<T extends string> {
    value: T | null;
    onChange: (value: T) => void;
    options: SelectOption<T>[];
    placeholder?: React.ReactNode;
    size?: "sm" | "md";
    disabled?: boolean;
    id?: string;
    className?: string;
    bare?: boolean;
    variant?: "default" | "described";
    width?: "longest" | "content" | "full";
    title?: string;
}
export declare function SelectLayout<T extends string>({ options, value, size, width, disabled, className, rootRef, children }: Pick<SelectProps<T>, "options" | "value" | "size" | "width" | "disabled" | "className"> & {
    rootRef?: React.RefObject<HTMLDivElement | null>;
    children: React.ReactNode;
}): import("react/jsx-runtime").JSX.Element;
export declare function SelectOptions<T extends string>({ options, value, onChange, variant }: Pick<SelectProps<T>, "options" | "value" | "onChange" | "variant">): import("react/jsx-runtime").JSX.Element;
export declare function Select<T extends string>({ value, onChange, options, placeholder, size, disabled, id, className, bare, variant, width, title, }: SelectProps<T>): import("react/jsx-runtime").JSX.Element;
