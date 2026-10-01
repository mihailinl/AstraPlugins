// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice

type BadgeTone = "neutral" | "accent" | "success" | "warning" | "danger" | "info" | "subscription";
export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
    tone?: BadgeTone;
    size?: "sm" | "md";
}
export declare function Badge({ tone, size, className, children, ...rest }: BadgeProps): import("react/jsx-runtime").JSX.Element;
export {};
