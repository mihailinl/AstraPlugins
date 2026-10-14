// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice
export interface ListEdit {
    start: number;
    end: number;
    text: string;
}
export declare function composerParagraphBreak(child: HTMLElement, text: string): boolean;
export declare function composerListEdit(text: string, caret: number, action: "space" | "newline"): ListEdit | null;
export declare function editComposerList(root: HTMLElement, action: "space" | "newline"): boolean;
