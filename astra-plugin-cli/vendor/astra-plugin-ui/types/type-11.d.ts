// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice
import { type ReactNode } from "react";
export interface FloatingControlOption {
    value: string;
    label: string;
    disabled?: boolean;
}
export interface FloatingControlRequest {
    kind: "select" | "combobox" | "tooltip";
    options?: FloatingControlOption[];
    value?: string | null;
    content?: string;
    freeSolo?: boolean;
    search?: string;
    ownerId?: string;
}
export interface FloatingControls {
    open: (request: FloatingControlRequest, anchor: HTMLElement) => Promise<string | null>;
    close: (ownerId?: string) => Promise<unknown>;
    onChange?: (ownerId: string, callback: (value: string) => void) => () => void;
}
export declare function FloatingControlsProvider({ value, children }: {
    value: FloatingControls | null;
    children: ReactNode;
}): import("react/jsx-runtime").JSX.Element;
export declare function useFloatingControls(): FloatingControls | null;
