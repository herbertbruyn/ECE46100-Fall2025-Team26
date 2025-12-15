import { useState, useEffect } from 'react';
import { GitBranch, AlertCircle, ExternalLink } from 'lucide-react';
import apiService from '../services/api';
import LoadingSpinner from './LoadingSpinner';

interface LineageNode {
  artifact_id: number;
  name: string;
  source: string;
}

interface LineageEdge {
  from_node_artifact_id: number;
  to_node_artifact_id: number;
  relationship: string;
}

interface LineageGraphProps {
  modelId: number;
}

export function LineageGraph({ modelId }: LineageGraphProps) {
  const [loading, setLoading] = useState(true);
  const [nodes, setNodes] = useState<LineageNode[]>([]);
  const [edges, setEdges] = useState<LineageEdge[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadLineage();
  }, [modelId]); // eslint-disable-line react-hooks/exhaustive-deps

  const loadLineage = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiService.getArtifactLineage(modelId);
      setNodes(data.nodes || []);
      setEdges(data.edges || []);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load lineage graph');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div style={{
        backgroundColor: 'var(--card-bg)',
        border: '1px solid var(--border)',
        borderRadius: '12px',
        padding: '2rem',
        marginTop: '1.5rem',
      }}>
        <LoadingSpinner text="Loading lineage graph..." />
      </div>
    );
  }

  if (error) {
    return (
      <div style={{
        backgroundColor: 'var(--card-bg)',
        border: '1px solid var(--border)',
        borderRadius: '12px',
        padding: '1.5rem',
        marginTop: '1.5rem',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem' }}>
          <GitBranch size={24} color="var(--primary)" />
          <h3 style={{ fontSize: '1.25rem', fontWeight: 600 }}>Model Lineage</h3>
        </div>
        <div style={{
          padding: '1rem',
          backgroundColor: 'rgba(239, 68, 68, 0.1)',
          border: '1px solid rgba(239, 68, 68, 0.3)',
          borderRadius: '8px',
          display: 'flex',
          alignItems: 'center',
          gap: '0.75rem',
        }}>
          <AlertCircle size={20} color="#ef4444" />
          <span style={{ color: '#ef4444', fontSize: '0.875rem' }}>{error}</span>
        </div>
      </div>
    );
  }

  if (nodes.length === 0) {
    return (
      <div style={{
        backgroundColor: 'var(--card-bg)',
        border: '1px solid var(--border)',
        borderRadius: '12px',
        padding: '1.5rem',
        marginTop: '1.5rem',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem' }}>
          <GitBranch size={24} color="var(--primary)" />
          <h3 style={{ fontSize: '1.25rem', fontWeight: 600 }}>Model Lineage</h3>
        </div>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
          No lineage information available for this model.
        </p>
      </div>
    );
  }

  // Create a map of nodes by artifact_id for easy lookup
  const nodeMap = new Map<number, LineageNode>();
  nodes.forEach(node => {
    nodeMap.set(node.artifact_id, node);
  });

  return (
    <div style={{
      backgroundColor: 'var(--card-bg)',
      border: '1px solid var(--border)',
      borderRadius: '12px',
      padding: '1.5rem',
      marginTop: '1.5rem',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1.5rem' }}>
        <GitBranch size={24} color="var(--primary)" />
        <h3 style={{ fontSize: '1.25rem', fontWeight: 600 }}>Model Lineage</h3>
      </div>

      <p style={{ color: 'var(--text-secondary)', marginBottom: '1.5rem', fontSize: '0.875rem' }}>
        Visual representation of this model's dependencies and relationships.
      </p>

      {/* Lineage Visualization */}
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '1rem',
        padding: '1.5rem',
        backgroundColor: 'var(--bg-tertiary)',
        borderRadius: '8px',
      }}>
        {nodes.map((node) => {
          const isCurrentModel = node.artifact_id === modelId;
          const outgoingEdges = edges.filter(e => e.from_node_artifact_id === node.artifact_id);

          return (
            <div key={node.artifact_id} style={{ position: 'relative' }}>
              {/* Node Card */}
              <div style={{
                padding: '1rem',
                backgroundColor: isCurrentModel ? 'var(--primary)' : 'var(--card-bg)',
                border: `2px solid ${isCurrentModel ? 'var(--primary)' : 'var(--border)'}`,
                borderRadius: '8px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                boxShadow: isCurrentModel ? '0 4px 12px rgba(0, 0, 0, 0.15)' : 'none',
              }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
                    <span style={{
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      padding: '0.25rem 0.5rem',
                      backgroundColor: isCurrentModel ? 'rgba(255, 255, 255, 0.2)' : 'var(--bg-tertiary)',
                      borderRadius: '4px',
                      color: isCurrentModel ? 'white' : 'var(--text-secondary)',
                    }}>
                      {isCurrentModel ? 'Current Model' : 'Base Model'}
                    </span>
                    <span style={{
                      fontSize: '0.75rem',
                      color: isCurrentModel ? 'rgba(255, 255, 255, 0.8)' : 'var(--text-secondary)',
                    }}>
                      ID: {node.artifact_id}
                    </span>
                  </div>
                  <p style={{
                    fontSize: '1rem',
                    fontWeight: 600,
                    color: isCurrentModel ? 'white' : 'var(--text-primary)',
                    margin: 0,
                    wordBreak: 'break-word',
                  }}>
                    {node.name}
                  </p>
                  <p style={{
                    fontSize: '0.75rem',
                    color: isCurrentModel ? 'rgba(255, 255, 255, 0.7)' : 'var(--text-secondary)',
                    marginTop: '0.25rem',
                  }}>
                    Source: {node.source}
                  </p>
                </div>
                <a
                  href={`/artifact/${node.artifact_id}`}
                  onClick={(e) => {
                    e.preventDefault();
                    window.location.href = `/artifact/${node.artifact_id}`;
                  }}
                  style={{
                    marginLeft: '1rem',
                    padding: '0.5rem',
                    color: isCurrentModel ? 'white' : 'var(--primary)',
                    textDecoration: 'none',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.25rem',
                    fontSize: '0.875rem',
                  }}
                >
                  <ExternalLink size={16} />
                </a>
              </div>

              {/* Relationship Arrow */}
              {outgoingEdges.length > 0 && (
                <div style={{
                  display: 'flex',
                  justifyContent: 'center',
                  padding: '0.5rem 0',
                }}>
                  <div style={{
                    width: '2px',
                    height: '2rem',
                    backgroundColor: 'var(--border)',
                    position: 'relative',
                  }}>
                    <div style={{
                      position: 'absolute',
                      bottom: '-4px',
                      left: '-4px',
                      width: 0,
                      height: 0,
                      borderLeft: '5px solid transparent',
                      borderRight: '5px solid transparent',
                      borderTop: '8px solid var(--border)',
                    }} />
                  </div>
                </div>
              )}

              {/* Relationship Label */}
              {outgoingEdges.length > 0 && (
                <div style={{
                  textAlign: 'center',
                  padding: '0.25rem 0.5rem',
                  fontSize: '0.75rem',
                  color: 'var(--text-secondary)',
                  fontStyle: 'italic',
                }}>
                  {outgoingEdges[0].relationship}
                </div>
              )}
            </div>
          );
        })}

        {edges.length === 0 && nodes.length > 0 && (
          <p style={{
            textAlign: 'center',
            color: 'var(--text-secondary)',
            fontSize: '0.875rem',
            fontStyle: 'italic',
            padding: '1rem',
          }}>
            No relationships found
          </p>
        )}
      </div>

      {/* Summary */}
      <div style={{
        marginTop: '1.5rem',
        padding: '1rem',
        backgroundColor: 'var(--bg-tertiary)',
        borderRadius: '8px',
        fontSize: '0.875rem',
      }}>
        <p style={{ color: 'var(--text-secondary)', margin: 0 }}>
          <strong>Total Nodes:</strong> {nodes.length} | <strong>Total Relationships:</strong> {edges.length}
        </p>
      </div>
    </div>
  );
}

export default LineageGraph;

