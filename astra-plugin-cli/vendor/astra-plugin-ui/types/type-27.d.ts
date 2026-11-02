// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice

export interface SliderProps {
    value: number;
    onChange: (value: number) => void;
    min?: number;
    max?: number;
    step?: number;
    showValue?: boolean;
    disabled?: boolean;
    id?: string;
    className?: string;
    formatValue?: (value: number) => string;
    marks?: boolean;
    "aria-label"?: string;
    "aria-valuetext"?: string;
}
export declare function Slider({ value, onChange, min, max, step, showValue, disabled, id, className, formatValue, marks, "aria-label": ariaLabel, "aria-valuetext": ariaValueText, }: SliderProps): import("react/jsx-runtime").JSX.Element;
