import React from "react";
import { View, StyleSheet } from "react-native";
import { primitives, radius, spacing } from "../../theme";
import { Typography } from "./Typography";

export interface BadgeProps {
  variant?: "default" | "success" | "warning" | "danger" | "glow";
  style?: any;
  children?: React.ReactNode;
}

export function Badge({ variant = "default", style, children, ...rest }: BadgeProps) {
  const getVariantStyles = () => {
    switch (variant) {
      case "success":
        return { bg: "#dce6d2", text: "#2b5e3b" };
      case "warning":
        return { bg: "#fef3c7", text: "#d97706" };
      case "danger":
        return { bg: "#f5e5e3", text: primitives.terracotta };
      case "glow":
        return { bg: "rgba(0, 242, 254, 0.12)", text: "#00b4d8" };
      case "default":
      default:
        return { bg: "rgba(31, 36, 29, 0.08)", text: primitives.deepCharcoal };
    }
  };

  const { bg, text } = getVariantStyles();

  return (
    <View style={[styles.badge, { backgroundColor: bg }, style]} {...rest}>
      {typeof children === "string" ? (
        <Typography variant="label" color={text}>
          {children}
        </Typography>
      ) : (
        children
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    borderRadius: radius.full,
    paddingHorizontal: spacing[12],
    paddingVertical: spacing[4],
    alignSelf: "flex-start",
    flexDirection: "row",
    alignItems: "center",
  },
});
