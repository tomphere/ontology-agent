import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useToast, useTheme } from '../App'
import { 
  Network, LayoutDashboard, FolderKanban, Factory, Waypoints, 
  Shield, Bot, Moon, Sun, Monitor, KeyRound, LogOut, X 
} from 'lucide-react'

export default function Layout() {
  const navigate = useNavigate()
  const addToast = useToast()
  const { theme, toggleTheme } = useTheme()
  const user = JSON.parse(localStorage.getItem('auth_user') || '{}')
  const [showPasswordModal, setShowPasswordModal] = useState(false)
  const [passwordForm, setPasswordForm] = useState({ current_password: '', new_password: '', confirm_password: '' })
  const [changingPassword, setChangingPassword] = useState(false)

  const handleLogout = () => {
    localStorage.removeItem('auth_token')
    localStorage.removeItem('auth_user')
    navigate('/login')
  }

  const handleChangePassword = async (e) => {
    e.preventDefault()
    if (passwordForm.new_password !== passwordForm.confirm_password) {
      addToast('两次输入的新密码不一致', 'error')
      return
    }
    setChangingPassword(true)
    try {
      await api.changePassword(passwordForm.current_password, passwordForm.new_password)
      setPasswordForm({ current_password: '', new_password: '', confirm_password: '' })
      setShowPasswordModal(false)
      addToast('密码已更新', 'success')
    } catch (err) {
      addToast('改密失败: ' + err.message, 'error')
    } finally {
      setChangingPassword(false)
    }
  }

  return (
    <div className="app-layout">
      {/* 侧边栏 */}
      <aside className="sidebar">
        <div className="sidebar-logo">
          <div className="logo-icon"><Network size={24} strokeWidth={2} /></div>
          <div>
            <div className="logo-text">本体智能体</div>
            <div className="logo-sub">Ontology Intelligence</div>
          </div>
        </div>

        <nav className="sidebar-nav">
          <div className="nav-section-title">平台管理</div>
          <NavLink to="/dashboard" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <span className="nav-icon"><LayoutDashboard size={18} /></span>
            <span>仪表盘</span>
          </NavLink>
          <NavLink to="/data-workbench" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <span className="nav-icon"><FolderKanban size={18} /></span>
            <span>场景空间</span>
          </NavLink>
          <NavLink to="/ontology-workbench" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <span className="nav-icon"><Factory size={18} /></span>
            <span>本体工坊</span>
          </NavLink>
          <NavLink to="/graph" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <span className="nav-icon"><Waypoints size={18} /></span>
            <span>图谱浏览</span>
          </NavLink>
          {user.role === 'admin' && (
            <NavLink to="/admin" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
              <span className="nav-icon"><Shield size={18} /></span>
              <span>运营管理</span>
            </NavLink>
          )}

          <div className="nav-section-title">智能交互</div>
          <NavLink to="/chat" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <span className="nav-icon"><Bot size={18} /></span>
            <span>智能体对话</span>
          </NavLink>
        </nav>

        <div className="sidebar-footer">
          <div className="avatar">{(user.display_name || 'U')[0]}</div>
          <div className="user-info">
            <div className="user-name">{user.display_name || '用户'}</div>
            <div className="user-role">{user.role || 'user'}</div>
          </div>
          <button className="btn btn-ghost sidebar-icon-btn" onClick={toggleTheme} title="切换主题">
            {theme === 'dark' ? <Moon size={18} /> : theme === 'light' ? <Sun size={18} /> : <Monitor size={18} />}
          </button>
          <button className="btn btn-ghost" onClick={() => setShowPasswordModal(true)} title="修改密码"><KeyRound size={18} /></button>
          <button className="btn btn-ghost" onClick={handleLogout} title="退出登录"><LogOut size={18} /></button>
        </div>
      </aside>

      {/* 主内容区 */}
      <main className="main-content">
        <Outlet />
      </main>

      {showPasswordModal && (
        <div className="modal-overlay" onClick={() => setShowPasswordModal(false)}>
          <div className="modal-content account-modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h3>修改密码</h3>
              <button className="btn btn-ghost btn-sm" onClick={() => setShowPasswordModal(false)}><X size={18}/></button>
            </div>
            <form className="modal-body" onSubmit={handleChangePassword}>
              <div className="form-group">
                <label>当前密码</label>
                <input className="form-input" type="password" value={passwordForm.current_password}
                  onChange={e => setPasswordForm(p => ({ ...p, current_password: e.target.value }))} />
              </div>
              <div className="form-group">
                <label>新密码</label>
                <input className="form-input" type="password" value={passwordForm.new_password}
                  onChange={e => setPasswordForm(p => ({ ...p, new_password: e.target.value }))} />
              </div>
              <div className="form-group">
                <label>确认新密码</label>
                <input className="form-input" type="password" value={passwordForm.confirm_password}
                  onChange={e => setPasswordForm(p => ({ ...p, confirm_password: e.target.value }))} />
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                <button type="button" className="btn btn-outline" onClick={() => setShowPasswordModal(false)}>取消</button>
                <button type="submit" className="btn btn-primary" disabled={changingPassword}>
                  {changingPassword ? '保存中...' : '保存'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
