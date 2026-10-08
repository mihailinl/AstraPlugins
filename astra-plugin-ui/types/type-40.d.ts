// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice
import { createElement, type ReactNode } from "react";
import { type UiEnvironment } from "./type-30";
import { type FloatingControls } from "./type-11";
export * from "./type-38";
export declare const h: typeof createElement;

export interface UiRoot {
    render(tree: ReactNode): void;
    unmount(): void;
}
export declare function mount(container: Element, tree: ReactNode): UiRoot;
