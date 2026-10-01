// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice

type StaticCardProps = {
    interactive?: false;
    actionLabel?: never;
    actionDisabled?: never;
    onActivate?: never;
};
type ActionableCardProps = {
    interactive: true;
    actionLabel: string;
    actionDisabled?: boolean;
    onActivate: () => void;
};
interface CardBaseProps extends React.HTMLAttributes<HTMLDivElement> {
    padding?: "none" | "sm" | "md" | "lg";
    variant?: "surface" | "subtle";
    selected?: boolean;
    as?: "div" | "section" | "article" | "li";
}
export type CardProps = CardBaseProps & (StaticCardProps | ActionableCardProps);
export declare function Card({ padding, variant, interactive, actionLabel, actionDisabled, onActivate, selected, as, className, children, ...rest }: CardProps): import("react/jsx-runtime").JSX.Element;
export {};
