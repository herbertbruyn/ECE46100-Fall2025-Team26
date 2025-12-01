import { formatScore, formatLatency } from '../utils/format';
import type { ModelRating } from '../types';

interface MetricsDisplayProps {
  metrics: ModelRating;
}

export function MetricsDisplay({ metrics }: MetricsDisplayProps) {
  const metricGroups = [
    {
      title: 'Overall Scores',
      metrics: [
        { label: 'Net Score', value: metrics.net_score, latency: metrics.net_score_latency },
        { label: 'Size Score', value: metrics.size_score, latency: metrics.size_score_latency },
      ],
    },
    {
      title: 'Code & Dataset Quality',
      metrics: [
        { label: 'Dataset & Code Score', value: metrics.dataset_and_code_score, latency: metrics.dataset_and_code_score_latency },
        { label: 'Dataset Quality', value: metrics.dataset_quality, latency: metrics.dataset_quality_latency },
        { label: 'Code Quality', value: metrics.code_quality, latency: metrics.code_quality_latency },
      ],
    },
    {
      title: 'Project Health',
      metrics: [
        { label: 'Ramp Up Time', value: metrics.ramp_up_time, latency: metrics.ramp_up_time_latency },
        { label: 'Bus Factor', value: metrics.bus_factor, latency: metrics.bus_factor_latency },
        { label: 'Reproducibility', value: metrics.reproducibility, latency: metrics.reproducibility_latency },
        { label: 'Reviewedness', value: metrics.reviewedness, latency: metrics.reviewedness_latency },
      ],
    },
    {
      title: 'Compliance',
      metrics: [
        { label: 'License', value: metrics.license, latency: metrics.license_latency },
        { label: 'Performance Claims', value: metrics.performance_claims, latency: metrics.performance_claims_latency },
      ],
    },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
      <div style={{
        padding: '1rem',
        backgroundColor: 'var(--primary-dark)',
        borderRadius: '8px',
        textAlign: 'center',
      }}>
        <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
          Total Rating Time
        </div>
        <div style={{ fontSize: '1.5rem', fontWeight: 600, color: 'var(--primary)' }}>
          {formatLatency(metrics.total_rating_time)}
        </div>
      </div>

      {metricGroups.map((group) => (
        <div key={group.title}>
          <h3 style={{ marginBottom: '1rem', fontSize: '1.125rem', color: 'var(--primary)' }}>
            {group.title}
          </h3>
          <div style={{ display: 'grid', gap: '1rem' }}>
            {group.metrics.map((metric) => (
              <div
                key={metric.label}
                style={{
                  padding: '1rem',
                  backgroundColor: 'var(--card-bg)',
                  border: '1px solid var(--border)',
                  borderRadius: '8px',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
                    {metric.label}
                  </span>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    {formatLatency(metric.latency)}
                  </span>
                </div>
                <div style={{ marginTop: '0.5rem', fontSize: '1.25rem', fontWeight: 600 }}>
                  {formatScore(metric.value)}
                </div>
                <div
                  style={{
                    marginTop: '0.5rem',
                    height: '4px',
                    backgroundColor: 'var(--border)',
                    borderRadius: '2px',
                    overflow: 'hidden',
                  }}
                >
                  <div
                    style={{
                      height: '100%',
                      width: `${(metric.value || 0) * 100}%`,
                      backgroundColor: 'var(--primary)',
                      transition: 'width 0.3s',
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export default MetricsDisplay;