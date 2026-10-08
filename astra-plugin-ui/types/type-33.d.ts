// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice
export declare function useSurfacePresence<T>(value: T | null): {
    present: boolean;
    value: T | null;
    onExitComplete: () => void;
};
