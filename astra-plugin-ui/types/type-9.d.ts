// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice

export interface ComboboxOption {
    value: string;
    label?: React.ReactNode;
    badge?: React.ReactNode;
}
export interface ComboboxProps {
    value: string;
    onChange: (value: string) => void;
    options: ComboboxOption[];
    placeholder?: string;
    freeSolo?: boolean;
    onCreate?: (value: string) => void;
    disabled?: boolean;
    size?: "sm" | "md";
    id?: string;
    className?: string;
}
export declare function Combobox({ value, onChange, options, placeholder, freeSolo, onCreate, disabled, size, id, className, }: ComboboxProps): import("react/jsx-runtime").JSX.Element;
