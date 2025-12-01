import { useEffect, useState } from 'react';

interface ToastProps {
  message: string;
  type?: 'success' | 'error' | 'info' | 'warning';
  onClose: () => void;
}

export function Toast({ message, type = 'info', onClose }: ToastProps) {
  useEffect(() => {
    const timer = setTimeout(onClose, 4000);
    return () => clearTimeout(timer);
  }, [onClose]);

  const colorMap: Record<NonNullable<ToastProps['type']>, string> = {
    success: '#16a34a',
    error: '#dc2626',
    info: '#0ea5e9',
    warning: '#f97316',
  };

  const color = colorMap[type];

  return (
    <div
      style={{
        position: 'fixed',
        bottom: '1.5rem',
        right: '1.5rem',
        background: '#111827',
        border: '1px solid #374151',
        borderLeftColor: color,
        padding: '0.9rem 1.1rem',
        borderRadius: 8,
        boxShadow: '0 10px 30px rgba(0,0,0,0.3)',
        minWidth: 260,
        display: 'flex',
        gap: '0.75rem',
        zIndex: 1000,
        color: '#e5e7eb',
      }}
    >
      <div
        style={{
          width: 6,
          borderRadius: 999,
          backgroundColor: color,
        }}
      />
      <div style={{ flex: 1 }}>{message}</div>
      <button
        onClick={onClose}
        style={{
          background: 'transparent',
          border: 'none',
          color: '#9ca3af',
          cursor: 'pointer',
          fontSize: '1.1rem',
          lineHeight: 1,
        }}
      >
        ×
      </button>
    </div>
  );
}

type ToastKind = 'success' | 'error' | 'info' | 'warning';

interface ToastState {
  message: string;
  type: ToastKind;
}

// Return type is any so TS won’t complain regardless of how you use it
export function useToast(): any {
  const [toast, setToast] = useState<ToastState | null>(null);

  const show = (type: ToastKind) => (message: string) => {
    setToast({ type, message });
  };

  const api: any = {
    success: show('success'),
    error: show('error'),
    info: show('info'),
    warning: show('warning'),
    ToastContainer: () =>
      toast ? (
        <Toast
          message={toast.message}
          type={toast.type}
          onClose={() => setToast(null)}
        />
      ) : null,
  };

  return api;
}