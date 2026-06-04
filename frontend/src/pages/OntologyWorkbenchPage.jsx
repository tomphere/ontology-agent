import { useState, useEffect } from 'react'
import { Box, CheckCircle, Factory, Link as LinkIcon, Palette, Plus, RefreshCw, Trash2, User, X } from 'lucide-react'
import { api } from '../api'
import { useToast } from '../App'
import OntologyStudio from '../components/OntologyStudio'

export default function OntologyWorkbenchPage() {
  const addToast = useToast()
  const [ontologies, setOntologies] = useState([])
  const [loading, setLoading] = useState(true)
  const [selectedOntology, setSelectedOntology] = useState(null)
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [createForm, setCreateForm] = useState({ name: '', description: '', iri: '' })
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    loadOntologies()
  }, [])

  const loadOntologies = async () => {
    setLoading(true)
    try {
      const data = await api.listAllOntologies()
      setOntologies(data.ontologies || [])
    } catch (e) {
      addToast('加载本体列表失败: ' + e.message, 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleCreate = async () => {
    if (!createForm.name.trim()) {
      addToast('本体名称不能为空', 'error')
      return
    }
    setCreating(true)
    try {
      const result = await api.createOntology(createForm)
      addToast(`本体 "${result.name}" 已创建`, 'success')
      setCreateForm({ name: '', description: '', iri: '' })
      setShowCreateForm(false)
      loadOntologies()
    } catch (e) {
      addToast('创建本体失败: ' + e.message, 'error')
    } finally {
      setCreating(false)
    }
  }

  const handleDelete = async (ontologyId) => {
    if (!confirm('确定要删除这个本体吗？此操作不可恢复。')) return
    try {
      await api.deleteOntology(ontologyId)
      addToast('本体已删除', 'success')
      if (selectedOntology?.id === ontologyId) {
        setSelectedOntology(null)
      }
      loadOntologies()
    } catch (e) {
      addToast('删除本体失败: ' + e.message, 'error')
    }
  }

  const handleBackToList = () => {
    setSelectedOntology(null)
    loadOntologies()
  }

  if (selectedOntology) {
    return (
      <div className="ontology-workbench-page ontology-workbench-page--studio">
        <div className="page-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <button className="btn btn-ghost btn-sm" onClick={handleBackToList}>
              ← 返回列表
            </button>
            <h1 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Factory size={24} /> 本体工坊 - {selectedOntology.name}
            </h1>
          </div>
        </div>
        <OntologyStudio ontologyId={selectedOntology.id} addToast={addToast} />
      </div>
    )
  }

  return (
    <div className="ontology-workbench-page ontology-workbench-page--list">
      <div className="page-header">
        <h1 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}><Palette size={24} /> 本体工坊</h1>
        <button className="btn btn-primary" onClick={() => setShowCreateForm(!showCreateForm)} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          {showCreateForm ? <><X size={16} /> 取消</> : <><Plus size={16} /> 创建新本体</>}
        </button>
      </div>

      {showCreateForm && (
        <div className="card" style={{ marginBottom: 24 }}>
          <h3 style={{ marginBottom: 16 }}>创建新本体</h3>
          <div className="form-grid">
            <div className="form-group">
              <label>本体名称 *</label>
              <input
                className="form-input"
                placeholder="例如：医疗本体"
                value={createForm.name}
                onChange={e => setCreateForm(p => ({ ...p, name: e.target.value }))}
              />
            </div>
            <div className="form-group">
              <label>本体 IRI</label>
              <input
                className="form-input"
                placeholder="http://ontology.example.com/my-ontology"
                value={createForm.iri}
                onChange={e => setCreateForm(p => ({ ...p, iri: e.target.value }))}
              />
            </div>
            <div className="form-group" style={{ gridColumn: '1 / -1' }}>
              <label>描述</label>
              <textarea
                className="form-input"
                rows={2}
                placeholder="本体的描述和用途"
                value={createForm.description}
                onChange={e => setCreateForm(p => ({ ...p, description: e.target.value }))}
              />
            </div>
          </div>
          <div style={{ marginTop: 16 }}>
            <button className="btn btn-success" onClick={handleCreate} disabled={creating} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              {creating ? <><RefreshCw size={16} className="spinning" /> 创建中...</> : <><CheckCircle size={16} /> 创建本体</>}
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="loading">加载中...</div>
      ) : ontologies.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: 60 }}>
          <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'center' }}><Palette size={48} /></div>
          <h3>暂无本体</h3>
          <p style={{ color: 'var(--text-muted)', marginBottom: 24 }}>
            点击上方"创建新本体"按钮开始创建您的第一个本体
          </p>
        </div>
      ) : (
        <div className="ontology-grid">
          {ontologies.map(ontology => (
            <div key={ontology.id} className="card ontology-card">
              <div className="ontology-card-header">
                <h3 className="ontology-card-title">{ontology.name}</h3>
                <div className="ontology-card-actions">
                  <button
                    className="btn btn-ghost btn-xs"
                    onClick={() => handleDelete(ontology.id)}
                    title="删除"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
              <p className="ontology-card-desc">{ontology.description || '暂无描述'}</p>
              <div className="ontology-card-stats">
                <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}><Box size={14} /> {ontology.classes_count || 0} 个类</span>
                <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}><User size={14} /> {ontology.individuals_count || 0} 个个体</span>
                <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}><LinkIcon size={14} /> {ontology.properties_count || 0} 个属性</span>
              </div>
              <div className="ontology-card-footer">
                <span className="ontology-card-date">
                  {new Date(ontology.updated_at || ontology.created_at).toLocaleString('zh-CN')}
                </span>
                <button
                  className="btn btn-primary btn-sm"
                  onClick={() => setSelectedOntology(ontology)}
                >
                  编辑本体
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
