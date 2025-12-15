import { Routes, Route } from 'react-router-dom';
import { Header } from './components/Header';

import { LoginPage } from './pages/LoginPage';
import { BrowsePage } from './pages/BrowsePage';
import UploadPage from './pages/UploadPage';
import { SearchPage } from './pages/SearchPage';
import ArtifactDetailPage from './pages/ArtifactDetailPage';
import { ActivityLogPage } from './pages/ActivityLogPage';
import AdminPage from './pages/AdminPage';

// TESTING MODE: All routes are unprotected for testing purposes
function App() {
  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Header />
      <main style={{ flex: 1 }}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<BrowsePage />} />
          <Route path="/upload" element={<UploadPage />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/artifact/:id" element={<ArtifactDetailPage />} />
          <Route path="/activity" element={<ActivityLogPage />} />
          <Route path="/admin" element={<AdminPage />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;