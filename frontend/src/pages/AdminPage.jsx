import { Fragment, useEffect, useRef, useState } from 'react'
import { Calendar, Shield, RefreshCw, Plus, Trash2, KeyRound, Download, Play, Filter, Check, X } from 'lucide-react'
import { api } from '../api'
import { useToast } from '../App'

function formatTime(value) {
  if (!value) return ''
  try { return new Date(value).toLocaleString() } catch { return value }
}

function AuditDateTimeField({ label, value, onChange }) {
  const inputRef = useRef(null)

  const openPicker = () => {
    const input = inputRef.current
    if (!input) return
    if (typeof input.showPicker === 'function') input.showPicker()
    else input.focus()
  }

  const handleChange = (e) => onChange(e.currentTarget.value)

  return (
    <label className="audit-time-field">
      <span>{label}</span>
      <span className="audit-time-control">
        <input
          ref={inputRef}
          className="form-input"
          type="datetime-local"
          aria-label={label}
          value={value}
          onInput={handleChange}
          onChange={handleChange}
        />
        <button
          type="button"
          className="btn btn-outline btn-sm audit-picker-button"
          onClick={openPicker}
          title={`${label}选择器`}
          aria-label={`${label}选择器`}
          style={{ padding: 4 }}
        >
          <Calendar size={16} />
        </button>
      </span>
    </label>
  )
}

export default function AdminPage() {
  const addToast = useToast()
  const [users, setUsers] = useState([])
  const [auditEvents, setAuditEvents] = useState([])
  const [scenes, setScenes] = useState([])
  const [loading, setLoading] = useState(true)
  const [savingUser, setSavingUser] = useState(false)
  const [migrating, setMigrating] = useState(false)
  const [migrationResult, setMigrationResult] = useState(null)
  const [expandedAuditKey, setExpandedAuditKey] = useState('')
  const [auditFilter, setAuditFilter] = useState({ limit: 200, username: '', action: '', status: '', since: '', until: '' })
  const [newUser, setNewUser] = useState({ username: '', display_name: '', role: 'user', password: '' })
  const [migration, setMigration] = useState({ scene_id: '', dry_run: true })

  const loadAll = async () => {
    setLoading(true)
    try {
      const [userRes, auditRes, sceneRes] = await Promise.all([
        api.listUsers(),
        api.getAuditEvents(auditFilter),
        api.listScenes(),
      ])
      setUsers(userRes.users || [])
      setAuditEvents(auditRes.events || [])
      setScenes(sceneRes.scenes || [])
      if (!migration.scene_id && sceneRes.scenes?.length) {
        setMigration(p => ({ ...p, scene_id: sceneRes.scenes[0].id }))
      }
    } catch (e) {
      addToast('加载运营数据失败: ' + e.message, 'error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadAll() }, [])

  const refreshAudit = async () => {
    try {
      const params = {
        limit: auditFilter.limit,
        username: auditFilter.username || undefined,
        action: auditFilter.action || undefined,
        status: auditFilter.status || undefined,
        since: auditFilter.since ? new Date(auditFilter.since).toISOString() : undefined,
        until: auditFilter.until ? new Date(auditFilter.until).toISOString() : undefined,
      }
      const res = await api.getAuditEvents(params)
      setAuditEvents(res.events || [])
    } catch (e) {
      addToast('加载审计日志失败: ' + e.message, 'error')
    }
  }

  const handleCreateUser = async () => {
    setSavingUser(true)
    try {
      await api.createUser(newUser)
      setNewUser({ username: '', display_name: '', role: 'user', password: '' })
      addToast('用户已创建', 'success')
      loadAll()
    } catch (e) {
      addToast('创建用户失败: ' + e.message, 'error')
    } finally {
      setSavingUser(false)
    }
  }

  const handleToggleUser = async (user) => {
    try {
      await api.updateUser(user.username, { disabled: !user.disabled })
      addToast(user.disabled ? '用户已启用' : '用户已停用', 'success')
      loadAll()
    } catch (e) {
      addToast('更新用户失败: ' + e.message, 'error')
    }
  }

  const handleRoleChange = async (user, role) => {
    try {
      await api.updateUser(user.username, { role })
      addToast('角色已更新', 'success')
      loadAll()
    } catch (e) {
      addToast('更新角色失败: ' + e.message, 'error')
    }
  }

  const handleResetPassword = async (user) => {
    const password = window.prompt(`为 ${user.username} 设置新密码，至少 8 位`)
    if (!password) return
    try {
      await api.updateUser(user.username, { password })
      addToast('密码已重置', 'success')
    } catch (e) {
      addToast('重置密码失败: ' + e.message, 'error')
    }
  }

  const handleDeleteUser = async (user) => {
    if (!window.confirm(`确认删除用户 ${user.username}？`)) return
    try {
      await api.deleteUser(user.username)
      addToast('用户已删除', 'success')
      loadAll()
    } catch (e) {
      addToast('删除用户失败: ' + e.message, 'error')
    }
  }

  const handleMigrate = async () => {
    if (!migration.scene_id) return addToast('请选择场景', 'error')
    setMigrating(true)
    try {
      const res = await api.adoptSceneGraph(migration.scene_id, migration.dry_run)
      setMigrationResult(res)
      addToast(migration.dry_run ? '预检查完成' : '迁移完成', 'success')
      refreshAudit()
    } catch (e) {
      addToast('迁移失败: ' + e.message, 'error')
    } finally {
      setMigrating(false)
    }
  }

  const handleExportAudit = async (format = 'csv') => {
    try {
      const params = {
        limit: auditFilter.limit,
        username: auditFilter.username || undefined,
        action: auditFilter.action || undefined,
        status: auditFilter.status || undefined,
        since: auditFilter.since ? new Date(auditFilter.since).toISOString() : undefined,
        until: auditFilter.until ? new Date(auditFilter.until).toISOString() : undefined,
      }
      const { blob, filename } = await api.exportAuditEvents(params, format)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      link.click()
      URL.revokeObjectURL(url)
      addToast('审计日志已导出', 'success')
    } catch (e) {
      addToast('导出失败: ' + e.message, 'error')
    }
  }

  if (loading) {
    return <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}><div className="spinner spinner-lg" /></div>
  }

  return (
    <>
      <div className="page-header">
        <h2 style={{ display: 'flex', alignItems: 'center', gap: 8 }}><Shield size={24} /> 运营管理</h2>
        <p>用户权限、审计日志与历史图谱治理</p>
      </div>
      <div className="page-body">
        <div className="admin-grid">
          <section className="card">
            <div className="card-header">
              <div className="card-title">用户管理</div>
              <button className="btn btn-ghost btn-sm" onClick={loadAll} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <RefreshCw size={14} /> 刷新
              </button>
            </div>

            <div className="admin-form-row">
              <input className="form-input" placeholder="用户名" value={newUser.username} onChange={e => setNewUser(p => ({ ...p, username: e.target.value }))} />
              <input className="form-input" placeholder="显示名称" value={newUser.display_name} onChange={e => setNewUser(p => ({ ...p, display_name: e.target.value }))} />
              <select className="form-input" value={newUser.role} onChange={e => setNewUser(p => ({ ...p, role: e.target.value }))}>
                <option value="user">普通用户</option>
                <option value="admin">管理员</option>
              </select>
              <input className="form-input" type="password" placeholder="初始密码" value={newUser.password} onChange={e => setNewUser(p => ({ ...p, password: e.target.value }))} />
              <button className="btn btn-primary" onClick={handleCreateUser} disabled={savingUser} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                {savingUser ? <RefreshCw size={14} className="spinning" /> : <Plus size={14} />} 新增用户
              </button>
            </div>

            <div className="preview-scroll" style={{ marginTop: 16 }}>
              <table className="data-table">
                <thead><tr><th>用户</th><th>角色</th><th>状态</th><th>更新时间</th><th>操作</th></tr></thead>
                <tbody>
                  {users.map(user => (
                    <tr key={user.username}>
                      <td>{user.display_name}<br/><span className="muted-text">{user.username}</span></td>
                      <td>
                        <select className="form-input form-input-sm" value={user.role} onChange={e => handleRoleChange(user, e.target.value)}>
                          <option value="user">普通用户</option>
                          <option value="admin">管理员</option>
                        </select>
                      </td>
                      <td>{user.disabled ? '停用' : '启用'}</td>
                      <td>{formatTime(user.updated_at)}</td>
                      <td>
                        <div className="table-actions">
                          <button className="btn btn-outline btn-sm" onClick={() => handleToggleUser(user)} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                            {user.disabled ? <Check size={12} /> : <X size={12} />} {user.disabled ? '启用' : '停用'}
                          </button>
                          <button className="btn btn-outline btn-sm" onClick={() => handleResetPassword(user)} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                            <KeyRound size={12} /> 改密
                          </button>
                          <button className="btn btn-ghost btn-sm btn-danger" onClick={() => handleDeleteUser(user)} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                            <Trash2 size={12} /> 删除
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="card">
            <div className="card-header">
              <div className="card-title">历史图谱迁移</div>
            </div>
            <div className="admin-form-row">
              <select className="form-input" value={migration.scene_id} onChange={e => setMigration(p => ({ ...p, scene_id: e.target.value }))}>
                {scenes.map(scene => <option key={scene.id} value={scene.id}>{scene.name}</option>)}
              </select>
              <label className="checkbox-label">
                <input type="checkbox" checked={migration.dry_run} onChange={e => setMigration(p => ({ ...p, dry_run: e.target.checked }))} />
                只预检查
              </label>
              <button className="btn btn-primary" onClick={handleMigrate} disabled={migrating} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                {migrating ? <RefreshCw size={14} className="spinning" /> : <Play size={14} />} 执行
              </button>
            </div>
            {migrationResult && (
              <div className="admin-result">
                <div className={`migration-status ${migrationResult.status}`}>
                  {migrationResult.dry_run ? '预检查' : '正式迁移'}：{migrationResult.status}
                </div>
                <div className="migration-summary-grid">
                  <div><span>迁移前节点</span><strong>{migrationResult.before?.nodes ?? 0}</strong></div>
                  <div><span>迁移后节点</span><strong>{migrationResult.after?.nodes ?? 0}</strong></div>
                  <div><span>计划节点</span><strong>{migrationResult.planned_nodes ?? 0}</strong></div>
                  <div><span>已迁移节点</span><strong>{migrationResult.adopted_nodes ?? 0}</strong></div>
                  <div><span>关系补标</span><strong>{migrationResult.relationships ?? 0}</strong></div>
                  <div><span>冲突数</span><strong>{migrationResult.conflicts?.length ?? 0}</strong></div>
                </div>
                {migrationResult.tables?.length > 0 && (
                  <table className="data-table" style={{ marginTop: 12 }}>
                    <thead><tr><th>表</th><th>类</th><th>计划节点</th><th>已迁移</th><th>冲突</th></tr></thead>
                    <tbody>
                      {migrationResult.tables.map(row => (
                        <tr key={`${row.table}-${row.class}`}>
                          <td>{row.table}</td>
                          <td>{row.class}</td>
                          <td>{row.planned_nodes}</td>
                          <td>{row.adopted_nodes}</td>
                          <td>{row.conflicts}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )}
          </section>

          <section className="card admin-card-wide">
            <div className="card-header">
              <div className="card-title">审计日志</div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="btn btn-outline btn-sm" onClick={() => handleExportAudit('csv')} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <Download size={14} /> 导出 CSV
                </button>
                <button className="btn btn-outline btn-sm" onClick={() => handleExportAudit('jsonl')} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <Download size={14} /> 导出 JSONL
                </button>
                <button className="btn btn-ghost btn-sm" onClick={refreshAudit} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <RefreshCw size={14} /> 刷新
                </button>
              </div>
            </div>
            <div className="admin-form-row audit-filter-row" style={{ marginBottom: 16 }}>
              <input className="form-input" placeholder="用户过滤" value={auditFilter.username} onChange={e => setAuditFilter(p => ({ ...p, username: e.target.value }))} />
              <input className="form-input" placeholder="动作过滤，如 scene.sync" value={auditFilter.action} onChange={e => setAuditFilter(p => ({ ...p, action: e.target.value }))} />
              <select className="form-input" value={auditFilter.status} onChange={e => setAuditFilter(p => ({ ...p, status: e.target.value }))}>
                <option value="">全部状态</option>
                <option value="success">success</option>
                <option value="failed">failed</option>
              </select>
              <AuditDateTimeField
                label="开始时间"
                value={auditFilter.since}
                onChange={since => setAuditFilter(p => ({ ...p, since }))}
              />
              <AuditDateTimeField
                label="结束时间"
                value={auditFilter.until}
                onChange={until => setAuditFilter(p => ({ ...p, until }))}
              />
              <button className="btn btn-outline" onClick={refreshAudit} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <Filter size={14} /> 应用过滤
              </button>
            </div>
            <div className="preview-scroll admin-audit-scroll">
              <table className="data-table">
                <thead><tr><th>时间</th><th>用户</th><th>动作</th><th>状态</th><th>详情</th></tr></thead>
                <tbody>
                  {auditEvents.map((event, idx) => {
                    const key = `${event.time}-${idx}`
                    const expanded = expandedAuditKey === key
                    return (
                      <Fragment key={key}>
                        <tr key={key} onClick={() => setExpandedAuditKey(expanded ? '' : key)} style={{ cursor: 'pointer' }}>
                          <td>{formatTime(event.time)}</td>
                          <td>{event.username}</td>
                          <td>{event.action}</td>
                          <td>{event.status}</td>
                          <td><code>{JSON.stringify(event.details || {}).slice(0, 120)}</code></td>
                        </tr>
                        {expanded && (
                          <tr key={`${key}-detail`}>
                            <td colSpan="5">
                              <pre className="audit-detail">{JSON.stringify(event, null, 2)}</pre>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      </div>
    </>
  )
}
