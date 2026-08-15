/**
 * Pure geometry for the scroll-driven DNA helix.
 *
 * The molecule lies along X (horizontal) and the camera travels down its length
 * as the page scrolls, so the page reads as one continuous move through a
 * molecule rather than a sequence of slides. Four base pairs act as anchors:
 * each one's feature card grows out of it as the camera arrives and fades as
 * the next comes into reach.
 *
 * Kept free of three.js and React so the whole choreography can be verified in
 * Node — see scripts/verify-dna-choreography.mjs.
 */

const TWO_PI = Math.PI * 2;

export const HELIX = {
  LENGTH: 120,               // world units along the X axis
  RADIUS: 2.55,
  TURNS: 9.5,                // full twists across the whole length
  BACKBONE_PER_STRAND: 420,  // dense enough to read as a continuous ribbon
  PAIR_COUNT: 84,
  BEADS_PER_RUNG: 9,         // each base pair is a line of small spheres
  /** Base pairs that anchor the four feature cards, spread down the molecule. */
  ANCHOR_PAIRS: [20, 33, 46, 58],
  /** How close (in world units along X) the camera must be for a card to show. */
  ANCHOR_REACH: 13,
  /** The far tip always scatters into loose spheres; the camera stops short. */
  DISSOLVE_FROM: 42,
  DISSOLVE_SPAN: 26,
  /**
   * Angle between the two strands. Real B-DNA is not symmetric — the strands
   * sit closer together on one side, which is what produces the wide major
   * groove and narrow minor groove. At a flat 180° the helix reads as a
   * generic twisted ladder rather than as DNA.
   */
  GROOVE_OFFSET: Math.PI * 0.78,
  /** Scattered bases that glow like called variants along a genome. */
  HOTSPOT_CUTOFF: 0.88,
  MOTE_COUNT: 130,
};

export function clamp01(value) {
  return Math.min(1, Math.max(0, value));
}

export function easeInOut(t) {
  return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
}

/** Smooth 0→1 ramp between two scroll positions. */
export function ramp(value, from, to) {
  if (to <= from) return value >= to ? 1 : 0;
  return easeInOut(clamp01((value - from) / (to - from)));
}

/** Deterministic pseudo-random in [0,1) — used so the dissolve is testable. */
export function hash(n) {
  const x = Math.sin(n * 127.1 + 311.7) * 43758.5453;
  return x - Math.floor(x);
}

/**
 * Splits scroll progress into the overlapping motions.
 *
 * `travel` is the dominant one: the camera glides along the molecule for most
 * of the page. `unravel` only ever partially opens the helix — fully unwinding
 * it stops reading as DNA.
 */
export function phases(progress) {
  const p = clamp01(progress);
  return {
    approach: ramp(p, 0, 0.18),   // settle in from the establishing shot
    // Travel is deliberately linear: an eased glide slows in the middle and
    // bunches the anchors together, leaving dead scroll at both ends.
    travel: clamp01((p - 0.1) / 0.85),
    unravel: ramp(p, 0.22, 0.82), // strands relax and open
    dissolve: ramp(p, 0.78, 1),   // trailing end scatters a little wider
  };
}

/** World X of a base pair index. */
export function pairX(index) {
  return ((index + 0.5) / HELIX.PAIR_COUNT - 0.5) * HELIX.LENGTH;
}

/** Every scalar the scene needs at a given scroll position. */
export function helixParams(progress) {
  const { approach, travel, unravel, dissolve } = phases(progress);

  // The camera runs from just before the first anchor to just past the last,
  // and always stops short of the dissolving tip.
  const from = pairX(HELIX.ANCHOR_PAIRS[0]) - 12;
  const to = pairX(HELIX.ANCHOR_PAIRS[HELIX.ANCHOR_PAIRS.length - 1]) + 10;
  const cameraX = from + (to - from) * travel;

  return {
    progress: clamp01(progress),
    approach,
    travel,
    unravel,
    dissolve,
    twist: 1 - unravel * 0.55,          // partial: still legibly a helix
    radius: HELIX.RADIUS * (1 + unravel * 0.15),
    separation: unravel * 1.5,          // strands ease apart vertically
    gap: unravel * 0.45,                // bases part in the middle
    cameraX,
    // Eases in from the establishing shot, then holds a steady framing. Kept
    // well back: close in, the near turns balloon and it stops reading as a
    // molecule.
    cameraY: 5.2 - approach * 2.6,
    // Eases back out at the very end so the closing frame isn't a wall of
    // out-of-frame backbone behind the call to action.
    cameraZ: 23 - approach * 4.5 + dissolve * 5,
    cameraLagX: 10,                     // camera trails the point it looks at
    lookAhead: 14,
    // The molecule is pale blue-white and the hero copy is white, so at full
    // brightness the title vanishes into the backbone. It sits back as a ghost
    // behind the hero and comes up to full as you start scrolling, which fixes
    // the legibility and makes the reveal a beat in its own right. A layout
    // fix could not work here: the helix spins, so no region stays clear.
    // Full by 0.12 — before the first feature card opens at ~0.13, so a lit
    // anchor base is never dimmer than the card growing out of it. The hero
    // title has scrolled off by then.
    brightness: 0.3 + 0.7 * ramp(clamp01(progress), 0.02, 0.12),
  };
}

/** Camera position and target, as the scene applies them. */
export function cameraFraming(params) {
  return {
    position: { x: params.cameraX - params.cameraLagX, y: params.cameraY, z: params.cameraZ },
    target: { x: params.cameraX + params.lookAhead, y: 0, z: 0 },
  };
}

/**
 * How much a point at world X has come apart, 0 → 1.
 *
 * The far tip of the molecule always scatters into loose spheres — that trailing
 * dissolve is a permanent feature of the composition, not something that
 * consumes the helix as you scroll. Scrolling only widens it a little; the
 * camera never travels far enough to reach it.
 */
export function dissolveAt(x, params) {
  const from = HELIX.DISSOLVE_FROM - params.dissolve * 5;
  return clamp01((x - from) / HELIX.DISSOLVE_SPAN);
}

/**
 * A point on one strand.
 * @param t normalised position along the molecule, 0 → 1
 * @param strand 0 or 1
 */
export function strandPoint(t, strand, params, rotation = 0, seed = 0) {
  const angle =
    t * HELIX.TURNS * TWO_PI * params.twist + strand * HELIX.GROOVE_OFFSET + rotation;
  const side = strand === 0 ? -1 : 1;
  const x = (t - 0.5) * HELIX.LENGTH;

  const point = {
    x,
    y: Math.cos(angle) * params.radius + side * params.separation,
    z: Math.sin(angle) * params.radius,
  };

  // A real backbone alternates bulky phosphate groups with smaller sugars.
  // Uniform spheres are what made the strand read as a plain dotted line.
  const cadence = 0.86 + 0.3 * Math.abs(Math.sin(seed * 1.31)) + 0.16 * hash(seed * 7 + 3);

  const melt = dissolveAt(x, params);
  if (melt > 0) {
    // Scatter outward along a stable per-sphere direction so the dissolve
    // reads as the molecule coming apart rather than random flicker.
    const spread = melt * melt * 13;
    point.x += (hash(seed) - 0.5) * spread * 1.6;
    point.y += (hash(seed + 91) - 0.5) * spread;
    point.z += (hash(seed + 197) - 0.5) * spread;
  }
  point.melt = melt;
  point.scale = cadence * (1 - melt * 0.75);
  return point;
}

/**
 * The beads making up one base pair, running strand to strand with a gap that
 * opens in the middle as the helix unwinds.
 */
export function basePairBeads(t, params, rotation = 0, seed = 0) {
  const a = strandPoint(t, 0, params, rotation, seed);
  const b = strandPoint(t, 1, params, rotation, seed + 7);
  const beads = [];
  const count = HELIX.BEADS_PER_RUNG;

  for (let i = 0; i < count; i += 1) {
    const along = (i + 0.5) / count;          // 0 → 1 across the rung
    // Pull each half back toward its own strand as the pair breaks open.
    const side = along < 0.5 ? 0 : 1;
    const local = side === 0 ? along * 2 : (1 - along) * 2;
    const reach = local * (1 - params.gap);
    const start = side === 0 ? a : b;
    const other = side === 0 ? b : a;

    beads.push({
      x: start.x + (other.x - start.x) * reach * 0.5,
      y: start.y + (other.y - start.y) * reach * 0.5,
      z: start.z + (other.z - start.z) * reach * 0.5,
      side,
      scale: Math.min(a.scale, b.scale),
      melt: Math.max(a.melt, b.melt),
    });
  }
  return { a, b, beads };
}

/**
 * How strongly each anchor's feature card should show, given where the camera
 * is. Exactly one card is near full strength at a time, and the handover is a
 * smooth cross-fade rather than a cut.
 */
export function anchorStrengths(params) {
  // Held back over the hero and released before the call to action, so a card
  // never competes with either for the same screen.
  const gate =
    ramp(params.progress, 0.1, 0.15) * (1 - ramp(params.progress, 0.88, 0.94));

  return HELIX.ANCHOR_PAIRS.map((pairIndex) => {
    const x = pairX(pairIndex);
    const distance = Math.abs(x - (params.cameraX + params.lookAhead * 0.35));
    const proximity = clamp01(1 - distance / HELIX.ANCHOR_REACH);
    return { pairIndex, x, distance, strength: easeInOut(proximity) * gate };
  });
}

export function distance(p, q) {
  return Math.hypot(p.x - q.x, p.y - q.y, p.z - q.z);
}

/**
 * How far toward the viewer a point sits, 0 (back of the helix) → 1 (front).
 *
 * Cool colours recede and warm ones advance, so shading the backbone by this
 * is what gives the molecule volume. Uniformly pale spheres read flat no
 * matter how good the material is.
 */
export function depthFactor(z, params) {
  return clamp01((z + params.radius) / (2 * params.radius));
}

/** True for the sparse bases that glow like called variants. */
export function isHotspot(pairIndex) {
  return hash(pairIndex * 13.7) > HELIX.HOTSPOT_CUTOFF;
}

/** Position of a drifting background mote. */
export function motePosition(index) {
  return {
    x: (hash(index * 3.1) - 0.5) * 150,
    y: (hash(index * 5.7) - 0.5) * 44,
    z: (hash(index * 9.3) - 0.5) * 60 - 10,
    scale: 0.5 + hash(index * 2.2) * 1.6,
  };
}
