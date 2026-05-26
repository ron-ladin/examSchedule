---
name: Organic Noir
colors:
  surface: '#0b1326'
  surface-dim: '#0b1326'
  surface-bright: '#31394d'
  surface-container-lowest: '#060e20'
  surface-container-low: '#131b2e'
  surface-container: '#171f33'
  surface-container-high: '#222a3d'
  surface-container-highest: '#2d3449'
  on-surface: '#dae2fd'
  on-surface-variant: '#c2c6d6'
  inverse-surface: '#dae2fd'
  inverse-on-surface: '#283044'
  outline: '#8c909f'
  outline-variant: '#424754'
  surface-tint: '#adc6ff'
  primary: '#adc6ff'
  on-primary: '#002e6a'
  primary-container: '#4d8eff'
  on-primary-container: '#00285d'
  inverse-primary: '#005ac2'
  secondary: '#d0bcff'
  on-secondary: '#3c0091'
  secondary-container: '#571bc1'
  on-secondary-container: '#c4abff'
  tertiary: '#ffb786'
  on-tertiary: '#502400'
  tertiary-container: '#df7412'
  on-tertiary-container: '#461f00'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#d8e2ff'
  primary-fixed-dim: '#adc6ff'
  on-primary-fixed: '#001a42'
  on-primary-fixed-variant: '#004395'
  secondary-fixed: '#e9ddff'
  secondary-fixed-dim: '#d0bcff'
  on-secondary-fixed: '#23005c'
  on-secondary-fixed-variant: '#5516be'
  tertiary-fixed: '#ffdcc6'
  tertiary-fixed-dim: '#ffb786'
  on-tertiary-fixed: '#311400'
  on-tertiary-fixed-variant: '#723600'
  background: '#0b1326'
  on-background: '#dae2fd'
  surface-variant: '#2d3449'
typography:
  display-lg:
    fontFamily: Sora
    fontSize: 48px
    fontWeight: '700'
    lineHeight: '1.1'
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Sora
    fontSize: 32px
    fontWeight: '600'
    lineHeight: '1.2'
  headline-lg-mobile:
    fontFamily: Sora
    fontSize: 24px
    fontWeight: '600'
    lineHeight: '1.2'
  body-md:
    fontFamily: Sora
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '1.6'
  label-sm:
    fontFamily: Sora
    fontSize: 12px
    fontWeight: '600'
    lineHeight: '1'
    letterSpacing: 0.1em
  button:
    fontFamily: Sora
    fontSize: 14px
    fontWeight: '600'
    lineHeight: '1'
    letterSpacing: 0.05em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  container-max: 1440px
  gutter: 24px
  margin-desktop: 64px
  margin-mobile: 20px
  sidebar-width: 72px
---

## Brand & Style

This design system embodies "Organic Noir"—a sophisticated fusion of cinematic depth and high-tech precision. The brand personality is premium, visionary, and calm, designed to feel like a high-end command center for academic or professional excellence. 

The visual language centers on **Glassmorphism**, utilizing extreme backdrop blurs and semi-transparent layers to create a sense of physical weightlessness. The interface should feel like "Liquid Glass" floating over a deep, atmospheric void. We lean into a dark, high-contrast aesthetic where light is treated as a precious resource, emanating from vibrant gradients and ethereal background orbs rather than flat surfaces. The goal is to evoke an emotional response of focused clarity and technological mastery.

## Colors

The palette is anchored in a "Noir" foundation, using deep charcoal and midnight blues as the canvas. The primary energy comes from a vibrant linear gradient flowing from **Electric Blue** to **Deep Purple**.

- **Primary & Secondary:** Used for interactive states, progress indicators, and focal points.
- **Surface Strategy:** Backgrounds are not solid; they are composed of deep neutral bases with large, incredibly faint, highly blurred orbs of the primary/secondary colors (opacity 5-10%) to provide spatial depth.
- **Glass Accents:** Transparent layers use a white or primary-tinted stroke at very low opacity (10-20%) to define edges without closing off the layout.

## Typography

**Sora** is utilized globally to reinforce the technical, geometric nature of the system. 

- **Hierarchy:** We use Bold and Semibold weights for headlines to create a strong architectural anchor against the soft glass backgrounds.
- **Labels & Buttons:** These levels employ wide tracking (letter-spacing) and Uppercase styling to ensure legibility and a sophisticated, "instrument-panel" feel.
- **Legibility:** Due to the glassmorphic nature of the UI, body text should maintain a high contrast ratio against the blurred backgrounds (typically White or very light Grey).

## Layout & Spacing

The layout follows a **Fluid Grid** model with generous outer margins to allow the background "orbs" and glass edges to breathe. 

- **The Sidebar:** A slim, 72px "elegant" sidebar acts as the primary navigation anchor, utilizing thin-weight icons to maintain the high-tech aesthetic.
- **Padding:** We use a generous spacing rhythm. Elements should never feel cramped; the "Organic" part of the noir aesthetic requires enough white space (or "dark space") to feel expansive and cinematic.
- **Breakpoints:** On desktop, use a 12-column grid. On mobile, transition to a single column with the sidebar collapsing into a bottom bar or a glass-overlay menu.

## Elevation & Depth

Depth is not achieved through traditional drop shadows alone, but through **Backdrop Blur** and **Tonal Layering**.

- **Glass Layers:** Surfaces use a background blur (typically 20px to 40px) and a semi-transparent fill (e.g., `rgba(255, 255, 255, 0.05)`).
- **Borders:** Every glass container must have a thin (1px), semi-transparent border. Use a top-down light source logic: the top border should be slightly more opaque than the bottom to simulate a "glint" on the glass edge.
- **Shadows:** Use "Expansive Shadows"—low opacity, very high blur radius (40px-80px), often tinted with the Deep Purple secondary color to create a soft glow rather than a harsh shadow.

## Shapes

The shape language is **Rounded**, mirroring the "Liquid" aspect of the design narrative. 

- **Standard Elements:** Use `0.5rem` (8px) for buttons and input fields.
- **Cards & Modals:** Use `1rem` (16px) or `1.5rem` (24px) to emphasize the organic, soft nature of the floating glass panels.
- **Icons:** Icons should be thin-stroke (1px to 1.5px) and avoid filled states unless active, maintaining the airy, high-tech feel.

## Components

### Buttons
Primary buttons use the Electric Blue to Deep Purple gradient with white text. Secondary buttons are "Glass Ghost" style: transparent background, 20px backdrop blur, and a thin white border.

### Chips & Badges
Small, pill-shaped elements with a subtle 5% white fill and high-contrast text. Use these for status indicators or academic tags.

### Input Fields
Inputs should be dark and recessed, using a 1px border that illuminates with the primary gradient when focused. The cursor should be a sharp, high-visibility blue.

### Cards
The centerpiece of the UI. Cards are large glass panels with strong `backdrop-filter: blur()`. Content inside cards should be grouped using "inner glass" panels for nested hierarchy.

### Sidebar
The slim sidebar uses ultra-thin (1pt) line icons. The active state is indicated by a subtle vertical gradient bar on the leading edge and a soft glow behind the icon.

### Checkboxes & Radios
Custom-styled geometric shapes. When checked, they should glow with the primary blue, appearing as "lit" hardware lights.