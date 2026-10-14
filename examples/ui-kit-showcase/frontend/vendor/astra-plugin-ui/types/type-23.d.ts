// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice
import { type ReactNode } from "react";

export interface SegmentedControlOption<T extends string> {
    value: T;
    label: ReactNode;
    icon?: ReactNode;
    disabled?: boolean;
    title?: string;
}
interface SegmentedControlBaseProps<T extends string> {
    value: T;
    options: readonly SegmentedControlOption<T>[];
    onChange: (value: T) => void;
    ariaLabel: string;
    variant?: "default" | "plain";
    className?: string;
}
export type SegmentedControlProps<T extends string> = SegmentedControlBaseProps<T> & ({
    mode: "tabs";
    id: string;
    panelId: string;
} | {
    mode?: "selection";
    id?: string;
    panelId?: never;
});
export declare function SegmentedControl<T extends string>({ value, options, onChange, ariaLabel, mode, variant, id, panelId, className, }: SegmentedControlProps<T>): import("react/jsx-runtime").JSX.Element;
export {};
