// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice

interface ModalBaseProps {
    open: boolean;
    onClose: () => void;
    children: React.ReactNode;
    footer?: React.ReactNode;
    footerLayout?: "row" | "stack";
    size?: "sm" | "md" | "lg";
    closeOnBackdrop?: boolean;
    closeOnEsc?: boolean;
    closeLabel?: string;
    hideClose?: boolean;
    clearBehind?: boolean;
    className?: string;
}
type ModalAccessibleName = {
    title: Exclude<React.ReactNode, null | undefined | boolean>;
    ariaLabel?: string;
} | {
    title?: undefined;
    ariaLabel: string;
};
export type ModalProps = ModalBaseProps & ModalAccessibleName;
export declare function Modal({ open, onClose, title, ariaLabel, children, footer, footerLayout, size, closeOnBackdrop, closeOnEsc, closeLabel, hideClose, clearBehind, className, }: ModalProps): import("react").ReactPortal | null;
export {};
