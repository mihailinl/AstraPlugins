// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice
import { type ReactNode } from "react";
export interface UiEnvironment {
    readonly language: string;
    readonly hideAdvancedSettings: boolean;
    readonly labels: Readonly<{
        advanced: string;
        more: string;
        increase: string;
        decrease: string;
    }>;
}
export declare const DEFAULT_UI_ENVIRONMENT: UiEnvironment;
export declare function UiEnvironmentProvider({ value, children }: {
    value: UiEnvironment;
    children: ReactNode;
}): import("react/jsx-runtime").JSX.Element;
export declare function useUiEnvironment(): UiEnvironment;
