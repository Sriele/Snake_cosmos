from __future__ import annotations

from dataclasses import dataclass, field
from random import Random
from typing import Iterable

from snake_cosmos.catalog import FoodDefinition, ItemDefinition

GridPos = tuple[int, int]


@dataclass(frozen=True)
class Settings:
    master_volume: float = 0.8
    music_volume: float = 0.55
    sfx_volume: float = 0.8
    fullscreen: bool = False
    screen_shake: float = 0.6
    keybinds: dict[str, str] = field(
        default_factory=lambda: {
            "up": "w",
            "down": "s",
            "left": "a",
            "right": "d",
            "sprint": "space",
            "pause": "escape",
        }
    )


@dataclass
class ActiveEffect:
    item_id: str
    label: str
    short_label: str
    description: str
    effect_type: str
    value: float
    duration: float
    remaining: float
    icon_id: str
    color: tuple[int, int, int]


@dataclass
class FoodPickupEvent:
    label: str
    rarity: str
    score_gain: int
    sprint_gain: float
    color: tuple[int, int, int]


@dataclass
class ItemPickupEvent:
    label: str
    description: str
    duration: float
    color: tuple[int, int, int]


@dataclass
class Toast:
    title: str
    body: str
    ttl: float
    color: tuple[int, int, int]


@dataclass
class GameEvents:
    food_pickups: list[FoodPickupEvent] = field(default_factory=list)
    item_pickups: list[ItemPickupEvent] = field(default_factory=list)
    game_over: bool = False
    spawned_item: bool = False


class SnakeGame:
    def __init__(
        self,
        foods: dict[str, FoodDefinition],
        items: dict[str, ItemDefinition],
        width: int = 21,
        height: int = 21,
        seed: int | None = None,
    ) -> None:
        self.width = width
        self.height = height
        self.foods = foods
        self.items = items
        self.random = Random(seed)
        self.base_speed = 7.0
        self.sprint_multiplier = 1.75
        self.sprint_drain_per_second = 34.0
        self.sprint_regen_per_second = 7.5
        self.max_sprint = 60.0
        self.sprint_restart_threshold_ratio = 0.15
        self.item_spawn_interval = (8.0, 14.0)
        self.toasts: list[Toast] = []
        self.reset()

    def reset(self) -> None:
        mid_x = self.width // 2
        mid_y = self.height // 2
        self.snake: list[GridPos] = [(mid_x, mid_y), (mid_x - 1, mid_y), (mid_x - 2, mid_y)]
        self.previous_snake: list[GridPos] = self.snake.copy()
        self.direction: GridPos = (1, 0)
        self.queued_direction: GridPos = self.direction
        self.pending_growth = 0
        self.score = 0
        self.best_score = 0
        self.alive = True
        self.sprint_meter = 30.0
        self.sprint_locked = False
        self.sprint_active = False
        self.item_spawn_timer = self.random.uniform(*self.item_spawn_interval)
        self.item: tuple[GridPos, ItemDefinition] | None = None
        self.food: tuple[GridPos, FoodDefinition] | None = None
        self.active_effects: list[ActiveEffect] = []
        self.step_accumulator = 0.0
        self.current_move_interval = 1.0 / self.base_speed
        self.last_progress = 0.0
        self.food_glow_timer = 0.0
        self.item_glow_timer = 0.0
        self.pickup_flash_color = (76, 255, 226)
        self.last_events = GameEvents()
        self.food = self._spawn_food()

    def snapshot_previous_snake(self) -> None:
        self.previous_snake = self.snake.copy()

    def enqueue_direction(self, direction: GridPos) -> None:
        opposite = (-self.direction[0], -self.direction[1])
        if direction != opposite:
            self.queued_direction = direction

    def update(self, dt: float, sprint_pressed: bool) -> GameEvents:
        events = GameEvents()
        self.last_events = events
        self._update_toasts(dt)
        if not self.alive:
            return events

        self._tick_effects(dt)
        self.food_glow_timer = max(0.0, self.food_glow_timer - dt)
        self.item_glow_timer = max(0.0, self.item_glow_timer - dt)
        self.sprint_meter = min(self.max_sprint, self.sprint_meter + self._sprint_regen_rate() * dt)
        if self.sprint_locked and self.sprint_meter >= self.max_sprint * self.sprint_restart_threshold_ratio:
            self.sprint_locked = False

        if self.item is None:
            self.item_spawn_timer -= dt
            if self.item_spawn_timer <= 0:
                self.item = self._spawn_item()
                self.item_spawn_timer = self.random.uniform(*self.item_spawn_interval)
                events.spawned_item = True

        speed_multiplier = self._speed_multiplier()
        self.sprint_active = False
        if sprint_pressed and not self.sprint_locked and self.sprint_meter > 0:
            speed_multiplier *= self.sprint_multiplier
            self.sprint_meter = max(0.0, self.sprint_meter - self.sprint_drain_per_second * dt)
            self.sprint_active = True
            if self.sprint_meter <= 0:
                self.sprint_meter = 0.0
                self.sprint_active = False
                self.sprint_locked = True
        self.current_move_interval = 1.0 / (self.base_speed * speed_multiplier)
        self.step_accumulator += dt

        while self.step_accumulator >= self.current_move_interval and self.alive:
            self.step_accumulator -= self.current_move_interval
            self._step(events)

        if self.current_move_interval > 0:
            self.last_progress = min(1.0, self.step_accumulator / self.current_move_interval)
        return events

    def _update_toasts(self, dt: float) -> None:
        for toast in self.toasts:
            toast.ttl -= dt
        self.toasts = [toast for toast in self.toasts if toast.ttl > 0]

    def _tick_effects(self, dt: float) -> None:
        for effect in self.active_effects:
            effect.remaining -= dt
        self.active_effects = [effect for effect in self.active_effects if effect.remaining > 0]

    def _speed_multiplier(self) -> float:
        multiplier = 1.0
        if self._effect_value("time_dilation"):
            multiplier *= max(0.65, 1.0 - self._effect_value("time_dilation"))
        if self._effect_value("comet_regen"):
            multiplier *= 1.15
        return multiplier

    def _sprint_regen_rate(self) -> float:
        regen = self.sprint_regen_per_second
        if self._effect_value("comet_regen"):
            regen += self._effect_value("comet_regen")
        return regen

    def _effect_value(self, effect_type: str) -> float:
        total = 0.0
        for effect in self.active_effects:
            if effect.effect_type == effect_type:
                total += effect.value
        return total

    def _step(self, events: GameEvents) -> None:
        self.snapshot_previous_snake()
        self.direction = self.queued_direction
        head_x, head_y = self.snake[0]
        dx, dy = self.direction
        next_head = (head_x + dx, head_y + dy)

        if self._effect_value("border_wrap"):
            next_head = (next_head[0] % self.width, next_head[1] % self.height)
        elif not (0 <= next_head[0] < self.width and 0 <= next_head[1] < self.height):
            self.alive = False
            events.game_over = True
            self._register_game_over()
            return

        body_to_check = self.snake[:-1] if self.pending_growth == 0 else self.snake
        if next_head in body_to_check:
            self.alive = False
            events.game_over = True
            self._register_game_over()
            return

        self.snake.insert(0, next_head)
        if self.food and next_head == self.food[0]:
            self._consume_food(events)
        elif self.item and next_head == self.item[0]:
            self._consume_item(events)
        else:
            if self.pending_growth > 0:
                self.pending_growth -= 1
            else:
                self.snake.pop()

    def _consume_food(self, events: GameEvents) -> None:
        assert self.food is not None
        _, food_def = self.food
        multiplier = 2 if self._effect_value("score_mult") else 1
        gained_score = food_def.score * multiplier
        self.score += gained_score
        self.pending_growth += max(0, food_def.growth - 1)
        self.sprint_meter = min(self.max_sprint, self.sprint_meter + food_def.sprint_gain)
        events.food_pickups.append(
            FoodPickupEvent(
                label=food_def.label,
                rarity=food_def.rarity,
                score_gain=gained_score,
                sprint_gain=food_def.sprint_gain,
                color=food_def.glow_color,
            )
        )
        self.toasts.append(
            Toast(
                title=food_def.label,
                body=f"+{gained_score} score  |  +{int(food_def.sprint_gain)} sprint",
                ttl=2.2,
                color=food_def.glow_color,
            )
        )
        self.food_glow_timer = max(self.food_glow_timer, 0.65)
        self.pickup_flash_color = food_def.glow_color
        self.food = self._spawn_food()

    def _consume_item(self, events: GameEvents) -> None:
        assert self.item is not None
        _, item_def = self.item
        self.item = None
        self.sprint_meter = min(self.max_sprint, self.sprint_meter + item_def.instant_sprint)
        effect = ActiveEffect(
            item_id=item_def.item_id,
            label=item_def.label,
            short_label=item_def.short_label,
            description=item_def.description,
            effect_type=item_def.effect_type,
            value=item_def.value,
            duration=item_def.duration,
            remaining=item_def.duration,
            icon_id=item_def.icon_id,
            color=item_def.glow_color,
        )
        self.active_effects = [e for e in self.active_effects if e.effect_type != effect.effect_type]
        self.active_effects.append(effect)
        events.item_pickups.append(
            ItemPickupEvent(
                label=item_def.label,
                description=item_def.description,
                duration=item_def.duration,
                color=item_def.glow_color,
            )
        )
        self.toasts.append(
            Toast(
                title=item_def.label,
                body=f"{item_def.description} ({item_def.duration:.0f}s)",
                ttl=3.2,
                color=item_def.glow_color,
            )
        )
        self.item_glow_timer = max(self.item_glow_timer, 1.15)
        self.pickup_flash_color = item_def.glow_color
        if self.pending_growth > 0:
            self.pending_growth -= 1
        else:
            self.snake.pop()

    def _register_game_over(self) -> None:
        self.best_score = max(self.best_score, self.score)
        self.toasts.append(
            Toast(
                title="Signal Lost",
                body=f"Final score: {self.score}",
                ttl=3.0,
                color=(255, 116, 116),
            )
        )

    def _open_positions(self) -> list[GridPos]:
        blocked: set[GridPos] = set(self.snake)
        if self.food:
            blocked.add(self.food[0])
        if self.item:
            blocked.add(self.item[0])
        return [(x, y) for x in range(self.width) for y in range(self.height) if (x, y) not in blocked]

    def _choose_weighted(self, definitions: Iterable[FoodDefinition | ItemDefinition]) -> FoodDefinition | ItemDefinition:
        options = list(definitions)
        total = sum(item.spawn_weight for item in options)
        roll = self.random.uniform(0, total)
        cursor = 0.0
        for option in options:
            cursor += option.spawn_weight
            if roll <= cursor:
                return option
        return options[-1]

    def _spawn_food(self) -> tuple[GridPos, FoodDefinition]:
        positions = self._open_positions()
        position = self.random.choice(positions)
        definition = self._choose_weighted(self.foods.values())
        assert isinstance(definition, FoodDefinition)
        return position, definition

    def _spawn_item(self) -> tuple[GridPos, ItemDefinition]:
        positions = self._open_positions()
        position = self.random.choice(positions)
        definition = self._choose_weighted(self.items.values())
        assert isinstance(definition, ItemDefinition)
        return position, definition
