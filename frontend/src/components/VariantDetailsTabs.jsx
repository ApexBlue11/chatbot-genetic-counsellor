import { useState } from 'react';
import { Download } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

function VariantDetailsTabs({ data }) {
  const [activeTab, setActiveTab] = useState('vep');

  if (!data || !data.raw_data) return null;
  const raw = data.raw_data;

  // Extract VEP data
  const vepData = raw.vep_data && raw.vep_data.length > 0 ? raw.vep_data[0] : null;
  const primaryTranscript = vepData?.transcript_consequences?.find(t => 
    t.flags?.includes('MANE_SELECT') || t.canonical === 1
  ) || vepData?.transcript_consequences?.[0];

  // Extract ClinVar data
  const clinvar = raw.clinvar_data || {};

  // Extract Predictors
  const mvData = raw.myvariant_data?.hits?.[0] || raw.myvariant_data || {};
  const dbnsfp = mvData?.dbnsfp || {};

  const getDbnsfpVal = (val) => {
    if (Array.isArray(val)) {
      const firstValid = val.find(v => v !== null && v !== undefined && v !== '');
      // If it's a number that got turned into a string array like '0.7890.789', it means it was stringified poorly somewhere, 
      // but usually MyVariant returns actual arrays of numbers/strings like [0.789, 0.789]
      if (typeof firstValid === 'number') return firstValid.toPrecision(3);
      return firstValid;
    }
    if (typeof val === 'number') return val.toPrecision(3);
    return val;
  };

  // Extract Freq dynamically across gnomad_genome, gnomad_exome, and exac
  const gg = mvData?.gnomad_genome || {};
  const ge = mvData?.gnomad_exome || {};
  const gg_af = gg.af || gg;
  const ge_af = ge.af || ge;

  const getAfVal = (key) => {
    return gg_af[key] ?? ge_af[key] ?? gg[key] ?? ge[key] ?? 0;
  };

  const freqData = [
    { name: 'Global', value: getAfVal('af') },
    { name: 'African', value: getAfVal('af_afr') || getAfVal('af_afr_raw') },
    { name: 'Latino', value: getAfVal('af_amr') || getAfVal('af_admixt') },
    { name: 'European (Non-Finnish)', value: getAfVal('af_nfe') },
    { name: 'European (Finnish)', value: getAfVal('af_fin') },
    { name: 'Ashkenazi Jewish', value: getAfVal('af_asj') },
    { name: 'East Asian', value: getAfVal('af_eas') },
    { name: 'South Asian', value: getAfVal('af_sas') },
  ].filter(d => d.value !== undefined && d.value !== null);

  // Check if it's an indel (length of ref/alt differ or contains del/ins)
  const isIndel = data.variant_id && (data.variant_id.includes('del') || data.variant_id.includes('ins') || (primaryTranscript?.amino_acids && primaryTranscript.amino_acids.includes('-')));

  const AMINO_ACIDS_MAP = {
    'A': 'Ala', 'R': 'Arg', 'N': 'Asn', 'D': 'Asp', 'C': 'Cys',
    'E': 'Glu', 'Q': 'Gln', 'G': 'Gly', 'H': 'His', 'I': 'Ile',
    'L': 'Leu', 'K': 'Lys', 'M': 'Met', 'F': 'Phe', 'P': 'Pro',
    'S': 'Ser', 'T': 'Thr', 'W': 'Trp', 'Y': 'Tyr', 'V': 'Val',
    'X': 'Term', '*': 'Term'
  };

  const formatAminoAcids = (aaStr) => {
    if (!aaStr) return 'N/A';
    if (aaStr.includes('/')) {
      const parts = aaStr.split('/');
      if (parts.length === 2) {
        const ref = AMINO_ACIDS_MAP[parts[0].toUpperCase()] || parts[0];
        const alt = AMINO_ACIDS_MAP[parts[1].toUpperCase()] || parts[1];
        return `${aaStr} (${ref} → ${alt})`;
      }
    }
    return aaStr;
  };

  const handleDownloadJSON = () => {
    const blob = new Blob([JSON.stringify(raw, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `variant_${data.variant_id}_raw.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="variant-details-tabs" style={{ marginTop: '1rem', border: '1px solid var(--border-color)', borderRadius: '8px', overflow: 'hidden' }}>
      <div className="tabs-header" style={{ display: 'flex', borderBottom: '1px solid var(--border-color)', backgroundColor: 'var(--bg-main)' }}>
        {['vep', 'clinvar', 'predictors', 'population'].map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: '0.75rem 1rem',
              border: 'none',
              background: activeTab === tab ? 'var(--bg-surface)' : 'transparent',
              color: activeTab === tab ? 'var(--primary)' : 'var(--text-secondary)',
              borderBottom: activeTab === tab ? '2px solid var(--primary)' : '2px solid transparent',
              cursor: 'pointer',
              fontWeight: activeTab === tab ? 600 : 400,
              flex: 1,
              textTransform: 'capitalize'
            }}
          >
            {tab}
          </button>
        ))}
      </div>

      <div className="tab-content" style={{ padding: '1rem', backgroundColor: 'var(--bg-surface)', fontSize: '0.85rem' }}>
        {activeTab === 'vep' && (
          <div>
            <h4 style={{ marginBottom: '0.5rem', color: 'var(--text-primary)' }}>Primary Transcript (Ensembl)</h4>
            {primaryTranscript ? (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div>
                  <div style={{ color: 'var(--text-secondary)' }}>Transcript ID</div>
                  <div>{primaryTranscript.transcript_id}</div>
                </div>
                <div>
                  <div style={{ color: 'var(--text-secondary)' }}>Gene Name</div>
                  <div style={{ fontWeight: 600 }}>{primaryTranscript.gene_symbol || 'N/A'}</div>
                </div>
                <div>
                  <div style={{ color: 'var(--text-secondary)' }}>Consequence</div>
                  <div style={{ textTransform: 'capitalize' }}>
                    {primaryTranscript.consequence_terms?.map(c => c.replace(/_/g, ' ')).join(', ')}
                  </div>
                </div>
                <div>
                  <div style={{ color: 'var(--text-secondary)' }}>Amino Acid Change</div>
                  <div>{formatAminoAcids(primaryTranscript.amino_acids)}</div>
                </div>
                <div>
                  <div style={{ color: 'var(--text-secondary)' }}>Impact</div>
                  <div>{primaryTranscript.impact || 'N/A'}</div>
                </div>
              </div>
            ) : <div>No VEP data available.</div>}
          </div>
        )}

        {activeTab === 'clinvar' && (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
              <h4 style={{ color: 'var(--text-primary)' }}>ClinVar Record</h4>
            </div>
            
            {/* Primary Summary Record */}
            {clinvar.clinical_significance ? (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', paddingBottom: '1rem', borderBottom: '1px solid var(--border)' }}>
                <div>
                  <div style={{ color: 'var(--text-secondary)' }}>Overall Clinical Significance</div>
                  <div style={{ fontWeight: 600, color: clinvar.clinical_significance.toLowerCase().includes('pathogenic') ? 'var(--error)' : 'var(--text-primary)' }}>
                    {clinvar.clinical_significance}
                  </div>
                </div>
                <div>
                  <div style={{ color: 'var(--text-secondary)' }}>Review Status</div>
                  <div>{clinvar.review_status || 'N/A'}</div>
                </div>
                <div style={{ gridColumn: '1 / -1' }}>
                  <div style={{ color: 'var(--text-secondary)' }}>Associated Conditions</div>
                  <div>
                    {clinvar.trait_set?.map(t => t.trait_name).join(', ') 
                      || (Array.isArray(mvData?.clinvar?.rcv) ? mvData.clinvar.rcv[0]?.conditions?.name : mvData?.clinvar?.rcv?.conditions?.name)
                      || 'N/A'}
                  </div>
                </div>
              </div>
            ) : (
              <div style={{ color: 'var(--text-secondary)' }}>No summary record available.</div>
            )}
            
            {/* Detailed Submissions from MyVariant */}
            {mvData?.clinvar?.rcv && (
              <div style={{ marginTop: '1rem' }}>
                <details>
                  <summary style={{ cursor: 'pointer', fontWeight: 600, color: 'var(--primary)' }}>View All Submissions ({Array.isArray(mvData.clinvar.rcv) ? mvData.clinvar.rcv.length : 1})</summary>
                  <div style={{ marginTop: '0.5rem', maxHeight: '200px', overflowY: 'auto', background: 'var(--surface-sunken)', padding: '0.5rem', borderRadius: '4px' }}>
                    {(Array.isArray(mvData.clinvar.rcv) ? mvData.clinvar.rcv : [mvData.clinvar.rcv])
                      .sort((a, b) => {
                        const score = (sig) => sig?.toLowerCase().includes('pathogenic') ? 1 : 0;
                        return score(b.clinical_significance) - score(a.clinical_significance);
                      })
                      .map((rcv, idx) => (
                      <div key={idx} style={{ marginBottom: '0.5rem', paddingBottom: '0.5rem', borderBottom: '1px solid var(--border)' }}>
                        <div style={{ fontWeight: 600 }}>
                          {rcv.clinical_significance} 
                          <span style={{ fontSize: '0.75rem', fontWeight: 400, marginLeft: '0.5rem', color: 'var(--text-secondary)'}}>
                            ({rcv.accession || 'N/A'})
                          </span>
                        </div>
                        <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                          Condition: {Array.isArray(rcv.conditions?.name) ? rcv.conditions.name.join(', ') : rcv.conditions?.name || 'N/A'}
                        </div>
                      </div>
                    ))}
                  </div>
                </details>
              </div>
            )}
          </div>
        )}

        {activeTab === 'predictors' && (
          <div>
            <h4 style={{ marginBottom: '0.5rem', color: 'var(--text-primary)' }}>Functional Predictors (dbNSFP)</h4>
            {Object.keys(dbnsfp).length > 0 ? (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div>
                  <div style={{ color: 'var(--text-secondary)' }}>SIFT Prediction</div>
                  <div>{getDbnsfpVal(dbnsfp.sift?.pred) || getDbnsfpVal(dbnsfp.sift_pred) || 'N/A'}</div>
                </div>
                <div>
                  <div style={{ color: 'var(--text-secondary)' }}>PolyPhen-2</div>
                  <div>{getDbnsfpVal(dbnsfp.polyphen2?.hdiv?.pred) || getDbnsfpVal(dbnsfp.polyphen2_hdiv_pred) || 'N/A'}</div>
                </div>
                <div>
                  <div style={{ color: 'var(--text-secondary)' }}>REVEL Score</div>
                  <div>{getDbnsfpVal(dbnsfp.revel?.score) || 'N/A'}</div>
                </div>
                <div>
                  <div style={{ color: 'var(--text-secondary)' }}>CADD Phred</div>
                  <div>{getDbnsfpVal(dbnsfp.cadd?.phred) || 'N/A'}</div>
                </div>
              </div>
            ) : (
              <div>
                <div style={{ color: 'var(--text-secondary)' }}>No dbNSFP predictors available.</div>
                {isIndel && (
                  <div style={{ marginTop: '0.5rem', padding: '0.75rem', background: '#FEF3C7', color: '#B45309', borderRadius: '4px', fontSize: '0.85rem' }}>
                    <strong>Note on Indels:</strong> Predictors like SIFT, PolyPhen, and REVEL are primarily trained on and calculate scores for Single Nucleotide Variants (SNVs). As this variant involves an insertion or deletion (Indel), these scores are generally not applicable or available.
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {activeTab === 'population' && (
          <div>
            <h4 style={{ marginBottom: '0.5rem', color: 'var(--text-primary)' }}>gnomAD Allele Frequencies</h4>
            {getAfVal('af') > 0 || freqData.some(d => d.value > 0) ? (
              <div style={{ height: 200, width: '100%', marginTop: '1rem' }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={freqData.filter(d => d.value > 0)} layout="vertical" margin={{ left: 20 }}>
                    <XAxis type="number" domain={[0, 'dataMax']} />
                    <YAxis dataKey="name" type="category" width={80} fontSize={12} fill="var(--text-secondary)" />
                    <Tooltip formatter={(value) => value.toExponential(3)} />
                    <Bar dataKey="value" fill="var(--primary)" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : <div style={{ color: 'var(--text-secondary)' }}>No population frequency data available for this variant.</div>}
          </div>
        )}
      </div>

      <div style={{ padding: '0.5rem 1rem', borderTop: '1px solid var(--border-color)', backgroundColor: 'var(--bg-main)', display: 'flex', justifyContent: 'flex-end' }}>
        <button 
          onClick={handleDownloadJSON}
          style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', background: 'transparent', border: '1px solid var(--border-color)', padding: '0.25rem 0.75rem', borderRadius: '4px', cursor: 'pointer', color: 'var(--text-primary)', fontSize: '0.75rem' }}
        >
          <Download size={14} /> Download Raw JSON
        </button>
      </div>
    </div>
  );
}

export default VariantDetailsTabs;
