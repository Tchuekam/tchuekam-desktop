/**
 * TchueKAM Design System — Typography System
 * Exhaustive font family & semantic style tokens. Never hardcode font sizes.
 */

export const fontFamilies = {
  serif: "InstrumentSerif",
  serifFallback: "PlayfairDisplay",
  sans: "PlusJakartaSans",
  sansFallback: "Inter",
  mono: "JetBrainsMono",
} as const;

export const typography = {
  display: {
    fontFamily: fontFamilies.serif,
    fontSize: 42,
    lineHeight: 46,
    letterSpacing: -0.5,
  },
  hero: {
    fontFamily: fontFamilies.serif,
    fontSize: 34,
    lineHeight: 38,
    letterSpacing: -0.3,
  },
  h1: {
    fontFamily: fontFamilies.serif,
    fontSize: 28,
    lineHeight: 32,
    letterSpacing: -0.2,
  },
  h2: {
    fontFamily: fontFamilies.sans,
    fontSize: 22,
    lineHeight: 28,
    fontWeight: "700" as const,
  },
  h3: {
    fontFamily: fontFamilies.sans,
    fontSize: 18,
    lineHeight: 24,
    fontWeight: "600" as const,
  },
  title: {
    fontFamily: fontFamilies.sans,
    fontSize: 16,
    lineHeight: 22,
    fontWeight: "600" as const,
  },
  subtitle: {
    fontFamily: fontFamilies.sans,
    fontSize: 14,
    lineHeight: 20,
    fontWeight: "500" as const,
  },
  body: {
    fontFamily: fontFamilies.sans,
    fontSize: 14,
    lineHeight: 20,
    fontWeight: "400" as const,
  },
  bodySmall: {
    fontFamily: fontFamilies.sans,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: "400" as const,
  },
  caption: {
    fontFamily: fontFamilies.sans,
    fontSize: 11,
    lineHeight: 14,
    fontWeight: "400" as const,
  },
  label: {
    fontFamily: fontFamilies.mono,
    fontSize: 10,
    lineHeight: 12,
    letterSpacing: 1.2,
    textTransform: "uppercase" as const,
  },
  button: {
    fontFamily: fontFamilies.sans,
    fontSize: 14,
    lineHeight: 18,
    fontWeight: "600" as const,
  },
  mono: {
    fontFamily: fontFamilies.mono,
    fontSize: 12,
    lineHeight: 16,
  },
} as const;

export type TypographyVariant = keyof typeof typography;
