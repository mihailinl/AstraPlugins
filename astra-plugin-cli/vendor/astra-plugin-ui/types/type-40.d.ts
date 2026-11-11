// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice
export declare function uiAnimationsEnabled(): boolean;
export declare function setUiAnimationsEnabled(enabled: boolean): void;
export declare function restoreUiAnimations(): void;
export declare function subscribeUiAnimations(listener: () => void): () => void;
export declare function isReducedMotion(): boolean;
export declare function subscribeReducedMotion(listener: () => void): () => void;
export declare function useReducedMotion(): boolean;
export declare function useUiAnimationsEnabled(): boolean;
