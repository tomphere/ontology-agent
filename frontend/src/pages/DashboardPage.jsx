import { useState, useEffect } from 'react'
import { LayoutDashboard, Wrench, Database, Sparkles, BrainCircuit, BarChart2, Dna, Tag, Link as LinkIcon, FileText, Box, ChevronUp, Lock, ChevronRight, X } from 'lucide-react'
import { api } from '../api'
import { useToast } from '../App'

function ToolCard({ tool }) {
  return (
    <div className="tool-card">
      <div className="tool-card-header-v2">
        <span className="tool-icon"><Wrench size={18} /></span>
        <div className="tool-info">
          <div className="tool-name">{tool.name}</div>
        </div>
      </div>
      <div className="tool-card-body-v2">
        <div className="tool-desc-full">{tool.description}</div>
        {tool.parameters?.length > 0 && (
          <div className="tool-params-badges">
            {tool.parameters.map(p => (
              <div key={p.name} className={`param-badge ${p.required ? 'param-required' : ''}`}>
                <span className="param-name">{p.name}</span>
                <span className="param-type">{p.type}</span>
                {p.description && <span className="param-desc">- {p.description}</span>}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default function DashboardPage() {
  const [status, setStatus] = useState(null)
  const [graphStats, setGraphStats] = useState(null)
  const [syncStatus, setSyncStatus] = useState(null)
  const [agentStatus, setAgentStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState({ ontology: false, database: false })
  const [ontologyDir, setOntologyDir] = useState('')
  const [fetchUrl, setFetchUrl] = useState('')
  const [fetching, setFetching] = useState(false)
  const [dirTab, setDirTab] = useState('local') // 'local' | 'remote'
  const [viewerFile, setViewerFile] = useState(null) // {filename, content, size}
  const [viewerLoading, setViewerLoading] = useState(false)
  const addToast = useToast()

  const handleViewFile = async (filename) => {
    setViewerLoading(true)
    try {
      const data = await api.readOntologyFile(filename)
      setViewerFile(data)
    } catch (err) {
      addToast('读取文件失败: ' + err.message, 'error')
    } finally {
      setViewerLoading(false)
    }
  }

  const loadData = async () => {
    setLoading(true)
    try {
      const [sys, sync, agent] = await Promise.all([
        api.getSystemStatus().catch(() => null),
        api.getSyncStatus().catch(() => null),
        api.getAgentStatus().catch(() => null),
      ])
      setStatus(sys)
      setSyncStatus(sync)
      setAgentStatus(agent)
      if (sys?.ontology_dir) setOntologyDir(sys.ontology_dir)

      if (sys?.neo4j?.connected) {
        const gs = await api.getGraphStats().catch(() => null)
        setGraphStats(gs)
      }
    } catch (err) {
      addToast('加载状态信息失败: ' + err.message, 'error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadData() }, [])

  const handleSyncOntology = async () => {
    setSyncing(p => ({ ...p, ontology: true }))
    try {
      const r = await api.syncOntology(ontologyDir)
      addToast(r.message || '本体同步完成', 'success')
      loadData()
    } catch (err) { addToast('本体同步失败: ' + err.message, 'error') }
    finally { setSyncing(p => ({ ...p, ontology: false })) }
  }

  const handleSyncDatabase = async () => {
    setSyncing(p => ({ ...p, database: true }))
    try {
      const r = await api.syncDatabase()
      addToast(r.message || '数据库同步完成', 'success')
      loadData()
    } catch (err) { addToast('数据库同步失败: ' + err.message, 'error') }
    finally { setSyncing(p => ({ ...p, database: false })) }
  }

  const handleSaveOntologyDir = async () => {
    try {
      await api.updateOntologyDir(ontologyDir)
      addToast('本体目录路径已保存', 'success')
      loadData()
    } catch (err) { addToast('保存失败: ' + err.message, 'error') }
  }

  const handleFetchRemote = async () => {
    if (!fetchUrl) return addToast('请输入有效远程链接', 'error')
    setFetching(true)
    try {
      const r = await api.fetchRemoteOntology(fetchUrl)
      addToast(r.message || '远程拉取成功', 'success')
      setFetchUrl('')
      loadData()
    } catch (err) {
      addToast('拉取失败: ' + err.message, 'error')
    } finally {
      setFetching(false)
    }
  }

  const handleInitAgent = async () => {
    addToast('正在初始化智能体，请稍候...', 'info')
    try {
      const r = await api.initAgent()
      addToast('智能体初始化成功！已加载工具: ' + (r.tools || []).join(', '), 'success')
      loadData()
    } catch (err) { addToast('智能体初始化失败: ' + err.message, 'error') }
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
        <h2 style={{ display: 'flex', alignItems: 'center', gap: 8 }}><LayoutDashboard size={24} /> 控制台仪表盘</h2>
        <p>系统连接状态、图谱概览与同步管理</p>
      </div>
      <div className="page-body">
        {/* 状态卡片 */}
        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-icon neo4j"><Database size={24}/></div>
            <div className="stat-info">
              <div className="stat-label">Neo4j 图数据库</div>
              <div className="stat-value">
                <span className={`status-dot ${status?.neo4j?.connected ? 'online' : 'offline'}`}/>
                {status?.neo4j?.connected ? '已连接' : '未连接'}
              </div>
              <div className="stat-sub">{status?.neo4j?.message || ''}</div>
            </div>
          </div>



          <div className="stat-card">
            <div className="stat-icon llm"><Sparkles size={24}/></div>
            <div className="stat-info">
              <div className="stat-label">大语言模型 (LLM)</div>
              <div className="stat-value">
                <span className={`status-dot ${status?.llm?.configured ? 'online' : 'offline'}`}/>
                {status?.llm?.configured ? '已配置' : '未配置'}
              </div>
              <div className="stat-sub">
                {status?.llm?.provider?.toUpperCase()}: {status?.llm?.model || 'N/A'}
              </div>
            </div>
          </div>

          <div className="stat-card">
            <div className="stat-icon agent"><BrainCircuit size={24}/></div>
            <div className="stat-info">
              <div className="stat-label">智能体状态</div>
              <div className="stat-value">
                <span className={`status-dot ${agentStatus?.initialized ? 'online' : 'unknown'}`}/>
                {agentStatus?.initialized ? '已就绪' : agentStatus?.initializing ? '初始化中...' : '未启动'}
              </div>
              <div className="stat-sub">
                {agentStatus?.initialized ? `${agentStatus.tools?.length || 0} 个工具已加载` : ''}
              </div>
            </div>
          </div>
        </div>

        {/* 同步操作区 */}
        {/* 数据同步管理已迁移至场景空间 */}


        {/* [V2] 工具清单 */}
        {agentStatus?.tools_detail?.length > 0 && (
          <div className="card" style={{ marginBottom: 24 }}>
            <div className="card-header">
              <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 6 }}><Wrench size={18} /> 智能体工具清单 ({agentStatus.tools_detail.length})</div>
            </div>
            <div className="tools-list">
              {agentStatus.tools_detail.map(t => <ToolCard key={t.name} tool={t} />)}
            </div>
          </div>
        )}

        {/* 图谱概览 */}
        {graphStats && (
          <div className="card">
            <div className="card-header">
              <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 6 }}><BarChart2 size={18} /> 知识图谱概览</div>
            </div>
            <div className="stats-grid">
              <div className="stat-card">
                <div className="stat-info">
                  <div className="stat-label">节点总数</div>
                  <div className="stat-value" style={{ color: 'var(--info)' }}>{graphStats.total_nodes?.toLocaleString()}</div>
                </div>
              </div>
              <div className="stat-card">
                <div className="stat-info">
                  <div className="stat-label">关系总数</div>
                  <div className="stat-value" style={{ color: 'var(--success)' }}>{graphStats.total_relationships?.toLocaleString()}</div>
                </div>
              </div>
            </div>

            {graphStats.labels?.length > 0 && (
              <>
                <div style={{ fontSize: '0.85rem', fontWeight: 600, marginTop: 16, marginBottom: 8 }}>节点标签分布</div>
                <div className="label-cloud">
                  {graphStats.labels.map(l => (
                    <span key={l.label} className="label-tag">
                      {l.label} <span className="count">{l.count}</span>
                    </span>
                  ))}
                </div>
              </>
            )}

            {graphStats.rel_types?.length > 0 && (
              <>
                <div style={{ fontSize: '0.85rem', fontWeight: 600, marginTop: 16, marginBottom: 8 }}>关系类型分布</div>
                <div className="label-cloud">
                  {graphStats.rel_types.map(r => (
                    <span key={r.type} className="label-tag">
                      {r.type} <span className="count">{r.count}</span>
                    </span>
                  ))}
                </div>
              </>
            )}
          </div>
        )}
      </div>

      {/* 本体文件可视化查看弹窗 */}
      {(viewerFile || viewerLoading) && (
        <div className="modal-overlay" onClick={() => { setViewerFile(null); setViewerLoading(false) }}>
          <div className="modal-content" style={{ maxWidth: 960, maxHeight: '90vh' }} onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h3 style={{ display: 'flex', alignItems: 'center', gap: 8 }}><Dna size={20} /> 本体可视化 — {viewerFile?.filename || '加载中...'}</h3>
              <button className="btn btn-ghost btn-sm" onClick={() => setViewerFile(null)}><X size={18}/></button>
            </div>
            <div className="modal-body" style={{ padding: 0 }}>
              {viewerLoading ? (
                <div style={{ textAlign: 'center', padding: 60 }}><div className="spinner spinner-lg" /></div>
              ) : viewerFile ? (
                <div className="onto-vis">
                  {/* 概览统计 */}
                  <div className="onto-stats-bar">
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}><Tag size={14} /> 类: <b>{viewerFile.classes?.length || 0}</b></span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}><LinkIcon size={14} /> 对象属性: <b>{viewerFile.object_properties?.length || 0}</b></span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}><FileText size={14} /> 数据属性: <b>{viewerFile.data_properties?.length || 0}</b></span>
                    {viewerFile.ontology_uri && <span style={{color: 'var(--text-muted)', fontSize: '0.75rem'}}>URI: {viewerFile.ontology_uri}</span>}
                  </div>

                  {/* 类层次 */}
                  <div className="onto-section">
                    <div className="onto-section-title" style={{ display: 'flex', alignItems: 'center', gap: 6 }}><Box size={16} /> 类定义 (Classes)</div>
                    <div className="onto-class-grid">
                      {(viewerFile.classes || []).map(cls => (
                        <div key={cls.name} className="onto-class-card">
                          <div className="onto-class-name">{cls.name}</div>
                          {cls.label && cls.label !== cls.name && <div className="onto-class-label">{cls.label}</div>}
                          {cls.comment && <div className="onto-class-comment">{cls.comment}</div>}
                          {cls.parents?.length > 0 && (
                            <div className="onto-class-parents" style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                              <ChevronUp size={14} /> 父类: {cls.parents.map(p => <span key={p} className="onto-tag parent">{p}</span>)}
                            </div>
                          )}
                          {cls.restrictions?.length > 0 && (
                            <div className="onto-class-restrictions">
                              {cls.restrictions.map((r, i) => (
                                <div key={i} className="onto-restriction">
                                  <span className="onto-tag constraint" style={{ display: 'flex', alignItems: 'center', gap: 4 }}><Lock size={10} /> {r.property}</span>
                                  <span className="onto-restriction-desc">
                                    {r.type === 'exactly' && `恰好 ${r.value} 个`}
                                    {r.type === 'min' && `至少 ${r.value} 个`}
                                    {r.type === 'max' && `至多 ${r.value} 个`}
                                    {r.type === 'some' && `存在关联: ${r.value}`}
                                    {r.dataRange && ` (${r.dataRange})`}
                                  </span>
                                  {r.comment && <div className="onto-restriction-comment">{r.comment}</div>}
                                </div>
                              ))}
                            </div>
                          )}
                          {/* 该类拥有的数据属性 */}
                          {(viewerFile.data_properties || []).filter(dp => dp.domains?.includes(cls.name)).length > 0 && (
                            <div className="onto-class-dataprops">
                              <div className="onto-dp-title" style={{ display: 'flex', alignItems: 'center', gap: 4 }}><FileText size={12} /> 数据属性</div>
                              {viewerFile.data_properties.filter(dp => dp.domains?.includes(cls.name)).map(dp => (
                                <div key={dp.name} className="onto-dp-row">
                                  <span className="onto-tag data">{dp.name}</span>
                                  <span className="onto-dp-type">{dp.range}</span>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* 对象属性: 关系连接 */}
                  <div className="onto-section">
                    <div className="onto-section-title" style={{ display: 'flex', alignItems: 'center', gap: 6 }}><LinkIcon size={16} /> 对象属性 (关系)</div>
                    <div className="onto-rel-list">
                      {(viewerFile.object_properties || []).map(op => (
                        <div key={op.name} className="onto-rel-row">
                          <span className="onto-tag domain">{op.domain}</span>
                          <span className="onto-rel-arrow">
                            <span className="onto-rel-line" />
                            <span className="onto-rel-name">{op.name}</span>
                            <span className="onto-rel-line" />
                            <span className="onto-rel-head"><ChevronRight size={10} /></span>
                          </span>
                          <span className="onto-tag range">{op.range}</span>
                          {op.comment && <div className="onto-rel-comment">{op.comment}</div>}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      )}
    </>
  )
}
