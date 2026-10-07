// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice

interface EmptyStateProps {
    icon: React.ReactNode;
    title: string;
    subtitle?: string;
    action?: {
        label: string;
        onClick: () => void;
    };
}
export declare function EmptyState({ icon, title, subtitle, action }: EmptyStateProps): import("react/jsx-runtime").JSX.Element;
export {};
