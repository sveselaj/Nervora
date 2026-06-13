# Diagrams

- `nervora-architecture.svg` / `.png` — the Nervora reference architecture.

Both are generated from `generate_diagram.py` (data-driven, no stock icons), so
the diagram is reproducible and version-controllable as source:

```bash
pip install cairosvg          # for PNG rendering (SVG is dependency-free)
python docs/diagrams/generate_diagram.py
```

On macOS, cairosvg needs the cairo native lib on its load path:

```bash
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib python docs/diagrams/generate_diagram.py
```

The PNG is rendered at 2× (3280×1960) for crisp display on GitHub and the web.
