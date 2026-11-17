
import { useEffect, useState } from 'react';
import './App.css';

const API_ROOT = import.meta.env.VITE_API_ROOT || 'http://127.0.0.1:8000';
const PAGE_SIZE = 20;

function App() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [page, setPage] = useState(0);
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [hasNext, setHasNext] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => {
      setPage(0);
      setSearch(searchInput.trim());
    }, 400);

    return () => clearTimeout(timer);
  }, [searchInput]);

  useEffect(() => {
    const controller = new AbortController();

    async function fetchUsers() {
      setLoading(true);
      setError('');

      try {
        const params = new URLSearchParams({
          skip: String(page * PAGE_SIZE),
          limit: String(PAGE_SIZE + 1),
        });

        if (search) params.append('search', search);

        const response = await fetch(
          `${API_ROOT}/api/users/all?${params.toString()}`,
          { signal: controller.signal }
        );

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();

        if (!Array.isArray(data)) {
          throw new Error('Invalid API response');
        }

        setHasNext(data.length > PAGE_SIZE);
        setUsers(data.slice(0, PAGE_SIZE));
      } catch (err) {
        if (err.name !== 'AbortError') {
          console.error(err);
          setError('Unable to load users. Please try again.');
          setUsers([]);
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }

    fetchUsers();
    return () => controller.abort();
  }, [page, search]);

  const formatDate = (date) => {
    if (!date) return '—';
    const parsed = new Date(date);
    return Number.isNaN(parsed.getTime())
      ? '—'
      : parsed.toLocaleString();
  };

  return (
    <main className="page-container">
      <header className="page-header">
        <div>
          <div className="eyebrow">RECORD MANAGEMENT</div>
          <h1>ARRT Users</h1>
          <p>Search and view all imported user records.</p>
        </div>

        <div className="connection-status">
          <span className="status-dot"></span>
          API Connected
        </div>
      </header>

      <section className="users-card">
        <div className="card-header">
          <div>
            <h2>All Users</h2>
            <p>Browse user information and credentials.</p>
          </div>

          <span className="record-count">
            {loading ? 'Loading...' : `${users.length} records`}
          </span>
        </div>

        <div className="toolbar">
          <div className="search-box">
            <span className="search-icon">⌕</span>
            <input
              type="text"
              placeholder="Search by user name..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
            />

            {searchInput && (
              <button
                className="clear-btn"
                onClick={() => setSearchInput('')}
                aria-label="Clear search"
              >
                ×
              </button>
            )}
          </div>

          <span className="page-size-label">
            {PAGE_SIZE} records per page
          </span>
        </div>

        {error && (
          <div className="error-message">
            {error}
            <button onClick={() => setPage((p) => p)}>Retry</button>
          </div>
        )}

        <div className="table-wrapper">
          <table className="users-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>NAME</th>
                <th>CITY</th>
                <th>STATE</th>
                <th>CREDENTIAL</th>
              </tr>
            </thead>

            <tbody>
              {loading ? (
                Array.from({ length: 7 }).map((_, index) => (
                  <tr key={index}>
                    {Array.from({ length: 7 }).map((__, cell) => (
                      <td key={cell}>
                        <div className="skeleton"></div>
                      </td>
                    ))}
                  </tr>
                ))
              ) : error ? null : users.length === 0 ? (
                <tr>
                  <td colSpan="7" className="empty-state">
                    <div className="empty-icon">⌕</div>
                    <strong>No users found</strong>
                    <p>Try another search term.</p>
                  </td>
                </tr>
              ) : (
                users.map((user) => (
                  <tr key={user.id}>
                    <td className="id-cell">#{user.id}</td>
                    <td className="name-cell">{user.name}</td>
                    <td>{user.city || '—'}</td>
                    <td>{user.state || '—'}</td>
                    <td>
                      <span className="credential-badge">
                        {user.credential_string || '—'}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <footer className="pagination-footer">
          <span>
            Page <strong>{page + 1}</strong>
          </span>

          <div className="pagination">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0 || loading}
            >
              ← Previous
            </button>

            <span className="page-number">{page + 1}</span>

            <button
              onClick={() => hasNext && setPage((p) => p + 1)}
              disabled={!hasNext || loading}
            >
              Next →
            </button>
          </div>
        </footer>
      </section>

      <footer className="page-footer">
        ARRT Users Management System
      </footer>
    </main>
  );
}

export default App;
