import { useState, useEffect } from 'react';
import { api } from '../services/api';
import type { Artifact } from '../types';
import { ArtifactCard } from '../components/ArtifactCard';
import { LoadingSpinner } from '../components/LoadingSpinner';
import { Toast } from '../components/Toast';
import { Filter, RefreshCw } from 'lucide-react';

const ITEMS_PER_PAGE = 12;

export function BrowsePage() {
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [filteredArtifacts, setFilteredArtifacts] = useState<Artifact[]>([]);
  const [loading, setLoading] = useState(true);
  const [currentPage, setCurrentPage] = useState(1);
  const [showFilters, setShowFilters] = useState(false);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' | 'info' } | null>(null);

  // Filters
  const [filters, setFilters] = useState({
    type: 'all' as 'all' | 'model' | 'dataset' | 'code',
    status: [] as string[],
    dateFrom: '',
    dateTo: '',
    owner: '',
    minSize: '',
    maxSize: '',
  });

  // Sort
  const [sortBy, setSortBy] = useState<'created_at' | 'updated_at' | 'name' | 'size_bytes'>('created_at');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');

  useEffect(() => {
    loadArtifacts();
  }, []);

  useEffect(() => {
    applyFiltersAndSort();
    setCurrentPage(1);
  }, [artifacts, filters, sortBy, sortOrder]);

  const loadArtifacts = async () => {
    setLoading(true);
    try {
      const data = await api.getArtifacts();
      setArtifacts(data);
    } catch (error: any) {
      setToast({
        message: error.response?.data?.error || 'Failed to load artifacts',
        type: 'error',
      });
    } finally {
      setLoading(false);
    }
  };

  const applyFiltersAndSort = () => {
    let filtered = [...artifacts];

    // Type filter
    if (filters.type !== 'all') {
      filtered = filtered.filter((a) => a.type === filters.type);
    }

    // Status filter
    if (filters.status.length > 0) {
      filtered = filtered.filter((a) => filters.status.includes(a.status));
    }

    // Date range filter
    if (filters.dateFrom) {
      const fromDate = new Date(filters.dateFrom);
      filtered = filtered.filter((a) => new Date(a.created_at) >= fromDate);
    }
    if (filters.dateTo) {
      const toDate = new Date(filters.dateTo);
      toDate.setHours(23, 59, 59, 999);
      filtered = filtered.filter((a) => new Date(a.created_at) <= toDate);
    }

    // Owner filter
    if (filters.owner) {
      filtered = filtered.filter((a) =>
        a.uploaded_by?.toLowerCase().includes(filters.owner.toLowerCase())
      );
    }

    // Size filter
    if (filters.minSize) {
      const minBytes = parseFloat(filters.minSize) * 1024 * 1024;
      filtered = filtered.filter((a) => (a.size_bytes || 0) >= minBytes);
    }
    if (filters.maxSize) {
      const maxBytes = parseFloat(filters.maxSize) * 1024 * 1024;
      filtered = filtered.filter((a) => (a.size_bytes || 0) <= maxBytes);
    }

    // Sort
    filtered.sort((a, b) => {
      let aVal: any;
      let bVal: any;

      switch (sortBy) {
        case 'created_at':
        case 'updated_at':
          aVal = new Date(a[sortBy]).getTime();
          bVal = new Date(b[sortBy]).getTime();
          break;
        case 'name':
          aVal = a.name.toLowerCase();
          bVal = b.name.toLowerCase();
          break;
        case 'size_bytes':
          aVal = a.size_bytes || 0;
          bVal = b.size_bytes || 0;
          break;
      }

      if (sortOrder === 'asc') {
        return aVal > bVal ? 1 : -1;
      } else {
        return aVal < bVal ? 1 : -1;
      }
    });

    setFilteredArtifacts(filtered);
  };

  const clearFilters = () => {
    setFilters({
      type: 'all',
      status: [],
      dateFrom: '',
      dateTo: '',
      owner: '',
      minSize: '',
      maxSize: '',
    });
  };

  const handleStatusToggle = (status: string) => {
    setFilters((prev) => ({
      ...prev,
      status: prev.status.includes(status)
        ? prev.status.filter((s) => s !== status)
        : [...prev.status, status],
    }));
  };

  const activeFilterCount = [
    filters.type !== 'all',
    filters.status.length > 0,
    filters.dateFrom,
    filters.dateTo,
    filters.owner,
    filters.minSize,
    filters.maxSize,
  ].filter(Boolean).length;

  // Pagination
  const totalPages = Math.ceil(filteredArtifacts.length / ITEMS_PER_PAGE);
  const startIndex = (currentPage - 1) * ITEMS_PER_PAGE;
  const paginatedArtifacts = filteredArtifacts.slice(startIndex, startIndex + ITEMS_PER_PAGE);

  const goToPage = (page: number) => {
    setCurrentPage(page);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const renderPageNumbers = () => {
    const pages = [];
    const maxVisible = 7;

    if (totalPages <= maxVisible) {
      for (let i = 1; i <= totalPages; i++) {
        pages.push(i);
      }
    } else {
      if (currentPage <= 4) {
        for (let i = 1; i <= 5; i++) pages.push(i);
        pages.push(-1);
        pages.push(totalPages);
      } else if (currentPage >= totalPages - 3) {
        pages.push(1);
        pages.push(-1);
        for (let i = totalPages - 4; i <= totalPages; i++) pages.push(i);
      } else {
        pages.push(1);
        pages.push(-1);
        for (let i = currentPage - 1; i <= currentPage + 1; i++) pages.push(i);
        pages.push(-1);
        pages.push(totalPages);
      }
    }

    return pages;
  };

  return (
    <div style={{ maxWidth: '1400px', margin: '0 auto', padding: '2rem' }}>
      {/* Header */}
      <div style={{ marginBottom: '2rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ fontSize: '2rem', fontWeight: 'bold', marginBottom: '0.5rem' }}>
            Browse Artifacts
          </h1>
          <p style={{ color: 'var(--text-secondary)' }}>
            {filteredArtifacts.length} artifact{filteredArtifacts.length !== 1 ? 's' : ''} found
          </p>
        </div>

        <div style={{ display: 'flex', gap: '1rem' }}>
          <button
            onClick={() => setShowFilters(!showFilters)}
            style={{
              padding: '0.75rem 1.5rem',
              backgroundColor: showFilters ? 'var(--primary)' : 'var(--card-bg)',
              border: '1px solid var(--border)',
              borderRadius: '6px',
              color: showFilters ? 'white' : 'var(--text-primary)',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
            }}
          >
            <Filter size={16} />
            Filters {activeFilterCount > 0 && `(${activeFilterCount})`}
          </button>
          <button
            onClick={loadArtifacts}
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
        </div>
      </div>

      {/* Filters */}
      {showFilters && (
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
            gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
            gap: '1.5rem',
          }}>
            {/* Type Filter */}
            <div>
              <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', fontWeight: 500 }}>
                Type
              </label>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {['all', 'model', 'dataset', 'code'].map((type) => (
                  <label key={type} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
                    <input
                      type="radio"
                      name="type"
                      checked={filters.type === type}
                      onChange={() => setFilters({ ...filters, type: type as any })}
                    />
                    <span style={{ textTransform: 'capitalize' }}>{type}</span>
                  </label>
                ))}
              </div>
            </div>

            {/* Status Filter */}
            <div>
              <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', fontWeight: 500 }}>
                Status
              </label>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {['completed', 'pending', 'rating', 'failed', 'rejected'].map((status) => (
                  <label key={status} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={filters.status.includes(status)}
                      onChange={() => handleStatusToggle(status)}
                    />
                    <span style={{ textTransform: 'capitalize' }}>{status}</span>
                  </label>
                ))}
              </div>
            </div>

            {/* Date Range */}
            <div>
              <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', fontWeight: 500 }}>
                Date Range
              </label>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                <input
                  type="date"
                  value={filters.dateFrom}
                  onChange={(e) => setFilters({ ...filters, dateFrom: e.target.value })}
                  placeholder="From"
                  style={{
                    padding: '0.5rem',
                    backgroundColor: 'var(--input-bg)',
                    border: '1px solid var(--border)',
                    borderRadius: '6px',
                    color: 'var(--text-primary)',
                  }}
                />
                <input
                  type="date"
                  value={filters.dateTo}
                  onChange={(e) => setFilters({ ...filters, dateTo: e.target.value })}
                  placeholder="To"
                  style={{
                    padding: '0.5rem',
                    backgroundColor: 'var(--input-bg)',
                    border: '1px solid var(--border)',
                    borderRadius: '6px',
                    color: 'var(--text-primary)',
                  }}
                />
              </div>
            </div>

            {/* Owner Filter */}
            <div>
              <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', fontWeight: 500 }}>
                Owner
              </label>
              <input
                type="text"
                value={filters.owner}
                onChange={(e) => setFilters({ ...filters, owner: e.target.value })}
                placeholder="Filter by owner..."
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

            {/* Size Range */}
            <div>
              <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', fontWeight: 500 }}>
                Size Range (MB)
              </label>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <input
                  type="number"
                  value={filters.minSize}
                  onChange={(e) => setFilters({ ...filters, minSize: e.target.value })}
                  placeholder="Min"
                  style={{
                    flex: 1,
                    padding: '0.5rem',
                    backgroundColor: 'var(--input-bg)',
                    border: '1px solid var(--border)',
                    borderRadius: '6px',
                    color: 'var(--text-primary)',
                  }}
                />
                <input
                  type="number"
                  value={filters.maxSize}
                  onChange={(e) => setFilters({ ...filters, maxSize: e.target.value })}
                  placeholder="Max"
                  style={{
                    flex: 1,
                    padding: '0.5rem',
                    backgroundColor: 'var(--input-bg)',
                    border: '1px solid var(--border)',
                    borderRadius: '6px',
                    color: 'var(--text-primary)',
                  }}
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Sort Controls */}
      <div style={{
        display: 'flex',
        gap: '1rem',
        marginBottom: '1.5rem',
        alignItems: 'center',
      }}>
        <span style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>Sort by:</span>
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value as any)}
          style={{
            padding: '0.5rem',
            backgroundColor: 'var(--input-bg)',
            border: '1px solid var(--border)',
            borderRadius: '6px',
            color: 'var(--text-primary)',
          }}
        >
          <option value="created_at">Created Date</option>
          <option value="updated_at">Updated Date</option>
          <option value="name">Name</option>
          <option value="size_bytes">Size</option>
        </select>
        <button
          onClick={() => setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')}
          style={{
            padding: '0.5rem 1rem',
            backgroundColor: 'var(--card-bg)',
            border: '1px solid var(--border)',
            borderRadius: '6px',
            color: 'var(--text-primary)',
            cursor: 'pointer',
          }}
        >
          {sortOrder === 'asc' ? '↑' : '↓'} {sortOrder === 'asc' ? 'Ascending' : 'Descending'}
        </button>
      </div>

      {/* Artifacts Grid */}
      {loading ? (
        <LoadingSpinner />
      ) : (
        <>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
            gap: '1.5rem',
            marginBottom: '2rem',
          }}>
            {paginatedArtifacts.map((artifact) => (
              <ArtifactCard key={artifact.id} artifact={artifact} />
            ))}
          </div>

          {filteredArtifacts.length === 0 && (
            <div style={{
              textAlign: 'center',
              padding: '3rem',
              color: 'var(--text-secondary)',
            }}>
              <p>No artifacts found</p>
            </div>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <div style={{
              display: 'flex',
              justifyContent: 'center',
              alignItems: 'center',
              gap: '0.5rem',
              marginTop: '2rem',
            }}>
              <button
                onClick={() => goToPage(currentPage - 1)}
                disabled={currentPage === 1}
                style={{
                  padding: '0.5rem 1rem',
                  backgroundColor: currentPage === 1 ? 'var(--border)' : 'var(--card-bg)',
                  border: '1px solid var(--border)',
                  borderRadius: '6px',
                  color: currentPage === 1 ? 'var(--text-muted)' : 'var(--text-primary)',
                  cursor: currentPage === 1 ? 'not-allowed' : 'pointer',
                }}
              >
                Previous
              </button>

              {renderPageNumbers().map((page, index) =>
                page === -1 ? (
                  <span key={`ellipsis-${index}`} style={{ padding: '0 0.5rem', color: 'var(--text-secondary)' }}>
                    ...
                  </span>
                ) : (
                  <button
                    key={page}
                    onClick={() => goToPage(page)}
                    style={{
                      padding: '0.5rem 1rem',
                      backgroundColor: currentPage === page ? 'var(--primary)' : 'var(--card-bg)',
                      border: '1px solid var(--border)',
                      borderRadius: '6px',
                      color: currentPage === page ? 'white' : 'var(--text-primary)',
                      cursor: 'pointer',
                      fontWeight: currentPage === page ? 600 : 400,
                    }}
                  >
                    {page}
                  </button>
                )
              )}

              <button
                onClick={() => goToPage(currentPage + 1)}
                disabled={currentPage === totalPages}
                style={{
                  padding: '0.5rem 1rem',
                  backgroundColor: currentPage === totalPages ? 'var(--border)' : 'var(--card-bg)',
                  border: '1px solid var(--border)',
                  borderRadius: '6px',
                  color: currentPage === totalPages ? 'var(--text-muted)' : 'var(--text-primary)',
                  cursor: currentPage === totalPages ? 'not-allowed' : 'pointer',
                }}
              >
                Next
              </button>

              <span style={{ marginLeft: '1rem', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
                Page {currentPage} of {totalPages}
              </span>
            </div>
          )}
        </>
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