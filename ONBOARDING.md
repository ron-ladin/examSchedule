# Syncademic — UI Development Guide

## Stack
React + Vite + Tailwind CSS. Run with `npm run dev` from `/frontend`.

---

## Design System

### Colors
```css
:root {
  --color-primary: #440154;
  --color-secondary: #21918C;
  --color-cta: #FDE725;
  --color-cta_text: #1A1A2E;
  --color-background: #F5F5F5;
  --color-text: #1A1A2E;
}
```

### Fonts
```html
<style>@import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600;700&family=Fira+Sans:wght@300;400;500;600;700&display=swap');</style>
```
- **Fira Sans** → body text, labels
- **Fira Code** → numbers, data, code

---

## App Layout

```
┌─────────────────────────────────────────────────┐
│  Navbar (logo + status bar)                     │
├──────────────┬──────────────────────────────────┤
│              │  KPI row (schedules / programs)  │
│   Sidebar    ├──────────────────────────────────┤
│  - Upload    │  Calendar / Schedule grid        │
│  - Programs  ├──────────────────────────────────┤
│  - Status    │  Results table + export button   │
└──────────────┴──────────────────────────────────┘
```

```css
.dashboard {
  display: grid;
  grid-template-columns: 250px 1fr;
  min-height: 100vh;
}
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
  margin-bottom: 1.5rem;
}
```

---

## Screen Flow

```
Upload screen  →  Program select  →  Generate  →  Results / Calendar
(courses.txt       (multi-select,      (button +     (paginated,
 dates.txt)         max 5)             polling)       export)
```

---

## Inspiration Sites

| Site | What to copy |
|------|-------------|
| linear.app | Sidebar, card layout, typography |
| vercel.com/dashboard | KPI cards, status badges |
| cal.com | Calendar grid, time slot cells |
| stripe.com/dashboard | Data tables, color-coded status |

Open DevTools and inspect their spacing, border-radius, and shadows — copy directly.

---

## Build Order

1. CSS tokens (`colors`, `fonts`, `spacing`) into `index.css`
2. Layout shell — sidebar + main grid
3. Navbar with status indicator
4. Upload panel (drag & drop, two files)
5. Programme multi-select (max 5, badges)
6. Generate button + polling loop (`GET /api/generate/status`)
7. Schedule calendar grid
8. Export button (`GET /api/schedules/{id}/export`)

Get one component pixel-perfect before moving to the next.

---

## API Endpoints (backend on port 8000)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/data/courses/upload` | Upload courses.txt |
| POST | `/api/data/periods/upload` | Upload dates.txt |
| GET | `/api/data/status` | Check what's loaded |
| GET | `/api/programmes` | List available programs |
| POST | `/api/schedules/generate` | Start generation (returns 202) |
| GET | `/api/generate/status` | Poll generation progress |
| GET | `/api/schedules` | Get paginated results |
| GET | `/api/schedules/{id}/export` | Download schedule |

Poll `/api/generate/status` every 2s while `status === "running"`. Stop when `completed` or `failed`.

---

## Component Checklist (SCRUM-79 to SCRUM-94)

- [ ] SCRUM-79: React + Vite + Tailwind scaffold
- [ ] SCRUM-80: `api/client.ts` typed fetch wrapper
- [ ] SCRUM-81: Toast notification system
- [ ] SCRUM-82: File upload panel (courses + dates)
- [ ] SCRUM-83: Programme multi-select panel
- [ ] SCRUM-84: Course drill-down accordion
- [ ] SCRUM-85: ExamPeriodCalendar component
- [ ] SCRUM-86: Date range pickers per semester
- [ ] SCRUM-87: Input screen layout + status bar
- [ ] SCRUM-88: Generate button + loading state
- [ ] SCRUM-89: ScheduleCalendar component
- [ ] SCRUM-90: ExamSlot cell component
- [ ] SCRUM-91: Semester group layout
- [ ] SCRUM-92: Nav bar + pagination
- [ ] SCRUM-93: Programme colour coding
- [ ] SCRUM-94: Save schedule button

---

## Before Writing Any Component

Always query the design tool first:
```
ui-ux-pro → get_design_system
  query: "dashboard web app schedule calendar clean minimal"
  platform: web
```
It returns ready-to-paste CSS for layout, hover effects, and spacing.
