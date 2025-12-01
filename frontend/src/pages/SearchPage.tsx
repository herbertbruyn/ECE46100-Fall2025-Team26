import React, { useState } from 'react';
import { api } from '../services/api';
import { ArtifactCard } from '../components/ArtifactCard';
import { LoadingSpinner } from '../components/LoadingSpinner';
import { Toast } from '../components/Toast';
import type { Artifact } from '../types';
import { Search } from 'lucide-react';

export function SearchPage() {
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchType, setSearchType] = useState<'name' | 'regex'>('name');
  const [nameQuery, setNameQuery] = useState('');
  const [regexQuery, setRegexQuery] = useState('');
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' | 'info' } | null>(null);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      let results: Artifact[];
      if (searchType === 'name') {
        results = await api.searchArtifacts({ name: nameQuery });
      } else {
        results = await api.searchByRegex({ regex: regexQuery });
      }
      setArtifacts(results);
      setToast({
        message: `Found ${results.length} artifact(s)`,
        type: 'success',
      });
    } catch (error: any) {
      setToast({
        message: error.response?.data?.error || 'Search failed',
        type: 'error',
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '2rem' }}>
      <div style={{ marginBottom: '2rem' }}>
        <h1 style={{ fontSize: '2rem', fontWeight: 'bold', marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <Search size={32} color="var(--primary)" />
          Search Artifacts
        </h1>
        <p style={{ color: 'var(--text-secondary)' }}>
          Search by name (supports wildcards *) or by regex pattern
        </p>
      </div>

      <div style={{
        backgroundColor: 'var(--card-bg)',
        border: '1px solid var(--border)',
        borderRadius: '12px',
        padding: '1.5rem',
        marginBottom: '2rem',
      }}>
        <div style={{ display: 'flex', gap: '1rem', marginBottom: '1rem' }}>
          <button
            onClick={() => setSearchType('name')}
            style={{
              padding: '0.5rem 1rem',
              backgroundColor: searchType === 'name' ? 'var(--primary)' : 'transparent',
              color: searchType === 'name' ? 'white' : 'var(--text-secondary)',
              border: '1px solid var(--border)',
              borderRadius: '6px',
              cursor: 'pointer',
            }}
          >
            Name Search
          </button>
          <button
            onClick={() => setSearchType('regex')}
            style={{
              padding: '0.5rem 1rem',
              backgroundColor: searchType === 'regex' ? 'var(--primary)' : 'transparent',
              color: searchType === 'regex' ? 'white' : 'var(--text-secondary)',
              border: '1px solid var(--border)',
              borderRadius: '6px',
              cursor: 'pointer',
            }}
          >
            Regex Search
          </button>
        </div>

        <form onSubmit={handleSearch}>
          {searchType === 'name' ? (
            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', fontWeight: 500 }}>
                Artifact Name
              </label>
              <input
                type="text"
                value={nameQuery}
                onChange={(e) => setNameQuery(e.target.value)}
                placeholder="e.g., model* or *dataset"
                style={{
                  width: '100%',
                  padding: '0.75rem',
                  backgroundColor: 'var(--input-bg)',
                  border: '1px solid var(--border)',
                  borderRadius: '6px',
                  color: 'var(--text-primary)',
                  fontSize: '1rem',
                }}
                required
              />
              <p style={{ marginTop: '0.5rem', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
                Use * as wildcard (e.g., "model*" matches "model1", "model2")
              </p>
            </div>
          ) : (
            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', fontWeight: 500 }}>
                Regex Pattern
              </label>
              <input
                type="text"
                value={regexQuery}
                onChange={(e) => setRegexQuery(e.target.value)}
                placeholder="e.g., ^model[0-9]+$"
                style={{
                  width: '100%',
                  padding: '0.75rem',
                  backgroundColor: 'var(--input-bg)',
                  border: '1px solid var(--border)',
                  borderRadius: '6px',
                  color: 'var(--text-primary)',
                  fontSize: '1rem',
                  fontFamily: 'monospace',
                }}
                required
              />
              <p style={{ marginTop: '0.5rem', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
                Full regex support (e.g., "^model.*v[0-9]+" for versioned models)
              </p>
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            style={{
              padding: '0.75rem 1.5rem',
              backgroundColor: loading ? 'var(--border)' : 'var(--primary)',
              color: 'white',
              border: 'none',
              borderRadius: '6px',
              fontSize: '1rem',
              fontWeight: 500,
              cursor: loading ? 'not-allowed' : 'pointer',
              transition: 'all 0.2s',
            }}
          >
            {loading ? 'Searching...' : 'Search'}
          </button>
        </form>
      </div>

      {loading && <LoadingSpinner />}

      {!loading && artifacts.length > 0 && (
        <div>
          <h2 style={{ marginBottom: '1rem', fontSize: '1.25rem' }}>
            Results ({artifacts.length})
          </h2>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
            gap: '1.5rem',
          }}>
            {artifacts.map((artifact) => (
              <ArtifactCard key={artifact.id} artifact={artifact} />
            ))}
          </div>
        </div>
      )}

      {!loading && artifacts.length === 0 && nameQuery && (
        <div style={{
          textAlign: 'center',
          padding: '3rem',
          color: 'var(--text-secondary)',
        }}>
          <Search size={48} style={{ opacity: 0.5, marginBottom: '1rem' }} />
          <p>No artifacts found matching your search</p>
        </div>
      )}

      {toast && (
        <Toast
          message={toast.message}
          type={toast.type}
          onClose={() => setToast(null)}
        />
      )}
    </div>
  );
}