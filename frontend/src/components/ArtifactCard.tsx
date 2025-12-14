import { Link } from 'react-router-dom';
import { StatusBadge } from './StatusBadge';
import { formatBytes, formatDate } from '../utils/format';
import type { Artifact } from '../types';
import { Package, Calendar, HardDrive, User } from 'lucide-react';

interface ArtifactCardProps {
  artifact: Artifact;
}

export function ArtifactCard({ artifact }: ArtifactCardProps) {
  return (
    <Link
      to={`/artifact/${artifact.id}`}
      style={{
        display: 'block',
        backgroundColor: 'var(--card-bg)',
        border: '1px solid var(--border)',
        borderRadius: '12px',
        padding: '1.5rem',
        transition: 'all 0.2s',
        textDecoration: 'none',
        color: 'inherit',
      }}
      onMouseEnter={(e: React.MouseEvent<HTMLAnchorElement>) => {
        e.currentTarget.style.transform = 'translateY(-2px)';
        e.currentTarget.style.boxShadow = '0 4px 12px rgba(74, 144, 226, 0.2)';
      }}
      onMouseLeave={(e: React.MouseEvent<HTMLAnchorElement>) => {
        e.currentTarget.style.transform = 'translateY(0)';
        e.currentTarget.style.boxShadow = 'none';
      }}
    >
      <div style={{ display: 'flex', alignItems: 'start', justifyContent: 'space-between', marginBottom: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <Package size={24} color="var(--primary)" />
          <h3 style={{ margin: 0, fontSize: '1.125rem', fontWeight: 600 }}>{artifact.name}</h3>
        </div>
        <StatusBadge status={artifact.status} />
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span style={{
            padding: '0.25rem 0.5rem',
            backgroundColor: 'var(--primary-dark)',
            borderRadius: '4px',
            fontSize: '0.75rem',
            fontWeight: 500,
            textTransform: 'uppercase',
          }}>
            {artifact.type}
          </span>
        </div>

        {artifact.uploaded_by && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <User size={14} />
            <span>{artifact.uploaded_by}</span>
          </div>
        )}

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Calendar size={14} />
          <span>{formatDate(artifact.created_at)}</span>
        </div>

        {artifact.size_bytes && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <HardDrive size={14} />
            <span>{formatBytes(artifact.size_bytes)}</span>
          </div>
        )}
      </div>

      {artifact.status_message && artifact.status === 'failed' && (
        <div style={{
          marginTop: '1rem',
          padding: '0.75rem',
          backgroundColor: 'var(--error-bg, rgba(244, 67, 54, 0.1))',
          border: '1px solid var(--error)',
          borderRadius: '6px',
          fontSize: '0.875rem',
          color: 'var(--error)',
        }}>
          {artifact.status_message}
        </div>
      )}
    </Link>
  );
}

export default ArtifactCard;