/**
 * TchueKAM Design System — Color Tokens (Sage Organic Palette)
 * Never reference raw colors in components. Always use semantic color tokens.
 */

export const primitives = {
  outerCanvas: "#5c6356",   // Muted Olive Outer Background
  phoneShell: "#e4ebd8",    // Soft Sage Screen Shell Container
  cardSurface: "#f4f7ef",   // Off-white Card Background
  pureWhite: "#ffffff",     // Pure White High Elevation Card
  deepCharcoal: "#1f241d",  // Primary Dark Text & Headings
  mutedSage: "#5a6355",     // Secondary Body & Muted Labels
  accentBlack: "#1a1e19",   // Primary Interactive Pill Buttons
  terracotta: "#a34237",    // Alert & Danger Status Accent
  cyanGlow: "#00F2FE",      // Active AI Glow & Highlight
} as const;

export const semanticColors = {
  background: {
    primary: primitives.outerCanvas,
    secondary: primitives.phoneShell,
  },
  surface: {
    default: primitives.cardSurface,
    elevated: primitives.pureWhite,
    glass: "rgba(244, 247, 239, 0.85)",
  },
  text: {
    primary: primitives.deepCharcoal,
    secondary: primitives.mutedSage,
    inverse: primitives.pureWhite,
    accent: primitives.terracotta,
    glow: primitives.cyanGlow,
  },
  border: {
    default: "rgba(31, 36, 29, 0.12)",
    subtle: "rgba(31, 36, 29, 0.06)",
    active: primitives.accentBlack,
  },
  interactive: {
    primary: primitives.accentBlack,
    secondary: primitives.mutedSage,
    accent: primitives.cyanGlow,
    danger: primitives.terracotta,
  },
  status: {
    success: "#2b5e3b",
    warning: "#d97706",
    danger: primitives.terracotta,
    info: "#2563eb",
  },
} as const;

export type Colors = typeof semanticColors;
