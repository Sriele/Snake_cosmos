import unittest

from snake_cosmos.catalog import load_food_definitions, load_item_definitions
from snake_cosmos.core import SnakeGame


def make_game() -> SnakeGame:
    return SnakeGame(load_food_definitions(), load_item_definitions(), width=9, height=9, seed=42)


class SnakeCoreTests(unittest.TestCase):
    def test_food_spawn_never_starts_on_snake(self) -> None:
        game = make_game()
        self.assertNotIn(game.food[0], game.snake)

    def test_consuming_food_increases_score_and_growth(self) -> None:
        game = make_game()
        head_x, head_y = game.snake[0]
        definition = next(iter(game.foods.values()))
        game.food = ((head_x + 1, head_y), definition)
        game.enqueue_direction((1, 0))
        game.update(0.3, sprint_pressed=False)
        self.assertEqual(game.score, definition.score)
        self.assertEqual(len(game.snake), 4)

    def test_border_wrap_effect_applies(self) -> None:
        game = make_game()
        effect = next(item for item in game.items.values() if item.effect_type == "border_wrap")
        game.item = ((game.snake[0][0] + 1, game.snake[0][1]), effect)
        game.update(0.3, sprint_pressed=False)
        game.snake = [(8, 4), (7, 4), (6, 4)]
        game.previous_snake = game.snake.copy()
        game.direction = (1, 0)
        game.queued_direction = (1, 0)
        game.update(0.15, sprint_pressed=False)
        self.assertTrue(game.alive)
        self.assertEqual(game.snake[0], (0, 4))

    def test_sprint_locks_when_empty_and_requires_recovery_threshold(self) -> None:
        game = make_game()
        game.base_speed = 0.01
        game.current_move_interval = 1.0 / game.base_speed
        game.sprint_meter = 1.0
        game.update(0.2, sprint_pressed=True)
        self.assertTrue(game.sprint_locked)
        self.assertFalse(game.sprint_active)
        self.assertEqual(game.sprint_meter, 0.0)

        game.update(0.5, sprint_pressed=True)
        self.assertTrue(game.sprint_locked)
        self.assertFalse(game.sprint_active)

        required = game.max_sprint * game.sprint_restart_threshold_ratio
        while game.sprint_meter < required:
            game.update(0.2, sprint_pressed=False)

        game.update(0.05, sprint_pressed=True)
        self.assertFalse(game.sprint_locked)
        self.assertTrue(game.sprint_active)


if __name__ == "__main__":
    unittest.main()
