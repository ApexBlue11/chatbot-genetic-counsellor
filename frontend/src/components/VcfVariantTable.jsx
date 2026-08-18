import React, { useState } from 'react';
import { ChevronDown, ChevronUp, AlertTriangle, AlertCircle, HelpCircle, CheckCircle, Search, Info } from 'lucide-react';
import VariantDetailsTabs from './VariantDetailsTabs';

const PAGE_SIZE = 5;

const categoryConfig = {
  dangerous:       { label: 'Pathogenic / Dangerous',               icon: <AlertTriangle size={16} />, color: '#EF4444', bg: '#FEE2E2' },
  possibly_harmful:{ label: 'Likely Pathogenic / Possibly Harmful',  icon: <AlertCircle size={16} />,   color: '#F59E0B', bg: '#FEF3C7' },
  vus:             { label: 'Variant of Uncertain Significance (VUS)',icon: <HelpCircle size={16} />,    color: '#3B82F6', bg: '#DBEAFE' },
  unannotated:     { label: 'Unannotated / Novel',                   icon: <Search size={16} />,         color: '#6B7280', bg: '#F3F4F6' },
  benign:          { label: 'Benign / Likely Benign',                icon: <CheckCircle size={16} />,   color: '#10B981', bg: '#D1FAE5' },
};

// A variant can be filed under Pathogenic/Dangerous purely because VEP scored
// its impact HIGH, with no ClinVar call at all. The prioritiser already computes
// impact, SIFT, PolyPhen and allele frequency; the table used to drop all four,
// leaving the counselor no way to see why a row was ranked where it was.
const IMPACT_COLORS = {
  HIGH:     { color: '#EF4444', bg: '#FEE2E2' },
  MODERATE: { color: '#F59E0B', bg: '#FEF3C7' },
  LOW:      { color: '#10B981', bg: '#D1FAE5' },
  MODIFIER: { color: '#6B7280', bg: '#F3F4F6' },
};

// SIFT and PolyPhen arrive as dbNSFP's single-letter codes.
const SIFT_LABELS = { D: 'Deleterious', T: 'Tolerated' };
const POLYPHEN_LABELS = { D: 'Probably damaging', P: 'Possibly damaging', B: 'Benign' };

const expandPred = (raw, labels) => {
  const v = String(raw ?? '').trim();
  if (!v || v === '.' || v === 'None') return null;
  // Multi-transcript calls come through as "D;D;T" — report the worst.
  const codes = v.split(/[;,]/).map(c => c.trim()).filter(Boolean);
  const worst = codes.find(c => c === 'D') || codes.find(c => c === 'P') || codes[0];
  return labels[worst] || worst;
};

// Frequencies span many orders of magnitude, so a fixed number of decimal places
// renders the rare ones — the clinically interesting ones — as a row of zeros.
const formatAf = (af) => {
  const n = Number(af);
  if (af === null || af === undefined || af === '' || Number.isNaN(n)) return '—';
  if (n === 0) return '0';
  return n < 0.001 ? n.toExponential(2) : n.toFixed(4);
};

function VcfVariantTable({ prioritized, onVariantClick }) {
  const [expandedRows,   setExpandedRows]   = useState({});
  const [variantDetails, setVariantDetails] = useState({});
  const [loadingDetails, setLoadingDetails] = useState({});

  // Per-category state: { dangerous: { search: '', page: 0 }, ... }
  const [catState, setCatState] = useState(
    Object.fromEntries(Object.keys(categoryConfig).map(k => [k, { search: '', page: 0 }]))
  );

  const setSearch = (cat, value) =>
    setCatState(prev => ({ ...prev, [cat]: { search: value, page: 0 } }));

  const setPage = (cat, page) =>
    setCatState(prev => ({ ...prev, [cat]: { ...prev[cat], page } }));

  const toggleRow = async (variantId) => {
    const isExpanding = !expandedRows[variantId];
    setExpandedRows(prev => ({ ...prev, [variantId]: isExpanding }));
    if (isExpanding && !variantDetails[variantId]) {
      setLoadingDetails(prev => ({ ...prev, [variantId]: true }));
      try {
        const data = await onVariantClick(variantId);
        setVariantDetails(prev => ({ ...prev, [variantId]: data }));
      } catch (err) {
        console.error(err);
      } finally {
        setLoadingDetails(prev => ({ ...prev, [variantId]: false }));
      }
    }
  };

  const renderTable = (variants, categoryKey, rowOffset = 0) => {
    if (!variants || variants.length === 0) return null;
    const config = categoryConfig[categoryKey];
    const { search, page } = catState[categoryKey];

    // Filter by search term (variant ID or gene)
    const term = search.trim().toLowerCase();
    const filtered = term
      ? variants.filter(v =>
          v.variant?.toLowerCase().includes(term) ||
          v.gene?.toLowerCase().includes(term) ||
          v.location?.toLowerCase().includes(term) ||
          v.clinical_sig?.toLowerCase().includes(term)
        )
      : variants;

    const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
    const safePage   = Math.min(page, totalPages - 1);
    const pageSlice  = filtered.slice(safePage * PAGE_SIZE, (safePage + 1) * PAGE_SIZE);

    // Compute global row number for first item on current page
    const filteredOffset = term
      ? 0  // when searching, row numbers are relative to search results
      : rowOffset;

    return (
      <div key={categoryKey} style={{ marginBottom: '2rem' }}>
        {/* Category header + search bar */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: config.color, fontWeight: 600 }}>
            {config.icon}
            {config.label} ({variants.length})
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginLeft: 'auto',
                        background: 'var(--bg-main)', border: '1px solid var(--border-color)',
                        borderRadius: '6px', padding: '4px 8px' }}>
            <Search size={13} style={{ color: 'var(--text-secondary)' }} />
            <input
              type="text"
              placeholder="Search variant, gene…"
              value={search}
              onChange={e => setSearch(categoryKey, e.target.value)}
              style={{
                border: 'none', background: 'transparent', outline: 'none',
                fontSize: '0.8rem', color: 'var(--text-primary)', width: '170px'
              }}
            />
            {search && (
              <button onClick={() => setSearch(categoryKey, '')}
                style={{ background: 'transparent', border: 'none', cursor: 'pointer',
                         color: 'var(--text-secondary)', padding: 0, lineHeight: 1 }}>
                ✕
              </button>
            )}
          </div>
        </div>

        {filtered.length === 0 ? (
          <div style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', padding: '0.75rem' }}>
            No variants match "{search}"
          </div>
        ) : (
          <>
            <div style={{ overflowX: 'auto', borderRadius: '8px', border: '1px solid var(--border-color)', background: 'var(--bg-surface)' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                <thead style={{ background: 'var(--bg-body)', borderBottom: '1px solid var(--border-color)', textAlign: 'left' }}>
                  <tr>
                    <th style={{ padding: '0.75rem 1rem', width: '30px' }}></th>
                    <th style={{ padding: '0.75rem 0.5rem', width: '40px', color: 'var(--text-secondary)', fontWeight: 400, textAlign: 'center' }}>#</th>
                    <th style={{ padding: '0.75rem 1rem' }}>Variant ID</th>
                    <th style={{ padding: '0.75rem 1rem' }}>Gene</th>
                    <th style={{ padding: '0.75rem 1rem' }}>Location</th>
                    <th style={{ padding: '0.75rem 1rem' }}>Change</th>
                    <th style={{ padding: '0.75rem 1rem' }}>Clinical Sig.</th>
                    <th style={{ padding: '0.75rem 1rem' }}>Impact</th>
                    <th style={{ padding: '0.75rem 1rem' }}>Predictors</th>
                    <th style={{ padding: '0.75rem 1rem' }}>gnomAD AF</th>
                  </tr>
                </thead>
                <tbody>
                  {pageSlice.map((variant, localIdx) => {
                    const globalIdx = term
                      ? filtered.indexOf(variant)
                      : variants.indexOf(variant);
                    const globalRowNum = filteredOffset + globalIdx + 1;
                    const isExpanded = expandedRows[variant.variant];
                    const details    = variantDetails[variant.variant];
                    const isLoading  = loadingDetails[variant.variant];

                    return (
                      <React.Fragment key={variant.variant}>
                        <tr
                          onClick={() => toggleRow(variant.variant)}
                          style={{
                            borderBottom: '1px solid var(--border-color)',
                            cursor: 'pointer',
                            background: isExpanded ? 'var(--bg-body)' : 'transparent',
                            transition: 'background 0.2s'
                          }}
                          className="vcf-row-hover"
                        >
                          <td style={{ padding: '0.75rem 1rem', color: 'var(--text-secondary)' }}>
                            {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                          </td>
                          <td style={{ padding: '0.75rem 0.5rem', color: 'var(--text-secondary)', fontSize: '0.75rem', textAlign: 'center', fontFamily: 'monospace' }}>
                            #{globalRowNum}
                          </td>
                          <td style={{ padding: '0.75rem 1rem', fontWeight: 500, color: 'var(--primary)' }}>
                            {variant.variant}
                          </td>
                          <td style={{ padding: '0.75rem 1rem', fontStyle: 'italic' }}>
                            {variant.gene}
                          </td>
                          <td style={{ padding: '0.75rem 1rem', fontFamily: 'monospace', fontSize: '0.75rem' }}>
                            {variant.location}
                          </td>
                          <td style={{ padding: '0.75rem 1rem', fontFamily: 'monospace', fontSize: '0.75rem' }}>
                            {variant.ref_alt}
                          </td>
                          <td style={{ padding: '0.75rem 1rem' }}>
                            <span style={{
                              padding: '2px 8px', borderRadius: '12px', fontSize: '0.75rem',
                              background: config.bg, color: config.color, fontWeight: 500
                            }}>
                              {variant.clinical_sig || 'N/A'}
                            </span>
                          </td>
                          <td style={{ padding: '0.75rem 1rem' }}>
                            {variant.impact ? (
                              <span style={{
                                padding: '2px 8px', borderRadius: '12px', fontSize: '0.75rem', fontWeight: 500,
                                background: (IMPACT_COLORS[variant.impact] || IMPACT_COLORS.MODIFIER).bg,
                                color: (IMPACT_COLORS[variant.impact] || IMPACT_COLORS.MODIFIER).color,
                              }}>
                                {variant.impact}
                              </span>
                            ) : <span style={{ color: 'var(--text-secondary)' }}>—</span>}
                          </td>
                          <td style={{ padding: '0.75rem 1rem', fontSize: '0.75rem' }}>
                            {(() => {
                              const sift = expandPred(variant.sift, SIFT_LABELS);
                              const pp = expandPred(variant.polyphen, POLYPHEN_LABELS);
                              if (!sift && !pp) {
                                return (
                                  <span
                                    style={{ color: 'var(--text-secondary)' }}
                                    title="dbNSFP scores missense SNVs only, so indels and non-coding variants have none."
                                  >
                                    —
                                  </span>
                                );
                              }
                              return (
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                                  {sift && <span title="SIFT">SIFT: {sift}</span>}
                                  {pp && <span title="PolyPhen-2 HDIV">PolyPhen: {pp}</span>}
                                </div>
                              );
                            })()}
                          </td>
                          <td style={{ padding: '0.75rem 1rem', fontFamily: 'monospace', fontSize: '0.75rem' }}>
                            {formatAf(variant.af)}
                          </td>
                        </tr>

                        {isExpanded && (
                          <tr style={{ background: '#fcfcfc', borderBottom: `2px solid ${config.color}` }}>
                            <td colSpan={10} style={{ padding: 0 }}>
                              <div style={{ padding: '1rem', borderLeft: `3px solid ${config.color}` }}>
                                {isLoading ? (
                                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                                    <Info size={14} /> Loading rich annotations...
                                  </div>
                                ) : details ? (
                                  <VariantDetailsTabs data={details} />
                                ) : (
                                  <div style={{ color: '#EF4444', fontSize: '0.85rem' }}>Failed to load annotations.</div>
                                )}
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Pagination controls */}
            {totalPages > 1 && (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.75rem', marginTop: '0.5rem' }}>
                <button
                  onClick={() => setPage(categoryKey, safePage - 1)}
                  disabled={safePage === 0}
                  style={{
                    background: 'transparent', border: '1px solid var(--border-color)',
                    borderRadius: '6px', padding: '3px 10px', cursor: safePage === 0 ? 'not-allowed' : 'pointer',
                    color: safePage === 0 ? 'var(--text-secondary)' : 'var(--primary)', fontSize: '0.85rem'
                  }}
                >
                  ‹
                </button>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                  Page {safePage + 1} / {totalPages}
                  {term && ` (${filtered.length} results)`}
                </span>
                <button
                  onClick={() => setPage(categoryKey, safePage + 1)}
                  disabled={safePage >= totalPages - 1}
                  style={{
                    background: 'transparent', border: '1px solid var(--border-color)',
                    borderRadius: '6px', padding: '3px 10px',
                    cursor: safePage >= totalPages - 1 ? 'not-allowed' : 'pointer',
                    color: safePage >= totalPages - 1 ? 'var(--text-secondary)' : 'var(--primary)', fontSize: '0.85rem'
                  }}
                >
                  ›
                </button>
              </div>
            )}
          </>
        )}
      </div>
    );
  };

  const dangerousLen     = (prioritized.dangerous || []).length;
  const harmfulLen       = (prioritized.possibly_harmful || []).length;
  const vusLen           = (prioritized.vus || []).length;
  const unannotatedLen   = (prioritized.unannotated || []).length;

  return (
    <div className="vcf-table-container">
      {renderTable(prioritized.dangerous,        'dangerous',        0)}
      {renderTable(prioritized.possibly_harmful, 'possibly_harmful', dangerousLen)}
      {renderTable(prioritized.vus,              'vus',              dangerousLen + harmfulLen)}
      {renderTable(prioritized.unannotated,      'unannotated',      dangerousLen + harmfulLen + vusLen)}
      {renderTable(prioritized.benign,           'benign',           dangerousLen + harmfulLen + vusLen + unannotatedLen)}
    </div>
  );
}

export default VcfVariantTable;
