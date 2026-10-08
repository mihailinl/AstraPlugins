// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice

import { type ControlTone } from "./type-31";
type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md";
export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
    variant?: ButtonVariant;
    size?: ButtonSize;
    tone?: ControlTone;
    loading?: boolean;
    iconLeft?: React.ReactNode;
    iconRight?: React.ReactNode;
    fullWidth?: boolean;
    ref?: React.Ref<HTMLButtonElement>;
}
export declare function Button({ variant, size, tone, loading, iconLeft, iconRight, fullWidth, className, children, disabled, type, ref, ...rest }: ButtonProps): import("react/jsx-runtime").JSX.Element;
export {};
