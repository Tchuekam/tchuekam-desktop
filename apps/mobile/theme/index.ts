import { semanticColors } from "./colors";
import { fontFamilies, typography } from "./typography";
import { spacing } from "./spacing";
import { radius } from "./radius";
import { shadows } from "./shadows";
import { motion } from "./motion";

export const theme = {
  colors: semanticColors,
  typography,
  fontFamilies,
  spacing,
  radius,
  shadows,
  motion,
} as const;

export type Theme = typeof theme;

export * from "./colors";
export * from "./typography";
export * from "./spacing";
export * from "./radius";
export * from "./shadows";
export * from "./motion";
