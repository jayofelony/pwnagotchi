# VT323 Font - Local Installation

The CSS now uses locally-hosted VT323 font files instead of Google Fonts CDN.

## Download Instructions

Download the VT323 font from Google Fonts and place the files in this directory:

### Option 1: Download from Google Fonts (Recommended)

1. Go to: https://fonts.google.com/download/VT323
2. Extract the zip file
3. Copy the font files to this directory (`/static/fonts/`)

### Option 2: Direct Download Links

- **TTF Format** (fallback): https://github.com/google/fonts/raw/main/ofl/vt323/VT323-Regular.ttf
- **WOFF2 Format** (optimized): Download from Google Fonts archive

## Expected Files

The CSS expects these font files (in order of preference):

1. `VT323-Regular.ttf` - TrueType format (fallback)
2. `VT323-Regular.woff2` - Web Open Font Format 2 (optimized for web)
3. `VT323-Regular.woff` - Web Open Font Format (legacy support)

## File Sizes (Approximate)

- TTF: ~40 KB
- WOFF2: ~20 KB (recommended)
- WOFF: ~25 KB

## CSS Reference

The font is declared in `/static/css/style.css` with:

```css
@font-face {
  font-family: "VT323";
  src:
    url("/static/fonts/VT323-Regular.ttf") format("truetype"),
    url("/static/fonts/VT323-Regular.woff2") format("woff2"),
    url("/static/fonts/VT323-Regular.woff") format("woff");
  font-weight: normal;
  font-style: normal;
  font-display: swap;
}
```

## Fallback Behavior

If font files are not found, the CSS will fall back to system monospace fonts (Monaco, Courier New, etc.)

## Quick Setup for Linux/macOS

```bash
cd static/fonts
wget https://github.com/google/fonts/raw/main/ofl/vt323/VT323-Regular.ttf
```
