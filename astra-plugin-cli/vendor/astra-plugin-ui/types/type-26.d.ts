// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice

export interface SettingRowProps {
    label: React.ReactNode;
    description?: React.ReactNode;
    control?: React.ReactNode;
    htmlFor?: string;
    layout?: "inline" | "stacked";
    children?: React.ReactNode;
    className?: string;
}
export declare function SettingRow({ label, description, control, htmlFor, layout, children, className, }: SettingRowProps): import("react/jsx-runtime").JSX.Element;
