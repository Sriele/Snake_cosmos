# Snake Cosmos

Snake Cosmos est un Snake moderne avec :

- une version `desktop` en `Python + pygame-ce`
- une version `web` statique dans [`docs/`](/home/Sriel/Vscode-Project/snake_codexgame/docs), pensée pour `GitHub Pages`

Le jeu propose un fond spatial animé, un snake fluide, de la nourriture à rareté variable, des items temporaires, une jauge de sprint, un menu pause, un codex d’items et des options de contrôle/audio.

## Version Web

URL de la version web GitHub Pages :

`https://sriele.github.io/Snake_cosmos/`

Si la page ne s’affiche pas encore, vérifie dans GitHub :

1. `Settings`
2. `Pages`
3. `Build and deployment`
4. `Source = Deploy from a branch`
5. `Branch = main`
6. `Folder = /docs`

## Prérequis Desktop

- `Python 3.11+`
- `pip`

La dépendance principale est :

- `pygame-ce`

## Installation Desktop

### Option 1 : avec `rtk`

`rtk` est un proxy CLI utilisé dans ce repo pour lancer les commandes shell. Si tu l’as déjà, tu peux utiliser :

```bash
rtk python3 -m venv .venv
rtk .venv/bin/pip install setuptools wheel
rtk .venv/bin/pip install -e .
```

### Option 2 : sans `rtk`

Si tu n’as pas `rtk`, ce n’est pas bloquant. Utilise simplement les commandes Python normales :

```bash
python3 -m venv .venv
.venv/bin/pip install setuptools wheel
.venv/bin/pip install -e .
```

## Lancer la Version Desktop

### Avec `rtk`

```bash
rtk .venv/bin/python -m snake_cosmos
```

### Sans `rtk`

```bash
.venv/bin/python -m snake_cosmos
```

## Lancer la Version Web en Local

La version web est entièrement statique. Le plus simple est de lancer un petit serveur local depuis la racine du projet :

```bash
python3 -m http.server 8000
```

Puis ouvre :

`http://localhost:8000/docs/`

## Contrôles

### En jeu

- Déplacement : `W`, `A`, `S`, `D`
- Sprint : `Space`
- Pause : `Escape` ou `P`

### Menus

- Naviguer : `Flèches` ou `W` / `S`
- Valider : `Enter` ou `Space`
- Retour : `Escape`

Les touches de déplacement et de sprint peuvent être changées dans le menu `Options`.

## Structure du Projet

- [`src/snake_cosmos/`](/home/Sriel/Vscode-Project/snake_codexgame/src/snake_cosmos) : version desktop Python
- [`docs/`](/home/Sriel/Vscode-Project/snake_codexgame/docs) : version web GitHub Pages
- [`tests/`](/home/Sriel/Vscode-Project/snake_codexgame/tests) : tests du cœur gameplay

## Vérification

Vérification Python :

```bash
python3 -m compileall src
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Si tu utilises `rtk` :

```bash
rtk python3 -m compileall src
PYTHONPATH=src rtk python3 -m unittest discover -s tests -v
```

## Notes

- Le repo contient à la fois la version desktop et la version web.
- La version web ne nécessite pas `pygame`.
- La version desktop sauvegarde les options et le meilleur score localement.
