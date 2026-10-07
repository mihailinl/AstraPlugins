// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice

export interface InputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "onChange" | "size"> {
    value: string;
    onChange: (value: string) => void;
    size?: "sm" | "md";
    invalid?: boolean;
    bare?: boolean;
    iconLeft?: React.ReactNode;
    clearable?: boolean;
    onClear?: () => void;
    clearLabel?: string;
    ref?: React.Ref<HTMLInputElement>;
}
export declare function Input({ value, onChange, size, invalid, bare, iconLeft, clearable, onClear, clearLabel, className, disabled, "aria-invalid": ariaInvalid, ref, ...rest }: InputProps): import("react/jsx-runtime").JSX.Element;
