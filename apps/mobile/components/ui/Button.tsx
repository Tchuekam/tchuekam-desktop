import React from "react";
import {
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
} from "react-native";
import { primitives, radius, spacing } from "../../theme";
import { Typography } from "./Typography";

export interface ButtonProps {
  variant?: "primary" | "secondary" | "danger" | "ghost";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
  disabled?: boolean;
  style?: any;
  onPress?: () => void;
  children?: React.ReactNode;
}

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  disabled = false,
  style,
  onPress,
  children,
  ...rest
}: ButtonProps) {
  const getVariantStyles = () => {
    switch (variant) {
      case "secondary":
        return {
          bg: primitives.cardSurface,
          text: primitives.deepCharcoal,
          border: primitives.accentBlack,
        };
      case "danger":
        return {
          bg: primitives.terracotta,
          text: primitives.pureWhite,
          border: "transparent",
        };
      case "ghost":
        return {
          bg: "transparent",
          text: primitives.deepCharcoal,
          border: "transparent",
        };
      case "primary":
      default:
        return {
          bg: primitives.accentBlack,
          text: primitives.pureWhite,
          border: "transparent",
        };
    }
  };

  const getSizeStyles = () => {
    switch (size) {
      case "sm":
        return { paddingVertical: spacing[8], paddingHorizontal: spacing[12] };
      case "lg":
        return { paddingVertical: spacing[16], paddingHorizontal: spacing[24] };
      case "md":
      default:
        return { paddingVertical: spacing[12], paddingHorizontal: spacing[20] };
    }
  };

  const { bg, text, border } = getVariantStyles();
  const sizeStyle = getSizeStyles();

  return (
    <TouchableOpacity
      activeOpacity={0.8}
      disabled={disabled || loading}
      onPress={onPress}
      style={[
        styles.button,
        sizeStyle,
        {
          backgroundColor: bg,
          borderColor: border,
          opacity: disabled ? 0.5 : 1,
        },
        style,
      ]}
      {...rest}
    >
      {loading ? (
        <ActivityIndicator color={text} />
      ) : typeof children === "string" ? (
        <Typography variant="button" color={text}>
          {children}
        </Typography>
      ) : (
        children
      )}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  button: {
    borderRadius: radius.full,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
  },
});
