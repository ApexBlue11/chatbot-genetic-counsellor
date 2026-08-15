'use client';

import { useEffect, useLayoutEffect, useMemo, useRef } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { Bloom, EffectComposer, Vignette } from '@react-three/postprocessing';
import * as THREE from 'three';

import { BASES } from './dna-bases';
import { createStudioEnvironment } from './dna-environment';
import {
  HELIX,
  anchorStrengths,
  basePairBeads,
  cameraFraming,
  depthFactor,
  helixParams,
  isHotspot,
  motePosition,
  pairX,
  strandPoint,
} from './dna-helix-math';

/**
 * The molecule behind the landing page.
 *
 * Built entirely from spheres — backbone and base rungs alike — which is what
 * gives it the soft, beaded look rather than the hard cylinder-and-ribbon
 * construction that reads as dated CGI. Geometry is created once; only the
 * per-instance matrices change each frame.
 *
 * The scene also projects each anchor base pair into screen space and writes
 * the result into `anchorsRef`, so the page can grow a feature card out of the
 * exact pixel where that base sits — without re-rendering React every frame.
 */

export interface AnchorScreen {
  x: number;
  y: number;
  strength: number;
  visible: boolean;
}

const BACKBONE_COUNT = HELIX.BACKBONE_PER_STRAND * 2;
const RUNG_COUNT = HELIX.PAIR_COUNT * HELIX.BEADS_PER_RUNG;

// The backbone is shaded by depth rather than painted one flat tone: near
// spheres are almost white, far ones sink to deep blue. That is what gives the
// molecule volume — a single pale colour reads flat however good the material.
// Kept neutral on purpose, so the A/T/C/G base colours (which the feature cards
// are matched to) stay the only saturated thing on screen.
const NEAR_COLOUR = new THREE.Color('#f4f9ff');
const FAR_COLOUR = new THREE.Color('#12386e');
const DEPTH_GAMMA = 1.5;
const BASE_WASH = 0.18;          // how far ordinary bases are pulled to pale
const MOTE_COLOUR = '#9ec5ff';
const FOG_COLOUR = '#0b1a3a';

interface HelixProps {
  progressRef: React.MutableRefObject<number>;
  anchorsRef: React.MutableRefObject<AnchorScreen[]>;
  reducedMotion: boolean;
}

function Helix({ progressRef, anchorsRef, reducedMotion }: HelixProps) {
  const backboneRef = useRef<THREE.InstancedMesh>(null);
  const rungRef = useRef<THREE.InstancedMesh>(null);
  const moteRef = useRef<THREE.InstancedMesh>(null);
  const backboneMat = useRef<THREE.MeshPhysicalMaterial>(null);
  const rungMat = useRef<THREE.MeshPhysicalMaterial>(null);
  const moteMat = useRef<THREE.MeshBasicMaterial>(null);
  const spin = useRef(0);
  const lastActive = useRef(-2);
  const { camera, size, gl, scene } = useThree();

  // Reflections come from a procedurally-built studio env map — see
  // dna-environment.ts for why this is not drei's <Environment>.
  useEffect(() => {
    const texture = createStudioEnvironment(gl);
    scene.environment = texture;
    return () => {
      scene.environment = null;
      texture.dispose();
    };
  }, [gl, scene]);

  const dummy = useMemo(() => new THREE.Object3D(), []);
  const projected = useMemo(() => new THREE.Vector3(), []);
  const target = useMemo(() => new THREE.Vector3(), []);
  const scratch = useMemo(() => new THREE.Color(), []);

  const pairBase = useMemo(
    () => Array.from({ length: HELIX.PAIR_COUNT }, (_, i) => i % BASES.length),
    []
  );

  /** Rung colours: saturated bases, full strength on the active anchor. */
  const paintRungs = (activeAnchor: number) => {
    const mesh = rungRef.current;
    if (!mesh) return;
    for (let pair = 0; pair < HELIX.PAIR_COUNT; pair += 1) {
      const anchorIndex = HELIX.ANCHOR_PAIRS.indexOf(pair);
      const base = BASES[anchorIndex >= 0 ? anchorIndex : pairBase[pair]];
      const partner = BASES.find((b) => b.letter === base.partner) ?? base;
      const lit = anchorIndex >= 0 && anchorIndex === activeAnchor;
      const hot = isHotspot(pair);

      for (let bead = 0; bead < HELIX.BEADS_PER_RUNG; bead += 1) {
        // Ordinary rungs are split base/partner. The lit anchor takes its own
        // base colour end to end, so it unmistakably matches the card growing
        // out of it — split colouring left the visible half showing the
        // partner's colour instead.
        const half = lit || bead < HELIX.BEADS_PER_RUNG / 2 ? base : partner;
        scratch.set(half.colour);
        scratch.lerp(NEAR_COLOUR, lit ? 0.05 : hot ? 0.12 : BASE_WASH);
        mesh.setColorAt(pair * HELIX.BEADS_PER_RUNG + bead, scratch);
      }
    }
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  };

  useLayoutEffect(() => {
    paintRungs(-1);

    // Motes never move, so their transforms are written once.
    const motes = moteRef.current;
    if (motes) {
      for (let i = 0; i < HELIX.MOTE_COUNT; i += 1) {
        const m = motePosition(i);
        dummy.position.set(m.x, m.y, m.z);
        dummy.scale.setScalar(m.scale);
        dummy.updateMatrix();
        motes.setMatrixAt(i, dummy.matrix);
      }
      motes.instanceMatrix.needsUpdate = true;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useFrame((_, delta) => {
    const backbone = backboneRef.current;
    const rungs = rungRef.current;
    if (!backbone || !rungs) return;

    const params = helixParams(progressRef.current);
    if (!reducedMotion) spin.current += delta * 0.12;
    const rotation = spin.current;

    // The material colour multiplies the per-instance colours in the shader, so
    // one assignment dims the whole molecule without touching the instance
    // buffers or introducing transparency sorting.
    backboneMat.current?.color.setScalar(params.brightness);
    rungMat.current?.color.setScalar(params.brightness);
    if (moteMat.current) moteMat.current.opacity = 0.5 * params.brightness;

    // -- backbone: position and depth-shade every sphere --
    for (let strand = 0; strand < 2; strand += 1) {
      for (let i = 0; i < HELIX.BACKBONE_PER_STRAND; i += 1) {
        const index = strand * HELIX.BACKBONE_PER_STRAND + i;
        const point = strandPoint(
          i / (HELIX.BACKBONE_PER_STRAND - 1), strand, params, rotation, index
        );
        dummy.position.set(point.x, point.y, point.z);
        dummy.scale.setScalar(Math.max(0.001, point.scale));
        dummy.updateMatrix();
        backbone.setMatrixAt(index, dummy.matrix);

        // Depth changes as the helix turns, so this has to be per-frame.
        scratch.copy(FAR_COLOUR).lerp(
          NEAR_COLOUR, Math.pow(depthFactor(point.z, params), DEPTH_GAMMA)
        );
        backbone.setColorAt(index, scratch);
      }
    }
    backbone.instanceMatrix.needsUpdate = true;
    if (backbone.instanceColor) backbone.instanceColor.needsUpdate = true;

    // -- base rungs --
    const anchors = anchorStrengths(params);
    let active = -1;
    let best = 0.35;
    anchors.forEach((anchor, i) => {
      if (anchor.strength > best) {
        best = anchor.strength;
        active = i;
      }
    });

    for (let pair = 0; pair < HELIX.PAIR_COUNT; pair += 1) {
      const anchorIndex = HELIX.ANCHOR_PAIRS.indexOf(pair);
      const emphasis = anchorIndex >= 0
        ? 1 + anchors[anchorIndex].strength * 1.15
        : isHotspot(pair) ? 1.45 : 1;
      const { beads } = basePairBeads(
        (pair + 0.5) / HELIX.PAIR_COUNT, params, rotation, pair * 31
      );

      for (let bead = 0; bead < beads.length; bead += 1) {
        const b = beads[bead];
        dummy.position.set(b.x, b.y, b.z);
        dummy.scale.setScalar(Math.max(0.001, b.scale * emphasis));
        dummy.updateMatrix();
        rungs.setMatrixAt(pair * HELIX.BEADS_PER_RUNG + bead, dummy.matrix);
      }
    }
    rungs.instanceMatrix.needsUpdate = true;

    if (active !== lastActive.current) {
      paintRungs(active);
      lastActive.current = active;
    }

    // -- camera travels along the molecule --
    const framing = cameraFraming(params);
    camera.position.set(framing.position.x, framing.position.y, framing.position.z);
    target.set(framing.target.x, framing.target.y, framing.target.z);
    camera.lookAt(target);

    // -- publish anchor positions in screen pixels --
    for (let i = 0; i < anchors.length; i += 1) {
      const anchor = anchors[i];
      const { a, b } = basePairBeads(
        (anchor.pairIndex + 0.5) / HELIX.PAIR_COUNT, params, rotation, anchor.pairIndex * 31
      );
      projected.set((a.x + b.x) / 2, (a.y + b.y) / 2, (a.z + b.z) / 2);
      projected.project(camera);

      const onScreen =
        projected.z < 1 &&
        projected.x > -1.35 && projected.x < 1.35 &&
        projected.y > -1.35 && projected.y < 1.35;

      anchorsRef.current[i] = {
        x: (projected.x * 0.5 + 0.5) * size.width,
        y: (-projected.y * 0.5 + 0.5) * size.height,
        strength: anchor.strength,
        visible: onScreen && anchor.strength > 0.02,
      };
    }
  });

  return (
    <group>
      <instancedMesh
        ref={backboneRef}
        args={[undefined, undefined, BACKBONE_COUNT]}
        frustumCulled={false}
      >
        <sphereGeometry args={[0.34, 20, 20]} />
        {/* Clearcoat gives the wet, polished highlight that a plain standard
            material cannot; the env map is what it reflects. */}
        <meshPhysicalMaterial
          ref={backboneMat}
          roughness={0.22}
          metalness={0.1}
          clearcoat={0.9}
          clearcoatRoughness={0.16}
          envMapIntensity={1.2}
          sheen={0.35}
          sheenColor="#bfd8ff"
        />
      </instancedMesh>

      <instancedMesh
        ref={rungRef}
        args={[undefined, undefined, RUNG_COUNT]}
        frustumCulled={false}
      >
        <sphereGeometry args={[0.2, 18, 18]} />
        {/* Emissive so the coloured bases carry their own light and pick up
            the bloom, instead of sitting flat against the backbone. */}
        <meshPhysicalMaterial
          ref={rungMat}
          roughness={0.18}
          metalness={0.05}
          clearcoat={1}
          clearcoatRoughness={0.1}
          envMapIntensity={1}
          emissive="#ffffff"
          emissiveIntensity={0.1}
          toneMapped={false}
        />
      </instancedMesh>

      {/* A sparse drift of motes at varying depths. Just enough to stop the
          space around the molecule reading as empty black, without becoming a
          starfield that competes with the copy. */}
      <instancedMesh
        ref={moteRef}
        args={[undefined, undefined, HELIX.MOTE_COUNT]}
        frustumCulled={false}
      >
        <sphereGeometry args={[0.09, 8, 8]} />
        <meshBasicMaterial ref={moteMat} color={MOTE_COLOUR} transparent opacity={0.5} />
      </instancedMesh>
    </group>
  );
}

interface DnaSceneProps {
  progressRef: React.MutableRefObject<number>;
  anchorsRef: React.MutableRefObject<AnchorScreen[]>;
}

export default function DnaScene({ progressRef, anchorsRef }: DnaSceneProps) {
  const reducedMotion =
    typeof window !== 'undefined' &&
    window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

  return (
    <Canvas
      dpr={[1, 2]}
      // Transparent, so the page's own gradient — the same one the loading
      // screen uses — shows through and the two never look like different apps.
      gl={{ antialias: true, alpha: true, powerPreference: 'high-performance' }}
      camera={{ position: [0, 3, 18], fov: 38 }}
      style={{ pointerEvents: 'none' }}
    >
      <fog attach="fog" args={[FOG_COLOUR, 26, 74]} />

      {/* Soft, wrapping studio light — no hard speculars, which is most of what
          separates this from plastic-looking early CGI. */}
      <ambientLight intensity={0.62} />
      <hemisphereLight args={['#cfe4ff', '#16306b', 1.05]} />
      <directionalLight position={[-14, 16, 14]} intensity={2.1} color="#f2f7ff" />
      <directionalLight position={[12, -8, 6]} intensity={0.75} color="#7ea8e8" />
      <pointLight position={[6, 4, -16]} intensity={220} distance={70} color="#4f7fd4" />

      <Helix
        progressRef={progressRef}
        anchorsRef={anchorsRef}
        reducedMotion={Boolean(reducedMotion)}
      />

      {/* Bloom is what turns lit spheres into something that glows. The
          threshold is set above the mid-tones so only the highlights and the
          emissive bases flare, rather than the whole molecule going soft. */}
      <EffectComposer enableNormalPass={false}>
        {/* Restrained: enough to put a halo on the brightest highlights, not
            enough to bleach the molecule and lose the base colours. */}
        <Bloom
          intensity={0.28}
          luminanceThreshold={0.84}
          luminanceSmoothing={0.25}
          mipmapBlur
          radius={0.55}
        />
        <Vignette offset={0.3} darkness={0.5} />
      </EffectComposer>
    </Canvas>
  );
}
