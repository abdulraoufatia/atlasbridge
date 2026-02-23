# AtlasBridge Brand System v1

> Canonical brand reference for AtlasBridge. All UI surfaces (dashboard, TUI, console, CLI, docs) should align with this spec.

---

## Brand DNA

| Keyword | Meaning |
|---------|---------|
| Deterministic | Every decision traceable to a policy rule |
| Governance | Structured control, not chaos |
| Autonomy | Agents act within defined boundaries |
| Safety | Default-safe, escalate on uncertainty |
| Transparency | Audit log, decision trace, hash chain |

---

## Positioning

**Statement:**
AtlasBridge is a deterministic governance runtime for AI agents. It provides structured autonomy under explicit policy control, ensuring AI-driven workflows operate safely, audibly, and predictably across development and enterprise environments.

**Taglines (approved):**
- "Controlled autonomy for AI agents."
- "Deterministic governance for AI execution."

---

## Color Palette

### Primary Colors

| Token | Name | Hex | Usage |
|-------|------|-----|-------|
| `--ab-primary` | Atlas Navy | `#0B2A3C` | Brand identity, headings, primary buttons |
| `--ab-neutral` | Bridge Slate | `#6E7A86` | Secondary text, muted UI elements |
| `--ab-bg` | Foundation Light | `#F5F7F9` | Light mode page background |
| `--ab-accent` | Governance Teal | `#1F8A8C` | Links, active states, small highlights (use sparingly) |

### Status Colors (Muted Enterprise)

| Token | Name | Hex | Usage |
|-------|------|-----|-------|
| `--ab-success` | Success | `#1E7E34` | Running, verified, pass |
| `--ab-warning` | Warning | `#C77D00` | Awaiting input, caution |
| `--ab-danger` | Danger | `#A4161A` | Crashed, failed, error |

### Dark Mode

| Token | Hex | Usage |
|-------|-----|-------|
| `--ab-bg` | `#071D2B` | Deep Control Navy background |
| `--ab-panel` | `#0D2B3E` | Card/panel background |
| `--ab-panel-hover` | `#133A52` | Hover state |
| `--ab-border` | `#1A4A64` | Borders |
| `--ab-text` | `#E6EEF5` | Primary text |
| `--ab-text-muted` | `#A8B3BD` | Secondary/muted text |
| `--ab-accent` | `#1F8A8C` | Governance Teal (same hex, may adjust opacity) |

### Light Mode

| Token | Hex | Usage |
|-------|-----|-------|
| `--ab-bg` | `#F5F7F9` | Foundation Light background |
| `--ab-panel` | `#FFFFFF` | Card/panel background |
| `--ab-panel-hover` | `#EDF0F3` | Hover state |
| `--ab-border` | `#D1D9E0` | Borders |
| `--ab-text` | `#0B2A3C` | Primary text (Atlas Navy) |
| `--ab-text-muted` | `#6E7A86` | Bridge Slate muted text |
| `--ab-accent` | `#1F8A8C` | Governance Teal |

---

## Typography

### Font Stacks

**UI / Body:**
```
Inter, "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif
```

**Monospace / Code:**
```
"JetBrains Mono", "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace
```

No external font downloads or CDNs. These stacks use system-installed fonts with safe fallbacks. If Inter or JetBrains Mono is not installed, the fallback chain ensures legibility.

### Weights

| Element | Weight |
|---------|--------|
| H1 | 600 (Semi-Bold) |
| H2 | 600 (Semi-Bold) |
| Body text | 400 (Regular) |
| UI labels | 500 (Medium) |
| Code / mono | 400 (Regular) |

Avoid ultra-light weights (100, 200). Minimum weight is 400 for body text.

---

## Icon and Logo Usage

### Rules

- Clear space around icon = width of one pillar element
- Never rotate, stretch, or skew
- No glow, drop shadow, or pattern overlays
- Flat colors only (no gradients)
- Approved color variants: Atlas Navy, White, Black

### Favicon Sizes

| Size | Purpose |
|------|---------|
| 16x16 | Browser tab |
| 32x32 | Browser tab (HiDPI) |
| 48x48 | Taskbar / bookmarks |
| 180x180 | Apple Touch Icon |
| 512x512 | PWA / social sharing |

### Asset Locations

```
assets/brand/
  logo/         # Full wordmark (placeholder until designed)
  icon/         # Icon-only mark (placeholder until designed)
  favicon/      # Generated favicon set
```

To replace placeholders: drop final artwork into `assets/brand/icon/` and run the favicon generation script (see `assets/brand/README.md`).

---

## Visual Style Guidance

### Preferred

- Screenshots of terminal sessions and dashboard views
- Policy YAML snippets
- Audit trace examples
- CI workflow diagrams
- Structured dashboards with data tables

### Avoid

- Stock illustrations or abstract "AI brain" imagery
- Flashy futuristic gradients
- Neon color schemes
- Excessive rounded corners or shadows
- Marketing language that contradicts "open-source, local-first" positioning

---

## CSS Variable Reference

All dashboard styling uses CSS custom properties prefixed with `--ab-`. The canonical definitions live in `src/atlasbridge/dashboard/static/style.css`.

### Variable Names

| Variable | Purpose |
|----------|---------|
| `--ab-bg` | Page background |
| `--ab-panel` | Card/panel background |
| `--ab-panel-hover` | Hover state for panels |
| `--ab-border` | Border color |
| `--ab-text` | Primary text color |
| `--ab-text-muted` | Secondary/muted text |
| `--ab-primary` | Atlas Navy (brand identity) |
| `--ab-accent` | Governance Teal (links, highlights) |
| `--ab-success` | Success/running state |
| `--ab-warning` | Warning/awaiting state |
| `--ab-danger` | Error/failed state |
| `--ab-warning-alt` | Secondary warning (orange) |
| `--ab-banner-bg` | Read-only banner background |
| `--ab-font` | UI font stack |
| `--ab-mono` | Monospace font stack |

---

## Applying Brand to Components

### Dashboard

- Dark mode is the default (Deep Control Navy background)
- Light mode available via toggle
- Accent teal for interactive elements only (links, active tab, focus ring)
- Status badges use muted enterprise colors with low-opacity backgrounds
- Nav brand name in Atlas Navy (light) or Teal (dark)

### TUI / Console (Textual)

- Uses Textual's semantic token system (`$accent`, `$surface`, etc.)
- No custom theme overrides needed; Textual's default theme provides compatible colors
- `$accent` maps conceptually to Governance Teal

### CLI (Rich)

- Standard Rich markup colors: `[red]`, `[green]`, `[yellow]`
- No custom hex colors in CLI output; terminal color schemes vary
- Keep output professional and minimal
