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
                        </tr>

                        {isExpanded && (
                          <tr style={{ background: '#fcfcfc', borderBottom: `2px solid ${config.color}` }}>
                            <td colSpan={7} style={{ padding: 0 }}>
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
