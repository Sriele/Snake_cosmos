# Snake Cosmos

Desktop-first modern Snake built in Python with a portable gameplay core for a later web port.

## Features

- Animated space background with layered stars and twinkle
- Premium board frame with external HUD
- Smooth interpolated snake motion on top of deterministic grid gameplay
- Food rarities, random items, sprint meter, pause menu, and options menu
- Portable content definitions stored as JSON

## Run

```bash
rtk python3 -m venv .venv
rtk .venv/bin/pip install -e .
rtk .venv/bin/python -m snake_cosmos
```

## Web Build

The browser adaptation lives in [`docs/`](/home/Sriel/Vscode-Project/snake_codexgame/docs) and is designed for `GitHub Pages`.

- Local preview: open `docs/index.html` in a simple static server
- GitHub Pages: publish from the repository `main` branch and the `/docs` folder

## Controls

- Move: `WASD` by default
- Sprint: `Space`
- Pause / Back: `Escape`
- Menus: arrows, `Enter`, `Escape`

All keybinds can be changed from the in-game options menu.
