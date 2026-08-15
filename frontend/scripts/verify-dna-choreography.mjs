/**
 * Automated verification of the landing page's scroll choreography.
 *
 * Runs the same geometry module the scene renders from, so this checks the
 * shipped behaviour rather than a copy of it. No browser, no GPU, no deps.
 *
 *     node scripts/verify-dna-choreography.mjs
 */

import {
  HELIX,
  anchorStrengths,
  basePairBeads,
  cameraFraming,
  dissolveAt,
  distance,
  helixParams,
  pairX,
  phases,
  strandPoint,
} from '../src/components/ui/dna-helix-math.js';

const checks = [];
const check = (name, condition, detail = '') =>
  checks.push({ name, pass: Boolean(condition), detail });

const SAMPLES = Array.from({ length: 401 }, (_, i) => i / 400);

// ── 1. Phases behave across the whole scroll ───────────────────────────────
{
  let monotonic = true;
  let inRange = true;
  let previous = phases(0);
  for (const p of SAMPLES) {
    const current = phases(p);
    for (const key of Object.keys(current)) {
      if (current[key] < previous[key] - 1e-9) monotonic = false;
      if (!(current[key] >= 0 && current[key] <= 1)) inRange = false;
    }
    previous = current;
  }
  check('phases never go backwards as you scroll', monotonic);
  check('phases stay within 0..1 and are never NaN', inRange);
  check('at the top, the molecule is untouched',
    phases(0).unravel === 0 && phases(0).travel === 0);
  check('by the bottom, travel has completed', phases(1).travel === 1);
}

// ── 2. At rest it is a proper double helix ─────────────────────────────────
{
  const params = helixParams(0);
  check('helix starts fully wound', Math.abs(params.twist - 1) < 1e-9);
  check('strands start joined', params.separation === 0);
  check('base pairs start intact', params.gap === 0);

  // Paired bases span a chord, not the diameter — the strands sit
  // GROOVE_OFFSET apart so the helix has a major and a minor groove.
  const expectedChord = 2 * params.radius * Math.sin(HELIX.GROOVE_OFFSET / 2);
  let chordHolds = true;
  let horizontal = true;
  for (const t of SAMPLES) {
    const a = strandPoint(t, 0, params, 0);
    const b = strandPoint(t, 1, params, 0);
    if (a.melt === 0 && b.melt === 0) {
      if (Math.abs(distance(a, b) - expectedChord) > 1e-6) chordHolds = false;
      // The molecule must lie along X: paired bases share an X, not a Y.
      if (Math.abs(a.x - b.x) > 1e-9) horizontal = false;
    }
  }
  check('every base pair spans the same distance', chordHolds,
    `chord ${expectedChord.toFixed(2)}`);
  check('the helix lies along the horizontal axis', horizontal);
  check('the strands are offset, giving a major and a minor groove',
    Math.abs(HELIX.GROOVE_OFFSET - Math.PI) > 0.2 && HELIX.GROOVE_OFFSET < Math.PI,
    `${((HELIX.GROOVE_OFFSET * 180) / Math.PI).toFixed(0)}° apart`);

  const span = Math.abs(strandPoint(1, 0, params, 0).x - strandPoint(0, 0, params, 0).x);
  check('the molecule is much wider than it is tall',
    span > params.radius * 8, `${span.toFixed(0)} long vs ${params.radius.toFixed(1)} radius`);
}

// ── 3. Scrolling opens the helix, but never destroys it ────────────────────
{
  const end = helixParams(1);
  check('twist relaxes as you scroll', end.twist < 0.5 && end.twist > 0.2,
    `twist ${end.twist.toFixed(2)}`);
  check('it still reads as a helix at the end', end.twist > 0.2);
  check('strands ease apart', end.separation > 1, `separation ${end.separation.toFixed(2)}`);
  check('base pairs open up', end.gap > 0.3, `gap ${end.gap.toFixed(2)}`);
}

// ── 4. Camera travels along the molecule and stops short of the tip ────────
{
  let monotonic = true;
  let previous = -Infinity;
  for (const p of SAMPLES) {
    const { cameraX } = helixParams(p);
    if (cameraX < previous - 1e-9) monotonic = false;
    previous = cameraX;
  }
  check('camera only ever moves forward', monotonic);

  const start = helixParams(0);
  const end = helixParams(1);
  check('camera actually travels a long way',
    end.cameraX - start.cameraX > 50,
    `${start.cameraX.toFixed(0)} → ${end.cameraX.toFixed(0)}`);
  check('camera stops before the dissolving tip',
    end.cameraX < HELIX.DISSOLVE_FROM,
    `ends at ${end.cameraX.toFixed(0)}, tip starts at ${HELIX.DISSOLVE_FROM}`);

  // The camera trails the point it looks at, which is what gives the recession.
  const framing = cameraFraming(end);
  check('camera looks ahead down the molecule', framing.target.x > framing.position.x);
  check('camera keeps its distance from the axis',
    SAMPLES.every((p) => helixParams(p).cameraZ > 12));
}

// ── 5. The dissolve stays at the far tip ───────────────────────────────────
{
  // Scattering *ahead* of the camera is the intended closing shot. What must
  // never happen is the molecule coming apart at or behind you, which would
  // read as the page falling to bits rather than as the end of a strand.
  let travelledStretchIntact = true;
  for (const p of SAMPLES) {
    const params = helixParams(p);
    for (let x = params.cameraX - 24; x <= params.cameraX + 2; x += 2) {
      if (dissolveAt(x, params) > 0.02) travelledStretchIntact = false;
    }
  }
  check('the stretch you travel through stays solid', travelledStretchIntact);
  check('the far tip does scatter',
    dissolveAt(HELIX.DISSOLVE_FROM + HELIX.DISSOLVE_SPAN, helixParams(1)) >= 1);
  check('the scatter is only ever ahead of the camera',
    SAMPLES.every((p) => {
      const params = helixParams(p);
      return HELIX.DISSOLVE_FROM - params.dissolve * 5 > params.cameraX;
    }));
}

// ── 6. Each feature grows from its own base, one at a time ─────────────────
{
  const peaks = HELIX.ANCHOR_PAIRS.map(() => 0);
  const peakAt = HELIX.ANCHOR_PAIRS.map(() => 0);
  let overlapping = 0;
  let dead = 0;

  for (const p of SAMPLES) {
    const strengths = anchorStrengths(helixParams(p));
    strengths.forEach((s, k) => {
      if (s.strength > peaks[k]) { peaks[k] = s.strength; peakAt[k] = p; }
    });
    // Two cards at full strength at once would read as clutter, not a handover.
    if (strengths.filter((s) => s.strength > 0.8).length > 1) overlapping += 1;
    if (strengths.every((s) => s.strength < 0.25)) dead += 1;
  }

  check('every feature reaches full strength', peaks.every((v) => v > 0.99),
    peaks.map((v) => v.toFixed(2)).join(' '));
  check('features appear in order',
    peakAt.every((v, i) => i === 0 || v > peakAt[i - 1]),
    peakAt.map((v) => v.toFixed(2)).join(' '));
  check('features are evenly spaced down the page',
    Math.max(...peakAt.slice(1).map((v, i) => v - peakAt[i])) -
    Math.min(...peakAt.slice(1).map((v, i) => v - peakAt[i])) < 0.06);
  check('only one feature is dominant at a time', overlapping === 0,
    `${overlapping} overlapping samples`);
  check('the page is not mostly empty scroll', dead / SAMPLES.length < 0.3,
    `${Math.round((100 * dead) / SAMPLES.length)}% with no card`);
  check('the first card waits until past the hero', peakAt[0] > 0.1);
  check('the last card clears before the call to action', peakAt.at(-1) < 0.9);

  // Anchors must be real base pairs, spread down the molecule.
  check('four anchors, one per feature', HELIX.ANCHOR_PAIRS.length === 4);
  check('anchors are inside the molecule',
    HELIX.ANCHOR_PAIRS.every((i) => i >= 0 && i < HELIX.PAIR_COUNT));
  check('anchors are spread along its length',
    pairX(HELIX.ANCHOR_PAIRS.at(-1)) - pairX(HELIX.ANCHOR_PAIRS[0]) > HELIX.LENGTH * 0.35);
}

// ── 7. The hero copy has to stay readable over the molecule ────────────────
{
  const hero = helixParams(0).brightness;
  const settled = helixParams(0.25).brightness;

  check('molecule sits back behind the hero copy', hero < 0.4,
    `brightness ${hero.toFixed(2)} at the top`);
  check('molecule comes up to full once scrolling starts', settled > 0.99,
    `brightness ${settled.toFixed(2)} by 25%`);

  let monotonic = true;
  let previous = -Infinity;
  for (const p of SAMPLES) {
    const { brightness } = helixParams(p);
    if (brightness < previous - 1e-9) monotonic = false;
    if (brightness < 0 || brightness > 1) monotonic = false;
    previous = brightness;
  }
  check('the molecule only ever brightens, and stays in range', monotonic);

  // It must reach full brightness before the first feature card appears,
  // otherwise the lit base would be dimmer than its own card.
  const firstCardAt = SAMPLES.find((p) =>
    anchorStrengths(helixParams(p)).some((s) => s.strength > 0.5));
  check('molecule is at full brightness before the first card',
    helixParams(firstCardAt).brightness > 0.99,
    `first card at ${firstCardAt.toFixed(2)}`);
}

// ── 8. Nothing degenerate anywhere in the sweep ────────────────────────────
{
  let finite = true;
  let beadsPerRung = true;
  for (const p of SAMPLES.filter((_, i) => i % 8 === 0)) {
    const params = helixParams(p);
    for (let i = 0; i < HELIX.PAIR_COUNT; i += 7) {
      const { beads, a, b } = basePairBeads((i + 0.5) / HELIX.PAIR_COUNT, params, p * 6.28, i * 31);
      if (beads.length !== HELIX.BEADS_PER_RUNG) beadsPerRung = false;
      for (const pt of [a, b, ...beads]) {
        if (![pt.x, pt.y, pt.z].every(Number.isFinite)) finite = false;
      }
      if (beads.some((bead) => !(bead.scale > 0))) finite = false;
    }
  }
  check('all geometry stays finite across the full scroll', finite);
  check('every base pair keeps its full run of beads', beadsPerRung);
}

// ── report ─────────────────────────────────────────────────────────────────
const failed = checks.filter((c) => !c.pass);
console.log(`DNA scroll choreography — ${checks.length} checks\n${'='.repeat(64)}`);
for (const { name, pass, detail } of checks) {
  console.log(`  ${pass ? 'PASS' : 'FAIL'}  ${name}${detail ? `  (${detail})` : ''}`);
}
console.log('='.repeat(64));
console.log(`${checks.length - failed.length} passed, ${failed.length} failed`);
process.exit(failed.length ? 1 : 0);
