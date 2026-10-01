// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice

export interface FieldLabelProps {
    htmlFor?: string;
    children: React.ReactNode;
    hint?: React.ReactNode;
    className?: string;
}
export declare function FieldLabel({ htmlFor, children, hint, className }: FieldLabelProps): import("react/jsx-runtime").JSX.Element;
