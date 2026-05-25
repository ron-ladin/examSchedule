# Syncademic Design System

**SCRUM-109** — UI/UX Design Document  
Version: 1.0 · Date: 2026-05-25  
Brand: **Organic Noir** (light + dark) · Stack: React 18 + Vite 5 + Tailwind 4

---

## 1. Brand Overview

Syncademic is a high-end command center for academic scheduling. The visual language centres on **Glassmorphism** — extreme `backdrop-filter` blur layers floating over a luminous or cinematic void — combined with the **Electric Blue → Deep Purple** gradient as the primary energy colour.

Brand personality: **premium · visionary · calm**.  
Every surface should feel like liquid glass; every interaction should feel precise and inevitable.

---

## 2. Colour System

Tokens are defined in `src/index.css` under `:root` (light) and `[data-theme="dark"]` (dark). The user switches modes via `ThemeToggle` — preference persists to `localStorage` under the key `syncademic-theme`.

### 2a. Light Mode — "Luminous Gallery"

| Token | Value | Role |
|---|---|---|
| `--surface` | `#faf8ff` | Page background |
| `--surface-container-lowest` | `#ffffff` | Cards, modals |
| `--surface-container-low` | `#f2f3ff` | Subtle insets |
| `--surface-container` | `#eaedff` | Chips, inner panels |
| `--surface-container-high` | `#e2e7ff` | Hover states |
| `--on-surface` | `#131b2e` | Primary text |
| `--on-surface-variant` | `#424754` | Secondary text |
| `--primary` | `#0058be` | Interactive Blue |
| `--secondary` | `#6b38d4` | Interactive Purple |
| `--outline` | `#727785` | Borders (strong) |
| `--outline-variant` | `#c2c6d6` | Borders (subtle) |
| `--success` | `#10b981` | Positive states |
| `--warning` | `#f59e0b` | Caution states |
| `--error` | `#ba1a1a` | Error states |

Gradient: `linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%)`  
Glass (light): `rgba(250,248,255,0.75)` + `backdrop-filter: blur(20px)` + `border: 1px solid #c2c6d6`

### 2b. Dark Mode — "Organic Noir"

| Token | Value | Role |
|---|---|---|
| `--surface` | `#0b1326` | Page background |
| `--surface-container-lowest` | `#060e20` | Cards, modals |
| `--surface-container-low` | `#131b2e` | Subtle insets |
| `--surface-container` | `#171f33` | Chips, inner panels |
| `--surface-container-high` | `#222a3d` | Hover states |
| `--on-surface` | `#dae2fd` | Primary text |
| `--on-surface-variant` | `#c2c6d6` | Secondary text |
| `--primary` | `#adc6ff` | Interactive Blue (light) |
| `--secondary` | `#d0bcff` | Interactive Purple (light) |
| `--outline` | `#8c909f` | Borders (strong) |
| `--outline-variant` | `#424754` | Borders (subtle) |
| `--success` | `#6ee7b7` | Positive states |
| `--warning` | `#fbbf24` | Caution states |
| `--error` | `#ffb4ab` | Error states |

Glass (dark): `rgba(255,255,255,0.05)` + `backdrop-filter: blur(20px)` + `border: 1px solid rgba(255,255,255,0.10)`

---

## 3. Typography

All fonts are loaded from Google Fonts via `index.html`.

| Role | Font | Weight | Size | Notes |
|---|---|---|---|---|
| Display / Hero | Sora | 800 | `clamp(2.5rem, 5vw, 4rem)` | `letter-spacing: -0.03em` |
| Headings (h1–h3) | Sora | 700 | 1.75rem – 1.1rem | `letter-spacing: -0.02em` |
| Body | Inter | 400 | 0.875rem – 1rem | `line-height: 1.65` |
| Labels / Chips | JetBrains Mono | 500 | 0.65rem – 0.7rem | `letter-spacing: 0.05em; text-transform: uppercase` |
| Buttons | Sora | 600 | 0.875rem – 0.9rem | `letter-spacing: 0.01em` |

---

## 4. Spacing & Shape

| Token | Value |
|---|---|
| `--radius-sm` | 0.5rem (8px) — inputs, badges |
| `--radius-md` | 1rem (16px) — upload zones |
| `--radius-lg` | 1.5rem (24px) — cards |
| `--radius-xl` | 2rem (32px) — hero card |
| `--radius-pill` | 9999px — buttons, chips |
| Container max-width | 1280px |
| Page gutter | 2rem (32px) |
| Sidebar width (Dashboard) | 240px |

---

## 5. Component Library

### 5.1 Buttons

```css
.btn-primary   /* gradient fill, pill, Sora 600, glow shadow */
.btn-ghost     /* transparent, white border, blur backdrop */
.btn-outline   /* transparent, primary-colour border */
.btn-secondary /* surface-container fill, on-surface text */
```

All primary CTAs use `MotionButton` from `src/components/Motion.jsx` for `scale(1.03)` hover / `scale(0.96)` tap feedback.

### 5.2 Cards

```css
.card          /* surface-container-lowest, radius-lg, glass-shadow */
.glass         /* semi-transparent + blur — dark hero surfaces */
.glass-light   /* semi-transparent light variant */
```

Interactive cards use `MotionCard` for `y: -3px` lift + glow on hover.

### 5.3 Chips

```
.chip .chip-blue   .chip-purple   .chip-green   .chip-orange   .chip-red
```

Pill shape, JetBrains Mono, uppercase, 0.7rem. Dark-mode variants automatically override via `[data-theme="dark"]`.

### 5.4 Upload Zone

```css
.upload-zone            /* dashed border, pointer cursor */
.upload-zone:hover      /* blue border + tint */
.upload-zone.drag-over  /* active drag state */
.upload-zone.has-file   /* success green border */
```

### 5.5 Sidebar Nav

```css
.sidebar-item           /* flex row, 0.875rem Inter 500 */
.sidebar-item:hover     /* surface-container tint + primary colour */
.sidebar-item.active    /* gradient background highlight */
```

---

## 6. Animation System

Implemented with **Framer Motion** (`framer-motion` package). Utilities live in `src/components/Motion.jsx`.

| Export | Effect | Usage |
|---|---|---|
| `PageShell` | `opacity 0→1, y 16→0` (0.22s) on enter; `opacity 1→0, y 0→-8` on exit | Wraps every page root |
| `MotionCard` | `y: -3, boxShadow glow` on hover | Schedule cards, calendar cells |
| `MotionButton` | `scale 1.03` hover, `scale 0.96` tap (spring) | Primary CTAs |
| `StaggerList` | `staggerChildren: 0.06s` container | Schedule option grid, exam lists |
| `StaggerItem` | `opacity 0→1, y 12→0` (0.22s) | Individual stagger children |

**Ambient orbs** on `LandingPage` and `ProcessingState`: `motion.div` with `animate={{ x:[0,18,-12,0], y:[0,-28,16,0] }}` and `repeat: Infinity`, duration 10–12s.

**Registration confetti**: `canvas-confetti` fires on `step === 'success'` with colours `#3b82f6`, `#8b5cf6`, `#10b981`, `#f59e0b`.

**Global page transitions**: `AnimatePresence mode="wait"` in `App.jsx` wraps `<Routes>` with `location` + `key={location.pathname}` so each navigation triggers the enter/exit sequence.

---

## 7. Screen Reference

Screenshots are stored in `docs/images/`. Add PNG files named as below and they will render inline.

| Screen | File | Description |
|---|---|---|
| Landing Page (Light) | `images/landing-light.png` | Hero, Nav with ThemeToggle |
| Landing Page (Dark) | `images/landing-dark.png` | Organic Noir hero |
| Dashboard (Light) | `images/dashboard-light.png` | Sidebar + upload cards |
| Dashboard (Dark) | `images/dashboard-dark.png` | Dark sidebar variant |
| Processing State | `images/processing.png` | Engine steps + animated orbs |
| Schedule Results | `images/results.png` | Three option cards + history |
| Detailed Calendar | `images/calendar.png` | Month view + day sidebar |
| Register — Success | `images/register-success.png` | Confetti on account creation |

To add screenshots: save the file to `docs/images/<name>.png` and uncomment the corresponding line below.

<!-- ![Landing Page Light](images/landing-light.png) -->
<!-- ![Landing Page Dark](images/landing-dark.png) -->
<!-- ![Dashboard Light](images/dashboard-light.png) -->
<!-- ![Dashboard Dark](images/dashboard-dark.png) -->
<!-- ![Processing State](images/processing.png) -->
<!-- ![Schedule Results](images/results.png) -->
<!-- ![Detailed Calendar](images/calendar.png) -->
<!-- ![Register Success](images/register-success.png) -->

---

## 8. CSS Custom Properties Reference

All tokens are consumed via `var(--token-name)` in components. Never hardcode hex values in component files — always use tokens or the named gradient variables.

```css
var(--gradient-primary)     /* 135deg Electric Blue → Deep Purple */
var(--gradient-electric)    /* 135deg lighter variant */
var(--gradient-glow)        /* 135deg transparent tint (15% opacity) */
var(--glass-bg)             /* surface for dark glass panels */
var(--glass-bg-light)       /* surface for light glass panels */
var(--glass-blur)           /* 20px — standard blur radius */
var(--glass-shadow)         /* card drop-shadow */
var(--glass-glow)           /* blue/purple outer glow */
```

---

## 9. File Map

```
src/
  index.css                   ← design tokens, keyframes, utility classes
  components/
    Motion.jsx                ← PageShell, MotionCard, MotionButton, Stagger*
    ThemeToggle.jsx           ← sun/moon toggle button
    NavBar.jsx                ← shared sticky nav (includes ThemeToggle)
    Toast.jsx                 ← ToastContainer + Toast pill
    ExamSlot.jsx              ← compact pill + full card (SCRUM-90)
    SemesterGroupLayout.jsx   ← FALL/SPRI/SUMM section grouper (SCRUM-91)
  hooks/
    useTheme.js               ← localStorage-backed light/dark state
    useToast.js               ← toast queue
    useScheduler.js           ← global app state
  utils/
    progColor.js              ← deterministic programme colour hash (SCRUM-93)
  api/
    client.js                 ← typed API client
doc/
  DESIGN_LIGHT.md             ← Stitch light-mode token export
  DESIGN_DARK.md              ← Stitch dark-mode token export
docs/
  design.md                   ← this file (SCRUM-109)
  images/                     ← screenshots (add manually)
```
