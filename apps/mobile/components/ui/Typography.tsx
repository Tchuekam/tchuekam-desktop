import React from "react";
import { Text } from "react-native";
import { typography, TypographyVariant, primitives } from "../../theme";

export interface TypographyComponentProps {
  variant?: TypographyVariant;
  color?: string;
  align?: "auto" | "left" | "right" | "center" | "justify";
  style?: any;
  children?: React.ReactNode;
}

export function Typography({
  variant = "body",
  color = primitives.deepCharcoal,
  align = "left",
  style,
  children,
  ...rest
}: TypographyComponentProps) {
  const variantStyle = typography[variant] || typography.body;

  return (
    <Text
      style={[
        variantStyle,
        { color, textAlign: align },
        style,
      ]}
      {...rest}
    >
      {children}
    </Text>
  );
}
