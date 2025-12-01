import { useState, useEffect } from 'react';
import { api } from '../services/api';
import { LoadingSpinner } from '../components/LoadingSpinner';
import { Toast } from '../components/Toast';
import { formatRelativeTime, formatDate } from '../utils/format';
import type { ActivityLog } from '../types/activity';
import {
  Activity,
  Upload,
  Trash2,
  Download,
  Search,
  Eye,
  Calculator,
  LogIn,
  LogOut,
  ChevronDown,
  ChevronRight,
  RefreshCw,
  FileDown,
} from 'lucide-react';

export function ActivityLogPage() {
  const [activities, setActivities] = useState<ActivityLog[]>([]);
  const [filteredActivities, setFilteredActivities] = useState<ActivityLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' | 'info' } | null>(null);

  // Filters
  const [filterUser, setFilterUser] = useState('');
  const [filterAction, setFilterAction] = useState('');
  const [filterType, setFilterType] = useState('');
  const [filterDateFrom, setFilterDateFrom] = useState('');
  const [filterDateTo, setFilterDateTo] = useState('');

  useEffect(() => {
    loadActivities();
  }, []);

  useEffect(() => {
    applyFilters();
  }, [activities, filterUser, filterAction, filterType, filterDateFrom, filterDateTo]);

  const loadActivities = async () => {
    setLoading(true);
    try {
      const data = await api.getActivityLog();
      
      // If no data from API, use mock data for demo
      if (data.length === 0) {
        const mockData = generateMockActivities();
        setActivities(mockData);
      } else {
        setActivities(data);
      }
    } catch (error) {
      console.error('Failed to load activities:', error);
      // Use mock data on error
      const mockData = generateMockActivities();
      setActivities(mockData);
    } finally {
      setLoading(false);
    }
  };

  const applyFilters = () => {
    let filtered = [...activities];

    if (filterUser) {
      filtered = filtered.filter((a) =>
        a.user.toLowerCase().includes(filterUser.toLowerCase())
      );
    }

    if (filterAction) {
      filtered = filtered.filter((a) => a.action === filterAction);
    }

    if (filterType) {
      filtered = filtered.filter((a) => a.artifact_type === filterType);
    }

    if (filterDateFrom) {
      const fromDate = new Date(filterDateFrom);
      filtered = filtered.filter((a) => new Date(a.timestamp) >= fromDate);
    }

    if (filterDateTo) {
      const toDate = new Date(filterDateTo);
      toDate.setHours(23, 59, 59, 999);
      filtered = filtered.filter((a) => new Date(a.timestamp) <= toDate);
    }

    setFilteredActivities(filtered);
  };

  const clearFilters = () => {
    setFilterUser('');
    setFilterAction('');
    setFilterType('');
    setFilterDateFrom('');
    setFilterDateTo('');
  };

  const exportToCSV = () => {
    const headers = ['Timestamp', 'User', 'Action', 'Artifact Type', 'Artifact Name', 'Details', 'IP Address'];
    const rows = filteredActivities.map((a) => [
      a.timestamp,
      a.user,
      a.action,
      a.artifact_type || '-',
      a.artifact_name || '-',
      a.details || '-',
      a.ip_address || '-',
    ]);

    const csvContent = [
      headers.join(','),
      ...rows.map((row) => row.map((cell) => `"${cell}"`).join(',')),
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `activity-log-${new Date().toISOString().split('T')[0]}.csv`;
    link.click();
    URL.revokeObjectURL(url);

    setToast({ message: 'Activity log exported successfully', type: 'success' });
  };

  const getActionIcon = (action: string) => {
    const icons: Record<string, JSX.Element> = {
      upload: <Upload size={16} />,
      delete: <Trash2 size={16} />,
      download: <Download size={16} />,
      search: <Search size={16} />,
      view: <Eye size={16} />,
      rate: <Calculator size={16} />,
      login: <LogIn size={16} />,
      logout: <LogOut size={16} />,
      update: <Upload size={16} />,
    };
    return icons[action] || <Activity size={16} />;
  };

  const getActionColor = (action: string) => {
    const colors: Record<string, string> = {
      upload: 'var(--success)',
      delete: 'var(--error)',
      download: 'var(--info)',
      search: 'var(--primary)',
      view: 'var(--info)',
      rate: 'var(--warning)',
      login: 'var(--success)',
      logout: 'var(--text-secondary)',
      update: 'var(--warning)',
    };
    return colors[action] || 'var(--text-secondary)';
  };

  return (
    <div style={{ maxWidth: '1400px', margin: '0 auto', padding: '2rem' }}>
      {/* Header */}
      <div style={{ marginBottom: '2rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{
            fontSize: '2rem',
            fontWeight: 'bold',
            marginBottom: '0.5rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.75rem',
          }}>
            <Activity size={32} color="var(--primary)" />
            Activity Log
          </h1>
          <p style={{ color: 'var(--text-secondary)' }}>
            Complete audit trail of all system activities
          </p>
        </div>

        <div style={{ display: 'flex', gap: '1rem' }}>
          <button
            onClick={loadActivities}
            style={{
              padding: '0.75rem 1.5rem',
              backgroundColor: 'var(--card-bg)',
              border: '1px solid var(--border)',
              borderRadius: '6px',
              color: 'var(--text-primary)',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
            }}
          >
            <RefreshCw size={16} />
            Refresh
          </button>
          <button
            onClick={exportToCSV}
            disabled={filteredActivities.length === 0}
            style={{
              padding: '0.75rem 1.5rem',
              backgroundColor: filteredActivities.length === 0 ? 'var(--border)' : 'var(--primary)',
              border: 'none',
              borderRadius: '6px',
              color: 'white',
              cursor: filteredActivities.length === 0 ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
            }}
          >
            <FileDown size={16} />
            Export CSV
          </button>
        </div>
      </div>

      {/* Filters */}
      <div style={{
        backgroundColor: 'var(--card-bg)',
        border: '1px solid var(--border)',
        borderRadius: '12px',
        padding: '1.5rem',
        marginBottom: '2rem',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h3 style={{ fontSize: '1.125rem', fontWeight: 600 }}>Filters</h3>
          <button
            onClick={clearFilters}
            style={{
              padding: '0.5rem 1rem',
              backgroundColor: 'transparent',
              border: '1px solid var(--border)',
              borderRadius: '6px',
              color: 'var(--text-secondary)',
              cursor: 'pointer',
              fontSize: '0.875rem',
            }}
          >
            Clear All
          </button>
        </div>

        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: '1rem',
        }}>
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', fontWeight: 500 }}>
              User
            </label>
            <input
              type="text"
              value={filterUser}
              onChange={(e) => setFilterUser(e.target.value)}
              placeholder="Filter by user..."
              style={{
                width: '100%',
                padding: '0.5rem',
                backgroundColor: 'var(--input-bg)',
                border: '1px solid var(--border)',
                borderRadius: '6px',
                color: 'var(--text-primary)',
              }}
            />
          </div>

          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', fontWeight: 500 }}>
              Action
            </label>
            <select
              value={filterAction}
              onChange={(e) => setFilterAction(e.target.value)}
              style={{
                width: '100%',
                padding: '0.5rem',
                backgroundColor: 'var(--input-bg)',
                border: '1px solid var(--border)',
                borderRadius: '6px',
                color: 'var(--text-primary)',
              }}
            >
              <option value="">All Actions</option>
              <option value="upload">Upload</option>
              <option value="update">Update</option>
              <option value="delete">Delete</option>
              <option value="download">Download</option>
              <option value="view">View</option>
              <option value="search">Search</option>
              <option value="rate">Rate</option>
              <option value="login">Login</option>
              <option value="logout">Logout</option>
            </select>
          </div>

          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', fontWeight: 500 }}>
              Artifact Type
            </label>
            <select
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
              style={{
                width: '100%',
                padding: '0.5rem',
                backgroundColor: 'var(--input-bg)',
                border: '1px solid var(--border)',
                borderRadius: '6px',
                color: 'var(--text-primary)',
              }}
            >
              <option value="">All Types</option>
              <option value="model">Model</option>
              <option value="dataset">Dataset</option>
              <option value="code">Code</option>
            </select>
          </div>

          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', fontWeight: 500 }}>
              From Date
            </label>
            <input
              type="date"
              value={filterDateFrom}
              onChange={(e) => setFilterDateFrom(e.target.value)}
              style={{
                width: '100%',
                padding: '0.5rem',
                backgroundColor: 'var(--input-bg)',
                border: '1px solid var(--border)',
                borderRadius: '6px',
                color: 'var(--text-primary)',
              }}
            />
          </div>

          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', fontWeight: 500 }}>
              To Date
            </label>
            <input
              type="date"
              value={filterDateTo}
              onChange={(e) => setFilterDateTo(e.target.value)}
              style={{
                width: '100%',
                padding: '0.5rem',
                backgroundColor: 'var(--input-bg)',
                border: '1px solid var(--border)',
                borderRadius: '6px',
                color: 'var(--text-primary)',
              }}
            />
          </div>
        </div>

        <div style={{ marginTop: '1rem', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
          Showing {filteredActivities.length} of {activities.length} activities
        </div>
      </div>

      {/* Activity List */}
      {loading ? (
        <LoadingSpinner />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          {filteredActivities.map((activity) => (
            <div
              key={activity.id}
              style={{
                backgroundColor: 'var(--card-bg)',
                border: '1px solid var(--border)',
                borderRadius: '8px',
                overflow: 'hidden',
              }}
            >
              {/* Activity Header */}
              <div
                onClick={() => setExpandedId(expandedId === activity.id ? null : activity.id)}
                style={{
                  padding: '1rem 1.5rem',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '1rem',
                  transition: 'background-color 0.2s',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = 'var(--primary-dark)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = 'transparent';
                }}
              >
                <div style={{ color: getActionColor(activity.action) }}>
                  {getActionIcon(activity.action)}
                </div>

                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '0.25rem' }}>
                    <span style={{ fontWeight: 600 }}>{activity.user}</span>
                    <span style={{ color: 'var(--text-secondary)' }}>•</span>
                    <span style={{ color: getActionColor(activity.action), textTransform: 'capitalize' }}>
                      {activity.action}
                    </span>
                    {activity.artifact_name && (
                      <>
                        <span style={{ color: 'var(--text-secondary)' }}>•</span>
                        <span style={{ color: 'var(--text-secondary)' }}>{activity.artifact_name}</span>
                      </>
                    )}
                  </div>
                  <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
                    {formatRelativeTime(activity.timestamp)} • {formatDate(activity.timestamp)}
                    {activity.ip_address && ` • ${activity.ip_address}`}
                  </div>
                </div>

                <div>
                  {expandedId === activity.id ? (
                    <ChevronDown size={20} color="var(--text-secondary)" />
                  ) : (
                    <ChevronRight size={20} color="var(--text-secondary)" />
                  )}
                </div>
              </div>

              {/* Expanded Details */}
              {expandedId === activity.id && activity.details && (
                <div style={{
                  padding: '1rem 1.5rem',
                  backgroundColor: 'var(--bg-secondary)',
                  borderTop: '1px solid var(--border)',
                }}>
                  <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
                    Details:
                  </div>
                  <div style={{ color: 'var(--text-primary)' }}>
                    {activity.details}
                  </div>
                </div>
              )}
            </div>
          ))}

          {filteredActivities.length === 0 && (
            <div style={{
              textAlign: 'center',
              padding: '3rem',
              color: 'var(--text-secondary)',
            }}>
              <Activity size={48} style={{ opacity: 0.5, marginBottom: '1rem' }} />
              <p>No activities found</p>
            </div>
          )}
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

// Mock data generator for demo purposes
function generateMockActivities(): ActivityLog[] {
  const users = ['alice', 'bob', 'charlie', 'admin', 'ece30861defaultadminuser'];
  const actions: ActivityLog['action'][] = ['upload', 'delete', 'download', 'view', 'search', 'rate', 'login', 'logout'];
  const types: ('model' | 'dataset' | 'code')[] = ['model', 'dataset', 'code'];
  const artifacts = [
    'bert-base-uncased',
    'gpt2-medium',
    'resnet50',
    'imagenet-1k',
    'coco-dataset',
    'pytorch-utils',
    'training-scripts',
  ];

  const activities: ActivityLog[] = [];
  const now = new Date();

  for (let i = 0; i < 50; i++) {
    const action = actions[Math.floor(Math.random() * actions.length)];
    const hasArtifact = !['login', 'logout', 'search'].includes(action);
    
    activities.push({
      id: i + 1,
      user: users[Math.floor(Math.random() * users.length)],
      action,
      artifact_type: hasArtifact ? types[Math.floor(Math.random() * types.length)] : undefined,
      artifact_id: hasArtifact ? Math.floor(Math.random() * 100) + 1 : undefined,
      artifact_name: hasArtifact ? artifacts[Math.floor(Math.random() * artifacts.length)] : undefined,
      details: action === 'search' 
        ? `Searched for: model*` 
        : action === 'rate'
        ? `Calculated metrics: net_score=0.75`
        : hasArtifact
        ? `${action} artifact successfully`
        : `User ${action}`,
      ip_address: `192.168.1.${Math.floor(Math.random() * 255)}`,
      timestamp: new Date(now.getTime() - Math.random() * 7 * 24 * 60 * 60 * 1000).toISOString(),
    });
  }

  return activities.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
}