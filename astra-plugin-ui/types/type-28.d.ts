// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice

export interface ToggleProps {
    checked: boolean;
    onChange: (checked: boolean) => void;
    disabled?: boolean;
    loading?: boolean;
    label?: React.ReactNode;
    description?: React.ReactNode;
    ariaLabel?: string;
    id?: string;
    className?: string;
}
export declare function Toggle({ checked, onChange, disabled, loading, label, description, ariaLabel, id, className, }: ToggleProps): import("react/jsx-runtime").JSX.Element;
