// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice

export interface CheckboxProps {
    checked: boolean;
    onChange: (checked: boolean) => void;
    label?: React.ReactNode;
    disabled?: boolean;
    indeterminate?: boolean;
    id?: string;
    className?: string;
}
export declare function Checkbox({ checked, onChange, label, disabled, indeterminate, id, className, }: CheckboxProps): import("react/jsx-runtime").JSX.Element;
