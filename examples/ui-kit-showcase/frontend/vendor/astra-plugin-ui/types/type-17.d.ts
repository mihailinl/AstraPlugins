// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice

export interface RadioOption<T extends string> {
    value: T;
    label: React.ReactNode;
    description?: React.ReactNode;
    disabled?: boolean;
}
export interface RadioGroupProps<T extends string> {
    value: T;
    onChange: (value: T) => void;
    options: RadioOption<T>[];
    name: string;
    className?: string;
}
export declare function RadioGroup<T extends string>({ value, onChange, options, name, className, }: RadioGroupProps<T>): import("react/jsx-runtime").JSX.Element;
