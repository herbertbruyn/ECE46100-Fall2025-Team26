import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { api } from '../services/api';
import type { User } from '../types';

interface AuthContextType {
  user: User | null;
  login: (username: string, password: string, isAdmin: boolean) => Promise<void>;
  logout: () => void;
  isAuthenticated: boolean;
  isAdmin: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  // TESTING MODE: Always return a mock authenticated admin user
  const mockUser: User = {
    name: 'test-user',
    is_admin: true,
  };

  const [user] = useState<User | null>(mockUser);

  const login = async (username: string, password: string, isAdmin: boolean) => {
    // Mock login - no actual API call
    console.log('Mock login - authentication disabled for testing');
  };

  const logout = () => {
    // Mock logout - no actual logout
    console.log('Mock logout - authentication disabled for testing');
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        login,
        logout,
        isAuthenticated: true, // Always authenticated
        isAdmin: true, // Always admin
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}