// src/pages/ArtifactDetailPage.tsx
import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { 
  Download, Edit, Trash2, DollarSign, ArrowLeft, 
  ExternalLink, Calendar, Hash, HardDrive, GitBranch, Shield
} from 'lucide-react';
import apiService from '../services/api';
import type { Artifact, ModelRating, CostResult } from '../types';
import StatusBadge from '../components/StatusBadge';
import MetricsDisplay from '../components/MetricsDisplay';
import LoadingSpinner from '../components/LoadingSpinner';
import LicenseCheck from '../components/LicenseCheck';
import LineageGraph from '../components/LineageGraph';
import { useToast } from '../components/Toast';
import { useAuth } from '../contexts/AuthContext';
import { formatBytes, formatDate } from '../utils/format';

export default function ArtifactDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [artifact, setArtifact] = useState<Artifact | null>(null);
  const [rating, setRating] = useState<ModelRating | null>(null);
  const [cost, setCost] = useState<CostResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingCost, setLoadingCost] = useState(false);
  const [deleting, setDeleting] = useState(false);
  
  const navigate = useNavigate();
  const toast = useToast();
  const { user } = useAuth();

  useEffect(() => {
    loadArtifact();
  }, [id]);

  const loadArtifact = async () => {
    if (!id) return;
    
    try {
      // Try to get artifact by ID - we'll need to try different types
      // First try model, then dataset, then code
      let data: Artifact | null = null;
      let artifactType: string = 'model';
      
      for (const type of ['model', 'dataset', 'code'] as const) {
        try {
          data = await apiService.getArtifact(type, Number(id));
          artifactType = type;
          break;
        } catch (err) {
          // Try next type
          continue;
        }
      }
      
      if (!data) {
        throw new Error('Artifact not found');
      }
      
      setArtifact(data);

      // Load rating for models
      if (artifactType === 'model' && data.status === 'completed') {
        try {
          const ratingData = await apiService.getModelRating(Number(id));
          setRating(ratingData);
        } catch (err) {
          console.error('Failed to load rating:', err);
        }
      }
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to load artifact');
      navigate('/');
    } finally {
      setLoading(false);
    }
  };

  const loadCost = async () => {
    if (!artifact) return;
    setLoadingCost(true);
    try {
      const costData = await apiService.calculateCost(artifact.type as any, artifact.id);
      setCost(costData);
      toast.success('Cost calculated successfully');
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to calculate cost');
    } finally {
      setLoadingCost(false);
    }
  };

  const handleDelete = async () => {
    if (!artifact || !window.confirm('Are you sure you want to delete this artifact?')) return;
    
    setDeleting(true);
    try {
      await apiService.deleteArtifact(artifact.type as any, artifact.id);
      toast.success('Artifact deleted successfully');
      navigate('/');
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to delete artifact');
    } finally {
      setDeleting(false);
    }
  };

  const handleDownload = () => {
    if (!artifact) return;
    const url = apiService.getDownloadUrl(artifact);
    if (url) {
      window.open(url, '_blank');
    } else {
      toast.error('Download URL not available');
    }
  };

  const canModify = user?.is_admin || artifact?.uploaded_by === user?.name;

  if (loading) {
    return <LoadingSpinner text="Loading artifact..." />;
  }

  if (!artifact) {
    return <div>Artifact not found</div>;
  }

  return (
    <div style={{ maxWidth: '1400px', margin: '0 auto', padding: '2rem 1.5rem' }}>
      <toast.ToastContainer />
      
      {/* Back Button */}
      <Link to="/" className="btn btn-secondary btn-sm" style={{ marginBottom: '1.5rem', display: 'inline-flex' }}>
        <ArrowLeft size={16} />
        Back to Browse
      </Link>

      {/* Header */}
      <div className="card" style={{ marginBottom: '2rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', gap: '1rem', flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
              <h1 style={{ fontSize: '2rem', wordBreak: 'break-word' }}>{artifact.name}</h1>
              <StatusBadge status={artifact.status} />
            </div>
            
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
              <span className="badge badge-info">{artifact.type}</span>
              {artifact.version && <span className="badge">{artifact.version}</span>}
            </div>

            <a 
              href={artifact.source_url} 
              target="_blank" 
              rel="noopener noreferrer"
              style={{ display: 'inline-flex', alignItems: 'center', gap: '0.375rem', fontSize: '0.875rem' }}
            >
              <ExternalLink size={14} />
              {artifact.source_url}
            </a>
          </div>

          {/* Action Buttons */}
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            {artifact.blob && (
              <button onClick={handleDownload} className="btn btn-primary">
                <Download size={18} />
                Download
              </button>
            )}
            {canModify && (
              <>
                <button className="btn btn-secondary">
                  <Edit size={18} />
                  Update
                </button>
                <button onClick={handleDelete} className="btn btn-danger" disabled={deleting}>
                  <Trash2 size={18} />
                  Delete
                </button>
              </>
            )}
            <button onClick={loadCost} className="btn btn-secondary" disabled={loadingCost}>
              <DollarSign size={18} />
              {loadingCost ? 'Calculating...' : 'Calculate Cost'}
            </button>
            {artifact.type === 'model' && (
              <a 
                href="#lineage" 
                className="btn btn-secondary"
                onClick={(e) => {
                  e.preventDefault();
                  document.getElementById('lineage-section')?.scrollIntoView({ behavior: 'smooth' });
                }}
              >
                <GitBranch size={18} />
                View Lineage
              </a>
            )}
            {artifact.type === 'model' && artifact.status === 'completed' && (
              <a 
                href="#license-check" 
                className="btn btn-secondary"
                onClick={(e) => {
                  e.preventDefault();
                  document.getElementById('license-check-section')?.scrollIntoView({ behavior: 'smooth' });
                }}
              >
                <Shield size={18} />
                License Check
              </a>
            )}
          </div>
        </div>
      </div>

      {/* Details Grid */}
      <div className="grid grid-cols-2" style={{ gap: '1.5rem', marginBottom: '2rem' }}>
        {/* Metadata Card */}
        <div className="card">
          <h3 style={{ marginBottom: '1rem' }}>Details</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            <DetailRow icon={<Calendar size={16} />} label="Created" value={formatDate(artifact.created_at)} />
            <DetailRow icon={<Calendar size={16} />} label="Updated" value={formatDate(artifact.updated_at)} />
            {artifact.size_bytes && (
              <DetailRow icon={<HardDrive size={16} />} label="Size" value={formatBytes(artifact.size_bytes)} />
            )}
            {artifact.sha256 && (
              <DetailRow icon={<Hash size={16} />} label="SHA256" value={artifact.sha256.substring(0, 16) + '...'} />
            )}
            {artifact.uploaded_by && (
              <DetailRow label="Uploaded By" value={artifact.uploaded_by} />
            )}
          </div>
        </div>

        {/* Dependencies Card */}
        {(artifact.dataset_name || artifact.code_name) && (
          <div className="card">
            <h3 style={{ marginBottom: '1rem' }}>Dependencies</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {artifact.dataset_name && (
                <div>
                  <p className="text-sm text-muted">Dataset</p>
                  <p className="font-medium">{artifact.dataset_name}</p>
                </div>
              )}
              {artifact.code_name && (
                <div>
                  <p className="text-sm text-muted">Code</p>
                  <p className="font-medium">{artifact.code_name}</p>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Cost Result */}
      {cost && (
        <div className="card" style={{ marginBottom: '2rem' }}>
          <h3 style={{ marginBottom: '1rem' }}>Cost Estimates</h3>
          <div className="grid grid-cols-4" style={{ gap: '1rem' }}>
            {Object.entries(cost).map(([platform, costs]) => (
              <div key={platform} style={{
                padding: '1rem',
                backgroundColor: 'var(--bg-tertiary)',
                borderRadius: 'var(--radius-md)'
              }}>
                <p className="text-sm text-muted">{platform.replace('_', ' ')}</p>
                <p className="text-xl font-semibold">${costs.total_cost.toFixed(2)}</p>
                <p className="text-xs text-muted">Standby: ${costs.standby.toFixed(2)}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Metrics (for models) */}
      {artifact.type === 'model' && rating && (
        <MetricsDisplay rating={rating} />
      )}

      {/* License Check (for models) */}
      {artifact.type === 'model' && artifact.status === 'completed' && (
        <div id="license-check-section">
          <LicenseCheck modelId={artifact.id} />
        </div>
      )}

      {/* Lineage Graph (for models) */}
      {artifact.type === 'model' && (
        <div id="lineage-section">
          <LineageGraph modelId={artifact.id} />
        </div>
      )}

      {/* Status Message */}
      {artifact.status_message && (
        <div className="card" style={{ marginTop: '2rem' }}>
          <h3 style={{ marginBottom: '0.5rem' }}>Status Message</h3>
          <p className="text-sm" style={{
            padding: '0.75rem',
            backgroundColor: 'var(--bg-tertiary)',
            borderRadius: 'var(--radius-md)'
          }}>
            {artifact.status_message}
          </p>
        </div>
      )}
    </div>
  );
}

function DetailRow({ icon, label, value }: { icon?: React.ReactNode; label: string; value: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
      {icon && <span style={{ color: 'var(--text-muted)' }}>{icon}</span>}
      <span className="text-sm text-muted" style={{ minWidth: '100px' }}>{label}:</span>
      <span className="text-sm font-medium">{value}</span>
    </div>
  );
}