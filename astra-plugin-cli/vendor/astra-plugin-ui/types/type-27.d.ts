// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice

export interface TextareaProps extends Omit<React.TextareaHTMLAttributes<HTMLTextAreaElement>, "onChange"> {
    value: string;
    onChange: (value: string) => void;
    autoResize?: boolean;
    autoList?: boolean;
    invalid?: boolean;
    ref?: React.Ref<HTMLTextAreaElement>;
}
export declare function Textarea({ value, onChange, autoResize, autoList, invalid, rows, className, "aria-invalid": ariaInvalid, ref, onKeyDown, ...rest }: TextareaProps): import("react/jsx-runtime").JSX.Element;
