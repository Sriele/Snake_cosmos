const canvas = document.getElementById("game");
const ctx = canvas.getContext("2d");

const WINDOW = { width: 1280, height: 760 };
const BOARD = { cells: 21, cellSize: 24 };
const BOARD_SIZE = BOARD.cells * BOARD.cellSize;
const BOARD_RECT = {
  x: (WINDOW.width - BOARD_SIZE) / 2,
  y: (WINDOW.height - BOARD_SIZE) / 2 - 6,
  width: BOARD_SIZE,
  height: BOARD_SIZE,
};

const STORAGE_KEY = "snake-cosmos-web-save";
const SCENE = {
  TITLE: "title",
  PLAYING: "playing",
  PAUSED: "paused",
  OPTIONS: "options",
  ITEMS: "items",
  GAME_OVER: "game_over",
};

const ACTIONS = ["up", "down", "left", "right", "sprint"];
const DEFAULT_SETTINGS = {
  masterVolume: 0.8,
  musicVolume: 0.55,
  sfxVolume: 0.8,
  keybinds: {
    up: "KeyW",
    down: "KeyS",
    left: "KeyA",
    right: "KeyD",
    sprint: "Space",
  },
};

const state = {
  foods: [],
  items: [],
  scene: SCENE.TITLE,
  returnScene: SCENE.TITLE,
  menuIndex: 0,
  optionsIndex: 0,
  rebindingAction: null,
  bestScore: 0,
  settings: structuredClone(DEFAULT_SETTINGS),
  stars: [],
  boardSpecks: [],
  particles: [],
  floatingTexts: [],
  titlePhase: 0,
  game: null,
  lastFrame: performance.now(),
  inputDown: new Set(),
  audio: null,
};

class WebAudioBank {
  constructor() {
    this.ctx = null;
    this.musicTimer = 0;
    this.musicPattern = [130.81, 146.83, 164.81, 146.83];
  }

  ensureContext() {
    if (!this.ctx) {
      this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (this.ctx.state === "suspended") {
      this.ctx.resume();
    }
  }

  get master() {
    return state.settings.masterVolume;
  }

  get sfx() {
    return this.master * state.settings.sfxVolume;
  }

  get music() {
    return this.master * state.settings.musicVolume;
  }

  playTone(freq, duration, type = "sine", gainValue = 0.12, delay = 0) {
    if (!this.ctx) return;
    const t = this.ctx.currentTime + delay;
    const osc = this.ctx.createOscillator();
    const gain = this.ctx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, t);
    gain.gain.setValueAtTime(0.0001, t);
    gain.gain.exponentialRampToValueAtTime(Math.max(0.0001, gainValue), t + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + duration);
    osc.connect(gain).connect(this.ctx.destination);
    osc.start(t);
    osc.stop(t + duration + 0.03);
  }

  play(name) {
    this.ensureContext();
    const v = this.sfx;
    if (name === "menu_move") {
      this.playTone(360, 0.08, "triangle", 0.05 * v);
    } else if (name === "menu_select") {
      this.playTone(520, 0.12, "triangle", 0.08 * v);
    } else if (name === "food") {
      this.playTone(420, 0.05, "sawtooth", 0.07 * v);
      this.playTone(260, 0.08, "triangle", 0.06 * v, 0.03);
    } else if (name === "item") {
      this.playTone(160, 0.06, "square", 0.1 * v);
      this.playTone(260, 0.12, "sawtooth", 0.09 * v, 0.04);
      this.playTone(420, 0.18, "triangle", 0.07 * v, 0.08);
    } else if (name === "rare") {
      this.playTone(660, 0.08, "triangle", 0.07 * v);
      this.playTone(840, 0.1, "triangle", 0.06 * v, 0.06);
      this.playTone(1040, 0.14, "sine", 0.05 * v, 0.1);
    } else if (name === "game_over") {
      this.playTone(240, 0.18, "triangle", 0.08 * v);
      this.playTone(190, 0.24, "triangle", 0.07 * v, 0.12);
      this.playTone(150, 0.32, "sine", 0.06 * v, 0.25);
    }
  }

  update(dt) {
    if (!this.ctx) return;
    this.musicTimer -= dt;
    if (this.musicTimer > 0) return;
    const note = this.musicPattern[Math.floor((state.titlePhase / 1.6) % this.musicPattern.length)];
    this.playTone(note, 1.35, "sine", 0.018 * this.music);
    this.playTone(note / 2, 1.55, "triangle", 0.012 * this.music);
    this.musicTimer = 1.6;
  }
}

class SnakeGame {
  constructor(foods, items) {
    this.foodDefs = foods;
    this.itemDefs = items;
    this.width = BOARD.cells;
    this.height = BOARD.cells;
    this.baseSpeed = 7;
    this.sprintMultiplier = 1.75;
    this.sprintDrainPerSecond = 34;
    this.sprintRegenPerSecond = 7.5;
    this.maxSprint = 60;
    this.sprintRestartThresholdRatio = 0.15;
    this.itemSpawnInterval = [8, 14];
    this.reset();
  }

  reset() {
    const mx = Math.floor(this.width / 2);
    const my = Math.floor(this.height / 2);
    this.snake = [
      { x: mx, y: my },
      { x: mx - 1, y: my },
      { x: mx - 2, y: my },
    ];
    this.previousSnake = this.snake.map((s) => ({ ...s }));
    this.direction = { x: 1, y: 0 };
    this.queuedDirection = { ...this.direction };
    this.pendingGrowth = 0;
    this.score = 0;
    this.alive = true;
    this.awaitFirstMove = true;
    this.sprintMeter = 30;
    this.sprintLocked = false;
    this.sprintActive = false;
    this.itemSpawnTimer = randomRange(...this.itemSpawnInterval);
    this.foodGlowTimer = 0;
    this.itemGlowTimer = 0;
    this.pickupFlashColor = [76, 255, 226];
    this.effects = [];
    this.item = null;
    this.stepAccumulator = 0;
    this.currentMoveInterval = 1 / this.baseSpeed;
    this.lastProgress = 0;
    this.food = this.spawnFood();
  }

  enqueueDirection(next) {
    const opposite = { x: -this.direction.x, y: -this.direction.y };
    if (next.x !== opposite.x || next.y !== opposite.y) {
      this.queuedDirection = next;
      this.awaitFirstMove = false;
    }
  }

  update(dt, sprintPressed) {
    const events = { foodPickups: [], itemPickups: [], gameOver: false };
    if (!this.alive || this.awaitFirstMove) return events;
    this.foodGlowTimer = Math.max(0, this.foodGlowTimer - dt);
    this.itemGlowTimer = Math.max(0, this.itemGlowTimer - dt);
    for (const effect of this.effects) effect.remaining -= dt;
    this.effects = this.effects.filter((effect) => effect.remaining > 0);
    this.sprintMeter = Math.min(this.maxSprint, this.sprintMeter + this.sprintRegenRate() * dt);
    if (this.sprintLocked && this.sprintMeter >= this.maxSprint * this.sprintRestartThresholdRatio) {
      this.sprintLocked = false;
    }
    if (!this.item) {
      this.itemSpawnTimer -= dt;
      if (this.itemSpawnTimer <= 0) {
        this.item = this.spawnItem();
        this.itemSpawnTimer = randomRange(...this.itemSpawnInterval);
      }
    }
    let speedMultiplier = this.speedMultiplier();
    this.sprintActive = false;
    if (sprintPressed && !this.sprintLocked && this.sprintMeter > 0) {
      speedMultiplier *= this.sprintMultiplier;
      this.sprintMeter = Math.max(0, this.sprintMeter - this.sprintDrainPerSecond * dt);
      this.sprintActive = true;
      if (this.sprintMeter <= 0) {
        this.sprintMeter = 0;
        this.sprintLocked = true;
        this.sprintActive = false;
      }
    }
    this.currentMoveInterval = 1 / (this.baseSpeed * speedMultiplier);
    this.stepAccumulator += dt;
    while (this.stepAccumulator >= this.currentMoveInterval && this.alive) {
      this.stepAccumulator -= this.currentMoveInterval;
      this.step(events);
    }
    this.lastProgress = Math.min(1, this.stepAccumulator / this.currentMoveInterval);
    return events;
  }

  speedMultiplier() {
    let multiplier = 1;
    const time = this.effectValue("time_dilation");
    const comet = this.effectValue("comet_regen");
    if (time) multiplier *= Math.max(0.65, 1 - time);
    if (comet) multiplier *= 1.15;
    return multiplier;
  }

  sprintRegenRate() {
    return this.sprintRegenPerSecond + this.effectValue("comet_regen");
  }

  effectValue(type) {
    return this.effects.reduce((total, effect) => total + (effect.effect_type === type ? effect.value : 0), 0);
  }

  step(events) {
    this.previousSnake = this.snake.map((s) => ({ ...s }));
    this.direction = { ...this.queuedDirection };
    const head = this.snake[0];
    let next = { x: head.x + this.direction.x, y: head.y + this.direction.y };
    if (this.effectValue("border_wrap")) {
      next = { x: mod(next.x, this.width), y: mod(next.y, this.height) };
    } else if (next.x < 0 || next.y < 0 || next.x >= this.width || next.y >= this.height) {
      this.alive = false;
      events.gameOver = true;
      return;
    }
    const body = this.pendingGrowth === 0 ? this.snake.slice(0, -1) : this.snake;
    if (body.some((part) => part.x === next.x && part.y === next.y)) {
      this.alive = false;
      events.gameOver = true;
      return;
    }
    this.snake.unshift(next);
    if (this.food && next.x === this.food.pos.x && next.y === this.food.pos.y) {
      this.consumeFood(events);
    } else if (this.item && next.x === this.item.pos.x && next.y === this.item.pos.y) {
      this.consumeItem(events);
    } else if (this.pendingGrowth > 0) {
      this.pendingGrowth -= 1;
    } else {
      this.snake.pop();
    }
  }

  consumeFood(events) {
    const def = this.food.def;
    const gainedScore = def.score * (this.effectValue("score_mult") ? 2 : 1);
    this.score += gainedScore;
    this.pendingGrowth += Math.max(0, def.growth - 1);
    this.sprintMeter = Math.min(this.maxSprint, this.sprintMeter + def.sprint_gain);
    this.foodGlowTimer = Math.max(this.foodGlowTimer, 0.65);
    this.pickupFlashColor = def.glow_color;
    events.foodPickups.push({
      rarity: def.rarity,
      scoreGain: gainedScore,
      sprintGain: def.sprint_gain,
      color: def.glow_color,
      label: def.label,
    });
    this.food = this.spawnFood();
  }

  consumeItem(events) {
    const def = this.item.def;
    this.sprintMeter = Math.min(this.maxSprint, this.sprintMeter + def.instant_sprint);
    this.effects = this.effects.filter((effect) => effect.effect_type !== def.effect_type);
    this.effects.push({
      ...def,
      remaining: def.duration,
    });
    this.itemGlowTimer = Math.max(this.itemGlowTimer, 1.15);
    this.pickupFlashColor = def.glow_color;
    events.itemPickups.push({
      label: def.label,
      description: def.description,
      duration: def.duration,
      color: def.glow_color,
    });
    this.item = null;
    if (this.pendingGrowth > 0) this.pendingGrowth -= 1;
    else this.snake.pop();
  }

  openPositions() {
    const blocked = new Set(this.snake.map((s) => `${s.x},${s.y}`));
    if (this.food) blocked.add(`${this.food.pos.x},${this.food.pos.y}`);
    if (this.item) blocked.add(`${this.item.pos.x},${this.item.pos.y}`);
    const positions = [];
    for (let y = 0; y < this.height; y += 1) {
      for (let x = 0; x < this.width; x += 1) {
        if (!blocked.has(`${x},${y}`)) positions.push({ x, y });
      }
    }
    return positions;
  }

  weightedChoice(defs) {
    const total = defs.reduce((sum, def) => sum + def.spawn_weight, 0);
    let roll = Math.random() * total;
    for (const def of defs) {
      roll -= def.spawn_weight;
      if (roll <= 0) return def;
    }
    return defs[defs.length - 1];
  }

  spawnFood() {
    return { pos: choice(this.openPositions()), def: this.weightedChoice(this.foodDefs) };
  }

  spawnItem() {
    return { pos: choice(this.openPositions()), def: this.weightedChoice(this.itemDefs) };
  }
}

function randomRange(min, max) {
  return min + Math.random() * (max - min);
}

function choice(items) {
  return items[Math.floor(Math.random() * items.length)];
}

function mod(value, divisor) {
  return ((value % divisor) + divisor) % divisor;
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function lerp(a, b, t) {
  return a + (b - a) * t;
}

function easeSnake(t) {
  return t * t * (3 - 2 * t);
}

function rgba(color, alpha = 1) {
  return `rgba(${color[0]}, ${color[1]}, ${color[2]}, ${alpha})`;
}

function saveWebState() {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      bestScore: state.bestScore,
      settings: state.settings,
    }),
  );
}

function loadWebState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const data = JSON.parse(raw);
    state.bestScore = Number(data.bestScore || 0);
    state.settings = { ...DEFAULT_SETTINGS, ...data.settings, keybinds: { ...DEFAULT_SETTINGS.keybinds, ...data.settings?.keybinds } };
  } catch {
    state.bestScore = 0;
  }
}

function pointForCell(cell) {
  return {
    x: BOARD_RECT.x + cell.x * BOARD.cellSize + BOARD.cellSize / 2,
    y: BOARD_RECT.y + cell.y * BOARD.cellSize + BOARD.cellSize / 2,
  };
}

function setupDecor() {
  state.stars = Array.from({ length: 120 }, () => ({
    x: Math.random() * WINDOW.width,
    y: Math.random() * WINDOW.height,
    speed: randomRange(10, 42),
    size: randomRange(1, 3.3),
    phase: randomRange(0, Math.PI * 2),
  }));
  state.boardSpecks = Array.from({ length: 38 }, () => ({
    x: Math.random() * BOARD_RECT.width,
    y: Math.random() * BOARD_RECT.height,
    size: Math.floor(randomRange(1, 3)),
  }));
}

function createFloatingText(x, y, iconId, text, color, life = 0.95, drift = 0) {
  state.floatingTexts.push({ x, y, iconId, text, color, life, maxLife: life, drift });
}

function spawnParticles(x, y, color, count, speed, life) {
  for (let i = 0; i < count; i += 1) {
    state.particles.push({
      x,
      y,
      vx: randomRange(-speed, speed),
      vy: randomRange(-speed * 1.3, speed * 0.4),
      color,
      radius: randomRange(2, 5),
      life,
      maxLife: life,
    });
  }
}

function handleEvents(events) {
  for (const pickup of events.foodPickups) {
    const head = pointForCell(state.game.snake[0]);
    spawnParticles(head.x, head.y, pickup.color, 14, 34, 0.8);
    createFloatingText(head.x - 18, head.y - 8, "diamond", `+${pickup.scoreGain}`, [255, 214, 92], 0.95, -4);
    createFloatingText(head.x + 18, head.y + 6, "spark", `+${pickup.sprintGain}`, [98, 220, 255], 0.95, 4);
    state.audio.play("food");
    if (pickup.rarity === "epic") {
      state.audio.play("rare");
      spawnRing(head.x, head.y, pickup.color);
    }
  }
  for (const item of events.itemPickups) {
    const head = pointForCell(state.game.snake[0]);
    spawnParticles(head.x, head.y, item.color, 26, 60, 1);
    createFloatingText(head.x, head.y - 12, "halo", item.label, item.color, 1.05, 0);
    state.audio.play("item");
    state.audio.play("rare");
    spawnRing(head.x, head.y, item.color);
  }
  if (events.gameOver) {
    state.audio.play("game_over");
    state.scene = SCENE.GAME_OVER;
    state.menuIndex = 0;
  }
}

function spawnRing(x, y, color) {
  for (let angle = 0; angle < 360; angle += 24) {
    const rad = (angle * Math.PI) / 180;
    state.particles.push({
      x: x + Math.cos(rad) * 10,
      y: y + Math.sin(rad) * 10,
      vx: Math.cos(rad) * 120,
      vy: Math.sin(rad) * 120,
      color,
      radius: 4.2,
      life: 0.75,
      maxLife: 0.75,
    });
  }
}

function update(dt) {
  state.titlePhase += dt;
  state.audio.update(dt);
  for (const star of state.stars) {
    star.x -= star.speed * dt;
    star.phase += dt * 1.15;
    if (star.x < -12) {
      star.x = WINDOW.width + Math.random() * 80;
      star.y = Math.random() * WINDOW.height;
    }
  }
  for (const particle of state.particles) {
    particle.life -= dt;
    particle.x += particle.vx * dt;
    particle.y += particle.vy * dt;
    particle.vy += 90 * dt;
  }
  state.particles = state.particles.filter((p) => p.life > 0);
  for (const floating of state.floatingTexts) {
    floating.life -= dt;
    floating.y -= 36 * dt;
    floating.x += floating.drift * dt;
  }
  state.floatingTexts = state.floatingTexts.filter((f) => f.life > 0);
  if (state.scene === SCENE.PLAYING) {
    const sprintPressed = state.inputDown.has(state.settings.keybinds.sprint);
    const events = state.game.update(dt, sprintPressed);
    state.bestScore = Math.max(state.bestScore, state.game.score);
    handleEvents(events);
    saveWebState();
  }
}

function drawBackground() {
  const gradient = ctx.createLinearGradient(0, 0, 0, WINDOW.height);
  gradient.addColorStop(0, "#07101f");
  gradient.addColorStop(1, "#12203a");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, WINDOW.width, WINDOW.height);
  for (const [x, y, radius, color] of [
    [180, 150, 220, "rgba(50,98,190,0.18)"],
    [1020, 240, 260, "rgba(40,170,190,0.16)"],
    [840, 620, 280, "rgba(120,60,160,0.12)"],
    [360, 580, 180, "rgba(160,88,120,0.10)"],
  ]) {
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, Math.PI * 2);
    ctx.fill();
  }
  for (const star of state.stars) {
    ctx.fillStyle = "rgba(220,232,255,0.9)";
    ctx.beginPath();
    ctx.arc(star.x, star.y, star.size, 0, Math.PI * 2);
    ctx.fill();
  }
}

function drawBoardShell() {
  roundRect(BOARD_RECT.x - 17, BOARD_RECT.y - 17, BOARD_RECT.width + 34, BOARD_RECT.height + 34, 30, "#0e1224", "#44608c");
}

function drawBoard() {
  ctx.save();
  ctx.beginPath();
  roundRectPath(BOARD_RECT.x, BOARD_RECT.y, BOARD_RECT.width, BOARD_RECT.height, 18);
  ctx.clip();
  ctx.fillStyle = "rgba(7,12,24,0.95)";
  ctx.fillRect(BOARD_RECT.x, BOARD_RECT.y, BOARD_RECT.width, BOARD_RECT.height);
  const centerX = BOARD_RECT.x + BOARD_RECT.width / 2;
  const centerY = BOARD_RECT.y + BOARD_RECT.height / 2;
  drawGlow(centerX, centerY, 240, "rgba(22,34,62,0.35)");
  drawGlow(centerX - 110, centerY + 70, 140, "rgba(15,52,74,0.12)");
  drawGlow(centerX + 130, centerY - 110, 120, "rgba(74,40,90,0.10)");
  ctx.strokeStyle = "rgba(80,130,160,0.18)";
  ctx.lineWidth = 2;
  for (const offset of [46, 118, 186]) {
    ctx.beginPath();
    ctx.ellipse(centerX, centerY, BOARD_RECT.width / 2 - offset, BOARD_RECT.height / 2 - offset, 0, 0.8, 2.2);
    ctx.stroke();
  }
  ctx.fillStyle = "rgba(180,200,255,0.08)";
  for (const speck of state.boardSpecks) {
    ctx.fillRect(BOARD_RECT.x + speck.x, BOARD_RECT.y + speck.y, speck.size, speck.size);
  }
  ctx.restore();
  drawFood();
  drawItem();
  drawSnake();
  if (state.scene === SCENE.PLAYING && state.game.awaitFirstMove) drawStartPrompt();
}

function interpolatedSnakePoints() {
  const progress = easeSnake(state.game.lastProgress);
  const current = state.game.snake;
  const previous = state.game.previousSnake;
  return current.map((segment, index) => {
    const prev = previous[index] || previous[previous.length - 1];
    return pointForCell({
      x: lerp(prev.x, segment.x, progress),
      y: lerp(prev.y, segment.y, progress),
    });
  });
}

function drawSnake() {
  const points = interpolatedSnakePoints();
  if (points.length < 2) return;
  const glowStrength = clamp(Math.max(state.game.foodGlowTimer * 1.2, state.game.itemGlowTimer * 1.7), 0, 1);
  const glowColor = state.game.pickupFlashColor;
  for (let i = points.length - 1; i > 0; i -= 1) {
    const t = i / Math.max(1, points.length - 1);
    const width = Math.max(6, Math.floor(16 - t * 6));
    drawLine(points[i], points[i - 1], width + 4, "#141a1e");
    if (glowStrength > 0) drawGlow(points[i].x, points[i].y, width + 7, rgba(glowColor, 0.3));
    const body = [78 - t * 18, 104 - t * 20, 82 - t * 14];
    const ridge = [body[0] + 18 + 40 * glowStrength, body[1] + 26 + 90 * glowStrength, body[2] + 12 + 80 * glowStrength];
    drawLine(points[i], points[i - 1], width, rgba(body, 1));
    ctx.fillStyle = rgba(body, 1);
    ctx.beginPath();
    ctx.arc(points[i].x, points[i].y, width / 2, 0, Math.PI * 2);
    ctx.fill();
    drawLine(points[i], points[i - 1], Math.max(2, Math.floor(width / 3)), rgba(ridge, 1));
  }
  const head = points[0];
  const neck = points[1];
  const dx = head.x - neck.x;
  const dy = head.y - neck.y;
  const length = Math.max(1, Math.hypot(dx, dy));
  const ux = dx / length;
  const uy = dy / length;
  const px = -uy;
  const py = ux;
  const angle = Math.atan2(uy, ux);
  const headColor = [94 + 96 * glowStrength, 120 + 104 * glowStrength, 92 + 120 * glowStrength];
  if (glowStrength > 0) drawGlow(head.x, head.y, 22, rgba(glowColor, 0.45));
  ctx.fillStyle = rgba(headColor, 1);
  ctx.beginPath();
  ctx.moveTo(head.x - ux * 2 + px * 6, head.y - uy * 2 + py * 6);
  ctx.lineTo(head.x + ux * 7 + px * 5, head.y + uy * 7 + py * 5);
  ctx.lineTo(head.x + ux * 7 - px * 5, head.y + uy * 7 - py * 5);
  ctx.lineTo(head.x - ux * 2 - px * 6, head.y - uy * 2 - py * 6);
  ctx.closePath();
  ctx.fill();
  ctx.save();
  ctx.translate(head.x + ux * 1.5, head.y + uy * 1.5);
  ctx.rotate(angle);
  ctx.fillStyle = rgba(headColor, 1);
  ctx.strokeStyle = "rgb(60,82,64)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.ellipse(16, 12, 12, 7, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = "rgba(24,34,30,1)";
  ctx.beginPath();
  ctx.arc(21, 10, 1.2, 0, Math.PI * 2);
  ctx.arc(21, 14, 1.2, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

function drawFood() {
  if (!state.game.food) return;
  const { pos, def } = state.game.food;
  const p = pointForCell(pos);
  drawGlow(p.x, p.y, 18, rgba(def.glow_color, 0.35));
  ctx.fillStyle = rgba(def.color, 1);
  ctx.beginPath();
  ctx.arc(p.x, p.y, 7, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#fff";
  ctx.beginPath();
  ctx.arc(p.x - 2, p.y - 2, 2, 0, Math.PI * 2);
  ctx.fill();
}

function drawItem() {
  if (!state.game.item) return;
  const { pos, def } = state.game.item;
  const p = pointForCell(pos);
  drawGlow(p.x, p.y, 20, rgba(def.glow_color, 0.32));
  drawIcon(def.icon_id, p.x, p.y, def.color, 10 + Math.sin(state.titlePhase * 4) * 1.6);
}

function drawTopHud() {
  const left = { x: BOARD_RECT.x, y: BOARD_RECT.y - 76 };
  const right = { x: BOARD_RECT.x + BOARD_RECT.width, y: BOARD_RECT.y - 76 };
  drawIcon("diamond", left.x - 16, left.y + 28, [255, 214, 92], 8);
  drawText("SCORE", left.x, left.y, 16, "#859ec4", "left", 500);
  drawText(String(state.game.score), left.x, left.y + 34, 26, "#f4f7ff", "left", 700);
  drawText("RECORD", right.x, right.y, 16, "#859ec4", "right", 500);
  drawText(String(state.bestScore), right.x, right.y + 34, 26, "#f4f7ff", "right", 700);
  drawText("Snake Cosmos", BOARD_RECT.x + BOARD_RECT.width / 2, BOARD_RECT.y - 48, 28, "#68dcff", "center", 700, "Georgia");
}

function drawBottomHud() {
  const bar = { x: BOARD_RECT.x, y: BOARD_RECT.y + BOARD_RECT.height + 18, width: BOARD_RECT.width, height: 22 };
  roundRect(bar.x, bar.y, bar.width, bar.height, 10, "#12182c", "#6088ba");
  roundRect(bar.x, bar.y, Math.max(1, bar.width * (state.game.sprintMeter / state.game.maxSprint)), bar.height, 10, state.game.sprintLocked ? "#8c98a8" : "#52beff");
  drawIcon("spark", bar.x + bar.width / 2 - 42, bar.y + bar.height / 2, [98, 220, 255], 8);
  drawText("SPRINT", bar.x + bar.width / 2, bar.y + bar.height / 2 + 6, 16, "#f0f8ff", "center", 700);
  let info = `Energy ${String(Math.floor(state.game.sprintMeter)).padStart(2, "0")}/${Math.floor(state.game.maxSprint)}`;
  if (state.game.sprintLocked) info = `Locked | recover to ${Math.floor(state.game.maxSprint * state.game.sprintRestartThresholdRatio)}`;
  else if (state.game.sprintActive) info += " | boost online";
  drawText(info, bar.x + bar.width / 2, bar.y + 42, 16, "#dfe7f8", "center", 500);
  drawEffects();
}

function drawEffects() {
  const y = BOARD_RECT.y + BOARD_RECT.height + 56;
  if (!state.game.effects.length) {
    drawText("No active effects", BOARD_RECT.x, y + 18, 16, "#94a6c6", "left", 500);
    return;
  }
  state.game.effects.slice(0, 5).forEach((effect, index) => {
    const x = BOARD_RECT.x + index * 98;
    roundRect(x, y, 86, 76, 18, "#0f1628", rgba(effect.glow_color, 1));
    drawIcon(effect.icon_id, x + 43, y + 24, effect.color, 10);
    drawText(effect.short_label.slice(0, 8), x + 43, y + 50, 14, "#c4d2e8", "center", 500);
    drawText(`${effect.remaining.toFixed(1)}s`, x + 43, y + 67, 14, "#f5f7ff", "center", 700);
  });
}

function drawParticles() {
  for (const p of state.particles) {
    ctx.fillStyle = rgba(p.color, p.life / p.maxLife);
    ctx.beginPath();
    ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
    ctx.fill();
  }
  for (const item of state.floatingTexts) {
    drawIcon(item.iconId, item.x - 12, item.y, item.color, 8, item.life / item.maxLife);
    drawText(item.text, item.x + 4, item.y - 4, 16, rgba(item.color, item.life / item.maxLife), "left", 700);
  }
}

function drawOverlay() {
  ctx.fillStyle = "rgba(5,8,18,0.5)";
  ctx.fillRect(0, 0, WINDOW.width, WINDOW.height);
}

function drawMenuPanel(title, items, footer) {
  const height = items.length <= 3 ? 300 : 360;
  const x = BOARD_RECT.x + BOARD_RECT.width / 2 - 210;
  const y = BOARD_RECT.y + BOARD_RECT.height / 2 - height / 2;
  roundRect(x, y, 420, height, 28, "#0b1022", "#547ec4");
  drawText(title, x + 210, y + 54, 42, "#ffffff", "center", 700);
  items.forEach(([label], index) => {
    const rowY = y + 100 + index * 44;
    if (index === state.menuIndex) roundRect(x + 24, rowY - 4, 372, 34, 16, "#22365a");
    drawText(label, x + 210, rowY + 20, 24, index === state.menuIndex ? "#ffffff" : "#9eb4d6", "center", 700);
  });
  drawText(footer, x + 210, y + height - 20, 16, "#b2c5e2", "center", 500);
}

function drawOptionsPanel() {
  const x = BOARD_RECT.x + BOARD_RECT.width / 2 - 260;
  const y = BOARD_RECT.y + BOARD_RECT.height / 2 - 270;
  roundRect(x, y, 520, 540, 28, "#0c1224", "#5882c6");
  drawText("Options", x + 260, y + 54, 42, "#fff", "center", 700);
  optionsItems().forEach(([_, label], index) => {
    const rowY = y + 84 + index * 34;
    if (index === state.optionsIndex) roundRect(x + 18, rowY - 4, 484, 28, 14, "#22365a");
    drawText(label, x + 28, rowY + 15, 16, index === state.optionsIndex ? "#fff" : "#a0b6d7", "left", 500);
  });
  if (state.rebindingAction) drawText(`Press a key for ${state.rebindingAction.toUpperCase()} | Esc cancels`, x + 260, y + 512, 16, "#ffd48c", "center", 500);
}

function drawItemsCodex() {
  const x = BOARD_RECT.x + BOARD_RECT.width / 2 - 320;
  const y = BOARD_RECT.y + BOARD_RECT.height / 2 - 205;
  roundRect(x, y, 640, 410, 28, "#0c1224", "#5882c6");
  drawText("Items Codex", x + 320, y + 54, 42, "#fff", "center", 700);
  drawText("Esc returns", x + 320, y + 78, 16, "#adc2e6", "center", 500);
  state.items.forEach((item, index) => {
    const rowY = y + 98 + index * 66;
    roundRect(x + 24, rowY, 592, 54, 18, "#12182c", rgba(item.glow_color, 1));
    drawIcon(item.icon_id, x + 52, rowY + 27, item.color, 11);
    drawText(item.label, x + 78, rowY + 22, 22, "#fff", "left", 700);
    drawText(item.description, x + 78, rowY + 42, 15, "#c4d4ec", "left", 500);
    drawText(`${item.duration.toFixed(0)}s | +${Math.floor(item.instant_sprint)} sprint`, x + 604, rowY + 28, 16, "#a4b6d2", "right", 500);
  });
}

function drawStartPrompt() {
  drawText("Press a direction to launch", WINDOW.width / 2, WINDOW.height / 2 + 132, 16, "#b8d0ee", "center", 700);
}

function roundRect(x, y, width, height, radius, fill, stroke = null) {
  roundRectPath(x, y, width, height, radius);
  ctx.fillStyle = fill;
  ctx.fill();
  if (stroke) {
    ctx.strokeStyle = stroke;
    ctx.lineWidth = 2;
    ctx.stroke();
  }
}

function roundRectPath(x, y, width, height, radius) {
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.arcTo(x + width, y, x + width, y + height, radius);
  ctx.arcTo(x + width, y + height, x, y + height, radius);
  ctx.arcTo(x, y + height, x, y, radius);
  ctx.arcTo(x, y, x + width, y, radius);
  ctx.closePath();
}

function drawGlow(x, y, radius, color) {
  const gradient = ctx.createRadialGradient(x, y, 0, x, y, radius);
  gradient.addColorStop(0, color);
  gradient.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = gradient;
  ctx.beginPath();
  ctx.arc(x, y, radius, 0, Math.PI * 2);
  ctx.fill();
}

function drawLine(a, b, width, color) {
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.lineCap = "round";
  ctx.beginPath();
  ctx.moveTo(a.x, a.y);
  ctx.lineTo(b.x, b.y);
  ctx.stroke();
}

function drawText(text, x, y, size, color, align = "left", weight = 500, family = "Avenir Next, Segoe UI, Trebuchet MS, sans-serif") {
  ctx.font = `${weight} ${size}px ${family}`;
  ctx.textAlign = align;
  ctx.fillStyle = color;
  ctx.fillText(text, x, y);
}

function drawIcon(iconId, x, y, color, size, alpha = 1) {
  ctx.save();
  ctx.translate(x, y);
  ctx.fillStyle = rgba(color, alpha);
  ctx.strokeStyle = rgba(color, alpha);
  ctx.lineWidth = 3;
  if (iconId === "spark") {
    ctx.beginPath();
    ctx.moveTo(0, -size);
    ctx.lineTo(size * 0.35, -size * 0.25);
    ctx.lineTo(size, 0);
    ctx.lineTo(size * 0.35, size * 0.25);
    ctx.lineTo(0, size);
    ctx.lineTo(-size * 0.35, size * 0.25);
    ctx.lineTo(-size, 0);
    ctx.lineTo(-size * 0.35, -size * 0.25);
    ctx.closePath();
    ctx.fill();
  } else if (iconId === "diamond") {
    ctx.beginPath();
    ctx.moveTo(0, -size);
    ctx.lineTo(size, 0);
    ctx.lineTo(0, size);
    ctx.lineTo(-size, 0);
    ctx.closePath();
    ctx.fill();
  } else if (iconId === "halo") {
    ctx.beginPath();
    ctx.arc(0, 0, size, 0, Math.PI * 2);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(0, 0, Math.max(2, size / 3), 0, Math.PI * 2);
    ctx.fill();
  } else if (iconId === "hourglass") {
    ctx.beginPath();
    ctx.moveTo(-size, -size);
    ctx.lineTo(size, -size);
    ctx.lineTo(3, -2);
    ctx.lineTo(-3, -2);
    ctx.closePath();
    ctx.fill();
    ctx.beginPath();
    ctx.moveTo(-size, size);
    ctx.lineTo(size, size);
    ctx.lineTo(3, 2);
    ctx.lineTo(-3, 2);
    ctx.closePath();
    ctx.fill();
    ctx.beginPath();
    ctx.moveTo(-2, -2);
    ctx.lineTo(2, 2);
    ctx.moveTo(2, -2);
    ctx.lineTo(-2, 2);
    ctx.stroke();
  }
  ctx.restore();
}

function menuItems() {
  if (state.scene === SCENE.TITLE) {
    return [
      ["Start Mission", "start"],
      ["Items Codex", "codex"],
      ["Options", "options"],
      ["Quit", "quit"],
    ];
  }
  if (state.scene === SCENE.PAUSED) {
    return [
      ["Resume", "resume"],
      ["Items Codex", "codex"],
      ["Options", "options"],
      ["Restart", "restart"],
      ["Main Menu", "menu"],
    ];
  }
  return [
    ["Retry", "restart"],
    ["Main Menu", "menu"],
    ["Quit", "quit"],
  ];
}

function optionsItems() {
  const s = state.settings;
  const keys = s.keybinds;
  return [
    ["masterVolume", `Master Volume     ${Math.round(s.masterVolume * 100).toString().padStart(3, " ")}%`],
    ["musicVolume", `Music Volume      ${Math.round(s.musicVolume * 100).toString().padStart(3, " ")}%`],
    ["sfxVolume", `SFX Volume        ${Math.round(s.sfxVolume * 100).toString().padStart(3, " ")}%`],
    ["up", `Move Up           ${keys.up.replace("Key", "")}`],
    ["down", `Move Down         ${keys.down.replace("Key", "")}`],
    ["left", `Move Left         ${keys.left.replace("Key", "")}`],
    ["right", `Move Right        ${keys.right.replace("Key", "")}`],
    ["sprint", `Sprint            ${keys.sprint === "Space" ? "SPACE" : keys.sprint.replace("Key", "")}`],
    ["back", "Back"],
  ];
}

function activateMenu(action) {
  if (action === "start") {
    state.game.reset();
    state.scene = SCENE.PLAYING;
    state.menuIndex = 0;
  } else if (action === "codex") {
    state.returnScene = state.scene;
    state.scene = SCENE.ITEMS;
  } else if (action === "options") {
    state.returnScene = state.scene;
    state.scene = SCENE.OPTIONS;
    state.optionsIndex = 0;
  } else if (action === "quit") {
    state.scene = SCENE.TITLE;
  } else if (action === "resume") {
    state.scene = SCENE.PLAYING;
  } else if (action === "restart") {
    state.game.reset();
    state.scene = SCENE.PLAYING;
  } else if (action === "menu") {
    state.scene = SCENE.TITLE;
  }
  state.audio.play("menu_select");
}

function adjustOption(id, direction) {
  const s = state.settings;
  const delta = 0.05 * direction;
  if (id === "masterVolume") s.masterVolume = clamp(s.masterVolume + delta, 0, 1);
  else if (id === "musicVolume") s.musicVolume = clamp(s.musicVolume + delta, 0, 1);
  else if (id === "sfxVolume") s.sfxVolume = clamp(s.sfxVolume + delta, 0, 1);
  saveWebState();
  state.audio.play("menu_move");
}

function onKeyDown(event) {
  state.audio.ensureContext();
  state.inputDown.add(event.code);
  if (state.rebindingAction) {
    if (event.code === "Escape") {
      state.rebindingAction = null;
      return;
    }
    state.settings.keybinds[state.rebindingAction] = event.code;
    state.rebindingAction = null;
    saveWebState();
    state.audio.play("menu_select");
    return;
  }
  if (state.scene === SCENE.PLAYING) {
    const dirs = {
      [state.settings.keybinds.up]: { x: 0, y: -1 },
      [state.settings.keybinds.down]: { x: 0, y: 1 },
      [state.settings.keybinds.left]: { x: -1, y: 0 },
      [state.settings.keybinds.right]: { x: 1, y: 0 },
    };
    if (dirs[event.code]) {
      state.game.enqueueDirection(dirs[event.code]);
      return;
    }
    if (event.code === "Escape" || event.code === "KeyP") {
      state.audio.play("menu_select");
      state.scene = SCENE.PAUSED;
      state.menuIndex = 0;
    }
    return;
  }
  if (state.scene === SCENE.ITEMS) {
    if (event.code === "Escape" || event.code === "Enter" || event.code === "Space") {
      state.audio.play("menu_select");
      state.scene = state.returnScene;
      state.menuIndex = 0;
    }
    return;
  }
  if (state.scene === SCENE.OPTIONS) {
    const items = optionsItems();
    if (event.code === "ArrowUp" || event.code === "KeyW") {
      state.optionsIndex = mod(state.optionsIndex - 1, items.length);
      state.audio.play("menu_move");
    } else if (event.code === "ArrowDown" || event.code === "KeyS") {
      state.optionsIndex = mod(state.optionsIndex + 1, items.length);
      state.audio.play("menu_move");
    } else if (event.code === "ArrowLeft" || event.code === "KeyA") {
      adjustOption(items[state.optionsIndex][0], -1);
    } else if (event.code === "ArrowRight" || event.code === "KeyD") {
      adjustOption(items[state.optionsIndex][0], 1);
    } else if (event.code === "Enter" || event.code === "Space") {
      const current = items[state.optionsIndex][0];
      if (current === "back") state.scene = state.returnScene;
      else if (ACTIONS.includes(current)) state.rebindingAction = current;
      else adjustOption(current, 1);
      state.audio.play("menu_select");
    } else if (event.code === "Escape") {
      state.scene = state.returnScene;
      state.audio.play("menu_select");
    }
    saveWebState();
    return;
  }
  const items = menuItems();
  if (event.code === "ArrowUp" || event.code === "KeyW") {
    state.menuIndex = mod(state.menuIndex - 1, items.length);
    state.audio.play("menu_move");
  } else if (event.code === "ArrowDown" || event.code === "KeyS") {
    state.menuIndex = mod(state.menuIndex + 1, items.length);
    state.audio.play("menu_move");
  } else if (event.code === "Enter" || event.code === "Space") {
    activateMenu(items[state.menuIndex][1]);
  } else if (event.code === "Escape") {
    if (state.scene === SCENE.PAUSED) {
      state.audio.play("menu_select");
      state.scene = SCENE.PLAYING;
    } else if (state.scene === SCENE.GAME_OVER) {
      state.audio.play("menu_select");
      state.scene = SCENE.TITLE;
    }
  } else if (event.code === "KeyP" && state.scene === SCENE.PAUSED) {
    state.audio.play("menu_select");
    state.scene = SCENE.PLAYING;
  }
}

function onKeyUp(event) {
  state.inputDown.delete(event.code);
}

function render() {
  drawBackground();
  drawBoardShell();
  drawBoard();
  drawTopHud();
  drawBottomHud();
  drawParticles();
  if (state.scene === SCENE.TITLE) {
    drawOverlay();
    drawMenuPanel("Snake Cosmos", menuItems(), "Press Enter to begin");
  } else if (state.scene === SCENE.PAUSED) {
    drawOverlay();
    drawMenuPanel("Paused", menuItems(), "Esc or P resumes");
  } else if (state.scene === SCENE.GAME_OVER) {
    drawOverlay();
    drawMenuPanel("Signal Lost", menuItems(), `Score ${state.game.score} | Best ${state.bestScore}`);
  } else if (state.scene === SCENE.OPTIONS) {
    drawOverlay();
    drawOptionsPanel();
  } else if (state.scene === SCENE.ITEMS) {
    drawOverlay();
    drawItemsCodex();
  }
}

function tick(now) {
  const dt = Math.min(0.05, (now - state.lastFrame) / 1000);
  state.lastFrame = now;
  update(dt);
  render();
  requestAnimationFrame(tick);
}

async function bootstrap() {
  loadWebState();
  const [foods, items] = await Promise.all([
    fetch("./content/foods.json").then((res) => res.json()),
    fetch("./content/items.json").then((res) => res.json()),
  ]);
  state.foods = foods;
  state.items = items;
  state.game = new SnakeGame(foods, items);
  state.audio = new WebAudioBank();
  setupDecor();
  window.addEventListener("keydown", onKeyDown);
  window.addEventListener("keyup", onKeyUp);
  requestAnimationFrame((now) => {
    state.lastFrame = now;
    tick(now);
  });
}

bootstrap();
