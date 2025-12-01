interface StatusBadgeProps {
  status: 'pending' | 'rating' | 'completed' | 'failed' | 'rejected';
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const colors = {
    pending: 'var(--warning)',
    rating: 'var(--info)',
    completed: 'var(--success)',
    failed: 'var(--error)',
    rejected: 'var(--error)',
  };

  return (
    <span
      style={{
        padding: '0.25rem 0.75rem',
        borderRadius: '12px',
        fontSize: '0.875rem',
        fontWeight: 500,
        backgroundColor: `${colors[status]}20`,
        color: colors[status],
        textTransform: 'capitalize',
      }}
    >
      {status}
    </span>
  );
}

export default StatusBadge;
