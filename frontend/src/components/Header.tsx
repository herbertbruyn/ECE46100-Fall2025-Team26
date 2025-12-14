import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Package, Upload, Search, Activity, Shield, LogOut } from 'lucide-react';

export function Header() {
  const { user, logout, isAdmin } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <header style={{
      backgroundColor: 'var(--card-bg)',
      borderBottom: '1px solid var(--border)',
      padding: '1rem 2rem',
    }}>
      <div style={{
        maxWidth: '1400px',
        margin: '0 auto',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '2rem' }}>
          <Link
            to="/"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              fontSize: '1.25rem',
              fontWeight: 'bold',
              color: 'var(--primary)',
              textDecoration: 'none',
            }}
          >
            <Package size={28} />
            Model Registry
          </Link>

          <nav style={{ display: 'flex', gap: '1.5rem' }}>
            <NavLink to="/" icon={<Package size={18} />}>
              Browse
            </NavLink>
            <NavLink to="/upload" icon={<Upload size={18} />}>
              Upload
            </NavLink>
            <NavLink to="/search" icon={<Search size={18} />}>
              Search
            </NavLink>
            <NavLink to="/activity" icon={<Activity size={18} />}>
              Activity
            </NavLink>
            {isAdmin && (
              <NavLink to="/admin" icon={<Shield size={18} />}>
                Admin
              </NavLink>
            )}
          </nav>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: '0.875rem', fontWeight: 500 }}>
              {user?.name}
            </div>
            {isAdmin && (
              <div style={{
                fontSize: '0.75rem',
                color: 'var(--primary)',
                display: 'flex',
                alignItems: 'center',
                gap: '0.25rem',
                justifyContent: 'flex-end',
              }}>
                <Shield size={12} />
                Administrator
              </div>
            )}
          </div>
          <button
            onClick={handleLogout}
            style={{
              padding: '0.5rem 1rem',
              backgroundColor: 'transparent',
              border: '1px solid var(--border)',
              borderRadius: '6px',
              color: 'var(--text-secondary)',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              transition: 'all 0.2s',
            }}
            onMouseEnter={(e: React.MouseEvent<HTMLButtonElement>) => {
              e.currentTarget.style.borderColor = 'var(--error)';
              e.currentTarget.style.color = 'var(--error)';
            }}
            onMouseLeave={(e: React.MouseEvent<HTMLButtonElement>) => {
              e.currentTarget.style.borderColor = 'var(--border)';
              e.currentTarget.style.color = 'var(--text-secondary)';
            }}
          >
            <LogOut size={16} />
            Logout
          </button>
        </div>
      </div>
    </header>
  );
}

interface NavLinkProps {
  to: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
}

function NavLink({ to, icon, children }: NavLinkProps) {
  return (
    <Link
      to={to}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
        color: 'var(--text-secondary)',
        textDecoration: 'none',
        fontSize: '0.875rem',
        fontWeight: 500,
        transition: 'color 0.2s',
      }}
      onMouseEnter={(e: React.MouseEvent<HTMLAnchorElement>) => {
        e.currentTarget.style.color = 'var(--primary)';
      }}
      onMouseLeave={(e: React.MouseEvent<HTMLAnchorElement>) => {
        e.currentTarget.style.color = 'var(--text-secondary)';
      }}
    >
      {icon}
      {children}
    </Link>
  );
}