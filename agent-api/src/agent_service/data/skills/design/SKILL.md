---
name: design
description: Create distinctive, production-grade frontend interfaces and visual artifacts (HTML/CSS/JS, PDF, PNG) with bold aesthetic direction and expert craftsmanship.
---

# Design Skill

Create visually striking, production-grade interfaces and visual artifacts that avoid generic AI aesthetics. Every output should look meticulously crafted by someone at the top of their field.

## Design Thinking Process

Before writing code, commit to a clear aesthetic direction:

1. **Purpose**: What problem does this solve? Who is the audience?
2. **Tone**: Pick a bold direction — brutally minimal, maximalist, retro-futuristic, organic, luxury, playful, editorial, brutalist, art deco, soft/pastel, industrial. Commit fully.
3. **Differentiation**: What makes this unforgettable? What's the one thing someone will remember?

## Frontend Interfaces (HTML/CSS/JS)

### Typography
- Choose distinctive, characterful fonts — never default to Inter, Roboto, Arial, or system fonts
- Pair a striking display font with a refined body font
- Use Google Fonts or CDN-hosted fonts for easy loading

```html
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700&family=DM+Serif+Display&display=swap" rel="stylesheet">
```

### Color & Theme
- Use CSS custom properties for a cohesive palette
- Dominant colors with sharp accents outperform timid, evenly-distributed palettes
- Commit to light OR dark — never generic gray

```css
:root {
  --bg: #0a0a0a;
  --surface: #141414;
  --text: #fafafa;
  --accent: #ff6b35;
  --muted: #666;
}
```

### Motion & Animation
- Use CSS transitions and keyframes for micro-interactions
- Staggered entrance reveals on page load (animation-delay)
- Meaningful hover states that surprise

```css
.card {
  opacity: 0;
  transform: translateY(20px);
  animation: fadeUp 0.6s ease forwards;
}
.card:nth-child(2) { animation-delay: 0.1s; }
.card:nth-child(3) { animation-delay: 0.2s; }

@keyframes fadeUp {
  to { opacity: 1; transform: translateY(0); }
}
```

### Spatial Composition
- Unexpected layouts: asymmetry, overlap, diagonal flow, grid-breaking elements
- Generous negative space OR controlled density — never middling
- CSS Grid and Flexbox for complex compositions

```css
.hero {
  display: grid;
  grid-template-columns: 1fr 1.5fr;
  gap: 0; /* deliberate overlap via negative margins */
  min-height: 100vh;
}
```

### Visual Details & Texture
- Create atmosphere with gradients, noise, grain overlays, geometric patterns
- Layered transparencies and dramatic shadows for depth
- Never settle for flat solid backgrounds

```css
.bg-texture {
  background:
    radial-gradient(ellipse at 20% 50%, rgba(255,107,53,0.15) 0%, transparent 50%),
    linear-gradient(180deg, #0a0a0a 0%, #111 100%);
}

/* Noise overlay */
.grain::after {
  content: '';
  position: fixed;
  inset: 0;
  background: url("data:image/svg+xml,...") repeat;
  opacity: 0.03;
  pointer-events: none;
}
```

### Production Pattern

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Project Name</title>
  <link href="https://fonts.googleapis.com/css2?family=YOUR+FONTS&display=swap" rel="stylesheet">
  <style>
    /* CSS custom properties, reset, layout, components, animations */
  </style>
</head>
<body>
  <!-- Semantic HTML with clear structure -->
  <script>
    // Interactivity: scroll triggers, dynamic effects, data binding
  </script>
</body>
</html>
```

## Visual Artifacts (PDF/PNG)

For posters, diagrams, reports, and visual compositions, use Python with reportlab or Pillow.

### reportlab (PDF)

```python
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor

c = canvas.Canvas("output.pdf", pagesize=A4)
w, h = A4

# Background
c.setFillColor(HexColor('#0a0a0a'))
c.rect(0, 0, w, h, fill=1)

# Geometric elements
c.setFillColor(HexColor('#ff6b35'))
c.circle(w*0.3, h*0.6, 80*mm, fill=1, stroke=0)

# Typography
c.setFillColor(HexColor('#fafafa'))
c.setFont("Helvetica-Bold", 48)
c.drawString(40*mm, h - 60*mm, "TITLE")

c.save()
```

### Pillow (PNG)

```python
from PIL import Image, ImageDraw, ImageFont

img = Image.new('RGB', (1920, 1080), '#0a0a0a')
draw = ImageDraw.Draw(img)

# Geometric composition
draw.ellipse([200, 100, 800, 700], fill='#ff6b35')
draw.rectangle([900, 200, 1700, 900], fill='#141414')

# Text (use a downloaded .ttf for distinctive typography)
font = ImageFont.truetype("font.ttf", 72)
draw.text((100, 900), "HEADING", font=font, fill='#fafafa')

img.save("output.png", quality=95)
```

## Anti-Patterns to Avoid

- Generic color schemes (purple gradients on white)
- Default fonts (Inter, Roboto, Arial, system-ui)
- Cookie-cutter card grids with uniform spacing
- Flat backgrounds with no texture or atmosphere
- Timid, evenly-distributed color palettes
- Decorative elements that serve no compositional purpose
- Identical spacing and sizing everywhere

## Principles

1. **Intentionality over intensity** — bold maximalism and refined minimalism both work; the key is commitment
2. **Every detail matters** — spacing, alignment, color relationships, font weights, shadow angles
3. **Context drives choices** — a punk venue poster and a luxury brand landing page demand different aesthetics
4. **No two designs the same** — vary themes, fonts, layouts, and color directions across projects
5. **Ship working code** — every output must be functional, not just a mockup
6. **Save to workspace** — always write output files (HTML, PDF, PNG) to the workspace directory
