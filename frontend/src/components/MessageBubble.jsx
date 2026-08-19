import { ChevronDown, ChevronUp, X, Loader2 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useState, useEffect } from 'react';
import rehypeRaw from 'rehype-raw';
import VariantDetailsTabs from './VariantDetailsTabs';
import api from '../services/api';
import VcfVariantTable from './VcfVariantTable';

function MessageBubble({ message }) {
  const { role, content, metadata } = message;
  const isUser = role === 'user';
  // Strip system context from user message if it accidentally got saved to DB
  const displayContent = isUser && content ? content.replace(/\[SYSTEM CONTEXT:[\s\S]*?\]/g, '').trim() : content;
  
  // VCF Modal State
  const [modalVariantId, setModalVariantId] = useState(null);
  const [modalData, setModalData] = useState(null);
  const [modalLoading, setModalLoading] = useState(false);

  useEffect(() => {
    if (modalVariantId) {
      setModalLoading(true);
      setModalData(null);
      api.getVariantDetails(modalVariantId)
        .then(data => setModalData(data))
        .catch(err => console.error(err))
        .finally(() => setModalLoading(false));
    }
  }, [modalVariantId]);

  const handleVariantClick = (id) => {
    if (id && id.startsWith('rs')) {
      setModalVariantId(id);
    }
  };

  const renderMetadata = () => {
    if (!metadata) return null;

    if (metadata.type === 'variant_analysis') {
      return (
        <div className="message-metadata">
          {metadata.literature && metadata.literature.length > 0 && (
            <div style={{ marginBottom: '1rem', paddingBottom: '1rem', borderBottom: '1px solid var(--border-color)' }}>
              <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.5rem' }}>
                📚 Literature References
                {/* A gene-level fallback search is background reading, not evidence
                    about this variant. Saying which one the reader is looking at
                    is the difference between a citation and a lead. */}
                <span style={{ fontWeight: 400, color: 'var(--text-secondary)', marginLeft: '0.4rem' }}>
                  {metadata.literature[0]?.scope === 'gene'
                    ? '— recent papers on the gene; none are linked to this variant'
                    : '— linked to this variant in dbSNP'}
                </span>
              </div>
              <ul style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', paddingLeft: '1.25rem' }}>
                {metadata.literature.map((p, i) => (
                  <li key={i}><a href={p.link} target="_blank" rel="noreferrer" style={{color: 'var(--primary)', textDecoration: 'none'}}>{p.title}</a> - {p.journal}</li>
                ))}
              </ul>
            </div>
          )}
          
          {metadata.raw_data && (
            <VariantDetailsTabs data={metadata} />
          )}
        </div>
      );
    }

    if (metadata.type === 'pedigree_chart') {
      // Charts are vector SVG. Rendering through a data: URI in an <img> keeps
      // the model-supplied names inert while staying sharp at any zoom.
      // image_base64 is the legacy PNG field, still present on older messages.
      const chartSrc = metadata.svg
        ? `data:image/svg+xml;charset=utf-8,${encodeURIComponent(metadata.svg)}`
        : metadata.image_base64
          ? `data:image/png;base64,${metadata.image_base64}`
          : null;

      return (
        <div className="message-metadata" style={{ textAlign: 'center' }}>
          <div style={{ marginBottom: '1rem', fontWeight: 600 }}>🧬 Generated Pedigree Chart</div>
          <div style={{ padding: '1rem', backgroundColor: '#F1F5F9', borderRadius: '8px' }}>
            {chartSrc ? (
              <img
                src={chartSrc}
                alt="Pedigree chart"
                style={{ maxWidth: '100%', height: 'auto', borderRadius: '4px', border: '1px solid #E2E8F0', background: '#fff' }}
              />
            ) : (
              <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                Chart generation failed. Backend returned structural data only.
              </span>
            )}
            <details style={{ textAlign: 'left', marginTop: '1rem' }}>
              <summary style={{ fontSize: '0.8rem', color: 'var(--primary)', cursor: 'pointer' }}>View Raw Data</summary>
              <pre style={{ fontSize: '0.75rem', marginTop: '0.5rem', maxHeight: '200px', overflowY: 'auto', background: '#fff', color: '#1E293B', padding: '0.5rem', borderRadius: '4px' }}>
                {JSON.stringify(metadata.pedigree_data, null, 2)}
              </pre>
            </details>
          </div>
        </div>
      );
    }

    if (metadata.type === 'vcf_analysis') {
       return (
         <div className="message-metadata" style={{ padding: '1.5rem', background: '#fff' }}>
           <div style={{ fontWeight: 600, marginBottom: '1rem', fontSize: '1.1rem' }}>📊 VCF Prioritization</div>
           <div style={{ marginBottom: '1.5rem', color: 'var(--text-secondary)' }}>{metadata.summary}</div>
           <VcfVariantTable 
             prioritized={metadata.prioritized} 
             onVariantClick={api.getVariantDetails} 
           />
         </div>
       )
    }

    return null;
  };

  return (
    <div className={`msg ${isUser ? 'msg--user' : 'msg--assistant'}`}>
      {/* The assistant is marked by the same orb the thinking indicator pulses
          with, so the finished reply lands under the mark the reader was just
          watching. The user's own turns need no mark: they are the ones the
          bubble aligns right, and a second filled square only added noise. */}
      <div className="msg-head">
        {!isUser && (
          <span className="msg-orb" aria-hidden="true">
            <span className="msg-orb-core" />
            <span className="msg-orb-ring" />
          </span>
        )}
        <span className="msg-who">{isUser ? 'You' : 'VariantMind'}</span>
      </div>
      <div className="message-content">
        
        {content && (
           <div className="markdown-body" style={{ color: 'var(--text-primary)' }}>
             <ReactMarkdown 
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeRaw]}
            components={{
              table: ({node, ...props}) => <table className="markdown-table" {...props} />,
              td: ({node, children, ...props}) => {
                const text = String(children);
                // If this is an rsID, wrap in click handler
                if (text && text.startsWith('rs')) {
                  return (
                    <td {...props}>
                      <span 
                        className="variant-link" 
                        onClick={() => handleVariantClick(text)}
                        style={{ color: 'var(--primary)', cursor: 'pointer', textDecoration: 'underline' }}
                      >
                        {text}
                      </span>
                    </td>
                  );
                }
                return <td {...props}>{children}</td>;
              }
            }}
          >
            {displayContent}
          </ReactMarkdown>
           </div>
        )}
        
        {renderMetadata()}
      </div>

      {/* VCF Variant Modal */}
      {modalVariantId && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.5)', zIndex: 9999,
          display: 'flex', alignItems: 'center', justifyContent: 'center'
        }} onClick={() => setModalVariantId(null)}>
          <div style={{
            background: 'var(--bg-surface)', width: '80%', maxWidth: '800px', 
            maxHeight: '90vh', overflowY: 'auto', borderRadius: '12px',
            padding: '1.5rem', boxShadow: 'var(--shadow-md)', position: 'relative'
          }} onClick={e => e.stopPropagation()}>
            <button onClick={() => setModalVariantId(null)} style={{ position: 'absolute', top: '1rem', right: '1rem', background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)' }}>
              <X size={20} />
            </button>
            <h3 style={{ marginBottom: '1rem', color: 'var(--text-primary)' }}>Variant Explorer: {modalVariantId}</h3>
            
            {modalLoading ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-secondary)' }}>
                <Loader2 size={16} className="animate-spin" /> Fetching detailed annotations...
              </div>
            ) : modalData ? (
              <VariantDetailsTabs data={modalData} />
            ) : (
              <div style={{ color: 'var(--text-secondary)' }}>Failed to load variant details.</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default MessageBubble;
