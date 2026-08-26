export const CLOUD_GAME_WIDTH = 360;
export const CLOUD_GAME_HEIGHT = 520;
export const CLOUD_PLAYER_WIDTH = 42;
export const CLOUD_PLAYER_HEIGHT = 34;

export const GRAVITY = 1040;
export const JUMP_VELOCITY = -485;
export const MOVE_SPEED = 220;
export const MOVE_RESPONSE = 12;
export const BOOST_MULTIPLIER = 1.5;
export const DPR_CAP = 2.5;
export const MAX_DIFFICULTY_HEIGHT = 1400;
export const MOVING_SPEED_CAP = 24;
export const MAX_JUMP_HEIGHT = (JUMP_VELOCITY * JUMP_VELOCITY) / (2 * GRAVITY);
export const SAFE_VERTICAL_REACH = MAX_JUMP_HEIGHT * 0.76;
export const BOOST_MAX_JUMP_HEIGHT = ((JUMP_VELOCITY * BOOST_MULTIPLIER) ** 2) / (2 * GRAVITY);
export const BOOST_SAFE_VERTICAL_REACH = BOOST_MAX_JUMP_HEIGHT * 0.72;
export const VISIBLE_PLATFORM_TARGET = { minimum: 4, maximum: 6 } as const;

const CAMERA_LINE = 215;
const START_Y = 430;
const PLATFORM_GENERATION_TOP = -65;
const DISAPPEAR_DELAY_SECONDS = 0.82;
const BOOST_CHALLENGE_MIN_HEIGHT = 900;
export const BOOST_CHALLENGE_CHANCE = 0.1;

export type Direction = -1 | 0 | 1;
export type PlatformKind = "normal" | "moving" | "disappearing" | "boost";
export type PlatformSide = "left" | "center" | "right";
export type BoostRoutePhase = "entry" | "target" | "continuation";
export type Platform = {
  id: number;
  x: number;
  y: number;
  width: number;
  kind: PlatformKind;
  mandatory: boolean;
  originX?: number;
  moveRange?: number;
  moveSpeed?: number;
  moveDirection?: Direction;
  disappearStartedAt?: number;
  opacity?: number;
  side?: PlatformSide;
  pathSides?: PlatformSide[];
  boostRoutePhase?: BoostRoutePhase;
};
export type CloudPlayer = { x: number; y: number; vx: number; vy: number };
export type CloudGameState = {
  player: CloudPlayer;
  platforms: Platform[];
  height: number;
  jumps: number;
  boostsUsed: number;
  boostEffectSeconds: number;
  elapsedSeconds: number;
  scrollOffset: number;
  nextPlatformId: number;
  status: "running" | "fallen" | "finished";
};

export type CloudGameMetadata = {
  game: "air_cloud_jump";
  height: number;
  best_height: number;
  jumps: number;
  duration_seconds: number;
  boosts_used: number;
};

export type CanvasBitmap = {
  cssWidth: number;
  cssHeight: number;
  bitmapWidth: number;
  bitmapHeight: number;
  dpr: number;
  scaleX: number;
  scaleY: number;
};

export function difficultyAtHeight(height: number): number {
  return clamp(height / MAX_DIFFICULTY_HEIGHT, 0, 1);
}

export function platformMechanicProbabilities(height: number) {
  const difficulty = difficultyAtHeight(height);
  return {
    moving: height < 400 ? 0 : 0.15 + difficulty * 0.12,
    disappearing: height < 700 ? 0 : 0.07 + difficulty * 0.09,
    boost: height < 900 ? 0 : Math.min(0.12, 0.05 + difficulty * 0.07),
  };
}

export function canvasBitmapSize(
  cssWidth: number,
  cssHeight: number,
  devicePixelRatio: number,
): CanvasBitmap {
  const dpr = clamp(devicePixelRatio || 1, 1, DPR_CAP);
  return {
    cssWidth,
    cssHeight,
    bitmapWidth: Math.max(1, Math.round(cssWidth * dpr)),
    bitmapHeight: Math.max(1, Math.round(cssHeight * dpr)),
    dpr,
    scaleX: Math.max(1, Math.round(cssWidth * dpr)) / CLOUD_GAME_WIDTH,
    scaleY: Math.max(1, Math.round(cssHeight * dpr)) / CLOUD_GAME_HEIGHT,
  };
}

export function calculateGameStageHeight(
  viewportHeight: number,
  stageTop: number,
  bottomBoundary: number,
): number {
  const available = Math.max(240, bottomBoundary - stageTop - 8);
  const ratioCap = viewportHeight * 0.64;
  return Math.round(clamp(Math.min(available, ratioCap), 240, 560));
}

export function createCloudGame(): CloudGameState {
  const normal = (id: number, x: number, y: number, width: number): Platform => ({
    id, x, y, width, kind: "normal", mandatory: true, side: platformSide(x, width),
  });
  const platforms: Platform[] = [
    normal(1, 112, 482, 136),
    normal(2, 36, 397, 122),
    normal(3, 199, 316, 116),
    normal(4, 82, 237, 112),
  ];
  return {
    player: { x: 159, y: START_Y, vx: 0, vy: JUMP_VELOCITY },
    platforms,
    height: 0,
    jumps: 1,
    boostsUsed: 0,
    boostEffectSeconds: 0,
    elapsedSeconds: 0,
    scrollOffset: 0,
    nextPlatformId: 5,
    status: "running",
  };
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.max(minimum, Math.min(maximum, value));
}

export function jumpAirTime(verticalGap: number, jumpVelocity = Math.abs(JUMP_VELOCITY)): number {
  const discriminant = Math.max(0, jumpVelocity * jumpVelocity - 2 * GRAVITY * verticalGap);
  return (jumpVelocity + Math.sqrt(discriminant)) / GRAVITY;
}

export function safeHorizontalTravel(verticalGap: number, jumpVelocity = Math.abs(JUMP_VELOCITY)): number {
  const controllableTime = Math.max(0, jumpAirTime(verticalGap, jumpVelocity) - 0.12);
  return MOVE_SPEED * controllableTime * 0.72;
}

export function isReachablePlatform(from: Platform, to: Platform, boosted = false): boolean {
  const verticalGap = from.y - to.y;
  const jumpVelocity = Math.abs(JUMP_VELOCITY) * (boosted ? BOOST_MULTIPLIER : 1);
  const verticalReach = boosted ? BOOST_SAFE_VERTICAL_REACH : SAFE_VERTICAL_REACH;
  if (verticalGap < 38 || verticalGap > verticalReach) return false;
  if (to.width < 68 || to.x < 0 || to.x + to.width > CLOUD_GAME_WIDTH) return false;
  const horizontalGap = Math.max(0, to.x - (from.x + from.width), from.x - (to.x + to.width));
  return horizontalGap <= safeHorizontalTravel(verticalGap, jumpVelocity);
}

export function platformSide(x: number, width: number): PlatformSide {
  const center = x + width / 2;
  if (center < CLOUD_GAME_WIDTH * 0.4) return "left";
  if (center > CLOUD_GAME_WIDTH * 0.6) return "right";
  return "center";
}

function nextSide(previous: Platform, random: () => number): PlatformSide {
  const history = previous.pathSides ?? [previous.side ?? platformSide(previous.x, previous.width)];
  const last = history.at(-1) ?? "center";
  const sameTail = history.slice(-3).filter(side => side === last).length;
  const roll = random();
  if (sameTail >= 2) return last === "right" ? "left" : "right";
  if (last === "left") return roll < 0.68 ? "right" : roll < 0.88 ? "center" : "left";
  if (last === "right") return roll < 0.68 ? "left" : roll < 0.88 ? "center" : "right";
  return roll < 0.45 ? "left" : roll < 0.9 ? "right" : "center";
}

function xForSide(side: PlatformSide, width: number, random: () => number): number {
  const margin = 8;
  const min = side === "left" ? margin : side === "center" ? 112 - width / 2 : 220;
  const max = side === "left" ? 122 - width / 2 : side === "center" ? 248 - width / 2 : CLOUD_GAME_WIDTH - width - margin;
  return clamp(min + random() * Math.max(0, max - min), margin, CLOUD_GAME_WIDTH - width - margin);
}

function pathHistory(previous: Platform, side: PlatformSide): PlatformSide[] {
  return [...(previous.pathSides ?? [previous.side ?? platformSide(previous.x, previous.width)]), side].slice(-3);
}

function makeBoostTarget(previous: Platform, id: number, random: () => number): Platform {
  const width = 108;
  const gap = clamp(
    SAFE_VERTICAL_REACH + 18 + random() * 22,
    SAFE_VERTICAL_REACH + 10,
    BOOST_SAFE_VERTICAL_REACH * 0.82,
  );
  const side = nextSide(previous, random);
  const desiredX = xForSide(side, width, random);
  const boostedTravel = safeHorizontalTravel(gap, Math.abs(JUMP_VELOCITY) * BOOST_MULTIPLIER);
  const maxGap = Math.max(0, boostedTravel - 10);
  const x = clamp(
    desiredX,
    previous.x - width - maxGap,
    previous.x + previous.width + maxGap,
  );
  const boundedX = clamp(x, 8, CLOUD_GAME_WIDTH - width - 8);
  return {
    id,
    x: boundedX,
    y: previous.y - gap,
    width,
    kind: "normal",
    mandatory: true,
    side: platformSide(boundedX, width),
    pathSides: pathHistory(previous, platformSide(boundedX, width)),
    boostRoutePhase: "target",
  };
}

export function generateNextReachablePlatform(
  previous: Platform,
  height: number,
  id: number,
  random: () => number = Math.random,
): Platform {
  if (previous.boostRoutePhase === "entry") return makeBoostTarget(previous, id, random);
  const difficulty = difficultyAtHeight(height);
  for (let attempt = 0; attempt < 18; attempt += 1) {
    const narrowLoad = difficulty * (0.55 + random() * 0.45);
    const width = Math.round(130 - narrowLoad * 30 + random() * 8);
    const verticalLoad = difficulty * (0.48 + random() * 0.52);
    let gap = 72 + verticalLoad * 8 + random() * 5;
    if (width < 102) gap -= 5;
    gap = clamp(gap, 69, SAFE_VERTICAL_REACH - 5);

    const side = nextSide(previous, random);
    const sideX = xForSide(side, width, random);
    const previousCenter = previous.x + previous.width / 2;
    const meaningful = 50 + difficulty * 12;
    let targetCenter = sideX + width / 2;
    if (Math.abs(targetCenter - previousCenter) < meaningful) {
      const direction = targetCenter >= previousCenter ? 1 : -1;
      targetCenter = previousCenter + direction * meaningful;
    }
    const compensation = 1 - verticalLoad * 0.25 - Math.max(0, 104 - width) / 180;
    const maxCenterOffset = 64 + difficulty * 24 * compensation;
    targetCenter = clamp(targetCenter, previousCenter - maxCenterOffset, previousCenter + maxCenterOffset);
    const x = clamp(targetCenter - width / 2, 8, CLOUD_GAME_WIDTH - width - 8);
    const actualSide = platformSide(x, width);
    const boostEntry = height >= BOOST_CHALLENGE_MIN_HEIGHT
      && previous.boostRoutePhase === undefined
      && random() < BOOST_CHALLENGE_CHANCE;
    const candidate: Platform = {
      id,
      x,
      y: previous.y - gap,
      width,
      kind: boostEntry ? "boost" : "normal",
      mandatory: true,
      side: actualSide,
      pathSides: pathHistory(previous, actualSide),
      boostRoutePhase: boostEntry ? "entry" : previous.boostRoutePhase === "target" ? "continuation" : undefined,
    };
    if (isReachablePlatform(previous, candidate)) return candidate;
  }

  const width = 116;
  return {
    id,
    x: clamp(previous.x + previous.width / 2 - width / 2, 8, CLOUD_GAME_WIDTH - width - 8),
    y: previous.y - 68,
    width,
    kind: "normal",
    mandatory: true,
    side: platformSide(previous.x + previous.width / 2 - width / 2, width),
    pathSides: pathHistory(previous, platformSide(previous.x + previous.width / 2 - width / 2, width)),
    boostRoutePhase: previous.boostRoutePhase === "target" ? "continuation" : undefined,
  };
}

function generateOptionalPlatform(
  lower: Platform,
  upper: Platform,
  height: number,
  id: number,
  random: () => number,
): Platform | null {
  const probabilities = platformMechanicProbabilities(height);
  const roll = random();
  const optionalChance = Math.min(0.24, probabilities.moving + probabilities.disappearing);
  if (roll >= optionalChance) return null;
  const kind: PlatformKind | null = roll < probabilities.moving * 0.58
    ? "moving"
    : roll < optionalChance
      ? "disappearing"
      : null;
  if (!kind) return null;
  const width = kind === "moving" ? 100 : 96;
  const x = clamp((lower.x + upper.x) / 2 + (random() * 2 - 1) * 72, 8, CLOUD_GAME_WIDTH - width - 8);
  const platform: Platform = {
    id,
    x,
    y: upper.y + (lower.y - upper.y) * (0.38 + random() * 0.18),
    width,
    kind,
    mandatory: false,
  };
  if (kind === "moving") {
    const travelMin = CLOUD_GAME_WIDTH * (0.12 + random() * 0.04);
    const travelMax = CLOUD_GAME_WIDTH * (0.8 + random() * 0.06) - width;
    platform.originX = (travelMin + travelMax) / 2;
    platform.x = platform.originX;
    platform.moveRange = Math.max(48, (travelMax - travelMin) / 2);
    platform.moveSpeed = Math.min(MOVING_SPEED_CAP, 15 + difficultyAtHeight(height) * 7 + random() * 2);
    platform.moveDirection = random() < 0.5 ? -1 : 1;
  }
  return platform;
}

function generatePlatforms(
  platforms: Platform[],
  nextId: number,
  height: number,
  random: () => number,
): { platforms: Platform[]; nextId: number } {
  const result = [...platforms];
  let top = result.filter(platform => platform.mandatory)
    .reduce((winner, item) => item.y < winner.y ? item : winner);
  let id = nextId;
  while (
    top.y > PLATFORM_GENERATION_TOP
    && result.filter(platform => platform.mandatory && platform.y >= -20 && platform.y <= CLOUD_GAME_HEIGHT + 20).length < 5
  ) {
    const next = generateNextReachablePlatform(top, height, id, random);
    id += 1;
    const visibleCount = result.filter(platform => platform.y >= -20 && platform.y <= CLOUD_GAME_HEIGHT + 20).length;
    const optional = visibleCount < VISIBLE_PLATFORM_TARGET.maximum - 1
      ? generateOptionalPlatform(top, next, height, id, random)
      : null;
    if (optional) { result.push(optional); id += 1; }
    result.push(next);
    top = next;
  }
  return { platforms: result, nextId: id };
}

export function generateMandatorySequence(count: number, random: () => number): Platform[] {
  const first: Platform = {
    id: 1, x: 112, y: 482, width: 136, kind: "normal", mandatory: true,
  };
  const result = [first];
  for (let index = 1; index < count; index += 1) {
    result.push(generateNextReachablePlatform(result[index - 1], index * 3, index + 1, random));
  }
  return result;
}

export function visibleInteractivePlatformCount(platforms: Platform[]): number {
  return platforms.filter(platform => platform.y >= -20 && platform.y <= CLOUD_GAME_HEIGHT + 20).length;
}

export function movingPlatformTravel(platform: Platform): { minimumX: number; maximumX: number; distance: number } {
  const origin = platform.originX ?? platform.x;
  const range = platform.moveRange ?? 0;
  const minimumX = clamp(origin - range, 0, CLOUD_GAME_WIDTH - platform.width);
  const maximumX = clamp(origin + range, 0, CLOUD_GAME_WIDTH - platform.width);
  return { minimumX, maximumX, distance: maximumX - minimumX };
}

function advancePlatforms(platforms: Platform[], dt: number, elapsed: number): Platform[] {
  return platforms.map(platform => {
    if (platform.kind === "moving") {
      const travel = movingPlatformTravel(platform);
      const speed = Math.min(platform.moveSpeed ?? 0, MOVING_SPEED_CAP);
      let direction = platform.moveDirection ?? 1;
      let x = platform.x + speed * direction * dt;
      if (x > travel.maximumX) { x = travel.maximumX; direction = -1; }
      if (x < travel.minimumX) { x = travel.minimumX; direction = 1; }
      return { ...platform, x, moveDirection: direction as Direction };
    }
    if (platform.kind === "disappearing" && platform.disappearStartedAt !== undefined) {
      const progress = (elapsed - platform.disappearStartedAt) / DISAPPEAR_DELAY_SECONDS;
      return { ...platform, opacity: clamp(1 - progress, 0, 1) };
    }
    return platform;
  }).filter(platform => (platform.opacity ?? 1) > 0);
}

export function stepCloudGame(
  state: CloudGameState,
  deltaSeconds: number,
  direction: Direction,
  random: () => number = Math.random,
): CloudGameState {
  if (state.status !== "running") return state;
  const dt = clamp(deltaSeconds, 0, 0.034);
  const elapsedSeconds = state.elapsedSeconds + dt;
  let platforms = advancePlatforms(state.platforms, dt, elapsedSeconds);
  const targetVx = direction * MOVE_SPEED;
  const response = Math.min(1, MOVE_RESPONSE * dt);
  let vx = state.player.vx + (targetVx - state.player.vx) * response;
  if (direction === 0 && Math.abs(vx) < 2) vx = 0;
  const x = clamp(state.player.x + vx * dt, 0, CLOUD_GAME_WIDTH - CLOUD_PLAYER_WIDTH);
  if (x === 0 || x === CLOUD_GAME_WIDTH - CLOUD_PLAYER_WIDTH) vx = 0;

  const previousBottom = state.player.y + CLOUD_PLAYER_HEIGHT;
  let vy = state.player.vy + GRAVITY * dt;
  let y = state.player.y + vy * dt;
  let jumps = state.jumps;
  let boostsUsed = state.boostsUsed;
  let boostEffectSeconds = Math.max(0, state.boostEffectSeconds - dt);
  if (vy > 0) {
    const nextBottom = y + CLOUD_PLAYER_HEIGHT;
    const landing = platforms.filter(platform =>
      previousBottom <= platform.y + 3
      && nextBottom >= platform.y
      && x + CLOUD_PLAYER_WIDTH >= platform.x + 5
      && x <= platform.x + platform.width - 5
    ).sort((left, right) => left.y - right.y)[0];
    if (landing) {
      y = landing.y - CLOUD_PLAYER_HEIGHT;
      const boosted = landing.kind === "boost";
      vy = JUMP_VELOCITY * (boosted ? BOOST_MULTIPLIER : 1);
      jumps += 1;
      if (boosted) { boostsUsed += 1; boostEffectSeconds = 0.75; }
      if (landing.kind === "disappearing" && landing.disappearStartedAt === undefined) {
        platforms = platforms.map(platform => platform.id === landing.id
          ? { ...platform, disappearStartedAt: elapsedSeconds }
          : platform);
      }
    }
  }

  let scrollOffset = state.scrollOffset;
  if (y < CAMERA_LINE) {
    const shift = CAMERA_LINE - y;
    y = CAMERA_LINE;
    scrollOffset += shift;
    platforms = platforms.map(platform => ({ ...platform, y: platform.y + shift }));
  }
  platforms = platforms.filter(platform => platform.y < CLOUD_GAME_HEIGHT + 90);
  const altitude = Math.max(0, scrollOffset + START_Y - y);
  const height = Math.max(state.height, Math.floor(altitude * 0.82));
  const generated = generatePlatforms(platforms, state.nextPlatformId, height, random);
  return {
    player: { x, y, vx, vy },
    platforms: generated.platforms,
    height,
    jumps,
    boostsUsed,
    boostEffectSeconds,
    elapsedSeconds,
    scrollOffset,
    nextPlatformId: generated.nextId,
    status: y > CLOUD_GAME_HEIGHT + 65 ? "fallen" : "running",
  };
}

export function finishCloudGame(state: CloudGameState): CloudGameState {
  return state.status === "finished" ? state : { ...state, status: "finished" };
}

export function cloudGameMetadata(state: CloudGameState, bestHeight: number): CloudGameMetadata {
  return {
    game: "air_cloud_jump",
    height: Math.max(0, Math.round(state.height)),
    best_height: Math.max(bestHeight, Math.round(state.height)),
    jumps: Math.max(0, state.jumps),
    duration_seconds: Math.max(0, Math.round(state.elapsedSeconds)),
    boosts_used: Math.max(0, state.boostsUsed),
  };
}
