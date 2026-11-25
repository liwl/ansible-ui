export const authStorage = {
  setAuth: (
    value: boolean,
    token: string | null = null,
    expiresInHours: number = 5,
    username: string | null = null,
    role: string | null = null,
  ) => {
    if (typeof localStorage !== 'undefined') {
      const expiresAt = new Date()
      expiresAt.setHours(expiresAt.getHours() + expiresInHours)

      localStorage.setItem('isAuthenticated', value ? 'true' : 'false')
      localStorage.setItem('authExpiresAt', expiresAt.toISOString())

      if (token) {
        localStorage.setItem('token', token)
      } else if (value === false) {
        localStorage.removeItem('token')
      }

      if (value && username) {
        localStorage.setItem('authUsername', username)
      }
      if (value && role) {
        localStorage.setItem('authRole', role)
      }
      if (value === false) {
        localStorage.removeItem('authUsername')
        localStorage.removeItem('authRole')
      }
    }
  },

  getAuth: (): boolean => {
    if (typeof localStorage !== 'undefined') {
      const isAuth = localStorage.getItem('isAuthenticated') === 'true'
      const expiresAt = localStorage.getItem('authExpiresAt')

      if (isAuth && expiresAt) {
        const now = new Date()
        const expiry = new Date(expiresAt)

        if (now < expiry) {
          return true
        }

        authStorage.clearAuth()
      }
    }

    return false
  },

  getToken: (): string | null => {
    if (typeof localStorage !== 'undefined') {
      return localStorage.getItem('token')
    }

    return null
  },

  getRole: (): string | null => {
    if (typeof localStorage !== 'undefined') {
      return localStorage.getItem('authRole')
    }

    return null
  },

  getUsername: (): string | null => {
    if (typeof localStorage !== 'undefined') {
      return localStorage.getItem('authUsername')
    }

    return null
  },

  clearAuth: () => {
    if (typeof localStorage !== 'undefined') {
      localStorage.removeItem('isAuthenticated')
      localStorage.removeItem('authExpiresAt')
      localStorage.removeItem('token')
      localStorage.removeItem('authUsername')
      localStorage.removeItem('authRole')
    }
  },
}
