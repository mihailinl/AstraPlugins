// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice

export type ProgressTone = "accent" | "neutral" | "success" | "warning" | "danger";
export interface ProgressSegment {
    value: number;
    tone?: ProgressTone;
    label?: string;
}
export interface ProgressBarProps {
    value?: number | null;
    max?: number;
    segments?: ProgressSegment[];
    tone?: ProgressTone;
    busy?: boolean;
    size?: "sm" | "md";
    label?: string;
    className?: string;
}
export declare function ProgressBar({ value, max, segments, tone, busy, size, label, className, }: ProgressBarProps): import("react/jsx-runtime").JSX.Element;
