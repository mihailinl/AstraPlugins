// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice

import { type IconName } from "./type-14";
export type { IconName } from "./type-14";
export { ICON_NAMES } from "./type-14";
interface IconProps {
    name: IconName;
    size?: number;
    strokeWidth?: number;
    className?: string;
}
export declare function Icon({ name, size, strokeWidth, className }: IconProps): import("react/jsx-runtime").JSX.Element;
