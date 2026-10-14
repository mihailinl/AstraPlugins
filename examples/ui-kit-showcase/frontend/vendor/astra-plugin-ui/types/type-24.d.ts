// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice

export interface SelectOption<T extends string> {
    value: T;
    label: React.ReactNode;
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
}
export declare function SelectOptions<T extends string>({ options, value, onChange }: Pick<SelectProps<T>, "options" | "value" | "onChange">): import("react/jsx-runtime").JSX.Element;
export declare function Select<T extends string>({ value, onChange, options, placeholder, size, disabled, id, className, bare, }: SelectProps<T>): import("react/jsx-runtime").JSX.Element;
