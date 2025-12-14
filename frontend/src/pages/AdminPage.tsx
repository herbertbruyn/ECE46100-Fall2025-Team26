// src/pages/AdminPage.tsx
import { useState, useEffect } from 'react';
import { Shield, Trash2, Activity, AlertTriangle } from 'lucide-react';
import apiService from '../services/api';
import { useToast } from '../components/Toast';
import type { HealthStatus } from '../types';

export default function AdminPage() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [resetting, setResetting] = useState(false);
  const toast = useToast();

  useEffect(() => {
    loadHealth();
  }, []);

  const loadHealth = async () => {
    try {
      const data = await apiService.getHealth();
      setHealth(data);
    } catch (error) {
      toast.error('Failed to load health status');
    }
  };

  const handleReset = async () => {
    if (!window.confirm(
      '⚠️ WARNING: This will DELETE ALL artifacts and reset the entire registry!\n\n' +
      'This action CANNOT be undone.\n\nAre you absolutely sure?'
    )) return;

    if (!window.confirm('Last chance! Are you REALLY sure you want to reset the registry?')) return;

    setResetting(true);
    try {
      await apiService.resetRegistry();
      toast.success('Registry reset successfully');
      setTimeout(() => window.location.href = '/', 1500);
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to reset registry');
    } finally {
      setResetting(false);
    }
  };

  return (
    <div style={{ maxWidth: '1000px', margin: '0 auto', padding: '2rem 1.5rem' }}>
      <toast.ToastContainer />
      
      <div style={{ marginBottom: '2rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
          <Shield size={32} color="var(--warning)" />
          <h1>Admin Panel</h1>
        </div>
        <p className="text-muted">Manage your Model Registry instance</p>
      </div>

      {/* Health Status */}
      <div className="card" style={{ marginBottom: '2rem' }}>
        <h3 style={{ marginBottom: '1rem' }}>System Health</h3>
        
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1rem' }}>
          <Activity size={24} color={health?.status === 'ok' ? 'var(--success)' : 'var(--error)'} />
          <div>
            <p className="font-semibold">
              Status: {health?.status?.toUpperCase() || 'Unknown'}
            </p>
            <button onClick={loadHealth} className="btn btn-sm btn-secondary" style={{ marginTop: '0.5rem' }}>
              Refresh Status
            </button>
          </div>
        </div>

        {health?.components && (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(2, 1fr)',
            gap: '1rem',
            marginTop: '1rem'
          }}>
            {Object.entries(health.components).map(([component, status]) => (
              <div key={component} style={{
                padding: '1rem',
                backgroundColor: 'var(--bg-tertiary)',
                borderRadius: 'var(--radius-md)'
              }}>
                <p className="text-sm text-muted">{component}</p>
                <p className="font-medium">{status}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Danger Zone */}
      <div className="card" style={{
        borderColor: 'var(--error)',
        borderWidth: '2px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem' }}>
          <AlertTriangle size={24} color="var(--error)" />
          <h3 style={{ color: 'var(--error)' }}>Danger Zone</h3>
        </div>

        <div style={{
          padding: '1.5rem',
          backgroundColor: 'rgba(239, 68, 68, 0.1)',
          borderRadius: 'var(--radius-md)',
          border: '1px solid rgba(239, 68, 68, 0.3)'
        }}>
          <h4 style={{ marginBottom: '0.5rem' }}>Reset Registry</h4>
          <p className="text-sm text-muted" style={{ marginBottom: '1rem' }}>
            This will permanently delete all artifacts, ratings, and metadata. 
            This action cannot be undone.
          </p>
          
          <button
            onClick={handleReset}
            className="btn btn-danger"
            disabled={resetting}
          >
            {resetting ? (
              <>
                <div className="spinner" style={{ width: '1rem', height: '1rem' }} />
                Resetting...
              </>
            ) : (
              <>
                <Trash2 size={18} />
                Reset Entire Registry
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}