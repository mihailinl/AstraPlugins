// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice

import { type IconName } from "./type-13";
export type { IconName } from "./type-13";
export { ICON_NAMES } from "./type-13";
interface IconProps {
    name: IconName;
    size?: number;
    strokeWidth?: number;
    className?: string;
}
export declare function Icon({ name, size, strokeWidth, className }: IconProps): import("react/jsx-runtime").JSX.Element;
