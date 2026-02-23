# AtlasBridge Brand Assets

This directory contains brand assets for AtlasBridge.

## Directory Structure

```
assets/brand/
  logo/         Full wordmark (placeholder — replace with final artwork)
  icon/         Icon-only mark (placeholder — replace with final artwork)
  favicon/      Generated favicon set (derived from icon)
```

## Favicon Set

Generated programmatically from the icon source. Sizes:

| File | Size | Purpose |
|------|------|---------|
| `favicon-16x16.png` | 16x16 | Browser tab |
| `favicon-32x32.png` | 32x32 | Browser tab (HiDPI) |
| `favicon-48x48.png` | 48x48 | Taskbar / bookmarks |
| `favicon-64x64.png` | 64x64 | High-resolution contexts |
| `apple-touch-icon.png` | 180x180 | iOS home screen |
| `favicon-512x512.png` | 512x512 | PWA / social sharing |

## Replacing Placeholders

1. Place final icon-only artwork in `icon/` (transparent PNG, flat colors)
2. Regenerate favicons by resizing the icon source
3. Copy the favicon files to `src/atlasbridge/dashboard/static/favicon/`
4. Commit both the source assets and the dashboard copies

## Brand Spec

Full brand system documentation: [docs/branding.md](../../docs/branding.md)
