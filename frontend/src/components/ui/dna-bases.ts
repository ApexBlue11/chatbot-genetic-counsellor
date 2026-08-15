/**
 * The four nucleotide bases, shared by the 3D scene and the page copy.
 *
 * Kept in its own module so the landing page can read the palette without
 * pulling three.js into the main bundle — the scene itself is lazy-loaded.
 */
export const BASES = [
  { letter: 'A', name: 'Adenine', colour: '#10b981', partner: 'T' },
  { letter: 'T', name: 'Thymine', colour: '#3b82f6', partner: 'A' },
  { letter: 'C', name: 'Cytosine', colour: '#6366f1', partner: 'G' },
  { letter: 'G', name: 'Guanine', colour: '#f43f5e', partner: 'C' },
] as const;

export type Base = (typeof BASES)[number];
