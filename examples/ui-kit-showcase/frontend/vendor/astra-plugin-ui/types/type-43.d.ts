// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice
import type { ReactNode } from "react";
import { type ButtonProps } from "./type-5";
import { type IconName } from "./type-13";

export declare function WidgetHead({ icon, title, meta, trailing, className }: {
    icon: IconName;
    title: ReactNode;
    meta?: ReactNode;
    trailing?: ReactNode;
    className?: string;
}): import("react/jsx-runtime").JSX.Element;
export declare function WidgetMetric({ children, size, className }: {
    children: ReactNode;
    size?: "xl" | "lg" | "md" | "sm";
    className?: string;
}): import("react/jsx-runtime").JSX.Element;
export declare function AstraLine({ children, className }: {
    children: ReactNode;
    className?: string;
}): import("react/jsx-runtime").JSX.Element;
export declare function WidgetPlate({ children, className, pill }: {
    children: ReactNode;
    className?: string;
    pill?: boolean;
}): import("react/jsx-runtime").JSX.Element;
export declare function WidgetMeter({ value, max, label, className }: {
    value: number;
    max?: number;
    label?: string;
    className?: string;
}): import("react/jsx-runtime").JSX.Element;
export declare function WidgetPlateButton({ className, ...props }: Omit<ButtonProps, "variant">): import("react/jsx-runtime").JSX.Element;
