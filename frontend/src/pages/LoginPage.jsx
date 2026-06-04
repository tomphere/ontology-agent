import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useToast, useTheme } from '../App'

export default function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const addToast = useToast()
  const { theme, toggleTheme } = useTheme()

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!username || !password) return
    setLoading(true)
    try {
      const data = await api.login(username, password)
      localStorage.setItem('auth_token', data.token)
      localStorage.setItem('auth_user', JSON.stringify(data.user))
      addToast(`欢迎回来，${data.user.display_name}！`, 'success')
      navigate('/dashboard')
    } catch (err) {
      addToast(err.message, 'error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      <button 
        className="btn btn-ghost" 
        onClick={toggleTheme} 
        title="切换主题"
        style={{ position: 'absolute', top: '20px', right: '20px', zIndex: 10, fontSize: '1.2rem' }}
      >
        {theme === 'dark' ? '🌙' : theme === 'light' ? '☀️' : '🧊'}
      </button>

      <div className="login-bg-effect">
        <div className="orb" />
        <div className="orb" />
        <div className="orb" />
      </div>

      <div className="login-card">
        <h1>本体智能体平台</h1>
        <p className="subtitle">Ontology Intelligence Web Platform</p>

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="username">用户名</label>
            <input
              id="username"
              className="form-input"
              type="text"
              placeholder="请输入用户名"
              value={username}
              onChange={e => setUsername(e.target.value)}
              autoFocus
            />
          </div>
          <div className="form-group">
            <label htmlFor="password">密码</label>
            <input
              id="password"
              className="form-input"
              type="password"
              placeholder="请输入密码"
              value={password}
              onChange={e => setPassword(e.target.value)}
            />
          </div>
          <button type="submit" className="btn btn-primary btn-full btn-lg" disabled={loading}>
            {loading ? <><div className="spinner" /> 登录中...</> : '登 录'}
          </button>
        </form>

        <p style={{ textAlign: 'center', marginTop: 20, color: 'var(--text-muted)', fontSize: '0.78rem' }}>
          请使用管理员分配的账号登录
        </p>
      </div>
    </div>
  )
}
