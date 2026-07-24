/** @type {import('tailwindcss').Config} */
module.exports = {
  // NOTE: Update this to include the paths to all of your component files.
  content: [
    "./app/**/*.{js,jsx,ts,tsx}",
    "./components/**/*.{js,jsx,ts,tsx}",
    "./features/**/*.{js,jsx,ts,tsx}",
    "./providers/**/*.{js,jsx,ts,tsx}",
  ],
  presets: [require("nativewind/preset")],
  theme: {
    extend: {
      colors: {
        // TchueKAM Primitive Tokens
        outerCanvas: "#5c6356",
        phoneShell: "#e4ebd8",
        cardSurface: "#f4f7ef",
        pureWhite: "#ffffff",
        deepCharcoal: "#1f241d",
        mutedSage: "#5a6355",
        accentBlack: "#1a1e19",
        terracotta: "#a34237",
        cyanGlow: "#00F2FE",

        // Semantic Colors
        background: {
          primary: "#5c6356",
          secondary: "#e4ebd8",
        },
        surface: {
          default: "#f4f7ef",
          elevated: "#ffffff",
          glass: "rgba(244, 247, 239, 0.85)",
        },
        text: {
          primary: "#1f241d",
          secondary: "#5a6355",
          inverse: "#ffffff",
        },
        border: {
          default: "rgba(31, 36, 29, 0.12)",
          subtle: "rgba(31, 36, 29, 0.06)",
        },
        interactive: {
          primary: "#1a1e19",
          secondary: "#5a6355",
          accent: "#00F2FE",
        },
        status: {
          success: "#2b5e3b",
          warning: "#d97706",
          danger: "#a34237",
          info: "#2563eb",
        },
      },
      fontFamily: {
        serif: ["InstrumentSerif", "PlayfairDisplay", "serif"],
        sans: ["PlusJakartaSans", "Inter", "sans-serif"],
        mono: ["JetBrainsMono", "monospace"],
      },
    },
  },
  plugins: [],
};
