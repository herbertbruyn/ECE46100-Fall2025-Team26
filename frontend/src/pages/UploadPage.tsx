import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import apiService from '../services/api';
import type { ArtifactType } from '../types';
import { useToast } from '../components/Toast';
import { Upload, Link as LinkIcon, Package, Database, Code as CodeIcon } from 'lucide-react';

export default function UploadPage() {
  const [type, setType] = useState<ArtifactType>('model');
  const [url, setUrl] = useState('');
  const [revision, setRevision] = useState('main');
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState('');
  
  const navigate = useNavigate();
  const toast = useToast();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setUploading(true);
    setProgress('Uploading artifact...');

    try {
      const response = await apiService.uploadArtifact(type, url, revision);
      
      if (response.status === 'disqualified') {
        toast.warning('Artifact rejected: Rating below threshold');
      } else {
        toast.success('Artifact uploaded successfully!');
        navigate(`/artifact/${type}/${response.metadata.id}`);
      }
    } catch (error: any) {
      const message = error.response?.data?.error || error.response?.data?.detail || 'Upload failed';
      toast.error(message);
    } finally {
      setUploading(false);
      setProgress('');
    }
  };

  return (
    <div style={{
      maxWidth: '800px',
      margin: '0 auto',
      padding: '2rem 1.5rem'
    }}>
      <toast.ToastContainer />
      
      <div style={{ marginBottom: '2rem' }}>
        <h1 style={{ marginBottom: '0.5rem' }}>Upload Artifact</h1>
        <p className="text-muted">
          Upload a new model, dataset, or code artifact from HuggingFace
        </p>
      </div>

      <form onSubmit={handleSubmit} className="card">
        {/* Type Selection */}
        <div style={{ marginBottom: '1.5rem' }}>
          <label className="text-sm font-medium" style={{ display: 'block', marginBottom: '0.75rem' }}>
            Artifact Type
          </label>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.75rem' }}>
            <TypeCard
              icon={<Package size={24} />}
              label="Model"
              selected={type === 'model'}
              onClick={() => setType('model')}
            />
            <TypeCard
              icon={<Database size={24} />}
              label="Dataset"
              selected={type === 'dataset'}
              onClick={() => setType('dataset')}
            />
            <TypeCard
              icon={<CodeIcon size={24} />}
              label="Code"
              selected={type === 'code'}
              onClick={() => setType('code')}
            />
          </div>
        </div>

        {/* URL Input */}
        <div style={{ marginBottom: '1.5rem' }}>
          <label className="text-sm font-medium" style={{ display: 'block', marginBottom: '0.5rem' }}>
            HuggingFace URL *
          </label>
          <div style={{ position: 'relative' }}>
            <LinkIcon
              size={18}
              style={{
                position: 'absolute',
                left: '1rem',
                top: '50%',
                transform: 'translateY(-50%)',
                color: 'var(--text-muted)'
              }}
            />
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              className="input"
              style={{ paddingLeft: '3rem' }}
              placeholder={`https://huggingface.co/${type === 'dataset' ? 'datasets/' : ''}username/${type}-name`}
              required
            />
          </div>
          <p className="text-xs text-muted" style={{ marginTop: '0.375rem' }}>
            Enter the full HuggingFace URL for the {type}
          </p>
        </div>

        {/* Revision Input */}
        <div style={{ marginBottom: '2rem' }}>
          <label className="text-sm font-medium" style={{ display: 'block', marginBottom: '0.5rem' }}>
            Revision (optional)
          </label>
          <input
            type="text"
            value={revision}
            onChange={(e) => setRevision(e.target.value)}
            className="input"
            placeholder="main"
          />
          <p className="text-xs text-muted" style={{ marginTop: '0.375rem' }}>
            Git branch, tag, or commit hash (defaults to 'main')
          </p>
        </div>

        {/* Progress */}
        {uploading && progress && (
          <div style={{
            padding: '1rem',
            backgroundColor: 'var(--bg-tertiary)',
            borderRadius: 'var(--radius-md)',
            marginBottom: '1.5rem',
            textAlign: 'center'
          }}>
            <div className="spinner" style={{ marginBottom: '0.5rem' }} />
            <p className="text-sm text-muted">{progress}</p>
            <p className="text-xs text-muted" style={{ marginTop: '0.25rem' }}>
              This may take several minutes for large artifacts...
            </p>
          </div>
        )}

        {/* Submit Button */}
        <button
          type="submit"
          className="btn btn-primary w-full"
          disabled={uploading}
        >
          {uploading ? (
            <>
              <div className="spinner" style={{ width: '1rem', height: '1rem' }} />
              Uploading...
            </>
          ) : (
            <>
              <Upload size={18} />
              Upload {type.charAt(0).toUpperCase() + type.slice(1)}
            </>
          )}
        </button>
      </form>
    </div>
  );
}

function TypeCard({
  icon,
  label,
  selected,
  onClick
}: {
  icon: React.ReactNode;
  label: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        padding: '1.25rem',
        border: `2px solid ${selected ? 'var(--accent-primary)' : 'var(--border-color)'}`,
        borderRadius: 'var(--radius-md)',
        backgroundColor: selected ? 'rgba(59, 130, 246, 0.1)' : 'var(--bg-tertiary)',
        cursor: 'pointer',
        transition: 'all 0.2s',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '0.5rem'
      }}
    >
      <div style={{ color: selected ? 'var(--accent-primary)' : 'var(--text-muted)' }}>
        {icon}
      </div>
      <span className="text-sm font-medium">{label}</span>
    </button>
  );
}