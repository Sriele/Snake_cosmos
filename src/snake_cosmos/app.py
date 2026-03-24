from __future__ import annotations

from dataclasses import replace
from enum import Enum, auto
import io
import math
import random
import struct
import wave

import pygame

from snake_cosmos.catalog import ItemDefinition, load_food_definitions, load_item_definitions
from snake_cosmos.core import GameEvents, GridPos, Settings, SnakeGame
from snake_cosmos.persistence import load_save, save_state


WINDOW_SIZE = (1280, 760)
BOARD_SIZE = (21, 21)
CELL_SIZE = 24
BOARD_PIXEL_SIZE = BOARD_SIZE[0] * CELL_SIZE
FPS = 60


class Scene(Enum):
    TITLE = auto()
    OPTIONS = auto()
    PLAYING = auto()
    PAUSED = auto()
    ITEMS = auto()
    GAME_OVER = auto()


class MenuAction(Enum):
    START = auto()
    CODEX = auto()
    OPTIONS = auto()
    QUIT = auto()
    RESUME = auto()
    RESTART = auto()
    ITEMS = auto()
    MAIN_MENU = auto()


class Particle:
    def __init__(self, x: float, y: float, color: tuple[int, int, int], radius: float, lifetime: float) -> None:
        self.x = x
        self.y = y
        self.vx = random.uniform(-34.0, 34.0)
        self.vy = random.uniform(-84.0, 26.0)
        self.color = color
        self.radius = radius
        self.lifetime = lifetime
        self.max_lifetime = lifetime

    def update(self, dt: float) -> None:
        self.lifetime -= dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += 90.0 * dt


class FloatingPickupText:
    def __init__(
        self,
        x: float,
        y: float,
        icon_id: str,
        text: str,
        color: tuple[int, int, int],
        lifetime: float = 0.95,
        x_drift: float = 0.0,
    ) -> None:
        self.x = x
        self.y = y
        self.icon_id = icon_id
        self.text = text
        self.color = color
        self.lifetime = lifetime
        self.max_lifetime = lifetime
        self.x_drift = x_drift

    def update(self, dt: float) -> None:
        self.lifetime -= dt
        self.y -= 36.0 * dt
        self.x += self.x_drift * dt


class Star:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.reset(initial=True)

    def reset(self, initial: bool = False) -> None:
        self.x = random.uniform(0, self.width)
        self.y = random.uniform(0, self.height)
        self.speed = random.uniform(10.0, 42.0)
        self.size = random.uniform(1.0, 3.3)
        self.phase = random.uniform(0.0, math.tau)
        if not initial:
            self.x = self.width + random.uniform(0, 80)
            self.y = random.uniform(0, self.height)

    def update(self, dt: float) -> None:
        self.x -= self.speed * dt
        self.phase += dt * 1.15
        if self.x < -12:
            self.reset()


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def ease_snake(t: float) -> float:
    return t * t * (3.0 - 2.0 * t)


def make_font(preferred: list[str], size: int, bold: bool = False) -> pygame.font.Font:
    path = None
    for name in preferred:
        path = pygame.font.match_font(name, bold=bold)
        if path:
            break
    return pygame.font.Font(path, size)


def _make_wave_bytes(samples: list[int], sample_rate: int = 22050) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))
    return buffer.getvalue()


def make_tone(frequency: float, duration: float, amplitude: float = 0.35, overtone: float = 0.15) -> bytes:
    sample_rate = 22050
    total = max(1, int(sample_rate * duration))
    samples: list[int] = []
    for index in range(total):
        t = index / sample_rate
        attack = min(1.0, index / max(1, int(sample_rate * 0.03)))
        release = min(1.0, (total - index) / max(1, int(sample_rate * 0.06)))
        envelope = min(attack, release)
        value = math.sin(math.tau * frequency * t)
        value += overtone * math.sin(math.tau * frequency * 2.0 * t)
        samples.append(int(32767 * amplitude * envelope * value))
    return _make_wave_bytes(samples, sample_rate)


def make_sequence(notes: list[tuple[float, float]], amplitude: float = 0.2) -> bytes:
    sample_rate = 22050
    samples: list[int] = []
    for frequency, duration in notes:
        count = int(sample_rate * duration)
        for index in range(count):
            t = index / sample_rate
            attack = min(1.0, index / max(1, int(sample_rate * 0.04)))
            release = min(1.0, (count - index) / max(1, int(sample_rate * 0.08)))
            envelope = min(attack, release)
            value = 0.72 * math.sin(math.tau * frequency * t)
            value += 0.18 * math.sin(math.tau * frequency * 0.5 * t)
            samples.append(int(32767 * amplitude * envelope * value))
    return _make_wave_bytes(samples, sample_rate)


class AudioBank:
    def __init__(self) -> None:
        self.enabled = pygame.mixer.get_init() is not None
        self.sounds: dict[str, pygame.mixer.Sound] = {}
        self.music: pygame.mixer.Sound | None = None
        self.music_channel: pygame.mixer.Channel | None = None
        if not self.enabled:
            return
        self.sounds = {
            "menu_move": pygame.mixer.Sound(file=io.BytesIO(make_tone(360, 0.08, 0.14))),
            "menu_select": pygame.mixer.Sound(file=io.BytesIO(make_tone(520, 0.12, 0.18))),
            "food": pygame.mixer.Sound(file=io.BytesIO(make_sequence([(420, 0.035), (300, 0.06), (240, 0.08)], amplitude=0.24))),
            "item": pygame.mixer.Sound(file=io.BytesIO(make_sequence([(160, 0.04), (120, 0.05), (260, 0.12), (420, 0.18)], amplitude=0.28))),
            "rare": pygame.mixer.Sound(file=io.BytesIO(make_sequence([(660, 0.06), (840, 0.08), (1040, 0.12)], amplitude=0.18))),
            "game_over": pygame.mixer.Sound(file=io.BytesIO(make_sequence([(240, 0.16), (190, 0.22), (150, 0.34)], amplitude=0.22))),
        }
        self.music = pygame.mixer.Sound(
            file=io.BytesIO(
                make_sequence([(130.81, 1.6), (146.83, 1.6), (164.81, 1.6), (146.83, 1.6)], amplitude=0.06)
            )
        )

    def set_levels(self, settings: Settings) -> None:
        if not self.enabled:
            return
        sfx_level = settings.master_volume * settings.sfx_volume
        for sound in self.sounds.values():
            sound.set_volume(sfx_level)
        if self.music:
            self.music.set_volume(settings.master_volume * settings.music_volume)

    def ensure_music(self) -> None:
        if not self.enabled or self.music is None:
            return
        if self.music_channel is None or not self.music_channel.get_busy():
            self.music_channel = self.music.play(loops=-1)

    def play(self, name: str) -> None:
        if not self.enabled:
            return
        sound = self.sounds.get(name)
        if sound:
            sound.play()


class SnakeCosmosApp:
    def __init__(self) -> None:
        pygame.init()
        try:
            pygame.mixer.init()
        except pygame.error:
            pass
        self.foods = load_food_definitions()
        self.items = load_item_definitions()
        self.best_score, self.settings = load_save()
        self.game = SnakeGame(self.foods, self.items, width=BOARD_SIZE[0], height=BOARD_SIZE[1])
        self.game.best_score = self.best_score
        self.screen = self._create_screen()
        pygame.display.set_caption("Snake Cosmos")
        self.clock = pygame.time.Clock()
        self.scene = Scene.TITLE
        self.return_scene = Scene.TITLE
        self.running = True
        self.menu_index = 0
        self.options_index = 0
        self.last_menu_index = 0
        self.rebinding_action: str | None = None
        self.stars = [Star(*WINDOW_SIZE) for _ in range(120)]
        self.particles: list[Particle] = []
        self.floating_pickups: list[FloatingPickupText] = []
        self.title_phase = 0.0
        self.font_small = make_font(["Avenir Next", "Segoe UI", "Trebuchet MS", "DejaVu Sans"], 16)
        self.font_ui = make_font(["Avenir Next", "Segoe UI", "Trebuchet MS", "DejaVu Sans"], 24, bold=True)
        self.font_large = make_font(["Avenir Next", "Segoe UI", "Trebuchet MS", "DejaVu Sans"], 42, bold=True)
        self.font_title = make_font(["Avenir Next", "Segoe UI", "Trebuchet MS", "DejaVu Sans"], 58, bold=True)
        self.font_hud = make_font(["Avenir Next", "Segoe UI", "Trebuchet MS", "DejaVu Sans"], 26, bold=True)
        self.font_logo = make_font(["Georgia", "DejaVu Serif", "Times New Roman"], 28, bold=True)
        self.input_down: dict[int, bool] = {}
        self.board_specks = [
            (random.randint(0, BOARD_PIXEL_SIZE - 1), random.randint(0, BOARD_PIXEL_SIZE - 1), random.randint(1, 2))
            for _ in range(38)
        ]
        self.board_rect = pygame.Rect(
            (WINDOW_SIZE[0] - BOARD_PIXEL_SIZE) // 2,
            (WINDOW_SIZE[1] - BOARD_PIXEL_SIZE) // 2 - 6,
            BOARD_PIXEL_SIZE,
            BOARD_PIXEL_SIZE,
        )
        self.audio = AudioBank()
        self.audio.set_levels(self.settings)
        self.audio.ensure_music()
        self.await_first_move = False

    def _create_screen(self) -> pygame.Surface:
        flags = pygame.SCALED
        if self.settings.fullscreen:
            flags |= pygame.FULLSCREEN
        return pygame.display.set_mode(WINDOW_SIZE, flags)

    def run(self) -> None:
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            self.title_phase += dt
            self._handle_events()
            self._update(dt)
            self._render()
        self._persist()
        pygame.quit()

    def _persist(self) -> None:
        self.best_score = max(self.best_score, self.game.best_score, self.game.score)
        self.game.best_score = self.best_score
        save_state(self.best_score, self.settings)

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                return
            if event.type == pygame.KEYDOWN:
                self.input_down[event.key] = True
                self._on_keydown(event.key)
            if event.type == pygame.KEYUP:
                self.input_down[event.key] = False

    def _key_for_action(self, action: str) -> int:
        return pygame.key.key_code(self.settings.keybinds[action])

    def _on_keydown(self, key: int) -> None:
        if self.rebinding_action is not None:
            if key == pygame.K_ESCAPE:
                self.rebinding_action = None
                return
            updated = dict(self.settings.keybinds)
            updated[self.rebinding_action] = pygame.key.name(key)
            self.settings = replace(self.settings, keybinds=updated)
            self.rebinding_action = None
            self.audio.play("menu_select")
            self._persist()
            return

        if self.scene == Scene.PLAYING:
            self._handle_playing_keydown(key)
        elif self.scene in {Scene.TITLE, Scene.PAUSED, Scene.GAME_OVER}:
            self._handle_menu_keydown(key)
        elif self.scene == Scene.OPTIONS:
            self._handle_options_keydown(key)
        elif self.scene == Scene.ITEMS:
            self._handle_items_keydown(key)

    def _handle_playing_keydown(self, key: int) -> None:
        mapping = {
            self._key_for_action("up"): (0, -1),
            self._key_for_action("down"): (0, 1),
            self._key_for_action("left"): (-1, 0),
            self._key_for_action("right"): (1, 0),
        }
        if key in mapping:
            self.await_first_move = False
            self.game.enqueue_direction(mapping[key])
            return
        if key in (self._key_for_action("pause"), pygame.K_p):
            self.audio.play("menu_select")
            self.scene = Scene.PAUSED
            self.menu_index = 0

    def _handle_menu_keydown(self, key: int) -> None:
        items = self._current_menu_items()
        if key in (pygame.K_UP, pygame.K_w):
            self.menu_index = (self.menu_index - 1) % len(items)
            self.audio.play("menu_move")
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.menu_index = (self.menu_index + 1) % len(items)
            self.audio.play("menu_move")
        elif key in (pygame.K_RETURN, pygame.K_SPACE):
            self.audio.play("menu_select")
            self._activate_menu_action(items[self.menu_index][1])
        elif key == pygame.K_ESCAPE:
            if self.scene == Scene.PAUSED:
                self.audio.play("menu_select")
                self.scene = Scene.PLAYING
            elif self.scene == Scene.GAME_OVER:
                self.audio.play("menu_select")
                self.scene = Scene.TITLE
                self.menu_index = 0
        elif key == pygame.K_p and self.scene == Scene.PAUSED:
            self.audio.play("menu_select")
            self.scene = Scene.PLAYING

    def _handle_items_keydown(self, key: int) -> None:
        if key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
            self.audio.play("menu_select")
            self.scene = self.return_scene
            self.menu_index = 0

    def _handle_options_keydown(self, key: int) -> None:
        items = self._options_items()
        if key in (pygame.K_UP, pygame.K_w):
            self.options_index = (self.options_index - 1) % len(items)
            self.audio.play("menu_move")
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.options_index = (self.options_index + 1) % len(items)
            self.audio.play("menu_move")
        elif key in (pygame.K_LEFT, pygame.K_a):
            self._adjust_option(items[self.options_index][0], -1)
        elif key in (pygame.K_RIGHT, pygame.K_d):
            self._adjust_option(items[self.options_index][0], 1)
        elif key in (pygame.K_RETURN, pygame.K_SPACE):
            self.audio.play("menu_select")
            self._activate_option(items[self.options_index][0])
        elif key == pygame.K_ESCAPE:
            self.scene = self.return_scene
            self.rebinding_action = None
            self.audio.play("menu_select")
            self._persist()

    def _adjust_option(self, option_id: str, direction: int) -> None:
        delta = 0.05 * direction
        if option_id == "master_volume":
            self.settings = replace(self.settings, master_volume=clamp(self.settings.master_volume + delta, 0.0, 1.0))
        elif option_id == "music_volume":
            self.settings = replace(self.settings, music_volume=clamp(self.settings.music_volume + delta, 0.0, 1.0))
        elif option_id == "sfx_volume":
            self.settings = replace(self.settings, sfx_volume=clamp(self.settings.sfx_volume + delta, 0.0, 1.0))
        elif option_id == "fullscreen":
            self.settings = replace(self.settings, fullscreen=not self.settings.fullscreen)
            self.screen = self._create_screen()
        elif option_id == "screen_shake":
            self.settings = replace(self.settings, screen_shake=clamp(self.settings.screen_shake + delta, 0.0, 1.0))
        self.audio.set_levels(self.settings)
        self.audio.play("menu_move")
        self._persist()

    def _activate_option(self, option_id: str) -> None:
        if option_id == "back":
            self.scene = self.return_scene
            self._persist()
        elif option_id in self.settings.keybinds:
            self.rebinding_action = option_id
        elif option_id in {"master_volume", "music_volume", "sfx_volume", "fullscreen", "screen_shake"}:
            self._adjust_option(option_id, 1)

    def _current_menu_items(self) -> list[tuple[str, MenuAction]]:
        if self.scene == Scene.TITLE:
            return [
                ("Start Mission", MenuAction.START),
                ("Items Codex", MenuAction.CODEX),
                ("Options", MenuAction.OPTIONS),
                ("Quit", MenuAction.QUIT),
            ]
        if self.scene == Scene.PAUSED:
            return [
                ("Resume", MenuAction.RESUME),
                ("Items Codex", MenuAction.ITEMS),
                ("Options", MenuAction.OPTIONS),
                ("Restart", MenuAction.RESTART),
                ("Main Menu", MenuAction.MAIN_MENU),
            ]
        return [
            ("Retry", MenuAction.RESTART),
            ("Main Menu", MenuAction.MAIN_MENU),
            ("Quit", MenuAction.QUIT),
        ]

    def _options_items(self) -> list[tuple[str, str]]:
        keys = self.settings.keybinds
        return [
            ("master_volume", f"Master Volume     {self.settings.master_volume * 100:>3.0f}%"),
            ("music_volume", f"Music Volume      {self.settings.music_volume * 100:>3.0f}%"),
            ("sfx_volume", f"SFX Volume        {self.settings.sfx_volume * 100:>3.0f}%"),
            ("fullscreen", f"Fullscreen        {'On' if self.settings.fullscreen else 'Off'}"),
            ("screen_shake", f"FX Intensity      {self.settings.screen_shake * 100:>3.0f}%"),
            ("up", f"Move Up           {keys['up'].upper()}"),
            ("down", f"Move Down         {keys['down'].upper()}"),
            ("left", f"Move Left         {keys['left'].upper()}"),
            ("right", f"Move Right        {keys['right'].upper()}"),
            ("sprint", f"Sprint            {keys['sprint'].upper()}"),
            ("back", "Back"),
        ]

    def _activate_menu_action(self, action: MenuAction) -> None:
        if action == MenuAction.START:
            self._start_game()
        elif action == MenuAction.CODEX:
            self.return_scene = Scene.TITLE
            self.scene = Scene.ITEMS
        elif action == MenuAction.OPTIONS:
            self.return_scene = Scene.TITLE if self.scene == Scene.TITLE else Scene.PAUSED
            self.scene = Scene.OPTIONS
            self.options_index = 0
        elif action == MenuAction.QUIT:
            self.running = False
        elif action == MenuAction.RESUME:
            self.scene = Scene.PLAYING
        elif action == MenuAction.RESTART:
            self._start_game()
        elif action == MenuAction.ITEMS:
            self.return_scene = Scene.PAUSED
            self.scene = Scene.ITEMS
        elif action == MenuAction.MAIN_MENU:
            self.scene = Scene.TITLE
            self.menu_index = 0

    def _start_game(self) -> None:
        self.game.reset()
        self.game.best_score = self.best_score
        self.scene = Scene.PLAYING
        self.menu_index = 0
        self.await_first_move = True
        self.audio.play("menu_select")

    def _update(self, dt: float) -> None:
        for star in self.stars:
            star.update(dt)
        for particle in self.particles:
            particle.update(dt)
        for floating in self.floating_pickups:
            floating.update(dt)
        self.particles = [particle for particle in self.particles if particle.lifetime > 0]
        self.floating_pickups = [floating for floating in self.floating_pickups if floating.lifetime > 0]

        if self.scene == Scene.PLAYING:
            if self.await_first_move:
                return
            sprint_pressed = bool(self.input_down.get(self._key_for_action("sprint")))
            events = self.game.update(dt, sprint_pressed=sprint_pressed)
            self.best_score = max(self.best_score, self.game.best_score, self.game.score)
            self.game.best_score = self.best_score
            self._spawn_particles(events)
            if events.food_pickups:
                self.audio.play("food")
            if events.item_pickups:
                self.audio.play("item")
                self.audio.play("rare")
            if events.game_over:
                self.audio.play("game_over")
                self.scene = Scene.GAME_OVER
                self.menu_index = 0

    def _spawn_particles(self, events: GameEvents) -> None:
        for event in events.food_pickups:
            x, y = self._pixel_center(self.game.snake[0])
            for _ in range(14):
                self.particles.append(Particle(x, y, event.color, random.uniform(2.0, 4.0), random.uniform(0.45, 0.85)))
            self.floating_pickups.append(FloatingPickupText(x - 18, y - 8, "diamond", f"+{event.score_gain}", (255, 214, 92), x_drift=-4.0))
            self.floating_pickups.append(FloatingPickupText(x + 18, y + 6, "spark", f"+{int(event.sprint_gain)}", (98, 220, 255), x_drift=4.0))
            if event.rarity == "epic":
                self.audio.play("rare")
                for angle in range(0, 360, 30):
                    rad = math.radians(angle)
                    particle = Particle(x + math.cos(rad) * 10, y + math.sin(rad) * 10, event.color, 4.0, 0.7)
                    particle.vx = math.cos(rad) * 90.0
                    particle.vy = math.sin(rad) * 90.0
                    self.particles.append(particle)
        for event in events.item_pickups:
            x, y = self._pixel_center(self.game.snake[0])
            for _ in range(28):
                self.particles.append(Particle(x, y, event.color, random.uniform(2.5, 5.0), random.uniform(0.65, 1.1)))
            self.floating_pickups.append(FloatingPickupText(x, y - 6, "halo", event.label, event.color, lifetime=1.05))
            for angle in range(0, 360, 24):
                rad = math.radians(angle)
                particle = Particle(x + math.cos(rad) * 14, y + math.sin(rad) * 14, event.color, 4.5, 0.8)
                particle.vx = math.cos(rad) * 120.0
                particle.vy = math.sin(rad) * 120.0
                self.particles.append(particle)

    def _pixel_center(self, cell: GridPos) -> tuple[float, float]:
        return (
            self.board_rect.x + cell[0] * CELL_SIZE + CELL_SIZE / 2,
            self.board_rect.y + cell[1] * CELL_SIZE + CELL_SIZE / 2,
        )

    def _render(self) -> None:
        self.screen.fill((6, 10, 24))
        self._draw_background()
        self._draw_board_shell()
        self._draw_board()
        if self.scene == Scene.PLAYING and self.await_first_move:
            self._draw_start_prompt()
        self._draw_top_hud()
        self._draw_bottom_hud()
        self._draw_particles()
        if self.scene == Scene.TITLE:
            self._draw_overlay()
            self._draw_menu_panel("Snake Cosmos", self._current_menu_items(), "Press Enter to begin")
        elif self.scene == Scene.PAUSED:
            self._draw_overlay()
            self._draw_menu_panel("Paused", self._current_menu_items(), "Esc resumes")
        elif self.scene == Scene.GAME_OVER:
            self._draw_overlay()
            self._draw_menu_panel("Signal Lost", self._current_menu_items(), f"Score {self.game.score}  |  Best {self.best_score}")
        elif self.scene == Scene.OPTIONS:
            self._draw_overlay()
            self._draw_options_panel()
        elif self.scene == Scene.ITEMS:
            self._draw_overlay()
            self._draw_items_codex()
        pygame.display.flip()

    def _draw_background(self) -> None:
        for y in range(WINDOW_SIZE[1]):
            t = y / WINDOW_SIZE[1]
            color = (int(7 + 14 * t), int(9 + 18 * t), int(22 + 42 * t))
            pygame.draw.line(self.screen, color, (0, y), (WINDOW_SIZE[0], y))
        nebula = pygame.Surface(WINDOW_SIZE, pygame.SRCALPHA)
        for cx, cy, radius, color in [
            (180, 150, 220, (50, 98, 190, 44)),
            (1020, 240, 260, (40, 170, 190, 34)),
            (840, 620, 280, (120, 60, 160, 24)),
            (360, 580, 180, (160, 88, 120, 22)),
        ]:
            pygame.draw.circle(nebula, color, (cx, cy), radius)
        self.screen.blit(nebula, (0, 0))
        for star in self.stars:
            alpha = 140 + int(110 * (0.5 + 0.5 * math.sin(star.phase)))
            pygame.draw.circle(self.screen, (220, 232, 255), (int(star.x), int(star.y)), int(star.size))
            if alpha > 220:
                pygame.draw.circle(self.screen, (255, 255, 255), (int(star.x), int(star.y)), max(1, int(star.size - 1)))

    def _draw_board_shell(self) -> None:
        outer = self.board_rect.inflate(34, 34)
        pygame.draw.rect(self.screen, (14, 18, 36), outer, border_radius=30)
        pygame.draw.rect(self.screen, (68, 96, 140), outer, width=2, border_radius=30)
        shine = pygame.Surface(outer.size, pygame.SRCALPHA)
        pygame.draw.rect(shine, (255, 255, 255, 16), shine.get_rect(), border_radius=30)
        pygame.draw.rect(shine, (170, 210, 255, 20), (0, 0, outer.width, outer.height // 3), border_radius=30)
        self.screen.blit(shine, outer.topleft)

    def _draw_board(self) -> None:
        board = pygame.Surface(self.board_rect.size, pygame.SRCALPHA)
        board.fill((7, 12, 24, 235))
        vignette = pygame.Surface(self.board_rect.size, pygame.SRCALPHA)
        center = (self.board_rect.width // 2, self.board_rect.height // 2)
        pygame.draw.circle(vignette, (22, 34, 62, 82), center, 240)
        pygame.draw.circle(vignette, (15, 52, 74, 26), (center[0] - 110, center[1] + 70), 140)
        pygame.draw.circle(vignette, (74, 40, 90, 20), (center[0] + 130, center[1] - 110), 120)
        board.blit(vignette, (0, 0))
        for offset, alpha in [(46, 30), (118, 20), (186, 14)]:
            pygame.draw.arc(board, (80, 130, 160, alpha), (offset, offset, self.board_rect.width - 2 * offset, self.board_rect.height - 2 * offset), 0.8, 2.2, 2)
        for x, y, size in self.board_specks:
            board.fill((180, 200, 255, 18), (x, y, size, size))
        self.screen.blit(board, self.board_rect.topleft)
        self._draw_food()
        self._draw_item()
        self._draw_snake()

    def _interpolated_segments(self) -> list[tuple[float, float]]:
        progress = ease_snake(self.game.last_progress)
        previous = self.game.previous_snake
        current = self.game.snake
        count = max(len(previous), len(current))
        segments: list[tuple[float, float]] = []
        for index in range(count):
            prev = previous[index] if index < len(previous) else previous[-1]
            curr = current[index] if index < len(current) else current[-1]
            segments.append((lerp(prev[0], curr[0], progress), lerp(prev[1], curr[1], progress)))
        return segments

    def _snake_points(self) -> list[tuple[float, float]]:
        return [
            (
                self.board_rect.x + x * CELL_SIZE + CELL_SIZE / 2,
                self.board_rect.y + y * CELL_SIZE + CELL_SIZE / 2,
            )
            for x, y in self._interpolated_segments()
        ]

    def _draw_snake(self) -> None:
        points = self._snake_points()
        if len(points) < 2:
            return
        glow_strength = clamp(max(self.game.food_glow_timer * 1.2, self.game.item_glow_timer * 1.7), 0.0, 1.0)
        glow_color = self.game.pickup_flash_color
        for index in range(len(points) - 1, 0, -1):
            t = index / max(1, len(points) - 1)
            width = max(6, int(16 - t * 6))
            shadow_color = (20, 26, 30)
            pygame.draw.line(self.screen, shadow_color, points[index], points[index - 1], width + 4)
            if glow_strength > 0:
                glow = pygame.Surface((64, 64), pygame.SRCALPHA)
                alpha = int(48 + 120 * glow_strength * (1.0 - t * 0.55))
                pygame.draw.circle(glow, (*glow_color, alpha), (32, 32), width + 7)
                self.screen.blit(glow, (points[index][0] - 32, points[index][1] - 32))
            base = (
                int(78 - t * 18),
                int(104 - t * 20),
                int(82 - t * 14),
            )
            pygame.draw.line(self.screen, base, points[index], points[index - 1], width)
            pygame.draw.circle(self.screen, base, (int(points[index][0]), int(points[index][1])), width // 2)
            ridge = (
                int(base[0] + 18 + 40 * glow_strength),
                int(base[1] + 26 + 90 * glow_strength),
                int(base[2] + 12 + 80 * glow_strength),
            )
            pygame.draw.line(self.screen, ridge, points[index], points[index - 1], max(2, width // 3))

        head_x, head_y = points[0]
        neck_x, neck_y = points[1]
        dx = head_x - neck_x
        dy = head_y - neck_y
        length = max(1.0, math.hypot(dx, dy))
        ux = dx / length
        uy = dy / length
        head_color = (
            int(94 + 96 * glow_strength),
            int(120 + 104 * glow_strength),
            int(92 + 120 * glow_strength),
        )
        if glow_strength > 0:
            glow = pygame.Surface((92, 92), pygame.SRCALPHA)
            pygame.draw.circle(glow, (*glow_color, int(84 + 120 * glow_strength)), (46, 46), 22)
            self.screen.blit(glow, (head_x - 46, head_y - 46))
        head_surface = pygame.Surface((34, 24), pygame.SRCALPHA)
        outline_color = (60, 82, 64)
        pygame.draw.ellipse(head_surface, head_color, (4, 5, 24, 14))
        pygame.draw.ellipse(head_surface, outline_color, (4, 5, 24, 14), 1)
        pygame.draw.ellipse(head_surface, (24, 34, 30), (21, 9, 3, 3))
        pygame.draw.ellipse(head_surface, (24, 34, 30), (21, 13, 3, 3))
        angle = -math.degrees(math.atan2(uy, ux))
        rotated_head = pygame.transform.rotate(head_surface, angle)
        head_rect = rotated_head.get_rect(center=(head_x + ux * 3, head_y + uy * 3))
        self.screen.blit(rotated_head, head_rect)

    def _draw_food(self) -> None:
        if not self.game.food:
            return
        cell, definition = self.game.food
        x, y = self._pixel_center(cell)
        glow = pygame.Surface((44, 44), pygame.SRCALPHA)
        pygame.draw.circle(glow, (*definition.glow_color, 72), (22, 22), 18)
        self.screen.blit(glow, (x - 22, y - 22))
        pygame.draw.circle(self.screen, definition.color, (int(x), int(y)), 7)
        pygame.draw.circle(self.screen, (255, 255, 255), (int(x - 2), int(y - 2)), 2)

    def _draw_item(self) -> None:
        if not self.game.item:
            return
        cell, definition = self.game.item
        x, y = self._pixel_center(cell)
        radius = 10 + 1.6 * math.sin(self.title_phase * 4.0)
        glow = pygame.Surface((52, 52), pygame.SRCALPHA)
        pygame.draw.circle(glow, (*definition.glow_color, 68), (26, 26), 20)
        self.screen.blit(glow, (x - 26, y - 26))
        self._draw_icon(definition.icon_id, (x, y), definition.color, int(radius))

    def _draw_top_hud(self) -> None:
        left_anchor = (self.board_rect.left, self.board_rect.top - 76)
        right_anchor = (self.board_rect.right, self.board_rect.top - 76)
        score_label = self.font_small.render("SCORE", True, (133, 158, 196))
        score_value = self.font_hud.render(str(self.game.score), True, (244, 247, 255))
        self._draw_icon("diamond", (left_anchor[0] - 16, left_anchor[1] + 28), (255, 214, 92), 8)
        self.screen.blit(score_label, left_anchor)
        self.screen.blit(score_value, (left_anchor[0], left_anchor[1] + 18))
        record_label = self.font_small.render("RECORD", True, (133, 158, 196))
        record_value = self.font_hud.render(str(self.best_score), True, (244, 247, 255))
        self.screen.blit(record_label, (right_anchor[0] - record_label.get_width(), right_anchor[1]))
        self.screen.blit(record_value, (right_anchor[0] - record_value.get_width(), right_anchor[1] + 18))
        title = self.font_logo.render("Snake Cosmos", True, (104, 220, 255))
        glow = self.font_logo.render("Snake Cosmos", True, (192, 246, 255))
        title_x = self.board_rect.centerx - title.get_width() // 2
        title_y = self.board_rect.top - 76
        self.screen.blit(glow, (title_x, title_y - 1))
        self.screen.blit(title, (title_x, title_y))

    def _draw_bottom_hud(self) -> None:
        self._draw_sprint_bar()
        self._draw_effect_strip()

    def _draw_sprint_bar(self) -> None:
        rect = pygame.Rect(self.board_rect.left, self.board_rect.bottom + 18, self.board_rect.width, 22)
        pygame.draw.rect(self.screen, (18, 24, 44), rect, border_radius=10)
        fill = rect.copy()
        fill.width = max(1, int(rect.width * (self.game.sprint_meter / self.game.max_sprint)))
        fill_color = (82, 190, 255) if not self.game.sprint_locked else (140, 152, 168)
        pygame.draw.rect(self.screen, fill_color, fill, border_radius=10)
        pygame.draw.rect(self.screen, (96, 136, 186), rect, width=2, border_radius=10)
        label = self.font_small.render("SPRINT", True, (240, 248, 255))
        self._draw_icon("spark", (rect.centerx - label.get_width() // 2 - 16, rect.centery), (98, 220, 255), 8)
        self.screen.blit(label, (rect.centerx - label.get_width() // 2, rect.centery - label.get_height() // 2))
        info = f"Energy {int(self.game.sprint_meter):02d}/{int(self.game.max_sprint)}"
        if self.game.sprint_locked:
            threshold = int(self.game.max_sprint * self.game.sprint_restart_threshold_ratio)
            info = f"Locked  |  recover to {threshold}"
        elif self.game.sprint_active:
            info = f"{info}  |  boost online"
        info_surface = self.font_small.render(info, True, (223, 231, 248))
        self.screen.blit(info_surface, (rect.centerx - info_surface.get_width() // 2, rect.bottom + 8))

    def _draw_effect_strip(self) -> None:
        y = self.board_rect.bottom + 56
        if not self.game.active_effects:
            text = self.font_small.render("No active effects", True, (148, 166, 198))
            self.screen.blit(text, (self.board_rect.left, y + 16))
            return
        for index, effect in enumerate(self.game.active_effects[:5]):
            rect = pygame.Rect(self.board_rect.left + index * 98, y, 86, 76)
            pygame.draw.rect(self.screen, (15, 22, 40), rect, border_radius=18)
            pygame.draw.rect(self.screen, effect.color, rect, width=2, border_radius=18)
            self._draw_icon(effect.icon_id, rect.centerx, rect.y + 24, effect.color, 10)
            timer = self.font_small.render(f"{effect.remaining:>3.1f}s", True, (245, 247, 255))
            name = self.font_small.render(effect.short_label[:8], True, (196, 210, 232))
            self.screen.blit(name, (rect.centerx - name.get_width() // 2, rect.y + 38))
            self.screen.blit(timer, (rect.centerx - timer.get_width() // 2, rect.y + 54))

    def _draw_particles(self) -> None:
        for particle in self.particles:
            alpha = int(255 * (particle.lifetime / particle.max_lifetime))
            surface = pygame.Surface((24, 24), pygame.SRCALPHA)
            pygame.draw.circle(surface, (*particle.color, alpha), (12, 12), int(particle.radius))
            self.screen.blit(surface, (particle.x - 12, particle.y - 12))
        for floating in self.floating_pickups:
            alpha = int(255 * (floating.lifetime / floating.max_lifetime))
            icon_pos = (floating.x - 12, floating.y)
            self._draw_icon(floating.icon_id, icon_pos, floating.color, 8, alpha=alpha)
            text_surface = self.font_small.render(floating.text, True, floating.color)
            text_surface.set_alpha(alpha)
            self.screen.blit(text_surface, (floating.x + 4, floating.y - 8))

    def _draw_overlay(self) -> None:
        overlay = pygame.Surface(WINDOW_SIZE, pygame.SRCALPHA)
        overlay.fill((5, 8, 18, 128))
        self.screen.blit(overlay, (0, 0))

    def _draw_start_prompt(self) -> None:
        prompt = self.font_small.render("Press a direction to launch", True, (184, 208, 238))
        glow = self.font_small.render("Press a direction to launch", True, (116, 232, 255))
        x = WINDOW_SIZE[0] // 2 - prompt.get_width() // 2
        y = WINDOW_SIZE[1] // 2 + 132
        self.screen.blit(glow, (x, y - 1))
        self.screen.blit(prompt, (x, y))

    def _panel_rect(self, width: int, height: int) -> pygame.Rect:
        return pygame.Rect(
            self.board_rect.centerx - width // 2,
            self.board_rect.centery - height // 2,
            width,
            height,
        )

    def _draw_menu_panel(self, title: str, items: list[tuple[str, MenuAction]], footer: str) -> None:
        rect = self._panel_rect(420, 300 if len(items) <= 3 else 360)
        pygame.draw.rect(self.screen, (11, 16, 34), rect, border_radius=28)
        pygame.draw.rect(self.screen, (84, 126, 196), rect, width=2, border_radius=28)
        title_surface = self.font_large.render(title, True, (255, 255, 255))
        self.screen.blit(title_surface, (rect.centerx - title_surface.get_width() // 2, rect.y + 24))
        for index, (label, _) in enumerate(items):
            y = rect.y + 100 + index * 44
            selected = index == self.menu_index
            if selected:
                pygame.draw.rect(self.screen, (34, 54, 90), (rect.x + 24, y - 4, rect.width - 48, 34), border_radius=16)
            item_surface = self.font_ui.render(label, True, (255, 255, 255) if selected else (158, 180, 214))
            self.screen.blit(item_surface, (rect.centerx - item_surface.get_width() // 2, y))
        foot = self.font_small.render(footer, True, (178, 197, 226))
        self.screen.blit(foot, (rect.centerx - foot.get_width() // 2, rect.bottom - 28))

    def _draw_options_panel(self) -> None:
        rect = self._panel_rect(520, 540)
        pygame.draw.rect(self.screen, (12, 18, 36), rect, border_radius=28)
        pygame.draw.rect(self.screen, (88, 130, 198), rect, width=2, border_radius=28)
        title = self.font_large.render("Options", True, (255, 255, 255))
        self.screen.blit(title, (rect.centerx - title.get_width() // 2, rect.y + 24))
        items = self._options_items()
        for index, (_, label) in enumerate(items):
            y = rect.y + 84 + index * 34
            selected = index == self.options_index
            if selected:
                pygame.draw.rect(self.screen, (34, 54, 90), (rect.x + 18, y - 4, rect.width - 36, 28), border_radius=14)
            text = self.font_small.render(label, True, (255, 255, 255) if selected else (160, 182, 215))
            self.screen.blit(text, (rect.x + 28, y))
        if self.rebinding_action is not None:
            prompt = self.font_small.render(f"Press a key for {self.rebinding_action.upper()}  |  Esc cancels", True, (255, 212, 140))
            self.screen.blit(prompt, (rect.centerx - prompt.get_width() // 2, rect.bottom - 28))

    def _draw_items_codex(self) -> None:
        rect = self._panel_rect(640, 410)
        pygame.draw.rect(self.screen, (12, 18, 36), rect, border_radius=28)
        pygame.draw.rect(self.screen, (88, 130, 198), rect, width=2, border_radius=28)
        title = self.font_large.render("Items Codex", True, (255, 255, 255))
        self.screen.blit(title, (rect.centerx - title.get_width() // 2, rect.y + 24))
        header = self.font_small.render("Esc returns to pause", True, (173, 194, 232))
        self.screen.blit(header, (rect.centerx - header.get_width() // 2, rect.y + 64))
        for index, definition in enumerate(self.items.values()):
            row = pygame.Rect(rect.x + 24, rect.y + 98 + index * 66, rect.width - 48, 54)
            pygame.draw.rect(self.screen, (18, 24, 44), row, border_radius=18)
            pygame.draw.rect(self.screen, definition.glow_color, row, width=1, border_radius=18)
            self._draw_icon(definition.icon_id, row.x + 28, row.centery, definition.color, 11)
            name = self.font_ui.render(definition.label, True, (255, 255, 255))
            desc = self.font_small.render(definition.description, True, (196, 212, 236))
            meta = self.font_small.render(f"{definition.duration:.0f}s  |  +{int(definition.instant_sprint)} sprint", True, (164, 182, 210))
            self.screen.blit(name, (row.x + 52, row.y + 6))
            self.screen.blit(desc, (row.x + 52, row.y + 28))
            self.screen.blit(meta, (row.right - meta.get_width() - 12, row.y + 18))

    def _draw_icon(
        self,
        icon_id: str,
        center_or_x: float | int | tuple[float, float],
        y: float | None = None,
        color: tuple[int, int, int] | None = None,
        size: int = 10,
        alpha: int = 255,
    ) -> None:
        if isinstance(center_or_x, tuple):
            cx, cy = center_or_x
            draw_color = y if isinstance(y, tuple) else color
            radius = color if isinstance(color, int) else size
        else:
            cx = float(center_or_x)
            assert y is not None and color is not None
            cy = float(y)
            draw_color = color
            radius = size
        assert draw_color is not None
        rgba = (*draw_color, alpha)
        icon_surface = pygame.Surface((radius * 4, radius * 4), pygame.SRCALPHA)
        icx = icon_surface.get_width() / 2
        icy = icon_surface.get_height() / 2
        if icon_id == "spark":
            points = [(icx, icy - radius), (icx + radius * 0.35, icy - radius * 0.25), (icx + radius, icy), (icx + radius * 0.35, icy + radius * 0.25), (icx, icy + radius), (icx - radius * 0.35, icy + radius * 0.25), (icx - radius, icy), (icx - radius * 0.35, icy - radius * 0.25)]
            pygame.draw.polygon(icon_surface, rgba, points)
        elif icon_id == "diamond":
            pygame.draw.polygon(icon_surface, rgba, [(icx, icy - radius), (icx + radius, icy), (icx, icy + radius), (icx - radius, icy)])
        elif icon_id == "halo":
            pygame.draw.circle(icon_surface, rgba, (int(icx), int(icy)), radius, 3)
            pygame.draw.circle(icon_surface, rgba, (int(icx), int(icy)), max(2, radius // 3))
        elif icon_id == "hourglass":
            pygame.draw.polygon(icon_surface, rgba, [(icx - radius, icy - radius), (icx + radius, icy - radius), (icx + 3, icy - 2), (icx - 3, icy - 2)])
            pygame.draw.polygon(icon_surface, rgba, [(icx - radius, icy + radius), (icx + radius, icy + radius), (icx + 3, icy + 2), (icx - 3, icy + 2)])
            pygame.draw.line(icon_surface, rgba, (icx - 2, icy - 2), (icx + 2, icy + 2), 3)
            pygame.draw.line(icon_surface, rgba, (icx + 2, icy - 2), (icx - 2, icy + 2), 3)
        else:
            pygame.draw.circle(icon_surface, rgba, (int(icx), int(icy)), radius)
        self.screen.blit(icon_surface, (cx - icon_surface.get_width() / 2, cy - icon_surface.get_height() / 2))


def main() -> None:
    app = SnakeCosmosApp()
    app.run()
