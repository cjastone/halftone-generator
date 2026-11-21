# Halftone Pattern Generator: Interactive Fading Shape-Grid Designer

Create halftone patterns of hexagons, circles, stars and more that fade smoothly across the image.  Live preview-base design with high-resolution PNG export.

Built in Python with a simple desktop UI.  Only one dependency: [Pillow](https://github.com/python-pillow/Pillow).

### Example screenshot 🖼️
<a href="gallery/screenshot.png"><img src="gallery/screenshot.png" alt="Example screenshot" width="800"></a>

### Key functions and features ⚡
 -  **Live preview** that updates instantly as you adjust settings
 -  **Seven shapes:** hexagon, circle, square, diamond, triangle, octagon and star, on an offset or square grid
 -  **Four fade modes:**
	 -  **Curve:** shapes follow a freely editable curve that you drag directly on the preview
	 -  **Linear:** a straight fade at any angle
	 -  **Radial:** a fade outwards from any point
	 -  **None:** a uniform grid
 -  **Flame effect** that breaks up the faded edge with organic, flame-like dropout
 -  **On-image handles** to drag the curve, fade points, radial centre, angles and cell size
 -  **Randomise and Mutate** functions to explore new designs, either across everything or one section at a time
 -  **Lock any setting** to keep what you like while randomising the rest
 -  **Undo and redo** for every change made
 -  **Saved pattern library** with thumbnails, plus import and export for sharing
 -  **Export PNGs at any resolution**, with smooth anti-aliased edges and optional transparent backgrounds
 -  **Custom colours** with automatic contrasting palettes

### Requirements 🔧
- **Python 3.8+** with Tkinter (included with most Python installs).
- **Pillow:** `pip install pillow`

### Quick start 🚀
Clone the repository:

    git clone https://github.com/cjastone/halftone-generator.git
    cd halftone-generator

Run the app:

    python halftone_generator.py

Press **R** a few times to explore random designs.  Lock the settings you like, then keep randomising or fine-tune by hand.

### Keyboard shortcuts ⌨️
| Key | Action |
|---|---|
| `R` | Randomise all unlocked settings |
| `M` | Mutate (small random tweaks) |
| `H` | Show or hide preview handles |
| `Ctrl+S` | Save the current pattern |
| `Ctrl+Z` / `Ctrl+Y` | Undo / redo |

### Development notes
Saved patterns are stored in `./halftone_patterns.json`.
Panel layout (folded sections) is stored in `./halftone_ui.json`.

Built with Claude Opus 5.5.

### Image gallery
Examples of the patterns generated using this tool.  Click a thumbnail to view the full-size image.
<table>
  <tr>
    <td width="25%"><a href="gallery/halftone_circle_curve-custom2pt_c29_g12_s620_1800x1200.png"><img src="gallery/thumbnails/halftone_circle_curve-custom2pt_c29_g12_s620_thumb.png" alt="Circles, custom curve fade, gap 12" width="100%"></a></td>
    <td width="25%"><a href="gallery/halftone_circle_curve-custom3pt_flame69_c48_s350_1800x1200.png"><img src="gallery/thumbnails/halftone_circle_curve-custom3pt_flame69_c48_s350_thumb.png" alt="Circles, custom curve fade, flame 69" width="100%"></a></td>
    <td width="25%"><a href="gallery/halftone_circle_curve-custom4pt_flame70_c25_s83_1800x1200.png"><img src="gallery/thumbnails/halftone_circle_curve-custom4pt_flame70_c25_s83_thumb.png" alt="Circles, custom curve fade, flame 70" width="100%"></a></td>
    <td width="25%"><a href="gallery/halftone_circle_linear65deg_flame63_c30_s952_1800x1200.png"><img src="gallery/thumbnails/halftone_circle_linear65deg_flame63_c30_s952_thumb.png" alt="Circles, linear fade 65°, flame 63" width="100%"></a></td>
  </tr>
  <tr>
    <td width="25%"><a href="gallery/halftone_circle_radial29-68_flame55_c46_s936_1800x1200.png"><img src="gallery/thumbnails/halftone_circle_radial29-68_flame55_c46_s936_thumb.png" alt="Circles, radial fade, flame 55" width="100%"></a></td>
    <td width="25%"><a href="gallery/halftone_hexagon_curve-custom3pt_c25_g13_s978_1800x1200.png"><img src="gallery/thumbnails/halftone_hexagon_curve-custom3pt_c25_g13_s978_thumb.png" alt="Hexagons, custom curve fade, gap 13" width="100%"></a></td>
    <td width="25%"><a href="gallery/halftone_hexagon_linear156deg_inv_flame77_c21_s900_1800x1200.png"><img src="gallery/thumbnails/halftone_hexagon_linear156deg_inv_flame77_c21_s900_thumb.png" alt="Hexagons, inverted linear fade 156°, flame 77" width="100%"></a></td>
    <td width="25%"><a href="gallery/halftone_hexagon_linear243deg_flame12_c21_s922_1800x1200.png"><img src="gallery/thumbnails/halftone_hexagon_linear243deg_flame12_c21_s922_thumb.png" alt="Hexagons, linear fade 243°, flame 12" width="100%"></a></td>
  </tr>
  <tr>
    <td width="25%"><a href="gallery/halftone_hexagon_radial55-99_flame66_c33_s385_1800x1200.png"><img src="gallery/thumbnails/halftone_hexagon_radial55-99_flame66_c33_s385_thumb.png" alt="Hexagons, radial fade, flame 66" width="100%"></a></td>
    <td width="25%"><a href="gallery/halftone_hexagon_radial76-66_c65_s408_1800x1200.png"><img src="gallery/thumbnails/halftone_hexagon_radial76-66_c65_s408_thumb.png" alt="Large hexagons, radial fade" width="100%"></a></td>
    <td width="25%"><a href="gallery/halftone_hexagon_radial86-79_inv_flame19_c22_g1_s962_1800x1200.png"><img src="gallery/thumbnails/halftone_hexagon_radial86-79_inv_flame19_c22_g1_s962_thumb.png" alt="Hexagons, inverted radial fade, flame 19" width="100%"></a></td>
    <td width="25%"><a href="gallery/halftone_square_curve-custom4pt_c17_s701_1800x1200.png"><img src="gallery/thumbnails/halftone_square_curve-custom4pt_c17_s701_thumb.png" alt="Squares, custom curve fade" width="100%"></a></td>
  </tr>
  <tr>
    <td width="25%"><a href="gallery/halftone_star_curve-custom4pt_flame72_c16_s310_1800x1200.png"><img src="gallery/thumbnails/halftone_star_curve-custom4pt_flame72_c16_s310_thumb.png" alt="Stars, custom curve fade, flame 72" width="100%"></a></td>
    <td width="25%"><a href="gallery/halftone_star_sqgrid_linear132deg_inv_flame61_c17_s990_1800x1200.png"><img src="gallery/thumbnails/halftone_star_sqgrid_linear132deg_inv_flame61_c17_s990_thumb.png" alt="Stars on square grid, inverted linear fade, flame 61" width="100%"></a></td>
    <td width="25%"><a href="gallery/halftone_triangle_curve-custom5pt_c39_s542_1800x1200.png"><img src="gallery/thumbnails/halftone_triangle_curve-custom5pt_c39_s542_thumb.png" alt="Triangles, custom curve fade" width="100%"></a></td>
    <td width="25%"><a href="gallery/halftone_triangle_radial60-24_c60_g7_s659_1800x1200.png"><img src="gallery/thumbnails/halftone_triangle_radial60-24_c60_g7_s659_thumb.png" alt="Triangles, radial fade, gap 7" width="100%"></a></td>
  </tr>
</table>