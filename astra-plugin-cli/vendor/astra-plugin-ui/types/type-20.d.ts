// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice

export interface SectionProps {
    title?: React.ReactNode;
    icon?: React.ReactNode;
    description?: React.ReactNode;
    actions?: React.ReactNode;
    id?: string;
    children: React.ReactNode;
    className?: string;
    dataTutorial?: string;
    advanced?: boolean;
}
export declare function Section({ title, icon, description, actions, id, children, className, dataTutorial, advanced, }: SectionProps): import("react/jsx-runtime").JSX.Element;
