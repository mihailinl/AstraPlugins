// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice

interface NumberInputProps {
    value: number;
    onChange: (value: number) => void;
    min?: number;
    max?: number;
    step?: number;
    placeholder?: string;
    className?: string;
    inputClassName?: string;
    id?: string;
    disabled?: boolean;
    incrementLabel?: string;
    decrementLabel?: string;
    emptyValue?: number;
}
export declare function NumberInput({ value, onChange, min, max, step, placeholder, className, inputClassName, id, disabled, incrementLabel, decrementLabel, emptyValue, }: NumberInputProps): import("react/jsx-runtime").JSX.Element;
export {};
