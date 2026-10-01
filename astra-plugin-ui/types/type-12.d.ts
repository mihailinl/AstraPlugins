// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice

export type IconName = "close" | "check" | "ellipsis" | "chevron-down" | "chevron-up" | "chevron-right" | "chevron-left" | "search" | "plus" | "minus" | "trash" | "edit" | "copy" | "settings" | "info" | "alert-triangle" | "x-circle" | "check-circle" | "badge-check" | "braces" | "menu" | "swap" | "external" | "steam" | "dot" | "terminal" | "file" | "folder" | "git-branch" | "globe" | "keyboard" | "play" | "volume" | "cloud-sun" | "command" | "brain" | "monitor" | "mouse-pointer" | "image" | "sticky-note" | "bell" | "calendar" | "list-checks" | "coins" | "app-window" | "clock" | "gauge" | "record" | "square" | "grip" | "eye" | "eye-off" | "mail" | "refresh" | "send" | "reply" | "forward" | "paperclip" | "download" | "lock" | "log-out" | "shield" | "plug" | "person";
interface IconProps {
    name: IconName;
    size?: number;
    strokeWidth?: number;
    className?: string;
}
export declare function Icon({ name, size, strokeWidth, className }: IconProps): import("react/jsx-runtime").JSX.Element;
export {};
