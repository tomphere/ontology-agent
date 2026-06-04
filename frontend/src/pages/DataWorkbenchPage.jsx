import { useState, useEffect, useRef, useCallback } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import yaml from 'js-yaml'
import { FileText, Link as LinkIcon, Database, Network, SlidersHorizontal, Activity, ScrollText, BookOpen, Route, FileCode, CheckCircle, Search, RefreshCw, Save, Trash2, Plus, X, AlertCircle, FolderKanban, ChevronRight, ChevronDown, Download, Upload, MousePointer2, Settings, Box, Tag, User, GitBranch, Pencil, Power, HelpCircle } from 'lucide-react'
import { api } from '../api'
import { useToast, useTheme } from '../App'
import MappingBuilder from '../components/MappingBuilder'

// =============================================================================
// 场景空间 - 两级导航
// =============================================================================

const LABEL_COLORS = [
  '#6366f1', '#ec4899', '#34d399', '#fbbf24', '#60a5fa',
  '#f87171', '#a78bfa', '#2dd4bf', '#fb923c', '#818cf8',
  '#f472b6', '#4ade80', '#facc15', '#38bdf8', '#e879f9',
]

export default function DataWorkbenchPage() {
  const [scenes, setScenes] = useState([])
  const [loading, setLoading] = useState(true)
  const [activeScene, setActiveScene] = useState(null)
  const [showCreate, setShowCreate] = useState(false)
  const [createForm, setCreateForm] = useState({ name: '', description: '', data_mode: 'import' })
  const addToast = useToast()

  // 自定义确认弹窗
  const [confirmDialog, setConfirmDialog] = useState(null) // { title, message, onConfirm }

  const loadScenes = async () => {
    setLoading(true)
    try {
      const data = await api.listScenes()
      setScenes(data.scenes || [])
    } catch (e) { addToast('加载场景失败: ' + e.message, 'error') }
    finally { setLoading(false) }
  }

  useEffect(() => { loadScenes() }, [])

  const handleCreate = async () => {
    if (!createForm.name.trim()) { addToast('请输入场景名称', 'error'); return }
    try {
      await api.createScene(createForm.name, createForm.description, createForm.data_mode)
      addToast(`场景"${createForm.name}"创建成功`, 'success')
      setShowCreate(false)
      setCreateForm({ name: '', description: '', data_mode: 'import' })
      loadScenes()
    } catch (e) { addToast('创建失败: ' + e.message, 'error') }
  }

  const handleDelete = (id, name) => {
    setConfirmDialog({
      title: '删除场景',
      message: `确定要删除场景"${name}"吗？此操作将删除该场景下所有本体文件和映射配置，且不可撤销。`,
      onConfirm: async () => {
        try {
          await api.deleteScene(id)
          addToast('场景已删除', 'success')
          if (activeScene?.id === id) setActiveScene(null)
          loadScenes()
        } catch (e) { addToast('删除失败: ' + e.message, 'error') }
        finally { setConfirmDialog(null) }
      }
    })
  }

  // 如果选中了场景，显示场景详情
  if (activeScene) {
    return (
      <>
        <SceneDetailView
          scene={activeScene}
          onBack={() => { setActiveScene(null); loadScenes() }}
          addToast={addToast}
          setConfirmDialog={setConfirmDialog}
        />
        <ConfirmDialog dialog={confirmDialog} onCancel={() => setConfirmDialog(null)} />
      </>
    )
  }

  // 否则显示场景列表
  return (
    <div className="scene-workbench-page">
      <div className="page-header">
        <h2 style={{ display: 'flex', alignItems: 'center', gap: 8 }}><FolderKanban size={24} /> 场景空间</h2>
        <p>以场景为维度管理本体文件、数据映射、数据源和一致性校验</p>
      </div>
      <div className="page-body">
        <div style={{ marginBottom: 20, display: 'flex', gap: 12, alignItems: 'center' }}>
          <button className="btn btn-primary" onClick={() => setShowCreate(!showCreate)} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            {showCreate ? <><X size={16} /> 取消</> : <><Plus size={16} /> 新建场景</>}
          </button>
        </div>

        {showCreate && (
          <div className="card" style={{ marginBottom: 24 }}>
            <div className="card-header"><span className="card-title">新建场景</span></div>
            <div className="ds-form">
              <div className="ds-form-row">
                <label>场景名称 *</label>
                <input className="form-input" value={createForm.name}
                  onChange={e => setCreateForm(p => ({ ...p, name: e.target.value }))}
                  placeholder="例：IT运维资产管理" />
              </div>
              <div className="ds-form-row">
                <label>场景描述</label>
                <input className="form-input" value={createForm.description}
                  onChange={e => setCreateForm(p => ({ ...p, description: e.target.value }))}
                  placeholder="可选的描述信息" />
              </div>
              <div className="ds-form-row">
                <label>数据模式</label>
                <div style={{ display: 'flex', gap: 16 }}>
                  <label className="radio-label">
                    <input type="radio" name="data_mode" value="import"
                      checked={createForm.data_mode === 'import'}
                      onChange={() => setCreateForm(p => ({ ...p, data_mode: 'import' }))} />
                    <span>导入模式（同步到 Neo4j）</span>
                  </label>
                  <label className="radio-label">
                    <input type="radio" name="data_mode" value="virtual"
                      checked={createForm.data_mode === 'virtual'}
                      onChange={() => setCreateForm(p => ({ ...p, data_mode: 'virtual' }))} />
                    <span>虚拟模式（查询原始数据库）</span>
                  </label>
                </div>
              </div>
              <button className="btn btn-success" onClick={handleCreate} style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
                <CheckCircle size={16} /> 创建场景
              </button>
            </div>
          </div>
        )}

        {loading ? (
          <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-muted)' }}>
            <div className="spinner" /> 加载中...
          </div>
        ) : scenes.length === 0 ? (
          <div className="card" style={{ textAlign: 'center', padding: 60 }}>
            <div style={{ fontSize: 48, marginBottom: 16, color: 'var(--text-muted)', display: 'flex', justifyContent: 'center' }}><FolderKanban size={48} /></div>
            <div style={{ color: 'var(--text-muted)', fontSize: 16 }}>暂无场景，点击上方按钮创建第一个场景</div>
          </div>
        ) : (
          <div className="scene-grid">
            {scenes.map(s => (
              <div key={s.id} className="scene-card" onClick={() => setActiveScene(s)}>
                <div className="scene-card-header">
                  <span className="scene-card-title">{s.name}</span>
                  <button className="btn btn-ghost btn-sm"
                    onClick={e => { e.stopPropagation(); handleDelete(s.id, s.name) }}
                    title="删除" style={{ color: 'var(--danger-color)' }}><Trash2 size={16} /></button>
                </div>
                {s.description && <div className="scene-card-desc">{s.description}</div>}
                <div className="scene-card-tags">
                  <span className={`scene-tag ${s.data_mode}`} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    {s.data_mode === 'import' ? <><Database size={12} /> 导入模式</> : <><LinkIcon size={12} /> 虚拟模式</>}
                  </span>
                  <span className={`scene-tag ${(s.has_ontology || s.has_linked_ontology) ? 'ok' : 'missing'}`} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    {s.has_ontology ? <><FileText size={12} /> 本体文件 <CheckCircle size={10} /></> : s.has_linked_ontology ? <><LinkIcon size={12} /> 已关联本体</> : <><FileText size={12} /> 未配置本体</>}
                  </span>
                  <span className={`scene-tag ${s.has_mapping ? 'ok' : 'missing'}`} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    {s.has_mapping ? <><LinkIcon size={12} /> 映射配置 <CheckCircle size={10} /></> : <><LinkIcon size={12} /> 未配置映射</>}
                  </span>
                </div>
                <div className="scene-card-meta">
                  创建时间: {new Date(s.created_at).toLocaleDateString()}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      <ConfirmDialog dialog={confirmDialog} onCancel={() => setConfirmDialog(null)} />
    </div>
  )
}

// =============================================================================
// 通用确认弹窗组件
// =============================================================================

function ConfirmDialog({ dialog, onCancel }) {
  if (!dialog) return null
  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: 420 }}>
        <div className="modal-header">
          <span className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--danger-color)' }}><AlertCircle size={18} /> {dialog.title}</span>
          <button className="btn btn-ghost btn-sm" onClick={onCancel}><X size={16}/></button>
        </div>
        <div style={{ padding: 20, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
          {dialog.message}
        </div>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', padding: '0 20px 20px' }}>
          <button className="btn btn-outline" onClick={onCancel}>取消</button>
          <button className="btn btn-danger" onClick={dialog.onConfirm}>确认删除</button>
        </div>
      </div>
    </div>
  )
}

// =============================================================================
// 场景详情视图 (第二级)
// =============================================================================

const SCENE_TABS = [
  { id: 'ontology', label: '本体文件', icon: <FileText size={16} /> },
  { id: 'mapping', label: '数据映射', icon: <LinkIcon size={16} /> },
  { id: 'datasource', label: '数据源', icon: <Database size={16} /> },
  { id: 'graph', label: '图谱空间', icon: <Network size={16} /> },
  { id: 'tuning', label: '智能体高级配置', icon: <SlidersHorizontal size={16} /> },
  { id: 'diagnostics', label: '诊断与校验', icon: <Activity size={16} /> },
]

function SceneDetailView({ scene: initialScene, onBack, addToast, setConfirmDialog }) {
  const [scene, setScene] = useState(initialScene)
  const [activeTab, setActiveTab] = useState('ontology')

  const refreshScene = async () => {
    try {
      const data = await api.getScene(scene.id)
      setScene(data)
    } catch (e) { /* ignore */ }
  }

  return (
    <>
      <div className="page-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button className="btn btn-ghost" onClick={onBack} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <ChevronRight size={18} style={{ transform: 'rotate(180deg)' }} /> 返回
          </button>
          <div>
            <h2 style={{ margin: 0 }}>{scene.name}</h2>
            <p style={{ margin: 0, opacity: 0.7 }}>
              {scene.description || '暂无描述'}
              <span className={`scene-tag ${scene.data_mode}`} style={{ marginLeft: 12 }}>
                {scene.data_mode === 'import' ? '导入模式' : '虚拟模式'}
              </span>
            </p>
          </div>
        </div>
      </div>
      <div className="page-body">
        <div className="workbench-tabs">
          {SCENE_TABS.map(tab => (
            <button key={tab.id}
              className={`workbench-tab ${activeTab === tab.id ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
              style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </div>
        <div className="workbench-content">
          {activeTab === 'ontology' && <SceneOntologyPanel scene={scene} addToast={addToast} onRefresh={refreshScene} setConfirmDialog={setConfirmDialog} />}
          {activeTab === 'mapping' && <SceneMappingPanel scene={scene} addToast={addToast} />}
          {activeTab === 'datasource' && <SceneDatasourcePanel scene={scene} addToast={addToast} onRefresh={refreshScene} setConfirmDialog={setConfirmDialog} />}
          {activeTab === 'graph' && <SceneGraphPanel scene={scene} addToast={addToast} />}
          {activeTab === 'tuning' && <SceneTuningPanel scene={scene} addToast={addToast} />}
          {activeTab === 'diagnostics' && <SceneDiagnosticsPanel scene={scene} addToast={addToast} />}
        </div>
      </div>
    </>
  )
}

// =============================================================================
// 高级配置面板 (组合)
// =============================================================================

function SceneTuningPanel({ scene, addToast }) {
  const [activeSubTab, setActiveSubTab] = useState('rules')
  
  return (
    <div style={{ display: 'flex', gap: 24, height: '100%' }}>
      <div style={{ width: 220, flexShrink: 0, borderRight: '1px solid var(--border-color)', paddingRight: 16 }}>
        <h3 style={{ marginTop: 0, marginBottom: 16, fontSize: 16, display: 'flex', alignItems: 'center', gap: 8 }}><SlidersHorizontal size={18} /> 智能体调优</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <button className={`btn ${activeSubTab === 'rules' ? 'btn-primary' : 'btn-ghost'}`} style={{ justifyContent: 'flex-start', display: 'flex', gap: 8 }} onClick={() => setActiveSubTab('rules')}><ScrollText size={16} /> 业务规则配置</button>
          <button className={`btn ${activeSubTab === 'aliases' ? 'btn-primary' : 'btn-ghost'}`} style={{ justifyContent: 'flex-start', display: 'flex', gap: 8 }} onClick={() => setActiveSubTab('aliases')}><BookOpen size={16} /> 业务词典映射</button>
          <button className={`btn ${activeSubTab === 'routing' ? 'btn-primary' : 'btn-ghost'}`} style={{ justifyContent: 'flex-start', display: 'flex', gap: 8 }} onClick={() => setActiveSubTab('routing')}><Route size={16} /> 查询路由策略</button>
          <button className={`btn ${activeSubTab === 'fewshots' ? 'btn-primary' : 'btn-ghost'}`} style={{ justifyContent: 'flex-start', display: 'flex', gap: 8 }} onClick={() => setActiveSubTab('fewshots')}><FileCode size={16} /> Agent 提示词</button>
        </div>
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        {activeSubTab === 'rules' && <SceneRulesPanel scene={scene} addToast={addToast} />}
        {activeSubTab === 'aliases' && <SceneAliasesPanel scene={scene} addToast={addToast} />}
        {activeSubTab === 'routing' && <SceneRoutingPanel scene={scene} addToast={addToast} />}
        {activeSubTab === 'fewshots' && <SceneFewShotsPanel scene={scene} addToast={addToast} />}
      </div>
    </div>
  )
}

// =============================================================================
// 诊断与校验面板 (组合)
// =============================================================================

function SceneDiagnosticsPanel({ scene, addToast }) {
  const [activeSubTab, setActiveSubTab] = useState('qahealth')
  
  return (
    <div style={{ display: 'flex', gap: 24, height: '100%' }}>
      <div style={{ width: 220, flexShrink: 0, borderRight: '1px solid var(--border-color)', paddingRight: 16 }}>
        <h3 style={{ marginTop: 0, marginBottom: 16, fontSize: 16, display: 'flex', alignItems: 'center', gap: 8 }}><Activity size={18} /> 诊断与校验</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <button className={`btn ${activeSubTab === 'qahealth' ? 'btn-primary' : 'btn-ghost'}`} style={{ justifyContent: 'flex-start', display: 'flex', gap: 8 }} onClick={() => setActiveSubTab('qahealth')}><Search size={16} /> 本体问答健康</button>
          <button className={`btn ${activeSubTab === 'validation' ? 'btn-primary' : 'btn-ghost'}`} style={{ justifyContent: 'flex-start', display: 'flex', gap: 8 }} onClick={() => setActiveSubTab('validation')}><CheckCircle size={16} /> 一致性校验</button>
        </div>
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        {activeSubTab === 'qahealth' && <SceneQaHealthPanel scene={scene} addToast={addToast} />}
        {activeSubTab === 'validation' && <SceneValidationPanel scene={scene} addToast={addToast} />}
      </div>
    </div>
  )
}

// =============================================================================
// 本体文件面板
// =============================================================================

function SceneOntologyPanel({ scene, addToast, onRefresh, setConfirmDialog }) {
  const [parsedData, setParsedData] = useState(null)
  const [parsing, setParsing] = useState(false)
  const [linkMode, setLinkMode] = useState(false)
  const [ontologies, setOntologies] = useState([])
  const [selectedOntologyId, setSelectedOntologyId] = useState('')
  const [loadingOntologies, setLoadingOntologies] = useState(false)
  const hasLinkedOntology = Boolean(scene.linked_ontology_id)
  const hasOntologySource = Boolean(scene.has_ontology || hasLinkedOntology)

  useEffect(() => {
    if (linkMode) {
      loadOntologies()
    }
  }, [linkMode])

  useEffect(() => {
    if (scene.linked_ontology_id) {
      setSelectedOntologyId(scene.linked_ontology_id)
    }
  }, [scene.linked_ontology_id])

  const loadOntologies = async () => {
    setLoadingOntologies(true)
    try {
      const data = await api.listAllOntologies()
      setOntologies(data.ontologies || [])
    } catch (e) {
      addToast('加载本体列表失败: ' + e.message, 'error')
    } finally {
      setLoadingOntologies(false)
    }
  }

  const handleLinkOntology = async () => {
    if (!selectedOntologyId) {
      addToast('请选择一个本体', 'error')
      return
    }
    try {
      await api.updateScene(scene.id, { linked_ontology_id: selectedOntologyId })
      addToast('本体关联成功', 'success')
      setLinkMode(false)
      await onRefresh()
      await handleParse()
    } catch (e) { addToast('关联本体失败: ' + e.message, 'error') }
  }

  const handleUnlinkOntology = async () => {
    if (!confirm('确定要取消关联本体吗？')) return
    try {
      await api.updateScene(scene.id, { linked_ontology_id: null })
      addToast('已取消关联', 'success')
      setSelectedOntologyId('')
      setParsedData(null)
      await onRefresh()
    } catch (e) { addToast('取消关联失败: ' + e.message, 'error') }
  }

  const handleParse = async () => {
    setParsing(true)
    try {
      const data = await api.parseSceneOntology(scene.id)
      setParsedData(data)
    } catch (e) { addToast('解析失败: ' + e.message, 'error'); setParsedData(null) }
    finally { setParsing(false) }
  }

  useEffect(() => {
    if (scene.has_ontology || scene.linked_ontology_id) handleParse()
  }, [scene.id, scene.has_ontology, scene.linked_ontology_id])

  return (
    <div className="panel-grid">
      <div className="card">
        <div className="card-header">
          <span className="card-title">本体来源</span>
          <div style={{ display: 'flex', gap: 8 }}>
            {!linkMode && (
              <button className="btn btn-outline btn-sm" onClick={() => setLinkMode(true)} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <LinkIcon size={14} /> 关联本体工坊
              </button>
            )}
            {linkMode && (
              <button className="btn btn-outline btn-sm" onClick={() => setLinkMode(false)}>
                返回
              </button>
            )}
          </div>
        </div>

        {!linkMode ? (
          <>
            <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
              {hasOntologySource && (
                <button className="btn btn-outline btn-sm" onClick={handleParse} disabled={parsing} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  {parsing ? <RefreshCw size={14} className="spinning" /> : <Search size={14} />} 解析
                </button>
              )}
            </div>
            {hasLinkedOntology && (
              <div className="ontology-file-info" style={{ marginBottom: 12 }}>
                <span className="file-icon"><LinkIcon size={24} /></span>
                <div>
                  <div className="file-name">已关联本体工坊模型</div>
                  <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>本体ID: {scene.linked_ontology_id}，解析和映射构建将优先使用此模型</div>
                  <button className="btn btn-ghost btn-xs" onClick={handleUnlinkOntology} style={{ marginTop: 8 }}>
                    取消关联
                  </button>
                </div>
              </div>
            )}
            {scene.has_ontology ? (
              <div className="ontology-file-info">
                <span className="file-icon"><FileText size={24} /></span>
                <div>
                  <div className="file-name">历史上传文件：{scene.ontology_file}</div>
                  <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>当前场景空间不再提供本体文件导入；请优先关联本体工坊模型</div>
                </div>
              </div>
            ) : hasLinkedOntology ? (
              null
            ) : (
              <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
                <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'center' }}><FolderKanban size={40} /></div>
                <div>尚未配置本体</div>
                <div style={{ fontSize: 13, marginTop: 4 }}>请关联本体工坊中的模型</div>
              </div>
            )}
          </>
        ) : (
          <div>
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: 'block', marginBottom: 8, fontWeight: 500 }}>选择本体工坊中的本体</label>
              {loadingOntologies ? (
                <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-muted)' }}><RefreshCw size={20} className="spinning" /> 加载中...</div>
              ) : ontologies.length === 0 ? (
                <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-muted)' }}>
                  暂无可用本体，请先在<a href="#/ontology-workbench" style={{ color: 'var(--primary)' }}>本体工坊</a>中创建
                </div>
              ) : (
                <select
                  className="form-input"
                  value={selectedOntologyId}
                  onChange={e => setSelectedOntologyId(e.target.value)}
                  style={{ marginBottom: 12 }}
                >
                  <option value="">请选择本体...</option>
                  {ontologies.map(o => (
                    <option key={o.id} value={o.id}>
                      {o.name} ({o.classes_count || 0} 个类, {o.individuals_count || 0} 个个体)
                    </option>
                  ))}
                </select>
              )}
              {selectedOntologyId && (
                <button className="btn btn-success btn-sm" onClick={handleLinkOntology} style={{ display: 'flex', alignItems: 'center', gap: 4, justifyContent: 'center' }}>
                  <CheckCircle size={14} /> 关联选中本体
                </button>
              )}
            </div>
            {scene.linked_ontology_id && (
              <div style={{ padding: 12, background: 'var(--info-bg)', borderRadius: 'var(--radius-md)', border: '1px solid var(--info)' }}>
                <div style={{ fontWeight: 600, marginBottom: 4, display: 'flex', alignItems: 'center', gap: 6 }}><LinkIcon size={14} /> 已关联本体</div>
                <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                  本体ID: {scene.linked_ontology_id}
                </div>
                <button className="btn btn-ghost btn-xs" onClick={handleUnlinkOntology} style={{ marginTop: 8 }}>
                  取消关联
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {parsedData && (
        <div className="card">
          <div className="card-header">
            <span className="card-title">📋 解析结果: {parsedData.filename}</span>
          </div>
          <div className="parsed-result">
            <div className="parsed-section">
              <div className="section-title">类 ({parsedData.classes?.length || 0})</div>
              {parsedData.classes?.map(c => (
                <div key={c.name} className="parsed-item">
                  <strong>{c.name}</strong>
                  {c.label !== c.name && <span className="parsed-meta"> ({c.label})</span>}
                  {c.parents?.length > 0 && <span className="parsed-meta"> ← {c.parents.join(', ')}</span>}
                  {c.comment && <div className="parsed-desc">{c.comment}</div>}
                </div>
              ))}
            </div>
            <div className="parsed-section">
              <div className="section-title">对象属性 ({parsedData.object_properties?.length || 0})</div>
              {parsedData.object_properties?.map(p => (
                <div key={p.name} className="parsed-item">
                  <strong>{p.name}</strong>: {p.domain || '?'} → {p.range || '?'}
                </div>
              ))}
            </div>
            <div className="parsed-section">
              <div className="section-title">数据属性 ({parsedData.data_properties?.length || 0})</div>
              {parsedData.data_properties?.map(p => (
                <div key={p.name} className="parsed-item">
                  <strong>{p.name}</strong>: {p.domains?.join(', ') || '?'} → {p.range || '?'}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// =============================================================================
// 数据映射面板
// =============================================================================

function SceneMappingPanel({ scene, addToast }) {
  const [content, setContent] = useState('')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [showYaml, setShowYaml] = useState(false)
  const [showBuilder, setShowBuilder] = useState(true)
  const [clearBeforeSync, setClearBeforeSync] = useState(false)
  
  // 同步日志状态
  const [showSyncLog, setShowSyncLog] = useState(false)
  const [syncLogContent, setSyncLogContent] = useState('')
  const [showInstructions, setShowInstructions] = useState(false)
  const logContainerRef = useRef(null)

  const load = async () => {
    setLoading(true)
    try {
      const data = await api.getSceneMapping(scene.id)
      setContent(data.raw || '')
    } catch (e) { addToast('加载映射配置失败: ' + e.message, 'error') }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [scene.id])

  const handleSave = async () => {
    setSaving(true)
    try {
      await api.updateSceneMapping(scene.id, content)
      addToast('映射配置已保存', 'success')
    } catch (e) { addToast('保存失败: ' + e.message, 'error') }
    finally { setSaving(false) }
  }

  const handleSync = async () => {
    if (scene.data_mode === 'virtual') { addToast('虚拟模式无需同步数据', 'info'); return }
    setSyncing(true)
    try {
      const res = await api.syncScene(scene.id, clearBeforeSync)
      addToast(res.message || '同步完成', 'success')
      fetchSyncLog(true) // 同步完成后自动拉取一下日志以便查看
    } catch (e) { 
      addToast('同步失败: ' + e.message, 'error') 
    }
    finally { setSyncing(false) }
  }

  const fetchSyncLog = async (silent = false) => {
    try {
      const res = await api.getSceneSyncLog(scene.id)
      setSyncLogContent(res.log || '无日志内容')
      if (!silent) setShowSyncLog(true)
    } catch (e) {
      if (!silent) addToast('拉取日志失败: ' + e.message, 'error')
    }
  }

  // 监听打开日志弹窗时自动滚动到底部
  useEffect(() => {
    if (showSyncLog && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight
    }
  }, [showSyncLog, syncLogContent])

  return (
    <div>
      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 0' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ fontSize: 20 }}>{scene.data_mode === 'import' ? <Download size={24} /> : <LinkIcon size={24} />}</span>
            <div>
              <strong>{scene.data_mode === 'import' ? '导入模式' : '虚拟模式'}</strong>
              <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>
                {scene.data_mode === 'import' ? '数据将同步到 Neo4j 图数据库' : '数据留在原始数据库，通过 SQL 翻译实时查询'}
              </div>
            </div>
          </div>
          {scene.data_mode === 'import' && (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <button className="btn btn-outline btn-sm" onClick={() => setShowInstructions(true)} style={{ color: 'var(--warning-color)', borderColor: 'var(--warning-color)', display: 'flex', alignItems: 'center', gap: 4 }}>
                <BookOpen size={14} /> 配置说明
              </button>
              <label className="checkbox-label" style={{ fontSize: 13 }}>
                <input
                  type="checkbox"
                  checked={clearBeforeSync}
                  onChange={e => setClearBeforeSync(e.target.checked)}
                />
                同步前清空旧数据
              </label>
              <button className="btn btn-outline btn-sm" onClick={() => fetchSyncLog(false)} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <ScrollText size={14} /> 查看同步日志
              </button>
              <button className="btn btn-primary btn-sm" onClick={handleSync} disabled={syncing} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                {syncing ? <RefreshCw size={14} className="spinning" /> : <Power size={14} />}
                {syncing ? '同步中...' : '同步到 Neo4j'}
              </button>
            </div>
          )}
        </div>
      </div>

      {/* 映射配置指导说明弹窗 */}
      {showInstructions && (
        <div className="modal-overlay" onClick={() => setShowInstructions(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: 600 }}>
            <div className="modal-header">
              <span className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 6 }}><BookOpen size={18} /> 数据映射配置指引</span>
              <button className="btn btn-ghost btn-sm" onClick={() => setShowInstructions(false)}><X size={16} /></button>
            </div>
            <div style={{ padding: '0 20px 20px' }}>
              <div style={{ background: 'rgba(255,193,7,0.05)', border: '1px solid rgba(255,193,7,0.2)', borderRadius: 8, padding: 12, marginBottom: 16, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                数据映射（Mapping）是连接关系型数据库与图本体的桥梁。正确的配置能确保业务数据准确地转化为知识图谱。
              </div>
              <div className="instruction-list" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                {[
                  { title: '1. 实体映射 (表 → 类)', content: '在左侧“数据库”面板中点击并展开一张表，然后在右侧“本体结构”面板中点击一个本体类。系统会将该表的所有记录映射为该类的实例。' },
                  { title: '2. 属性映射 (字段 → 数据属性)', content: '点击左侧表中已展开的某个字段（变为蓝色高亮），然后在右侧面板中点击对应类下的某个数据属性。这会将表字段的值同步到实体的属性中。' },
                  { title: '3. 关系映射 (外键 → 对象属性)', content: '点击左侧表中字段旁边的关系图标按钮。在弹窗中选择目标实体类、对象属性名及关系方向。这用于构建图谱中的边。' },
                  { title: '4. 关系边表模式', content: '如果某张表仅作为两个实体之间的连接桥梁（如“转账记录”连接两个“账户”），请在映射模式中选择“关系映射”，并配置起点/终点信息。' },
                  { title: '5. 保存与同步', content: '配置完成后，务必点击下方“保存映射”，然后点击“同步到 Neo4j”。同步进度可点击“查看同步日志”观察。' }
                ].map((item, i) => (
                  <div key={i}>
                    <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4, fontSize: 14 }}>{item.title}</div>
                    <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.5 }}>{item.content}</div>
                  </div>
                ))}
              </div>
              <div style={{ marginTop: 24, display: 'flex', justifyContent: 'flex-end' }}>
                <button className="btn btn-primary" onClick={() => setShowInstructions(false)}>知道了</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 同步日志查看器弹窗 */}
      {showSyncLog && (
        <div className="modal-overlay" onClick={() => setShowSyncLog(false)}>
           <div className="modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: 800, width: '90%' }}>
             <div className="modal-header">
               <span className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 6 }}><ScrollText size={18} /> 后端引擎同步日志 (sync.log)</span>
               <div style={{ display: 'flex', gap: 8 }}>
                 <button className="btn btn-outline btn-sm" onClick={() => fetchSyncLog(false)} style={{ display: 'flex', alignItems: 'center', gap: 4 }}><RefreshCw size={14} /> 刷新</button>
                 <button className="btn btn-ghost btn-sm" onClick={() => setShowSyncLog(false)}><X size={16} /></button>
               </div>
             </div>
             <div style={{ padding: 16 }}>
               <pre 
                 ref={logContainerRef}
                 style={{ 
                   background: '#1e1e1e', 
                   color: '#a6e22e', 
                   padding: 16, 
                   borderRadius: 6, 
                   maxHeight: '60vh', 
                   overflowY: 'auto',
                   whiteSpace: 'pre-wrap',
                   wordBreak: 'break-all',
                   fontSize: '0.82rem',
                   fontFamily: 'var(--font-mono)'
                 }}
               >
                 {syncLogContent}
               </pre>
               <div style={{ marginTop: 12, display: 'flex', justifyContent: 'flex-end' }}>
                 <button className="btn btn-primary" onClick={() => setShowSyncLog(false)}>关闭</button>
               </div>
             </div>
           </div>
        </div>
      )}

      <div style={{ marginBottom: 16, display: 'flex', gap: 8 }}>
        <button className={`btn btn-sm ${showBuilder ? 'btn-primary' : 'btn-outline'}`}
          onClick={() => { setShowBuilder(true); setShowYaml(false) }}>🎨 可视化构建</button>
        <button className={`btn btn-sm ${showYaml ? 'btn-primary' : 'btn-outline'}`}
          onClick={() => { setShowYaml(true); setShowBuilder(false) }}>📄 YAML 编辑器</button>
      </div>

      {showBuilder && (
        <MappingBuilder sceneId={scene.id} addToast={addToast}
          onYamlGenerated={(yaml) => { setContent(yaml); addToast('YAML 配置已生成', 'success') }} />
      )}

      {showYaml && (
        <div className="card">
          <div className="card-header">
            <span className="card-title">mapping.yaml</span>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-outline btn-sm" onClick={load} disabled={loading}>🔄 重新加载</button>
              <button className="btn btn-success btn-sm" onClick={handleSave} disabled={saving}>
                {saving ? '保存中...' : '💾 保存'}
              </button>
            </div>
          </div>
          <textarea className="form-textarea" value={content} onChange={e => setContent(e.target.value)}
            style={{ minHeight: 500, fontFamily: 'var(--font-mono)' }} spellCheck={false} />
        </div>
      )}
    </div>
  )
}

// =============================================================================
// 图谱空间面板
// =============================================================================

function SceneGraphPanel({ scene, addToast }) {
  const [graphData, setGraphData] = useState({ nodes: [], links: [] })
  const [loading, setLoading] = useState(false)
  const [filterLabel, setFilterLabel] = useState('')
  const [filterRel, setFilterRel] = useState('')
  const [limit, setLimit] = useState(200)
  const [graphScope, setGraphScope] = useState('data')
  const [labelOptions, setLabelOptions] = useState([])
  const [relOptions, setRelOptions] = useState([])
  const [selectedNode, setSelectedNode] = useState(null)
  const [labelColorMap, setLabelColorMap] = useState({})
  const [labelDisplayMap, setLabelDisplayMap] = useState({})
  const [relDisplayMap, setRelDisplayMap] = useState({})
  const [legendOpen, setLegendOpen] = useState(true)
  const graphRef = useRef()
  const { theme } = useTheme()

  const loadGraph = useCallback(async (silent = false) => {
    setLoading(true)
    setSelectedNode(null)
    try {
      const data = await api.exploreGraph({
        scene_id: scene.id,
        label: filterLabel || undefined,
        rel_type: filterRel || undefined,
        limit,
        scope: graphScope,
      })
      const uniqueLabels = [...new Set((data.nodes || []).map(n => n.label).filter(Boolean))]
      const cmap = {}
      uniqueLabels.forEach((lbl, i) => { cmap[lbl] = LABEL_COLORS[i % LABEL_COLORS.length] })
      setLabelColorMap(cmap)
      setGraphData({ nodes: data.nodes || [], links: data.links || [] })
      setLabelOptions(data.label_options || uniqueLabels.sort())
      setRelOptions(data.rel_options || [...new Set((data.links || []).map(l => l.type).filter(Boolean))].sort())
      setLabelDisplayMap(data.label_display || {})
      setRelDisplayMap(data.rel_display || {})
      if (!silent) addToast(`已加载 ${data.total_nodes || 0} 个节点, ${data.total_links || 0} 条关系`, 'success')
    } catch (e) {
      addToast('场景图谱加载失败: ' + e.message, 'error')
      setGraphData({ nodes: [], links: [] })
    } finally {
      setLoading(false)
    }
  }, [scene.id, filterLabel, filterRel, limit, graphScope, addToast])

  useEffect(() => { loadGraph(true) }, [loadGraph])

  const handleZoomFit = () => {
    if (graphRef.current) graphRef.current.zoomToFit(400, 40)
  }

  const nodeCanvasObject = useCallback((node, ctx, globalScale) => {
    const label = node.name || node.id || ''
    const fontSize = Math.max(12 / globalScale, 4)
    const radius = selectedNode?.id === node.id ? 8 : 6
    const baseColor = labelColorMap[node.label] || '#6366f1'

    ctx.beginPath()
    ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI, false)
    ctx.fillStyle = baseColor
    ctx.shadowColor = baseColor
    ctx.shadowBlur = 9 / globalScale
    ctx.fill()
    ctx.shadowBlur = 0

    if (selectedNode?.id === node.id) {
      ctx.beginPath()
      ctx.arc(node.x, node.y, radius + 5, 0, 2 * Math.PI, false)
      ctx.strokeStyle = (theme === 'light' || theme === 'glass') ? 'rgba(15, 23, 42, 0.45)' : 'rgba(255,255,255,0.45)'
      ctx.lineWidth = 2 / globalScale
      ctx.stroke()
    }

    if (globalScale > 0.65) {
      ctx.font = `600 ${fontSize}px Inter, sans-serif`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'top'
      ctx.fillStyle = (theme === 'light' || theme === 'glass') ? 'rgba(15, 23, 42, 0.9)' : 'rgba(232,234,237,0.9)'
      ctx.fillText(label.slice(0, 16) + (label.length > 16 ? '...' : ''), node.x, node.y + radius + 4)
    }
  }, [labelColorMap, selectedNode, theme])

  const graphSummary = `${graphData.nodes.length} 节点 / ${graphData.links.length} 关系`
  const selectedProperties = selectedNode?.display_properties || selectedNode?.properties || {}

  return (
    <div className="scene-graph-shell">
      <div className="scene-graph-toolbar">
        <div className="scene-graph-actions">
          <select className="form-select" value={graphScope} onChange={e => { setGraphScope(e.target.value); setFilterLabel(''); setFilterRel('') }}>
            <option value="data">业务图谱</option>
            <option value="ontology">本体图谱</option>
          </select>
          <select className="form-select" value={filterLabel} onChange={e => setFilterLabel(e.target.value)}>
            <option value="">全部标签</option>
            {labelOptions.map(label => <option key={label} value={label}>{labelDisplayMap[label] || label}</option>)}
          </select>
          <select className="form-select" value={filterRel} onChange={e => setFilterRel(e.target.value)}>
            <option value="">全部关系</option>
            {relOptions.map(rel => <option key={rel} value={rel}>{relDisplayMap[rel] || rel}</option>)}
          </select>
          <select className="form-select scene-graph-limit" value={limit} onChange={e => setLimit(Number(e.target.value))} title="关系加载上限，用于避免大图一次性渲染过慢">
            <option value={25}>25 条关系</option>
            <option value={50}>50 条关系</option>
            <option value={100}>100 条关系</option>
            <option value={200}>200 条关系</option>
            <option value={500}>500 条关系</option>
            <option value={1000}>1000 条关系</option>
          </select>
          <button className="btn btn-outline btn-sm" onClick={handleZoomFit} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <MousePointer2 size={14} /> 适合画布
          </button>
          <button className="btn btn-primary btn-sm" onClick={() => loadGraph(false)} disabled={loading} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            {loading ? <RefreshCw size={14} className="spinning" /> : <RefreshCw size={14} />}
            {loading ? '加载中...' : '刷新'}
          </button>
          <span className="scene-graph-summary">{graphSummary}</span>
        </div>
      </div>

      <div className="scene-graph-body">
        <div className="scene-graph-canvas">
          {loading ? (
            <div className="graph-loading">
              <div className="spinner spinner-lg" />
              <p>正在加载场景图谱...</p>
            </div>
          ) : graphData.nodes.length === 0 ? (
            <div className="scene-graph-empty">
              <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'center' }}><Network size={44} /></div>
              <div>当前场景暂无图谱数据</div>
              <p>请先在“数据映射”中同步到 Neo4j，或在运营管理中迁移历史图谱到当前场景。</p>
            </div>
          ) : (
            <ForceGraph2D
              ref={graphRef}
              graphData={graphData}
              nodeId="id"
              nodeCanvasObject={nodeCanvasObject}
              nodePointerAreaPaint={(node, color, ctx) => {
                ctx.beginPath()
                ctx.arc(node.x, node.y, 10, 0, 2 * Math.PI)
                ctx.fillStyle = color
                ctx.fill()
              }}
              linkColor={() => (theme === 'light' || theme === 'glass') ? 'rgba(15, 23, 42, 0.14)' : 'rgba(255,255,255,0.14)'}
              linkWidth={1}
              linkDirectionalArrowLength={4}
              linkDirectionalArrowRelPos={1}
              onNodeClick={setSelectedNode}
              onBackgroundClick={() => setSelectedNode(null)}
              nodeLabel={node => `${node.display_label || node.label || ''}：${node.name || node.id || ''}`}
              linkLabel={link => link.display_type || link.type || ''}
              backgroundColor="transparent"
              cooldownTicks={80}
              warmupTicks={40}
            />
          )}

          <div className={`scene-graph-legend ${legendOpen ? 'open' : 'collapsed'}`}>
            <button className="scene-graph-legend-toggle" onClick={() => setLegendOpen(!legendOpen)}>
              <span>图例</span>
              <span>{legendOpen ? '收起' : '展开'}</span>
            </button>
            {legendOpen && (
              Object.keys(labelColorMap).length === 0 ? (
                <div className="scene-graph-muted">暂无标签</div>
              ) : (
                <div className="legend-list">
                  {Object.entries(labelColorMap).map(([label, color]) => (
                    <div key={label} className="legend-item">
                      <span className="legend-dot" style={{ background: color }} />
                      <span>{labelDisplayMap[label] || label}</span>
                    </div>
                  ))}
                </div>
              )
            )}
          </div>

          {selectedNode && (
            <aside className="scene-graph-detail-drawer">
              <div className="scene-graph-detail-head">
                <div>
                  <div className="detail-section-title">节点详情</div>
                  <div className="scene-graph-muted">{selectedNode.name || selectedNode.id}</div>
                </div>
                <button className="scene-graph-close-btn" onClick={() => setSelectedNode(null)} title="关闭详情">✕</button>
              </div>
              <div className="scene-graph-node-detail">
                <div className="detail-row">
                  <span className="detail-key">类型</span>
                  <span className="label-tag">{selectedNode.display_label || selectedNode.label || '-'}</span>
                </div>
                <div className="detail-row">
                  <span className="detail-key">名称</span>
                  <span className="detail-val">{selectedNode.name || selectedNode.id}</span>
                </div>
                <div className="detail-divider" />
                {Object.entries(selectedProperties).map(([k, v]) => (
                  <div key={k} className="detail-row">
                    <span className="detail-key">{k}</span>
                    <span className="detail-val">{String(v)}</span>
                  </div>
                ))}
              </div>
            </aside>
          )}
        </div>
      </div>
    </div>
  )
}

// =============================================================================
// Rules 业务规则面板
// =============================================================================

function SceneRulesPanel({ scene, addToast }) {
  const [rules, setRules] = useState([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const data = await api.getSceneRules(scene.id)
      if (data.raw) {
        const parsed = yaml.load(data.raw)
        setRules(parsed?.rules || [])
      } else {
        setRules([])
      }
    } catch (e) { addToast('加载规则失败: ' + e.message, 'error') }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [scene.id])

  const handleSave = async () => {
    setSaving(true)
    try {
      const yamlStr = yaml.dump({ rules: rules.filter(r => r.trim() !== '') })
      await api.updateSceneRules(scene.id, yamlStr)
      addToast('业务规则已保存', 'success')
      load()
    } catch (e) { addToast('保存失败: ' + e.message, 'error') }
    finally { setSaving(false) }
  }

  const updateRule = (idx, val) => {
    const newRules = [...rules]
    newRules[idx] = val
    setRules(newRules)
  }

  const addRule = () => setRules([...rules, ''])
  const removeRule = (idx) => setRules(rules.filter((_, i) => i !== idx))

  return (
    <div>
      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ padding: '12px 16px', lineHeight: 1.6, color: 'var(--text-secondary)' }}>
          <div style={{color: 'var(--text-primary)', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6}}>
            <HelpCircle size={18} /> <strong>业务规则配置指导：</strong>
          </div>
          <p style={{ margin: '0 0 8px 0' }}>规则是智能体推理的“大脑常识”。当用户提问包含模糊的业务名词时，智能体会依据这里的规则翻译为具体的查询条件。</p>
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            <li><strong>条件定义：</strong>明确某类实体或事件的具体过滤条件（如“风险分数&gt;=80”）。</li>
            <li><strong>关联路径指导：</strong>如果跨实体查询路径复杂，直接写明路径（如“资金往来路径: Person-[:ownsAsset]-&gt;BankAcct...”）。</li>
          </ul>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
           <span className="card-title">规则列表 (rules)</span>
           <div style={{ display: 'flex', gap: 8 }}>
             <button className="btn btn-outline btn-sm" onClick={load} disabled={loading} style={{ display: 'flex', alignItems: 'center', gap: 4 }}><RefreshCw size={14}/> 刷新</button>
             <button className="btn btn-success btn-sm" onClick={handleSave} disabled={saving} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
               <Save size={14}/> {saving ? '保存中...' : '保存配置'}
             </button>
           </div>
        </div>
        <div style={{ padding: 16 }}>
          {rules.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '32px 0', color: 'var(--text-secondary)' }}>暂无配置规则</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {rules.map((rule, idx) => (
                <div key={idx} style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                  <div style={{ marginTop: 8, color: 'var(--text-secondary)', fontSize: 12 }}>{idx + 1}.</div>
                  <textarea 
                    className="form-textarea" 
                    value={rule} 
                    onChange={e => updateRule(idx, e.target.value)} 
                    style={{ flex: 1, minHeight: 60 }} 
                    placeholder="请输入业务规则描述..." 
                  />
                  <button className="btn btn-ghost btn-sm" style={{ color: 'var(--danger-color)' }} onClick={() => removeRule(idx)} title="删除规则"><Trash2 size={16} /></button>
                </div>
              ))}
            </div>
          )}
          <button className="btn btn-outline btn-full" style={{ marginTop: 16 }} onClick={addRule}>
            <Plus size={16} /> 添加一条新规则
          </button>
        </div>
      </div>
    </div>
  )
}

// =============================================================================
// Aliases 业务词典面板
// =============================================================================

function SceneAliasesPanel({ scene, addToast }) {
  const [aliases, setAliases] = useState([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const data = await api.getSceneAliases(scene.id)
      if (data.raw) {
        const parsed = yaml.load(data.raw)
        if (parsed?.aliases) {
          const arr = Object.entries(parsed.aliases).map(([key, vals]) => ({
            key,
            values: Array.isArray(vals) ? vals.join(', ') : String(vals)
          }))
          setAliases(arr)
        } else {
          setAliases([])
        }
      } else {
        setAliases([])
      }
    } catch (e) { addToast('加载词典失败: ' + e.message, 'error') }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [scene.id])

  const handleSave = async () => {
    setSaving(true)
    try {
      const aliasDict = {}
      aliases.forEach(a => {
        const k = a.key.trim()
        if (k) {
          aliasDict[k] = a.values.split(',').map(v => v.trim()).filter(v => v !== '')
        }
      })
      const yamlStr = yaml.dump({ aliases: aliasDict })
      await api.updateSceneAliases(scene.id, yamlStr)
      addToast('业务词典已保存', 'success')
      load()
    } catch (e) { addToast('保存失败: ' + e.message, 'error') }
    finally { setSaving(false) }
  }

  const updateAlias = (idx, field, val) => {
    const newArr = [...aliases]
    newArr[idx][field] = val
    setAliases(newArr)
  }

  const addAlias = () => setAliases([...aliases, { key: '', values: '' }])
  const removeAlias = (idx) => setAliases(aliases.filter((_, i) => i !== idx))

  return (
    <div>
      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ padding: '12px 16px', lineHeight: 1.6, color: 'var(--text-secondary)' }}>
          <div style={{color: 'var(--text-primary)', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6}}>
            <HelpCircle size={18} /> <strong>业务词典映射指导：</strong>
          </div>
          <p style={{ margin: '0 0 8px 0' }}>词典用于将用户口语化的名词映射为标准图谱本体类名或关系名。例如：</p>
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            <li><strong>标准词：</strong>输入英文类名或关系名（如 `Asset`，`Incident`）。</li>
            <li><strong>同义词：</strong>输入对应的中文同义词，多个同义词使用<strong>英文逗号</strong>分隔（如 `服务器, 主机, 节点`）。</li>
          </ul>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
           <span className="card-title">同义词列表 (aliases)</span>
           <div style={{ display: 'flex', gap: 8 }}>
             <button className="btn btn-outline btn-sm" onClick={load} disabled={loading} style={{ display: 'flex', alignItems: 'center', gap: 4 }}><RefreshCw size={14}/> 刷新</button>
             <button className="btn btn-success btn-sm" onClick={handleSave} disabled={saving} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
               <Save size={14}/> {saving ? '保存中...' : '保存配置'}
             </button>
           </div>
        </div>
        <div style={{ padding: 16 }}>
          {aliases.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '32px 0', color: 'var(--text-secondary)' }}>暂无业务词典</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {aliases.map((item, idx) => (
                <div key={idx} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <input 
                    type="text" 
                    className="form-input" 
                    placeholder="标准词 (例如: Asset)" 
                    style={{ width: 200 }}
                    value={item.key} 
                    onChange={e => updateAlias(idx, 'key', e.target.value)} 
                  />
                  <span style={{ color: 'var(--text-secondary)' }}>=&gt;</span>
                  <input 
                    type="text" 
                    className="form-input" 
                    placeholder="同义词，用逗号分隔 (例如: 服务器, 主机, 节点)" 
                    style={{ flex: 1 }}
                    value={item.values} 
                    onChange={e => updateAlias(idx, 'values', e.target.value)} 
                  />
                  <button className="btn btn-ghost btn-sm" style={{ color: 'var(--danger-color)' }} onClick={() => removeAlias(idx)} title="删除"><Trash2 size={16} /></button>
                </div>
              ))}
            </div>
          )}
          <button className="btn btn-outline btn-full" style={{ marginTop: 16 }} onClick={addAlias}>
            <Plus size={16} /> 添加一条新词典
          </button>
        </div>
      </div>
    </div>
  )
}

// =============================================================================
// Routing 路由策略面板
// =============================================================================

function SceneRoutingPanel({ scene, addToast }) {
  const [routes, setRoutes] = useState([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  const TOOL_OPTIONS = [
    { value: 'Semantic_Incident_Search', label: '事件文本搜索 (Semantic_Incident_Search)' },
    { value: 'Semantic_Ticket_Search', label: 'IT工单搜索 (Semantic_Ticket_Search)' },
    { value: 'Send_Alert_Notification', label: '发送告警通知 (Send_Alert_Notification)' },
    { value: 'Restart_Server_Action', label: '重启服务器 (Restart_Server_Action)' }
  ]

  const load = async () => {
    setLoading(true)
    try {
      const data = await api.getSceneRouting(scene.id)
      if (data.raw) {
        const parsed = yaml.load(data.raw)
        setRoutes(parsed?.query_routing || [])
      } else {
        setRoutes([])
      }
    } catch (e) { addToast('加载路由失败: ' + e.message, 'error') }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [scene.id])

  const handleSave = async () => {
    setSaving(true)
    try {
      // Clean up empty strings before saving
      const cleanedRoutes = routes.map(r => ({
        ...r,
        match: r.match ? {
          classes: (r.match.classes || []).filter(v => v),
          vector_fields: (r.match.vector_fields || []).filter(v => v),
          any_terms: (r.match.any_terms || []).filter(v => v)
        } : undefined
      }))
      const yamlStr = yaml.dump({ query_routing: cleanedRoutes })
      await api.updateSceneRouting(scene.id, yamlStr)
      addToast('查询路由已保存', 'success')
      load()
    } catch (e) { addToast('保存失败: ' + e.message, 'error') }
    finally { setSaving(false) }
  }

  const addRoute = () => {
    setRoutes([...routes, {
      name: 'new_route',
      mode: 'semantic_then_graph',
      tool: 'Semantic_Incident_Search',
      function: 'ontology_intelligence.plugins.semantic_incident_search.semantic_incident_search',
      match: { classes: [], vector_fields: [], any_terms: [] }
    }])
  }

  const removeRoute = (idx) => setRoutes(routes.filter((_, i) => i !== idx))

  const updateRoute = (idx, field, val) => {
    const newRoutes = [...routes]
    if (field.startsWith('match.')) {
      const matchField = field.split('.')[1]
      newRoutes[idx].match = { ...newRoutes[idx].match, [matchField]: val }
    } else {
      newRoutes[idx][field] = val
    }
    setRoutes(newRoutes)
  }

  const ListInput = ({ label, values, onChange, placeholder }) => (
    <div style={{ flex: 1 }}>
      <label style={{ display: 'block', marginBottom: 4, fontSize: 12, color: 'var(--text-secondary)' }}>{label}</label>
      <input 
        type="text" 
        className="form-input" 
        value={(values || []).join(', ')} 
        onChange={e => onChange(e.target.value.split(',').map(v => v.trim()).filter(v => v))}
        placeholder={placeholder}
      />
    </div>
  )

  return (
    <div>
      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ padding: '12px 16px', lineHeight: 1.6, color: 'var(--text-secondary)' }}>
          <div style={{color: 'var(--text-primary)', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6}}>
            <Route size={18} /> <strong>查询路由策略指导：</strong>
          </div>
          <p style={{ margin: '0 0 8px 0' }}>配置在特定条件下，绕过纯图谱查询（Cypher），将用户问题路由给专门的插件工具（如全文语义检索）。</p>
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            <li><strong>触发条件：</strong>当用户提问包含任意配置的 <code>触发关键词</code>，或问题匹配到指定的 <code>关联实体类</code> 时，该路由生效。</li>
            <li><strong>执行工具：</strong>下拉选择系统内已注册的插件工具。</li>
          </ul>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
           <span className="card-title">路由规则列表 (query_routing)</span>
           <div style={{ display: 'flex', gap: 8 }}>
             <button className="btn btn-outline btn-sm" onClick={load} disabled={loading} style={{ display: 'flex', alignItems: 'center', gap: 4 }}><RefreshCw size={14}/> 刷新</button>
             <button className="btn btn-success btn-sm" onClick={handleSave} disabled={saving} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
               <Save size={14}/> {saving ? '保存中...' : '保存配置'}
             </button>
           </div>
        </div>
        <div style={{ padding: 16 }}>
          {routes.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '32px 0', color: 'var(--text-secondary)' }}>暂无路由规则</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {routes.map((route, idx) => (
                <div key={idx} style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: 16, position: 'relative' }}>
                  <button 
                    className="btn btn-ghost btn-sm" 
                    style={{ position: 'absolute', top: 12, right: 12, color: 'var(--danger-color)' }} 
                    onClick={() => removeRoute(idx)}
                    title="删除该路由"
                  >
                    <Trash2 size={16} />
                  </button>
                  
                  <div style={{ display: 'flex', gap: 16, marginBottom: 12 }}>
                    <div style={{ flex: 1 }}>
                      <label style={{ display: 'block', marginBottom: 4, fontSize: 12, color: 'var(--text-secondary)' }}>路由规则名称 (Name)</label>
                      <input type="text" className="form-input" value={route.name || ''} onChange={e => updateRoute(idx, 'name', e.target.value)} />
                    </div>
                    <div style={{ flex: 1 }}>
                      <label style={{ display: 'block', marginBottom: 4, fontSize: 12, color: 'var(--text-secondary)' }}>执行工具 (Tool)</label>
                      <select className="form-input" value={route.tool || ''} onChange={e => updateRoute(idx, 'tool', e.target.value)}>
                        <option value="">-- 选择工具 --</option>
                        {TOOL_OPTIONS.map(opt => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
                      </select>
                    </div>
                  </div>

                  <div style={{ display: 'flex', gap: 16, marginBottom: 12 }}>
                    <div style={{ flex: 1 }}>
                      <label style={{ display: 'block', marginBottom: 4, fontSize: 12, color: 'var(--text-secondary)' }}>执行函数路径 (Function Path)</label>
                      <input type="text" className="form-input" value={route.function || ''} onChange={e => updateRoute(idx, 'function', e.target.value)} />
                    </div>
                  </div>

                  <div style={{ background: 'var(--bg-secondary)', padding: 12, borderRadius: 6 }}>
                    <div style={{ fontSize: 13, fontWeight: 'bold', marginBottom: 8, color: 'var(--text-primary)' }}>匹配条件 (Match)</div>
                    <div style={{ display: 'flex', gap: 16, marginBottom: 12 }}>
                      <ListInput 
                        label="关联实体类 (Classes) - 逗号分隔" 
                        values={route.match?.classes} 
                        onChange={v => updateRoute(idx, 'match.classes', v)} 
                        placeholder="Incident, Alert"
                      />
                      <ListInput 
                        label="检索向量字段 (Vector Fields) - 逗号分隔" 
                        values={route.match?.vector_fields} 
                        onChange={v => updateRoute(idx, 'match.vector_fields', v)} 
                        placeholder="incidents.detailed_docs"
                      />
                    </div>
                    <div style={{ display: 'flex', gap: 16 }}>
                      <ListInput 
                        label="触发关键词 (Any Terms) - 逗号分隔" 
                        values={route.match?.any_terms} 
                        onChange={v => updateRoute(idx, 'match.any_terms', v)} 
                        placeholder="线索, 告警, 事件"
                      />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
          <button className="btn btn-outline btn-full" style={{ marginTop: 16 }} onClick={addRoute}>
            <Plus size={16} /> 添加路由策略
          </button>
        </div>
      </div>
    </div>
  )
}

// =============================================================================
// Few Shots 提示词面板
// =============================================================================

function SceneFewShotsPanel({ scene, addToast }) {
  const [content, setContent] = useState('')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const data = await api.getSceneFewShots(scene.id)
      setContent(data.raw || '')
    } catch (e) { addToast('加载提示词失败: ' + e.message, 'error') }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [scene.id])

  const handleSave = async () => {
    setSaving(true)
    try {
      await api.updateSceneFewShots(scene.id, content)
      addToast('提示词已保存', 'success')
    } catch (e) { addToast('保存失败: ' + e.message, 'error') }
    finally { setSaving(false) }
  }

  return (
    <div>
      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ padding: '12px 16px', lineHeight: 1.6, color: 'var(--text-secondary)' }}>
          <div style={{color: 'var(--text-primary)', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6}}>
            <FileCode size={18} /> <strong>Agent 提示词样例指导：</strong>
          </div>
          <p style={{ margin: '0 0 8px 0' }}>为了应对智能体在面对极其复杂的多级跳跃关联时出现的查询错误，您可以在下方书写业务场景特定的 Few-Shot 小样本。智能体会通过局部向量 RAG 检索这里最匹配的样例进行学习。</p>
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            <li>格式严格为 <code>问题：[用户问题]</code> 和 <code>Cypher：[Cypher语句]</code> 交替。</li>
          </ul>
        </div>
      </div>
      
      <div className="card">
        <div className="card-header">
           <span className="card-title">few_shots.txt 专用引导库</span>
           <div style={{ display: 'flex', gap: 8 }}>
             <button className="btn btn-outline btn-sm" onClick={load} disabled={loading}><RefreshCw size={14}/> 刷新</button>
             <button className="btn btn-success btn-sm" onClick={handleSave} disabled={saving}>
               <Save size={14}/> {saving ? '保存中...' : '保存'}
             </button>
           </div>
        </div>
        <textarea className="form-textarea" value={content} onChange={e => setContent(e.target.value)}
          placeholder="问题：哪些设备之间存在异常关联？\nCypher：\nMATCH (a:Asset)-[:connectsTo]->(b:Asset)..."
          style={{ minHeight: 400, fontFamily: 'var(--font-mono)', lineHeight: 1.6 }} spellCheck={false} />
      </div>
    </div>
  )
}

// =============================================================================
// 本体问答健康检查面板
// =============================================================================

function SceneQaHealthPanel({ scene, addToast }) {
  const [health, setHealth] = useState(null)
  const [agentStatus, setAgentStatus] = useState(null)
  const [loading, setLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const [healthData, statusData] = await Promise.all([
        api.getSceneQaHealth(scene.id),
        api.getAgentStatus(scene.id).catch(() => null),
      ])
      setHealth(healthData)
      setAgentStatus(statusData)
    } catch (e) {
      addToast('加载问答健康检查失败: ' + e.message, 'error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [scene.id])

  const badgeClass = (status) => status === 'ok' ? 'success' : status === 'error' ? 'error' : 'warning'

  return (
    <div>
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-header">
          <span className="card-title">本体驱动问答健康检查</span>
          <button className="btn btn-primary btn-sm" onClick={load} disabled={loading}>
            {loading ? '检查中...' : '刷新'}
          </button>
        </div>
        <div style={{ color: 'var(--text-secondary)', lineHeight: 1.7 }}>
          当前检查本体绑定、映射契约、场景图谱数据、事件向量索引、语义检索工具和 Agent 初始化诊断。
        </div>
      </div>

      {health && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-header">
            <span className="card-title">场景检查</span>
            <span className={`validation-badge ${health.summary === 'ready' ? 'success' : health.summary === 'error' ? 'error' : 'warning'}`}>
              {health.summary === 'ready' ? 'Ready' : health.summary}
            </span>
          </div>
          <div className="validation-section">
            {(health.checks || []).map((item, index) => (
              <div key={index} className={`validation-item ${badgeClass(item.status)}`}>
                <span className="validation-category">{item.name}</span>
                <span>{item.message}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="card">
        <div className="card-header">
          <span className="card-title">Agent 诊断</span>
          <span className={`validation-badge ${agentStatus?.initialized ? 'success' : 'warning'}`}>
            {agentStatus?.initialized ? '已初始化' : '未初始化'}
          </span>
        </div>
        {agentStatus?.diagnostics ? (
          <div className="validation-section">
            <div className="validation-item success"><span className="validation-category">本体ID</span><span>{agentStatus.diagnostics.linked_ontology_id || '-'}</span></div>
            <div className="validation-item success"><span className="validation-category">映射数量</span><span>{agentStatus.diagnostics.mapping_count ?? '-'}</span></div>
            <div className="validation-item success"><span className="validation-category">候选路径</span><span>{agentStatus.diagnostics.candidate_path_count ?? '-'}</span></div>
            <div className="validation-item success"><span className="validation-category">工具</span><span>{(agentStatus.diagnostics.tool_names || agentStatus.tools || []).join('、') || '-'}</span></div>
          </div>
        ) : (
          <div style={{ color: 'var(--text-secondary)' }}>Agent 尚未初始化或暂无诊断信息。</div>
        )}
      </div>
    </div>
  )
}

// =============================================================================
// 数据源面板 - 支持完整增删改查
// =============================================================================

const DS_EMPTY = { type: 'mysql', host: '', port: '3306', user: '', password: '', database: '', schema: '', label: '' }

function SceneDatasourcePanel({ scene, addToast, onRefresh, setConfirmDialog }) {
  const [allDatasources, setAllDatasources] = useState([])
  const [selectedIds, setSelectedIds] = useState(scene.datasource_ids || [])
  const [saving, setSaving] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [editingDs, setEditingDs] = useState(null) // null=新建, ds对象=编辑
  const [dsForm, setDsForm] = useState({ ...DS_EMPTY })
  const [testing, setTesting] = useState(false)
  const [searchDs, setSearchDs] = useState('')

  const loadAll = async () => {
    try {
      const data = await api.listDatasources()
      setAllDatasources(data.datasources || [])
    } catch (e) { addToast('加载数据源失败: ' + e.message, 'error') }
  }

  useEffect(() => { loadAll() }, [])

  const toggleDs = (id) => {
    setSelectedIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id])
  }

  const handleSaveAssociation = async () => {
    setSaving(true)
    try {
      await api.updateSceneDatasources(scene.id, selectedIds)
      addToast('数据源关联已更新', 'success')
      onRefresh()
    } catch (e) { addToast('保存失败: ' + e.message, 'error') }
    finally { setSaving(false) }
  }

  // 新建数据源
  const handleAddNew = () => {
    setEditingDs(null)
    setDsForm({ ...DS_EMPTY })
    setShowForm(true)
  }

  // 编辑数据源
  const handleEdit = (ds) => {
    setEditingDs(ds)
    setDsForm({ ...ds })
    setShowForm(true)
  }

  // 删除数据源
  const handleDeleteDs = (ds) => {
    setConfirmDialog({
      title: '删除数据源',
      message: `确定要删除数据源"${ds.label || ds.database}"吗？所有引用该数据源的场景将受影响。`,
      onConfirm: async () => {
        try {
          await api.deleteDatasource(ds.id)
          addToast('数据源已删除', 'success')
          setSelectedIds(prev => prev.filter(id => id !== ds.id))
          loadAll()
        } catch (e) { addToast('删除失败: ' + e.message, 'error') }
        finally { setConfirmDialog(null) }
      }
    })
  }

  // 测试连接
  const handleTest = async () => {
    setTesting(true)
    try {
      const res = await api.testDatasource(dsForm)
      addToast(res.message || '连接成功', res.success ? 'success' : 'error')
    } catch (e) { addToast('连接测试失败: ' + e.message, 'error') }
    finally { setTesting(false) }
  }

  // 保存（新增或编辑）
  const handleSaveDs = async () => {
    if (!dsForm.host || !dsForm.database || !dsForm.user) {
      addToast('请填写完整的连接信息（主机、数据库、用户名）', 'error')
      return
    }
    try {
      if (editingDs) {
        // 删除旧的再添加新的（简化处理）
        await api.deleteDatasource(editingDs.id)
      }
      const res = await api.addDatasource(dsForm)
      addToast(editingDs ? '数据源已更新' : '数据源已添加', 'success')
      // 自动勾选新加的数据源
      if (res.id && !selectedIds.includes(res.id)) {
        setSelectedIds(prev => [...prev, res.id])
      }
      setShowForm(false)
      loadAll()
    } catch (e) { addToast('保存失败: ' + e.message, 'error') }
  }

  const filteredDs = allDatasources.filter(ds =>
    !searchDs ||
    (ds.label || '').toLowerCase().includes(searchDs.toLowerCase()) ||
    ds.database.toLowerCase().includes(searchDs.toLowerCase()) ||
    ds.host.toLowerCase().includes(searchDs.toLowerCase())
  )

  return (
    <div>
      <div className="card">
        <div className="card-header">
          <span className="card-title">数据源管理</span>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-primary btn-sm" onClick={handleAddNew} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <Plus size={14} /> 新增数据源
            </button>
            <button className="btn btn-success btn-sm" onClick={handleSaveAssociation} disabled={saving} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              {saving ? <RefreshCw size={14} className="spinning" /> : <Save size={14} />}
              {saving ? '保存中...' : '保存关联'}
            </button>
          </div>
        </div>
        <p style={{ color: 'var(--text-secondary)', marginBottom: 12 }}>
          勾选要关联到此场景的数据源。可在此直接新增、编辑或删除数据源。
        </p>

        {/* 搜索 */}
        {allDatasources.length > 3 && (
          <div className="mapping-search-bar" style={{ marginBottom: 12 }}>
            <input className="mapping-search-input" placeholder="搜索数据源..."
              value={searchDs} onChange={e => setSearchDs(e.target.value)} />
            {searchDs && <button className="mapping-search-clear" onClick={() => setSearchDs('')}><X size={14} /></button>}
          </div>
        )}

        {filteredDs.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
            {allDatasources.length === 0 ? '暂无数据源，点击"新增数据源"添加。' : '没有匹配的数据源'}
          </div>
        ) : (
          <div className="ds-checklist">
            {filteredDs.map(ds => (
              <div key={ds.id} className={`ds-check-item ${selectedIds.includes(ds.id) ? 'checked' : ''}`}>
                <input type="checkbox" checked={selectedIds.includes(ds.id)}
                  onChange={() => toggleDs(ds.id)} />
                <span className="ds-type-icon">
                  <Database size={16} />
                </span>
                <div style={{ flex: 1 }}>
                  <div className="ds-label">{ds.label || ds.database}</div>
                  <div className="ds-meta">{ds.type} · {ds.host}:{ds.port}/{ds.database}</div>
                </div>
                <div style={{ display: 'flex', gap: 4 }}>
                  <button className="btn btn-ghost btn-sm" onClick={() => handleEdit(ds)} title="编辑"><Pencil size={14} /></button>
                  <button className="btn btn-ghost btn-sm" onClick={() => handleDeleteDs(ds)} title="删除" style={{ color: 'var(--danger-color)' }}><Trash2 size={14} /></button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 新增/编辑数据源表单弹窗 */}
      {showForm && (
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: 520 }}>
            <div className="modal-header">
              <span className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                {editingDs ? <Pencil size={18} /> : <Plus size={18} />}
                {editingDs ? '编辑数据源' : '新增数据源'}
              </span>
              <button className="btn btn-ghost btn-sm" onClick={() => setShowForm(false)}><X size={16} /></button>
            </div>
            <div className="ds-form" style={{ padding: 20 }}>
              <div className="ds-form-row">
                <label>标签名称</label>
                <input className="form-input" value={dsForm.label}
                  onChange={e => setDsForm(p => ({ ...p, label: e.target.value }))}
                  placeholder="可选，用于显示" />
              </div>
              <div className="ds-form-row">
                <label>数据库类型</label>
                <select className="form-input" value={dsForm.type}
                  onChange={e => setDsForm(p => ({ ...p, type: e.target.value, port: e.target.value === 'mysql' ? '3306' : e.target.value === 'postgresql' ? '5432' : '1521' }))}>
                  <option value="mysql">MySQL</option>
                  <option value="postgresql">PostgreSQL</option>
                  <option value="oracle">Oracle</option>
                </select>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 12 }}>
                <div className="ds-form-row">
                  <label>主机地址 *</label>
                  <input className="form-input" value={dsForm.host}
                    onChange={e => setDsForm(p => ({ ...p, host: e.target.value }))}
                    placeholder="例：db.internal.example" />
                </div>
                <div className="ds-form-row">
                  <label>端口 *</label>
                  <input className="form-input" value={dsForm.port}
                    onChange={e => setDsForm(p => ({ ...p, port: e.target.value }))}
                    placeholder="3306" />
                </div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: dsForm.type === 'oracle' ? '2fr 1fr' : '1fr', gap: 12 }}>
                <div className="ds-form-row">
                  <label>数据库名 / SID *</label>
                  <input className="form-input" value={dsForm.database}
                    onChange={e => setDsForm(p => ({ ...p, database: e.target.value }))}
                    placeholder="数据库名称" />
                </div>
                {dsForm.type === 'oracle' && (
                  <div className="ds-form-row">
                    <label>Schema / Owner</label>
                    <input className="form-input" value={dsForm.schema}
                      onChange={e => setDsForm(p => ({ ...p, schema: e.target.value }))}
                      placeholder="大写用户名" />
                  </div>
                )}
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div className="ds-form-row">
                  <label>用户名 *</label>
                  <input className="form-input" value={dsForm.user}
                    onChange={e => setDsForm(p => ({ ...p, user: e.target.value }))}
                    placeholder="root" />
                </div>
                <div className="ds-form-row">
                  <label>密码</label>
                  <input className="form-input" type="password" value={dsForm.password}
                    onChange={e => setDsForm(p => ({ ...p, password: e.target.value }))}
                    placeholder="••••••" />
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
                <button className="btn btn-outline" onClick={handleTest} disabled={testing} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  {testing ? <RefreshCw size={14} className="spinning" /> : <Power size={14} />}
                  {testing ? '测试中...' : '测试连接'}
                </button>
                <button className="btn btn-success" onClick={handleSaveDs} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <CheckCircle size={14} /> {editingDs ? '更新' : '添加'}
                </button>
                <button className="btn btn-outline" onClick={() => setShowForm(false)}>取消</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// =============================================================================
// 一致性校验面板
// =============================================================================

function SceneValidationPanel({ scene, addToast }) {
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)

  const runCheck = async () => {
    setLoading(true)
    try {
      const data = await api.validateScene(scene.id)
      setResult(data)
      addToast(data.summary, data.errors?.length ? 'error' : 'success')
    } catch (e) { addToast('校验失败: ' + e.message, 'error') }
    finally { setLoading(false) }
  }

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">一致性校验</span>
        <button className="btn btn-primary btn-sm" onClick={runCheck} disabled={loading} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          {loading ? <RefreshCw size={14} className="spinning" /> : <Search size={14} />} 校验
        </button>
      </div>
      <p style={{ color: 'var(--text-secondary)', marginBottom: 20 }}>
        校验本体文件、映射配置与数据源表结构之间的一致性。
      </p>
      {result && (
        <div className="validation-result">
          <div className="validation-summary">
            <span className={`validation-badge ${result.errors?.length ? 'error' : 'success'}`}>
              {result.summary}
            </span>
          </div>
          {result.errors?.length > 0 && (
            <div className="validation-section">
              <div className="section-title" style={{ color: 'var(--danger)', display: 'flex', alignItems: 'center', gap: 6 }}><XCircle size={16} /> 错误 ({result.errors.length})</div>
              {result.errors.map((e, i) => (
                <div key={i} className="validation-item error">
                  <span className="validation-category">{e.category}</span>
                  <span>{e.message}</span>
                </div>
              ))}
            </div>
          )}
          {result.warnings?.length > 0 && (
            <div className="validation-section">
              <div className="section-title" style={{ color: 'var(--warning)', display: 'flex', alignItems: 'center', gap: 6 }}><AlertCircle size={16} /> 警告 ({result.warnings.length})</div>
              {result.warnings.map((w, i) => (
                <div key={i} className="validation-item warning">
                  <span className="validation-category">{w.category}</span>
                  <span>{w.message}</span>
                </div>
              ))}
            </div>
          )}
          {result.passed?.length > 0 && (
            <div className="validation-section">
              <div className="section-title" style={{ color: 'var(--success)', display: 'flex', alignItems: 'center', gap: 6 }}><CheckCircle size={16} /> 通过 ({result.passed.length})</div>
              {result.passed.map((p, i) => (
                <div key={i} className="validation-item passed">
                  <span className="validation-category">{p.category}</span>
                  <span>{p.message}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
