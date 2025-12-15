import React, { useState } from 'react';
import { Shield, AlertCircle, CheckCircle, Loader, Github } from 'lucide-react';
import apiService from '../services/api';

interface LicenseCheckProps {
  modelId: number;
}

export function LicenseCheck({ modelId }: LicenseCheckProps) {
  const [githubUrl, setGithubUrl] = useState('');
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleCheck = async () => {
    if (!githubUrl.trim()) {
      setError('Please enter a GitHub URL');
      return;
    }

    // Basic URL validation
    if (!githubUrl.includes('github.com')) {
      setError('Please enter a valid GitHub URL');
      return;
    }

    setChecking(true);
    setError(null);
    setResult(null);

    try {
      const compatible = await apiService.checkLicenseCompatibility(modelId, githubUrl);
      setResult(compatible);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to check license compatibility');
      setResult(null);
    } finally {
      setChecking(false);
    }
  };

  const handleReset = () => {
    setGithubUrl('');
    setResult(null);
    setError(null);
  };

  return (
    <div style={{
      backgroundColor: 'var(--card-bg)',
      border: '1px solid var(--border)',
      borderRadius: '12px',
      padding: '1.5rem',
      marginTop: '1.5rem',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem' }}>
        <Shield size={24} color="var(--primary)" />
        <h3 style={{ fontSize: '1.25rem', fontWeight: 600 }}>License Compatibility Check</h3>
      </div>

      <p style={{ color: 'var(--text-secondary)', marginBottom: '1.5rem', fontSize: '0.875rem' }}>
        Check if this model's license is compatible with your GitHub repository for fine-tuning and inference.
      </p>

      <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1rem' }}>
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.75rem', backgroundColor: 'var(--input-bg)', borderRadius: '8px', border: '1px solid var(--border)' }}>
          <Github size={18} color="var(--text-secondary)" />
          <input
            type="text"
            value={githubUrl}
            onChange={(e) => {
              setGithubUrl(e.target.value);
              setError(null);
              setResult(null);
            }}
            placeholder="https://github.com/owner/repo"
            style={{
              flex: 1,
              border: 'none',
              background: 'transparent',
              color: 'var(--text-primary)',
              fontSize: '0.875rem',
              outline: 'none',
            }}
            disabled={checking}
          />
        </div>
        <button
          onClick={handleCheck}
          disabled={checking || !githubUrl.trim()}
          style={{
            padding: '0.75rem 1.5rem',
            backgroundColor: checking || !githubUrl.trim() ? 'var(--border)' : 'var(--primary)',
            color: 'white',
            border: 'none',
            borderRadius: '8px',
            fontSize: '0.875rem',
            fontWeight: 600,
            cursor: checking || !githubUrl.trim() ? 'not-allowed' : 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            transition: 'background-color 0.2s',
          }}
        >
          {checking ? (
            <>
              <Loader size={16} style={{ animation: 'spin 1s linear infinite' }} />
              Checking...
            </>
          ) : (
            'Check License'
          )}
        </button>
        {result !== null && (
          <button
            onClick={handleReset}
            style={{
              padding: '0.75rem 1rem',
              backgroundColor: 'var(--bg-tertiary)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border)',
              borderRadius: '8px',
              fontSize: '0.875rem',
              cursor: 'pointer',
            }}
          >
            Reset
          </button>
        )}
      </div>

      {error && (
        <div style={{
          padding: '1rem',
          backgroundColor: 'rgba(239, 68, 68, 0.1)',
          border: '1px solid rgba(239, 68, 68, 0.3)',
          borderRadius: '8px',
          marginBottom: '1rem',
          display: 'flex',
          alignItems: 'center',
          gap: '0.75rem',
        }}>
          <AlertCircle size={20} color="#ef4444" />
          <span style={{ color: '#ef4444', fontSize: '0.875rem' }}>{error}</span>
        </div>
      )}

      {result !== null && (
        <div style={{
          padding: '1.5rem',
          backgroundColor: result ? 'rgba(34, 197, 94, 0.1)' : 'rgba(239, 68, 68, 0.1)',
          border: `1px solid ${result ? 'rgba(34, 197, 94, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`,
          borderRadius: '8px',
          display: 'flex',
          alignItems: 'center',
          gap: '0.75rem',
        }}>
          {result ? (
            <>
              <CheckCircle size={24} color="#22c55e" />
              <div>
                <p style={{ color: '#22c55e', fontWeight: 600, marginBottom: '0.25rem' }}>
                  Licenses are Compatible
                </p>
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                  This model's license is compatible with the GitHub repository. You can proceed with fine-tuning and inference.
                </p>
              </div>
            </>
          ) : (
            <>
              <AlertCircle size={24} color="#ef4444" />
              <div>
                <p style={{ color: '#ef4444', fontWeight: 600, marginBottom: '0.25rem' }}>
                  Licenses are Incompatible
                </p>
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                  This model's license may not be compatible with the GitHub repository. Please review the license terms before proceeding.
                </p>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

export default LicenseCheck;

