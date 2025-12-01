import { useState, useEffect } from 'react';
import apiService from '../services/api';
import type { Artifact } from '../types';
import ArtifactCard from '../components/ArtifactCard';
import LoadingSpinner from '../components/LoadingSpinner';
import { useToast } from '../components/Toast';
import { Filter, RefreshCw } from 'lucide-react';

export default function BrowsePage() {
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [loading, setLoading] = useState(true);
  const [typeFilter, setTypeFilter] = useState<'all' | 'model' | 'dataset' | 'code'>('all');
  const toast = useToast();

  const loadArtifacts = async () => {
    setLoading(true);
    try {
      const data = await apiService.listArtifacts([{ name: '*' }]);
      setArtifacts(data);
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to load artifacts');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadArtifacts();
  }, []);

  const filteredArtifacts = typeFilter === 'all'
    ? artifacts
    : artifacts.filter(a => a.type === typeFilter);

  return (
    <div style={{
      maxWidth: '1400px',
      margin: '0 auto',
      padding: '2rem 1.5rem'
    }}>
      <toast.ToastContainer />
      
      {/* Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: '2rem',
        flexWrap: 'wrap',
        gap: '1rem'
      }}>
        <div>
          <h1 style={{ marginBottom: '0.5rem' }}>Browse Artifacts</h1>
          <p className="text-muted">
            {filteredArtifacts.length} {typeFilter === 'all' ? 'total' : typeFilter} artifacts
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          {/* Refresh Button */}
          <button
            onClick={loadArtifacts}
            className="btn btn-secondary"
            disabled={loading}
          >
            <RefreshCw size={18} />
            Refresh
          </button>
        </div>
      </div>

      {/* Filters */}
      <div style={{
        display: 'flex',
        gap: '0.5rem',
        marginBottom: '2rem',
        flexWrap: 'wrap'
      }}>
        <Filter size={20} style={{ color: 'var(--text-muted)', marginTop: '0.5rem' }} />
        {(['all', 'model', 'dataset', 'code'] as const).map((type) => (
          <button
            key={type}
            onClick={() => setTypeFilter(type)}
            className="btn btn-sm"
            style={{
              backgroundColor: typeFilter === type ? 'var(--accent-primary)' : 'var(--bg-tertiary)',
              color: typeFilter === type ? 'white' : 'var(--text-primary)'
            }}
          >
            {type.charAt(0).toUpperCase() + type.slice(1)}
          </button>
        ))}
      </div>

      {/* Content */}
      {loading ? (
        <LoadingSpinner text="Loading artifacts..." />
      ) : filteredArtifacts.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: '3rem' }}>
          <p className="text-muted">No artifacts found</p>
        </div>
      ) : (
        <div className="grid grid-cols-1" style={{ gap: '1rem' }}>
          {filteredArtifacts.map((artifact) => (
            <ArtifactCard key={artifact.id} artifact={artifact} />
          ))}
        </div>
      )}
    </div>
  );
}