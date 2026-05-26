---
name: Organic Noir (Light Mode)
colors:
  surface: '#faf8ff'
  surface-dim: '#d2d9f4'
  surface-bright: '#faf8ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f2f3ff'
  surface-container: '#eaedff'
  surface-container-high: '#e2e7ff'
  surface-container-highest: '#dae2fd'
  on-surface: '#131b2e'
  on-surface-variant: '#424754'
  inverse-surface: '#283044'
  inverse-on-surface: '#eef0ff'
  outline: '#727785'
  outline-variant: '#c2c6d6'
  surface-tint: '#005ac2'
  primary: '#0058be'
  on-primary: '#ffffff'
  primary-container: '#2170e4'
  on-primary-container: '#fefcff'
  inverse-primary: '#adc6ff'
  secondary: '#6b38d4'
  on-secondary: '#ffffff'
  secondary-container: '#8455ef'
  on-secondary-container: '#fffbff'
  tertiary: '#924700'
  on-tertiary: '#ffffff'
  tertiary-container: '#b75b00'
  on-tertiary-container: '#fffbff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
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
  background: '#faf8ff'
  on-background: '#131b2e'
  surface-variant: '#dae2fd'
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

While the aesthetic remains "Noir" in spirit, this light-mode variant transitions from a deep void to a "Luminous Gallery" feel. The visual language centers on **Glassmorphism**, utilizing extreme backdrop blurs and semi-transparent layers to create a sense of physical weightlessness. The interface should feel like "Liquid Glass" floating over a bright, ethereal atmosphere. We lean into a high-clarity aesthetic where light is abundant, emanating from soft gradients and airy background orbs rather than flat surfaces. The goal is to evoke an emotional response of focused clarity and technological mastery.

## Colors

The palette is anchored in a luminous foundation, using soft off-whites and cool greys (derived from the Slate neutral) as the canvas. The primary energy comes from a vibrant linear gradient flowing from **Electric Blue** to **Deep Purple**.

- **Primary & Secondary:** Used for interactive states, progress indicators, and focal points.
- **Surface Strategy:** Backgrounds are not solid; they are composed of light neutral bases with large, incredibly faint, highly blurred orbs of the primary/secondary colors (opacity 5-8%) to provide spatial depth.
- **Glass Accents:** Transparent layers use a white or primary-tinted stroke at low opacity (20-30%) to define edges without closing off the layout.

## Typography

**Sora** is utilized globally to reinforce the technical, geometric nature of the system. 

- **Hierarchy:** We use Bold and Semibold weights for headlines to create a strong architectural anchor against the soft glass backgrounds.
- **Labels & Buttons:** These levels employ wide tracking (letter-spacing) and Uppercase styling to ensure legibility and a sophisticated, "instrument-panel" feel.
- **Legibility:** In light mode, body text utilizes deep charcoal (neutral-variant) to maintain a high contrast ratio against the bright blurred backgrounds.

## Layout & Spacing

The layout follows a **Fluid Grid** model with generous outer margins to allow the background "orbs" and glass edges to breathe. 

- **The Sidebar:** A slim, 72px "elegant" sidebar acts as the primary navigation anchor, utilizing thin-weight icons to maintain the high-tech aesthetic.
- **Padding:** We use a generous spacing rhythm. Elements should never feel cramped; the "Organic" part of the noir aesthetic requires enough white space to feel expansive and cinematic.
- **Breakpoints:** On desktop, use a 12-column grid. On mobile, transition to a single column with the sidebar collapsing into a bottom bar or a glass-overlay menu.

## Elevation & Depth

Depth is not achieved through traditional drop shadows alone, but through **Backdrop Blur** and **Tonal Layering**.

- **Glass Layers:** Surfaces use a background blur (typically 20px to 40px) and a semi-transparent white fill (e.g., `rgba(255, 255, 255, 0.4)`).
- **Borders:** Every glass container must have a thin (1px), semi-transparent border. Use a top-down light source logic: the top border should be slightly more opaque/lighter than the bottom to simulate a "glint" on the glass edge.
- **Shadows:** Use "Expansive Shadows"—low opacity, very high blur radius (40px-80px), using the neutral slate color to create a soft, natural lift from the surface.

## Shapes

The shape language is **Rounded**, mirroring the "Liquid" aspect of the design narrative. 

- **Standard Elements:** Use `0.5rem` (8px) for buttons and input fields.
- **Cards & Modals:** Use `1rem` (16px) or `1.5rem` (24px) to emphasize the organic, soft nature of the floating glass panels.
- **Icons:** Icons should be thin-stroke (1px to 1.5px) and avoid filled states unless active, maintaining the airy, high-tech feel.

## Components

### Buttons
Primary buttons use the Electric Blue to Deep Purple gradient with white text. Secondary buttons are "Glass Ghost" style: transparent white background (15% opacity), 20px backdrop blur, and a thin primary-tinted border.

### Chips & Badges
Small, pill-shaped elements with a subtle 10% neutral fill and high-contrast text. Use these for status indicators or academic tags.

### Input Fields
Inputs should be light and clean, using a 1px border that illuminates with the primary blue when focused. The background should be a slightly more opaque glass than the card it sits on.

### Cards
The centerpiece of the UI. Cards are large glass panels with strong `backdrop-filter: blur()`. Content inside cards should be grouped using "inner glass" panels for nested hierarchy.

### Sidebar
The slim sidebar uses ultra-thin (1pt) line icons. The active state is indicated by a subtle vertical gradient bar on the leading edge and a soft, luminous glow behind the icon.

### Checkboxes & Radios
Custom-styled geometric shapes. When checked, they should glow with the primary blue, appearing as "active" hardware lights.