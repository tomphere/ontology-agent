import { useState, useEffect } from 'react'
import { api } from '../api'
import { useToast } from '../App'

// .env 配置项分组定义
const ENV_GROUPS = [
  {
    title: '🗄️ Neo4j 图数据库', keys: [
      { key: 'NEO4J_URI', label: 'Neo4j 连接地址', placeholder: 'bolt://localhost:7687' },
      { key: 'NEO4J_USER', label: '用户名', placeholder: 'neo4j' },
      { key: 'NEO4J_PASSWORD', label: '密码', placeholder: '输入密码', secret: true },
    ]
  },
  {
    title: '🐬 MySQL 数据库', keys: [
      { key: 'MYSQL_HOST', label: '主机地址', placeholder: 'localhost' },
      { key: 'MYSQL_PORT', label: '端口', placeholder: '3306' },
      { key: 'MYSQL_USER', label: '用户名', placeholder: 'root' },
      { key: 'MYSQL_PASSWORD', label: '密码', placeholder: '输入密码', secret: true },
      { key: 'MYSQL_DB', label: '数据库名', placeholder: 'it_ops' },
    ]
  },
  {
    title: '✨ LLM 统一配置 (OpenAI 兼容)', keys: [
      { key: 'LLM_PROVIDER', label: '模型供应商', placeholder: 'LLM / openai / qwen / deepseek / ollama' },
      { key: 'LLM_API_KEY', label: 'API Key', placeholder: '输入您的 API Key', secret: true },
      { key: 'LLM_MODEL', label: '模型名称', placeholder: '如: LLM-1.5-pro' },
      { key: 'LLM_BASE_URL', label: 'API 代理地址 (可选)', placeholder: '如: https://api.openai.com/v1' },
    ]
  },
  {
    title: '📁 路径配置', keys: [
      { key: 'ONTOLOGY_DIR', label: '本体文件目录', placeholder: './ontology_files/' },
      { key: 'MAPPING_FILE', label: '映射配置文件', placeholder: 'database_mapping.yaml' },
      { key: 'USERS_FILE', label: '用户配置文件', placeholder: 'data/users/users.json' },
    ]
  },
]

function EnvFormMode({ parsed, onChange, isLocked }) {
  const [revealed, setRevealed] = useState({})

  const toggleReveal = (key) => setRevealed(p => ({ ...p, [key]: !p[key] }))
  const handleChange = (key, value) => onChange({ ...parsed, [key]: value })
  const handleKeyChange = (oldKey, newKey) => {
    if (oldKey === newKey) return
    const newParsed = { ...parsed }
    const val = newParsed[oldKey]
    delete newParsed[oldKey]
    newParsed[newKey] = val
    onChange(newParsed)
  }
  const handleRemove = (key) => {
    const newParsed = { ...parsed }
    delete newParsed[key]
    onChange(newParsed)
  }
  const handleAdd = () => {
    let suffix = 1
    while (`NEW_KEY_${suffix}` in parsed) suffix++
    onChange({ ...parsed, [`NEW_KEY_${suffix}`]: '' })
  }

  const isSecret = (k) => k.includes('PASSWORD') || k.includes('KEY') || k.includes('SECRET')

  return (
    <div className="env-form-groups">
      <div className="env-form-group">
        <div className="env-group-title">系统环境变量 (.env)</div>
        {Object.keys(parsed || {}).map(key => (
          <div key={key} className="env-form-row">
            <input
              className="env-form-key form-input"
              value={key}
              onChange={e => handleKeyChange(key, e.target.value)}
              placeholder="KEY"
              disabled={isLocked}
            />
            <div className="env-form-input-wrap">
              <input
                type={isSecret(key) && !revealed[key] ? 'password' : 'text'}
                className="form-input"
                value={parsed[key] || ''}
                onChange={e => handleChange(key, e.target.value)}
                placeholder="Value"
                disabled={isLocked}
              />
              {isSecret(key) && (
                <button className="btn btn-ghost btn-sm reveal-btn" onClick={() => toggleReveal(key)} title={revealed[key] ? '隐藏' : '显示'}>
                  {revealed[key] ? '🙈' : '👁️'}
                </button>
              )}
              {!isLocked && <button className="btn btn-ghost btn-sm btn-danger" style={{ marginLeft: 8 }} onClick={() => handleRemove(key)}>✕</button>}
            </div>
          </div>
        ))}
      </div>
      {!isLocked && <button className="btn btn-outline" onClick={handleAdd} style={{ marginTop: 12 }}>+ 追加配置项</button>}
    </div>
  )
}
// 移除过时的 MappingFormMode
// 将表单数据转回 .env 文本
function parsedToEnvRaw(parsed, originalRaw) {
  const lines = originalRaw.split('\n')
  const usedKeys = new Set()
  const result = lines.map(line => {
    const stripped = line.trim()
    if (!stripped || stripped.startsWith('#')) return line
    const eqIdx = stripped.indexOf('=')
    if (eqIdx === -1) return line
    const key = stripped.substring(0, eqIdx).trim()
    if (key in parsed) {
      usedKeys.add(key)
      return `${key}=${parsed[key]}`
    }
    return line
  })
  for (const [key, val] of Object.entries(parsed)) {
    if (!usedKeys.has(key) && val) result.push(`${key}=${val}`)
  }
  return result.join('\n')
}

// 废弃 parsedToYamlRaw



export default function ConfigPage() {
  const [envContent, setEnvContent] = useState('')
  const [envParsed, setEnvParsed] = useState({})
  const [envPath, setEnvPath] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [envTab, setEnvTab] = useState('form')      // 'form' | 'raw'
  const [isLocked, setIsLocked] = useState(true)
  const addToast = useToast()

  useEffect(() => { loadConfigs() }, [])

  const loadConfigs = async () => {
    setLoading(true)
    try {
      const [env] = await Promise.all([
        api.getEnvConfig()
      ])
      setEnvContent(env.raw || '')
      setEnvParsed(env.parsed || {})
      setEnvPath(env.path || '')
    } catch (err) {
      addToast('加载配置失败: ' + err.message, 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleSaveEnv = async () => {
    setSaving(true)
    try {
      const content = envTab === 'form' ? parsedToEnvRaw(envParsed, envContent) : envContent
      await api.updateEnvConfig(content)
      addToast('环境变量配置已保存 ✓', 'success')
      loadConfigs() // 刷新
    } catch (err) {
      addToast('保存失败: ' + err.message, 'error')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
        <div className="spinner spinner-lg" />
      </div>
    )
  }

  return (
    <>
      <div className="page-header">
        <h2>⚙️ 系统配置</h2>
        <p>管理全局网络、密钥与数据库连接等大核心环境变量</p>
      </div>
      <div className="page-body">
        {isLocked && (
          <div style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid var(--danger)', padding: '12px 16px', borderRadius: 6, marginBottom: 16, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ fontSize: 20 }}>🛡️</span>
            <div>
              <strong style={{ display: 'block', color: 'var(--danger)', marginBottom: 4 }}>生产环境保护中</strong>
              <span style={{ fontSize: '0.85rem' }}>系统核心环境变量默认处于锁定保护状态。非管理员严禁随意修改配置。点击右上角强制解锁开关方可编辑。</span>
            </div>
          </div>
        )}

        <div className="config-single" style={{ width: '100%' }}>
          {/* .env 配置 */}
          <div className="card">
            <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between' }}>
              <div className="card-title">🔑 环境变量 (.env)</div>
              <div style={{ display: 'flex', gap: 12 }}>
                <button className={`btn btn-sm ${isLocked ? 'btn-danger' : 'btn-outline'}`} onClick={() => setIsLocked(!isLocked)}>
                  {isLocked ? '🔓 强制解锁修改' : '🔒 重新锁定状态'}
                </button>
                {!isLocked && (
                  <button className="btn btn-primary" onClick={handleSaveEnv} disabled={saving || isLocked}>
                    {saving ? <><div className="spinner" /> 保存中...</> : '💾 保存'}
                  </button>
                )}
              </div>
            </div>
            <div className="config-tabs">
              <button className={`config-tab ${envTab === 'form' ? 'active' : ''}`} onClick={() => setEnvTab('form')}>📋 表单模式</button>
              <button className={`config-tab ${envTab === 'raw' ? 'active' : ''}`} onClick={() => setEnvTab('raw')}>📝 原始编辑</button>
            </div>
            {envTab === 'form' ? (
              <EnvFormMode parsed={envParsed} onChange={setEnvParsed} isLocked={isLocked} />
            ) : (
              <>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: 12 }}>{envPath}</div>
                <textarea className="form-textarea" value={envContent} onChange={e => setEnvContent(e.target.value)} spellCheck={false} disabled={isLocked} />
              </>
            )}
          </div>
        </div>
      </div>
    </>
  )
}
