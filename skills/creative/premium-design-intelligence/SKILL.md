---
name: premium-design-intelligence
description: >-
  World-class design system and evaluation engine derived from high-end visual inspirations (UI/UX, motion, luxury branding, typography, industrial design). Use when designing or evaluating web apps, user interfaces, graphic designs, animations, or product aesthetics to achieve Apple-, Stripe-, and Linear-grade visual excellence.
---

# Premium Design Intelligence

## Overview
This skill encodes universal principles of luxury and high-end digital design derived from analyzing top-tier product designs, dashboards, promotional materials, motion graphics, and luxury brand identities.

---

## 1. Core Philosophy
- **Disciplined Reduction**: True luxury and elegance are achieved not by adding elements, but by removing everything unnecessary until every pixel carries clear purpose.
- **Multi-Modal Hierarchy**: Never rely on a single attribute (such as color or font size) to establish hierarchy. Combine spatial density, font weight, contrast, alignment, opacity, and subtle micro-motion.
- **Tactile Digitality**: High-end UI bridges physical tactile qualities (materials, soft ambient lighting, glass refraction, physical bounce dynamics) with digital clarity.

---

## 2. Universal Design Laws

### LAW 01: Multi-Modal Hierarchy
Premium interfaces never rely on color alone to convey importance. They layer at least 3 distinct cues simultaneously: font weight differential, negative space padding, and luminance contrast.

### LAW 02: Corner Radius Continuity (Squircle Harmony)
Sub-elements inside a container must have a border radius proportional to the parent container:
$$\text{Radius}_{\text{child}} = \text{Radius}_{\text{parent}} - \text{Padding}$$
This maintains visual organic alignment without visual clashing.

### LAW 03: Ambient Light & Shadow Softness
Luxury digital depth avoids harsh black drop shadows. Use multi-layered ambient light diffusion with blur radii between $24\text{px}$ and $64\text{px}$, driven by ultra-low opacities ($3\% - 8\%$).

### LAW 04: High Contrast Typography Ratios
Primary body text should maintain high contrast ($12:1+$ against canvas), while secondary and metadata labels use controlled opacity drop ($60\% - 70\%$) rather than muted gray hex codes, ensuring crisp rendering across OLED screens.

---

## 3. Evaluation Rubric (100-Point Scale)

| Criterion | Max Score | Description & Benchmark |
| :--- | :--- | :--- |
| **Visual Hierarchy** | 10 | Immediate scanability; distinct focal points without visual clutter. |
| **Spacing & Padding** | 10 | Mathematical consistency (8px/4px grid system); generous whitespace. |
| **Typography** | 10 | Refined font selection, letter-spacing tuning, perfect leading. |
| **Composition & Balance**| 10 | Asymmetric balance, visual weight harmony, structured grid alignment. |
| **Material & Depth** | 10 | Realistic blur (glassmorphic), ambient diffusion, non-harsh depth layers. |
| **Color Harmony** | 10 | Curated palette (max 1 primary accent), tailored HSL values. |
| **Consistency** | 10 | Cohesive radius, icon weights, padding systems, border styling. |
| **Motion & Micro-anim** | 10 | Natural spring physics, instant response times ($<200\text{ms}$ ease-out). |
| **Luxury & Premium Feel**| 10 | Feels custom-built, bespoke, and expensive; zero generic stock aesthetics. |
| **Professionalism** | 10 | Flawless alignment, high readability, zero optical glitches. |

---

## 4. Beauty & Luxury Heuristics

1. **Subtle Tactile Feedback**: Micro-interactions should use elastic spring physics (e.g. `cubic-bezier(0.16, 1, 0.3, 1)` or damped spring `stiffness: 300, damping: 30`) to feel continuous and responsive.
2. **Dynamic Surface Reflection**: High-end glassmorphism uses multi-layered borders: top border high opacity highlight ($15\%-25\%$ white border), bottom border dark shadow ($5\%-10\%$ black border), overlaid on `backdrop-filter: blur(20px)`.
3. **Monochromatic Base with Focal Accent**: $90\%$ of the canvas utilizes refined monochrome/grayscale tones, allowing the single focal accent color to guide the eye without overwhelming perception.

---

## 5. Negative Anti-Patterns (What to Avoid)

- ❌ **Pure Black Shadows**: Using `rgba(0,0,0,0.5)` with low blur radius ($<10\text{px}$).
- ❌ **Saturated Default Colors**: Using default hex codes like `#FF0000` or `#0000FF`. Always tune HSL for softer saturation and luxury tone.
- ❌ **Inconsistent Radius**: Mixing sharp $0\text{px}$ corners with $16\text{px}$ cards without structural logic.
- ❌ **Text Over-crowding**: Line heights lower than $1.4$ for body copy, or line lengths exceeding $75$ characters.
- ❌ **Heavy Borders**: Solid $2\text{px}$ dark borders around elements. Use light $1\text{px}$ semi-transparent strokes instead (`rgba(255,255,255,0.1)` or `rgba(0,0,0,0.06)`).

---

## 6. Premium Design DNA

- **Typography**: Inter, SF Pro, Outfit, Geist, or custom serif accents. Strict scale ($12\text{px}, 14\text{px}, 16\text{px}, 20\text{px}, 24\text{px}, 32\text{px}, 48\text{px}, 64\text{px}$).
- **Spacing**: Base 8px scale. Component internal padding minimum 16px to 24px.
- **Motion**: Fast entry ($150\text{ms}-250\text{ms}$), fluid ease-out curves, subtle hover scale ($1.01\times-1.02\times$).
- **Color Palette**: Dark mode canvas `#090A0F` or `#0D0E12`, glass cards `rgba(255, 255, 255, 0.03)`, subtle accents (electric indigo, emerald green, warm amber).

---

## 7. Self-Evaluation & Generation Workflow

1. **Step 1 - Blueprinting**: Establish layout grid, define color tokens and radius system before writing visual elements.
2. **Step 2 - Composition**: Lay out components using negative space as a primary structural element.
3. **Step 3 - Polish**: Apply ambient shadows, glass strokes, subtle hover micro-animations, and typographic hierarchy.
4. **Step 4 - Self-Audit**: Score against the 100-point rubric. If any section drops below 9/10, apply corresponding design laws to refactor.
