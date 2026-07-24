import React from "react";
import { View, StyleSheet } from "react-native";
import { primitives, radius, shadows, spacing } from "../../theme";

export interface CardProps {
  variant?: "default" | "elevated" | "glass";
  padding?: keyof typeof spacing;
  style?: any;
  children?: React.ReactNode;
}

export function Card({
  variant = "default",
  padding = 20,
  style,
  children,
  ...rest
}: CardProps) {
  const getBackgroundColor = () => {
    switch (variant) {
      case "elevated":
        return primitives.pureWhite;
      case "glass":
        return "rgba(244, 247, 239, 0.85)";
      case "default":
      default:
        return primitives.cardSurface;
    }
  };

  const shadowStyle = variant === "elevated" ? shadows.card : shadows.surface;

  return (
    <View
      style={[
        styles.card,
        shadowStyle,
        {
          backgroundColor: getBackgroundColor(),
          padding: spacing[padding as keyof typeof spacing] ?? padding,
        },
        style,
      ]}
      {...rest}
    >
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: radius["2xl"],
    borderWidth: 1,
    borderColor: "rgba(31, 36, 29, 0.08)",
    overflow: "hidden",
  },
});
