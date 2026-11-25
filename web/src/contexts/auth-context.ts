import { createContext } from 'react'

export type UserRole = 'admin' | 'viewer'

export interface AuthContextType {
  isAuthenticated: boolean
  login: (username: string, password: string) => Promise<boolean>
  logout: () => void
  token: string | null
  username: string | null
  role: UserRole | null
  isAdmin: boolean
}

export const AuthContext = createContext<AuthContextType | undefined>(undefined)
