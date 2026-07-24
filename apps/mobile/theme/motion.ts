/**
 * TchueKAM Design System — Motion & Animation Tokens
 */

export const motion = {
  duration: {
    instant: 50,
    fast: 150,
    normal: 250,
    slow: 400,
    deliberate: 600,
  },
  easing: {
    standard: "cubic-bezier(0.2, 0.0, 0.0, 1.0)",
    accelerate: "cubic-bezier(0.3, 0.0, 1.0, 1.0)",
    decelerate: "cubic-bezier(0.0, 0.0, 0.2, 1.0)",
  },
  spring: {
    gentle: { damping: 20, stiffness: 120, mass: 1 },
    responsive: { damping: 15, stiffness: 180, mass: 0.8 },
    bouncy: { damping: 12, stiffness: 200, mass: 1 },
  },
} as const;

export type Motion = typeof motion;
