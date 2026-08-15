'use client';

import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ArrowDown, ArrowRight, BookOpen, Dna, GitBranch, ShieldCheck, Sparkles } from 'lucide-react';
import { BASES } from './dna-bases';
import ConnectionStatus from '../ConnectionStatus';
import type { AnchorScreen } from './dna-scene';
import { cn } from '@/lib/utils';

/**
 * Landing page.
 *
 * A horizontal double helix lies behind the whole page and the camera glides
 * along it as you scroll. Each of the four feature cards is pinned to a real
 * base pair: it grows out of that base as the camera reaches it and fades as
 * the next comes into view, so the page reads as one continuous move through a
 * molecule rather than a stack of slides.
 *
 * Card positions are written straight to the DOM from the render loop — putting
 * them in React state would re-render the tree sixty times a second.
 *
 * The backdrop is the same #1a3379 → #0f172a → black gradient the loading
 * screen uses, and the cards use the chat's frosted-glass treatment, so the
 * three surfaces read as one product.
 */

interface BackendStatus {
  status: string;
  isOnline: boolean;
  retry: () => void;
}

interface WelcomePageProps {
  onLaunch: () => void;
  backend?: BackendStatus;
}

// three.js is ~235 kB gzipped; it loads only for this page, never for the
// chat workspace, and the page is fully readable before it arrives.
const DnaScene = lazy(() => import('./dna-scene'));

const FEATURES = [
  {
    advantage: 'Automated variant prioritisation',
    description:
      'Parses patient VCFs, then queries ClinVar, dbSNP and gnomAD to rank pathogenic and VUS targets — the variants that matter surface first.',
    icon: Sparkles,
  },
  {
    advantage: 'Traceable PubMed citations',
    description:
      'Every claim is anchored to literature. Search terms are generated per variant and PubMed is queried live, returning links to peer-reviewed work rather than recalled assertions.',
    icon: BookOpen,
  },
  {
    advantage: 'Clinical pedigree charts',
    description:
      'Describe a family history in plain language and get a standards-compliant pedigree as vector art — correct generations, clean sibship lines, conventional notation.',
    icon: GitBranch,
  },
  {
    advantage: 'Genomic context engine',
    description:
      'Deep annotations, HGVS and rsID lookups, and multi-VCF workspaces for trio analysis, with each tool toggled independently.',
    icon: Dna,
  },
] as const;

/** Where a card sits relative to the base it grows from. */
const CARD_OFFSET = { x: 54, y: 34 };
const CARD_WIDTH = 340;

export default function WelcomePage({ onLaunch, backend }: WelcomePageProps) {
  const progressRef = useRef(0);
  const anchorsRef = useRef<AnchorScreen[]>(
    FEATURES.map(() => ({ x: 0, y: 0, strength: 0, visible: false }))
  );
  const cardRefs = useRef<(HTMLDivElement | null)[]>([]);
  const rafRef = useRef<number | null>(null);
  const [leaving, setLeaving] = useState(false);

  const supportsWebGL = useMemo(() => {
    if (typeof window === 'undefined') return false;
    try {
      const probe = document.createElement('canvas');
      return Boolean(probe.getContext('webgl2') || probe.getContext('webgl'));
    } catch {
      return false;
    }
  }, []);

  const onScroll = useCallback(() => {
    const scrollable = document.documentElement.scrollHeight - window.innerHeight;
    progressRef.current = scrollable > 0 ? window.scrollY / scrollable : 0;
  }, []);

  // One loop drives every card, reading the positions the scene publishes.
  useEffect(() => {
    if (!supportsWebGL) return undefined;

    const tick = () => {
      for (let i = 0; i < cardRefs.current.length; i += 1) {
        const el = cardRefs.current[i];
        const anchor = anchorsRef.current[i];
        if (!el || !anchor) continue;

        if (!anchor.visible || anchor.strength <= 0.01) {
          el.style.opacity = '0';
          el.style.visibility = 'hidden';
          continue;
        }

        // Keep the card on screen even when its base drifts toward an edge.
        const maxX = window.innerWidth - CARD_WIDTH - 28;
        const x = Math.min(Math.max(anchor.x, 20), Math.max(20, maxX));
        const maxY = window.innerHeight - 300;
        const y = Math.min(Math.max(anchor.y, 90), Math.max(90, maxY));

        const s = anchor.strength;
        el.style.visibility = 'visible';
        el.style.opacity = String(Math.min(1, s * 1.25));
        el.style.transform =
          `translate3d(${x}px, ${y}px, 0) scale(${0.9 + s * 0.1})`;
      }
      rafRef.current = window.requestAnimationFrame(tick);
    };

    rafRef.current = window.requestAnimationFrame(tick);
    return () => {
      if (rafRef.current !== null) window.cancelAnimationFrame(rafRef.current);
    };
  }, [supportsWebGL]);

  useEffect(() => {
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
    };
  }, [onScroll]);

  // Fade out rather than cut, so entering the workspace feels continuous.
  const launch = () => {
    setLeaving(true);
    window.setTimeout(onLaunch, 420);
  };

  return (
    <div className="relative min-h-screen text-slate-100 selection:bg-indigo-500/40">
      {/* Same gradient as the loading screen — the two must not look like
          different applications. */}
      <div className="fixed inset-0 z-0 bg-gradient-to-b from-[#1a3379] via-[#0f172a] to-black" />

      <div className="fixed inset-0 z-0" aria-hidden="true">
        {supportsWebGL && (
          <Suspense fallback={null}>
            <DnaScene progressRef={progressRef} anchorsRef={anchorsRef} />
          </Suspense>
        )}
      </div>

      {/* Feature cards, each pinned to the base pair it grows out of. */}
      {supportsWebGL && (
        <div className="pointer-events-none fixed inset-0 z-10" aria-hidden="true">
          {FEATURES.map((feature, index) => (
            <div
              key={feature.advantage}
              ref={(node) => { cardRefs.current[index] = node; }}
              className="absolute left-0 top-0 will-change-transform"
              style={{ opacity: 0, visibility: 'hidden', transition: 'opacity 220ms linear' }}
            >
              <BaseCard feature={feature} base={BASES[index]} />
            </div>
          ))}
        </div>
      )}

      <div className="relative z-20">
        {/* ── Hero ── */}
        <section className="relative flex min-h-screen flex-col items-center justify-center px-6 text-center">
          {/* Soft scrim so white copy stays readable wherever the spinning
              helix happens to be. Feathered to nothing at the edges, so it
              reads as depth rather than a panel behind the text. */}
          <div
            className="pointer-events-none absolute inset-0"
            aria-hidden="true"
            style={{
              background:
                'radial-gradient(58% 44% at 50% 46%, rgba(2,6,23,0.82) 0%, rgba(2,6,23,0.55) 45%, rgba(2,6,23,0) 78%)',
            }}
          />

          <div className="relative flex flex-col items-center">
            <span className="mb-6 rounded-full border border-indigo-400/40 bg-indigo-500/15 px-4 py-1.5 text-xs font-semibold uppercase tracking-[0.2em] text-indigo-200 backdrop-blur">
              AI genetic counselling assistant
            </span>
            <h1
              className="text-5xl font-black tracking-tight text-white md:text-7xl lg:text-8xl"
              style={{ textShadow: '0 2px 28px rgba(2,6,23,0.95), 0 1px 6px rgba(2,6,23,0.9)' }}
            >
              VariantMind
            </h1>
            <p
              className="mt-6 max-w-2xl text-base leading-relaxed text-slate-200 md:text-lg"
              style={{ textShadow: '0 1px 14px rgba(2,6,23,0.95)' }}
            >
              Variant curation and pedigree charting for genetic counsellors,
              clinical geneticists and researchers — grounded in live evidence,
              never in recollection.
            </p>
            <button
              onClick={launch}
              className="mt-10 inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-blue-600 to-indigo-600 px-8 py-4 text-base font-bold text-white shadow-lg shadow-indigo-900/40 transition-all duration-300 hover:from-blue-500 hover:to-indigo-500 active:scale-95"
            >
              Launch workspace
              <ArrowRight className="h-4 w-4" />
            </button>
            {/* Shown up front: the demo backend sleeps, and a visitor reading
                the intro is exactly who is waiting for it to wake. */}
            {backend && (
              <div className="mt-8">
                <ConnectionStatus
                  status={backend.status}
                  onRetry={backend.retry}
                  variant="pill"
                />
              </div>
            )}

            <div
              className="mt-10 flex flex-col items-center gap-2 text-[11px] uppercase tracking-[0.25em] text-slate-300"
              style={{ textShadow: '0 1px 12px rgba(2,6,23,0.95)' }}
            >
              Scroll along the molecule
              <ArrowDown className="h-4 w-4 animate-bounce" />
            </div>
          </div>
        </section>

        {/* Scroll runway. The cards are drawn in the fixed overlay above,
            anchored to their bases, so these only carry the scroll distance —
            except without WebGL, where they carry the content itself. */}
        {supportsWebGL ? (
          FEATURES.map((feature) => (
            <section key={feature.advantage} className="h-[105vh]" aria-hidden="true" />
          ))
        ) : (
          <div className="mx-auto max-w-3xl space-y-8 px-6 py-24">
            {FEATURES.map((feature, index) => (
              <BaseCard key={feature.advantage} feature={feature} base={BASES[index]} wide />
            ))}
          </div>
        )}

        {/* ── Call to action ── */}
        <section className="flex min-h-screen items-center justify-center px-6">
          <div className="w-full max-w-2xl rounded-3xl border border-slate-800/80 bg-slate-950/70 p-10 text-center shadow-2xl shadow-black/40 backdrop-blur-md md:p-14">
            <ShieldCheck className="mx-auto h-12 w-12 text-indigo-300" />
            <h2 className="mt-6 text-3xl font-extrabold tracking-tight text-white md:text-4xl">
              Start with a variant, or a family
            </h2>
            <p className="mt-5 text-sm leading-relaxed text-slate-400 md:text-base">
              Upload a VCF, paste an rsID or HGVS expression, or just describe a
              family history in plain language.
            </p>
            <button
              onClick={launch}
              className="group mt-9 inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-blue-600 to-indigo-600 px-8 py-4 text-base font-bold text-white shadow-lg shadow-indigo-900/40 transition-all duration-300 hover:from-blue-500 hover:to-indigo-500 active:scale-95"
            >
              Launch workspace
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
            </button>
            <p className="mt-10 text-xs leading-relaxed text-slate-600">
              For research and educational use only. Confirm all clinical
              decisions with a board-certified professional.
            </p>
          </div>
        </section>
      </div>

      {/* Cross-fade into the workspace. */}
      <div
        className={cn(
          'pointer-events-none fixed inset-0 z-50 bg-[#0F172A] transition-opacity duration-500',
          leaving ? 'opacity-100' : 'opacity-0'
        )}
      />
    </div>
  );
}

interface BaseCardProps {
  feature: (typeof FEATURES)[number];
  base: (typeof BASES)[number];
  wide?: boolean;
}

function BaseCard({ feature, base, wide = false }: BaseCardProps) {
  const Icon = feature.icon;
  return (
    <div className="relative" style={{ width: wide ? '100%' : CARD_WIDTH }}>
      {!wide && (
        // The tether back to the base pair this point grew out of.
        <svg
          className="pointer-events-none absolute"
          style={{ left: 0, top: 0, overflow: 'visible' }}
          width={CARD_OFFSET.x}
          height={CARD_OFFSET.y}
        >
          <line
            x1="0" y1="0" x2={CARD_OFFSET.x} y2={CARD_OFFSET.y}
            stroke={base.colour} strokeWidth="1" strokeOpacity="0.55"
          />
          <circle cx="0" cy="0" r="3.5" fill={base.colour} />
          <circle cx="0" cy="0" r="8" fill={base.colour} fillOpacity="0.22" />
        </svg>
      )}

      <div
        className="rounded-2xl border border-slate-800/80 bg-slate-950/70 p-6 shadow-2xl shadow-black/40 backdrop-blur-md"
        style={wide ? undefined : { marginLeft: CARD_OFFSET.x, marginTop: CARD_OFFSET.y }}
      >
        <div className="flex items-center gap-3">
          <div
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border font-mono text-xl font-black"
            style={{
              color: base.colour,
              borderColor: `${base.colour}55`,
              backgroundColor: `${base.colour}14`,
              boxShadow: `0 0 22px ${base.colour}33`,
            }}
          >
            {base.letter}
          </div>
          <div className="min-w-0">
            <div
              className="text-[10px] font-semibold uppercase tracking-[0.18em]"
              style={{ color: base.colour }}
            >
              {base.name}
            </div>
            <div className="text-[10px] text-slate-500">Pairs with {base.partner}</div>
          </div>
          <Icon className="ml-auto h-5 w-5 shrink-0 opacity-70" style={{ color: base.colour }} />
        </div>

        <h3 className="mt-4 text-lg font-bold leading-snug text-white">
          {feature.advantage}
        </h3>
        <p className="mt-2 text-[13px] leading-relaxed text-slate-400">
          {feature.description}
        </p>
      </div>
    </div>
  );
}
