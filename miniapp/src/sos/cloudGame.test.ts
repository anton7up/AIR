import { describe, expect, it } from "vitest";
import {
  BOOST_MULTIPLIER,
  BOOST_CHALLENGE_CHANCE,
  BOOST_SAFE_VERTICAL_REACH,
  CLOUD_GAME_HEIGHT,
  CLOUD_GAME_WIDTH,
  DPR_CAP,
  JUMP_VELOCITY,
  MAX_DIFFICULTY_HEIGHT,
  MAX_JUMP_HEIGHT,
  MOVING_SPEED_CAP,
  SAFE_VERTICAL_REACH,
  VISIBLE_PLATFORM_TARGET,
  calculateGameStageHeight,
  canvasBitmapSize,
  cloudGameMetadata,
  createCloudGame,
  difficultyAtHeight,
  finishCloudGame,
  generateMandatorySequence,
  isReachablePlatform,
  movingPlatformTravel,
  platformSide,
  platformMechanicProbabilities,
  stepCloudGame,
  visibleInteractivePlatformCount,
  type Platform,
} from "./cloudGame";

const fixedRandom = () => 0.5;
const platform = (overrides: Partial<Platform> = {}): Platform => ({
  id: 1, x: 112, y: 482, width: 136, kind: "normal", mandatory: true, ...overrides,
});

function seededRandom(seed = 42): () => number {
  let value = seed >>> 0;
  return () => {
    value = (value * 1664525 + 1013904223) >>> 0;
    return value / 0x100000000;
  };
}

describe("AIR cloud jump physics", () => {
  it("starts with an automatic jump and responds to horizontal controls", () => {
    const initial = createCloudGame();
    const upward = stepCloudGame(initial, 0.016, 0, fixedRandom);
    const right = stepCloudGame(initial, 0.034, 1, fixedRandom);
    const left = stepCloudGame({ ...initial, player: { ...initial.player, vx: 0 } }, 0.034, -1, fixedRandom);
    expect(initial.player.vy).toBeLessThan(0);
    expect(upward.player.y).toBeLessThan(initial.player.y);
    expect(right.player.x).toBeGreaterThan(initial.player.x);
    expect(left.player.x).toBeLessThan(initial.player.x);
  });

  it("lands, scrolls, generates, falls, restarts, and supports manual finish", () => {
    const initial = createCloudGame();
    const landing = stepCloudGame({
      ...initial, player: { x: 150, y: 445, vx: 0, vy: 80 }, jumps: 3,
    }, 0.034, 0, fixedRandom);
    expect(landing.player.vy).toBeLessThan(0);
    expect(landing.jumps).toBe(4);

    const high = { ...initial, player: { x: 160, y: 190, vx: 0, vy: -250 } };
    const scrolled = stepCloudGame(high, 0.034, 0, fixedRandom);
    expect(scrolled.scrollOffset).toBeGreaterThan(0);
    expect(scrolled.nextPlatformId).toBeGreaterThan(high.nextPlatformId);
    expect(scrolled.height).toBeGreaterThan(0);

    const fallen = stepCloudGame({
      ...initial, player: { x: 100, y: CLOUD_GAME_HEIGHT + 66, vx: 0, vy: 200 },
    }, 0.034, 0, fixedRandom);
    expect(fallen.status).toBe("fallen");
    expect(createCloudGame().status).toBe("running");
    expect(finishCloudGame(createCloudGame()).status).toBe("finished");
  });

  it("applies a capped AIR boost and exposes temporary feedback state", () => {
    const initial = createCloudGame();
    const boosted = stepCloudGame({
      ...initial,
      player: { x: 150, y: 445, vx: 0, vy: 80 },
      platforms: [platform({ kind: "boost" })],
    }, 0.034, 0, fixedRandom);
    expect(boosted.player.vy).toBeCloseTo(JUMP_VELOCITY * BOOST_MULTIPLIER);
    expect(BOOST_MULTIPLIER).toBeGreaterThanOrEqual(1.4);
    expect(BOOST_MULTIPLIER).toBeLessThanOrEqual(1.6);
    expect(boosted.boostsUsed).toBe(1);
    expect(boosted.boostEffectSeconds).toBeGreaterThan(0);
  });

  it("starts disappearing only after landing and then removes the cloud", () => {
    const initial = createCloudGame();
    const landed = stepCloudGame({
      ...initial,
      player: { x: 150, y: 445, vx: 0, vy: 80 },
      platforms: [platform({ kind: "disappearing", mandatory: false }), platform({ id: 2, y: 300 })],
    }, 0.034, 0, fixedRandom);
    expect(landed.platforms[0].disappearStartedAt).toBeDefined();
    let later = landed;
    for (let index = 0; index < 12; index += 1) later = stepCloudGame(later, 0.034, 0, fixedRandom);
    expect(later.platforms.some(item => item.id === 1)).toBe(true);
    for (let index = 0; index < 18; index += 1) later = stepCloudGame(later, 0.034, 0, fixedRandom);
    expect(later.platforms.some(item => item.id === 1)).toBe(false);
  });

  it("keeps moving clouds within bounds and below the speed cap", () => {
    let state = {
      ...createCloudGame(),
      platforms: [platform({ kind: "moving", mandatory: false, x: 100, originX: 100, moveRange: 20, moveSpeed: MOVING_SPEED_CAP, moveDirection: 1 }), platform({ id: 2, y: 300 })],
    };
    for (let index = 0; index < 200; index += 1) state = stepCloudGame(state, 0.034, 0, fixedRandom);
    const moving = state.platforms.find(item => item.id === 1);
    if (moving) {
      expect(moving.x).toBeGreaterThanOrEqual(80);
      expect(moving.x).toBeLessThanOrEqual(120);
      expect(moving.moveSpeed).toBeLessThanOrEqual(MOVING_SPEED_CAP);
    }
  });
});

describe("reachable generator and progression", () => {
  it("stress-tests 1500 mandatory platforms without an impossible jump", () => {
    const sequence = generateMandatorySequence(1500, seededRandom());
    expect(sequence).toHaveLength(1500);
    for (let index = 1; index < sequence.length; index += 1) {
      const previous = sequence[index - 1];
      const current = sequence[index];
      const boosted = previous.boostRoutePhase === "entry";
      expect(isReachablePlatform(previous, current, boosted), `jump ${index}`).toBe(true);
      expect(previous.y - current.y).toBeLessThanOrEqual(
        boosted ? BOOST_SAFE_VERTICAL_REACH : SAFE_VERTICAL_REACH,
      );
      expect(current.width).toBeGreaterThanOrEqual(68);
    }
  });

  it("uses physics-based reach and a compensating difficulty budget", () => {
    expect(MAX_JUMP_HEIGHT).toBeGreaterThan(SAFE_VERTICAL_REACH);
    const sequence = generateMandatorySequence(500, seededRandom(7));
    for (let index = 1; index < sequence.length; index += 1) {
      const previous = sequence[index - 1];
      const current = sequence[index];
      const gap = previous.y - current.y;
      const centerOffset = Math.abs(
        previous.x + previous.width / 2 - (current.x + current.width / 2),
      );
      if (current.boostRoutePhase !== "target" && (gap > 75 || current.width < 100)) {
        expect(centerOffset).toBeLessThan(96);
      }
    }
  });

  it("grows difficulty and stops at the hard cap", () => {
    expect(difficultyAtHeight(0)).toBe(0);
    expect(difficultyAtHeight(700)).toBeCloseTo(0.5);
    expect(difficultyAtHeight(MAX_DIFFICULTY_HEIGHT)).toBe(1);
    expect(difficultyAtHeight(MAX_DIFFICULTY_HEIGHT * 3)).toBe(1);
  });

  it("introduces moving, disappearing, and boost mechanics only after thresholds", () => {
    expect(platformMechanicProbabilities(200)).toEqual({ moving: 0, disappearing: 0, boost: 0 });
    expect(platformMechanicProbabilities(500).moving).toBeGreaterThan(0);
    expect(platformMechanicProbabilities(500).disappearing).toBe(0);
    expect(platformMechanicProbabilities(800).disappearing).toBeGreaterThan(0);
    expect(platformMechanicProbabilities(1000).boost).toBeGreaterThan(0);

    const low = stepCloudGame({ ...createCloudGame(), height: 200 }, 0.016, 0, () => 0);
    const moving = stepCloudGame({ ...createCloudGame(), height: 500 }, 0.016, 0, () => 0);
    const disappearing = stepCloudGame({ ...createCloudGame(), height: 800 }, 0.016, 0, () => 0.18);
    const boosted = stepCloudGame({ ...createCloudGame(), height: 1000 }, 0.016, 0, () => 0);
    expect(low.platforms.every(item => item.kind === "normal")).toBe(true);
    expect(moving.platforms.some(item => item.kind === "moving")).toBe(true);
    expect(disappearing.platforms.some(item => item.kind === "disappearing")).toBe(true);
    expect(boosted.platforms.some(item => item.kind === "boost")).toBe(true);
  });

  it("keeps a normal reachable continuation after a boost platform", () => {
    const sequence = generateMandatorySequence(900, seededRandom(99));
    const entryIndex = sequence.findIndex(item => item.boostRoutePhase === "entry");
    expect(entryIndex).toBeGreaterThan(0);
    const before = sequence[entryIndex - 1];
    const entry = sequence[entryIndex];
    const target = sequence[entryIndex + 1];
    const continuation = sequence[entryIndex + 2];
    expect(isReachablePlatform(before, entry)).toBe(true);
    expect(entry.kind).toBe("boost");
    expect(target.boostRoutePhase).toBe("target");
    expect(isReachablePlatform(entry, target)).toBe(false);
    expect(isReachablePlatform(entry, target, true)).toBe(true);
    expect(entry.y - target.y).toBeGreaterThan(SAFE_VERTICAL_REACH);
    expect(entry.y - target.y).toBeLessThanOrEqual(BOOST_SAFE_VERTICAL_REACH * 0.82 + 1);
    expect(continuation.boostRoutePhase).toBe("continuation");
    expect(isReachablePlatform(target, continuation)).toBe(true);
  });

  it("creates meaningful controlled horizontal variety without a rigid alternation", () => {
    const sequence = generateMandatorySequence(1200, seededRandom(2026));
    let meaningful = 0;
    let sideTransitions = 0;
    let oppositeOrCenter = 0;
    let sameSideRun = 1;
    let longestSameSideRun = 1;
    let strictAlternations = 0;
    for (let index = 1; index < sequence.length; index += 1) {
      const previous = sequence[index - 1];
      const current = sequence[index];
      const previousCenter = previous.x + previous.width / 2;
      const currentCenter = current.x + current.width / 2;
      if (Math.abs(currentCenter - previousCenter) >= 40) meaningful += 1;
      const previousSide = platformSide(previous.x, previous.width);
      const currentSide = platformSide(current.x, current.width);
      if (previousSide !== "center") {
        sideTransitions += 1;
        if (currentSide !== previousSide) oppositeOrCenter += 1;
      }
      sameSideRun = currentSide === previousSide ? sameSideRun + 1 : 1;
      longestSameSideRun = Math.max(longestSameSideRun, sameSideRun);
      if ((previousSide === "left" && currentSide === "right") || (previousSide === "right" && currentSide === "left")) strictAlternations += 1;
    }
    expect(meaningful / (sequence.length - 1)).toBeGreaterThan(0.56);
    expect(oppositeOrCenter / sideTransitions).toBeGreaterThan(0.64);
    expect(longestSameSideRun).toBeLessThanOrEqual(4);
    expect(strictAlternations / (sequence.length - 1)).toBeLessThan(0.72);
  });

  it("keeps the visible field sparse", () => {
    let state = { ...createCloudGame(), height: 800 };
    const random = seededRandom(51);
    for (let index = 0; index < 500; index += 1) state = stepCloudGame(state, 0.016, index % 80 < 40 ? 1 : -1, random);
    expect(visibleInteractivePlatformCount(state.platforms)).toBeLessThanOrEqual(VISIBLE_PLATFORM_TARGET.maximum);
    expect(visibleInteractivePlatformCount(createCloudGame().platforms)).toBeGreaterThanOrEqual(VISIBLE_PLATFORM_TARGET.minimum);
  });

  it("uses larger safe vertical gaps without approaching the physical maximum", () => {
    const sequence = generateMandatorySequence(1000, seededRandom(818));
    const ordinaryGaps = sequence.slice(1).flatMap((current, index) => {
      const previous = sequence[index];
      return current.boostRoutePhase === "target" ? [] : [previous.y - current.y];
    });
    const average = ordinaryGaps.reduce((sum, gap) => sum + gap, 0) / ordinaryGaps.length;
    expect(average).toBeGreaterThan(75);
    expect(Math.max(...ordinaryGaps)).toBeLessThanOrEqual(SAFE_VERTICAL_REACH - 2);
  });

  it("shows boost challenges several times in a long post-unlock run without making them routine", () => {
    expect(BOOST_CHALLENGE_CHANCE).toBeGreaterThanOrEqual(0.1);
    expect(BOOST_CHALLENGE_CHANCE).toBeLessThanOrEqual(0.15);
    const sequence = generateMandatorySequence(5000, seededRandom(611));
    const postUnlock = sequence.slice(300);
    const entries = postUnlock.filter(item => item.boostRoutePhase === "entry");
    const frequency = entries.length / postUnlock.length;
    expect(entries.length).toBeGreaterThan(100);
    expect(frequency).toBeGreaterThan(0.03);
    expect(frequency).toBeLessThan(0.08);
    for (const entry of entries) {
      const index = sequence.indexOf(entry);
      expect(isReachablePlatform(sequence[index - 1], entry)).toBe(true);
      expect(isReachablePlatform(entry, sequence[index + 1])).toBe(false);
      expect(isReachablePlatform(entry, sequence[index + 1], true)).toBe(true);
      expect(isReachablePlatform(sequence[index + 1], sequence[index + 2])).toBe(true);
    }
  });

  it("gives generated moving clouds a broad, bounded travel range", () => {
    let moving: Platform | undefined;
    for (let seed = 1; seed < 100 && !moving; seed += 1) {
      const state = stepCloudGame({ ...createCloudGame(), height: 1000 }, 0.016, 0, seededRandom(seed));
      moving = state.platforms.find(item => item.kind === "moving");
    }
    expect(moving).toBeDefined();
    const travel = movingPlatformTravel(moving!);
    expect(travel.distance).toBeGreaterThanOrEqual(CLOUD_GAME_WIDTH * 0.32);
    expect(travel.minimumX).toBeGreaterThanOrEqual(0);
    expect(travel.maximumX + moving!.width).toBeLessThanOrEqual(CLOUD_GAME_WIDTH);
    expect(moving!.moveSpeed).toBeLessThanOrEqual(MOVING_SPEED_CAP);
  });

  it("keeps a clear static route around every generated moving alternative", () => {
    let field: ReturnType<typeof stepCloudGame> | undefined;
    let moving: Platform | undefined;
    for (let seed = 1; seed < 150 && !moving; seed += 1) {
      const candidate = stepCloudGame({ ...createCloudGame(), height: 1000 }, 0.016, 0, seededRandom(seed));
      moving = candidate.platforms.find(item => item.kind === "moving");
      if (moving) field = candidate;
    }
    expect(moving).toBeDefined();
    expect(moving!.mandatory).toBe(false);
    const staticRoute = field!.platforms.filter(item => item.mandatory && item.kind !== "moving");
    expect(staticRoute).toHaveLength(5);
    expect(staticRoute.filter(item => Math.abs(item.y - moving!.y) < 70).length).toBeGreaterThanOrEqual(2);
    expect(visibleInteractivePlatformCount(field!.platforms)).toBeLessThanOrEqual(6);
  });
});

describe("responsive HiDPI canvas", () => {
  it.each([
    [390, 844], [393, 852], [430, 932], [1200, 900],
  ])("fits the game stage inside %sx%s", (width, height) => {
    const stageTop = width < 700 ? 150 : 120;
    const navigationTop = height - 72;
    const stageHeight = calculateGameStageHeight(height, stageTop, navigationTop);
    expect(stageTop + stageHeight).toBeLessThan(navigationTop);
    expect(stageHeight).toBeLessThanOrEqual(height * 0.64 + 1);
  });

  it.each([1, 2, 3])("creates a sharp bitmap at DPR %s", dpr => {
    const bitmap = canvasBitmapSize(390, 500, dpr);
    expect(bitmap.cssWidth).toBe(390);
    expect(bitmap.cssHeight).toBe(500);
    expect(bitmap.bitmapWidth).toBe(Math.round(390 * Math.min(dpr, DPR_CAP)));
    expect(bitmap.bitmapHeight).toBe(Math.round(500 * Math.min(dpr, DPR_CAP)));
    expect(bitmap.scaleX).toBe(bitmap.bitmapWidth / 360);
    expect(bitmap.scaleY).toBe(bitmap.bitmapHeight / 520);
  });

  it("builds compact SOS metadata without reducing a record", () => {
    const state = { ...createCloudGame(), height: 386, jumps: 24, boostsUsed: 2, elapsedSeconds: 47 };
    expect(cloudGameMetadata(state, 742)).toEqual({
      game: "air_cloud_jump",
      height: 386,
      best_height: 742,
      jumps: 24,
      duration_seconds: 47,
      boosts_used: 2,
    });
  });
});
