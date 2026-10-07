// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice

import { type ControlTone } from "./type-29";
type IconButtonSize = "sm" | "md" | "lg";
type IconButtonVariant = "ghost" | "solid" | "danger";
export interface IconButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
    label: string;
    size?: IconButtonSize;
    variant?: IconButtonVariant;
    tone?: ControlTone;
    children: React.ReactNode;
    ref?: React.Ref<HTMLButtonElement>;
}
export declare function IconButton({ label, size, variant, tone, className, children, type, ref, ...rest }: IconButtonProps): import("react/jsx-runtime").JSX.Element;
export {};
