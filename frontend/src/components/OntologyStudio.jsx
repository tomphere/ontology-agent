import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import ReactDOM from 'react-dom'
import { 
  Box, Link as LinkIcon, FileText, Tag, User, GitBranch, Network, 
  Search, FileSearch, Database, Scroll, Settings, Plus, Trash2, 
  Download, Upload, SearchCode, Check, X, ChevronRight, ChevronDown,
  RefreshCw, MousePointer2, Factory, Pencil, Save, AlertTriangle, 
  CheckCircle, XCircle, Play, BarChart2
} from 'lucide-react'
import { api } from '../api'
import { useToast } from '../App'
import DLQueryPanel from './DLQueryPanel'
import SPARQLPanel from './SPARQLPanel'
import SWRLRuleEditor from './SWRLRuleEditor'

const createPortal = ReactDOM.createPortal || ReactDOM.unstable_createPortal

// =============================================================================
// 本体工坊 - Protégé 风格的本体建模工具
// =============================================================================

const STUDIO_TABS = [
  { id: 'classes', label: '类', icon: <Box size={14} /> },
  { id: 'object-properties', label: '对象属性', icon: <LinkIcon size={14} /> },
  { id: 'data-properties', label: '数据属性', icon: <FileText size={14} /> },
  { id: 'annotation-properties', label: '注释属性', icon: <Tag size={14} /> },
  { id: 'individuals', label: '个体', icon: <User size={14} /> },
  { id: 'hierarchy', label: '层次结构', icon: <GitBranch size={14} /> },
  { id: 'graph', label: '关系图', icon: <Network size={14} /> },
  { id: 'reasoner', label: '推理机', icon: <Search size={14} /> },
  { id: 'dl-query', label: 'DL 查询', icon: <SearchCode size={14} /> },
  { id: 'sparql-query', label: 'SPARQL 查询', icon: <Database size={14} /> },
  { id: 'swrl-rules', label: 'SWRL 规则', icon: <Scroll size={14} /> },
  { id: 'metadata', label: '本体元数据', icon: <Settings size={14} /> },
]

export default function OntologyStudio({ ontologyId, addToast }) {
  const [activeTab, setActiveTab] = useState('classes')
  const [stats, setStats] = useState(null)
  const [showImport, setShowImport] = useState(false)
  const [importing, setImporting] = useState(false)
  const [graphRefreshKey, setGraphRefreshKey] = useState(0)
  const fileInputRef = useState(null)

  useEffect(() => {
    loadStats()
  }, [ontologyId])

  const loadStats = async () => {
    try {
      const data = await api.getOntologyStats(ontologyId)
      setStats(data)
    } catch (e) { /* ignore */ }
  }

  const handleImport = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return

    setImporting(true)
    try {
      const result = await api.importOntology(ontologyId, file)
      addToast(
        `导入成功！新增 ${result.stats.new_classes} 个类、${result.stats.new_object_properties} 个对象属性、${result.stats.new_data_properties} 个数据属性、${result.stats.new_individuals} 个个体`,
        'success'
      )
      loadStats()
      setGraphRefreshKey(k => k + 1)
      setShowImport(false)
    } catch (err) {
      addToast('导入失败: ' + err.message, 'error')
    } finally {
      setImporting(false)
      e.target.value = ''
    }
  }

  return (
    <div className="ontology-studio">
      <div className="studio-header">
        <div>
          <h3 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}><Factory size={20} /> 本体工坊</h3>
          <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--text-muted)' }}>
            Protégé 风格的本体建模工具，支持类/属性/个体管理，兼容 OWL/RDF/TTL 格式
          </p>
        </div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          {stats && (
            <div className="studio-stats">
              <span className="stat-item"><Box size={14} /> {stats.classes_count} 类</span>
              <span className="stat-item"><LinkIcon size={14} /> {stats.object_properties_count} 对象属性</span>
              <span className="stat-item"><FileText size={14} /> {stats.data_properties_count} 数据属性</span>
              <span className="stat-item"><User size={14} /> {stats.individuals_count} 个体</span>
            </div>
          )}
          <button
            className="btn btn-outline btn-sm"
            onClick={() => setShowImport(!showImport)}
            disabled={importing}
            style={{ display: 'flex', alignItems: 'center', gap: 4 }}
          >
            {importing ? <><RefreshCw size={14} className="spinning" /> 导入中...</> : <><Download size={14} /> 导入本体</>}
          </button>
        </div>
      </div>

      {showImport && (
        <div className="import-panel">
          <div className="import-panel-content">
            <div>
              <h4 style={{ margin: '0 0 8px', display: 'flex', alignItems: 'center', gap: 6 }}><Download size={18} /> 导入本体文件</h4>
              <p style={{ margin: 0, fontSize: 13, color: 'var(--text-muted)' }}>
                支持 OWL/RDF/TTL/N3/JSON-LD 格式，导入后将自动解析类、属性、个体等元素
              </p>
            </div>
            <label className="btn btn-primary btn-sm" style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <Upload size={14} /> 选择文件
              <input
                type="file"
                accept=".owl,.rdf,.ttl,.nt,.n3,.jsonld,.json-ld"
                onChange={handleImport}
                style={{ display: 'none' }}
                disabled={importing}
              />
            </label>
          </div>
        </div>
      )}

      <div className="studio-tabs">
        {STUDIO_TABS.map(tab => (
          <button
            key={tab.id}
            className={`studio-tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
            style={{ display: 'flex', alignItems: 'center', gap: 6 }}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      <div className="studio-content">
        {activeTab === 'classes' && <ClassPanel ontologyId={ontologyId} addToast={addToast} onStatsChange={loadStats} />}
        {activeTab === 'object-properties' && <ObjectPropertyPanel ontologyId={ontologyId} addToast={addToast} onStatsChange={loadStats} />}
        {activeTab === 'data-properties' && <DataPropertyPanel ontologyId={ontologyId} addToast={addToast} onStatsChange={loadStats} />}
        {activeTab === 'annotation-properties' && <AnnotationPropertyPanel ontologyId={ontologyId} addToast={addToast} onStatsChange={loadStats} />}
        {activeTab === 'individuals' && <IndividualPanel ontologyId={ontologyId} addToast={addToast} onStatsChange={loadStats} />}
        {activeTab === 'hierarchy' && <ClassHierarchyPanel ontologyId={ontologyId} addToast={addToast} />}
        {activeTab === 'graph' && <OntologyGraphPanel ontologyId={ontologyId} addToast={addToast} refreshKey={graphRefreshKey} />}
        {activeTab === 'reasoner' && <ReasonerPanel ontologyId={ontologyId} addToast={addToast} />}
        {activeTab === 'dl-query' && <DLQueryPanel ontologyId={ontologyId} />}
        {activeTab === 'sparql-query' && <SPARQLPanel ontologyId={ontologyId} />}
        {activeTab === 'swrl-rules' && <SWRLRuleEditor sceneId={ontologyId} />}
        {activeTab === 'metadata' && <MetadataPanel ontologyId={ontologyId} addToast={addToast} />}
      </div>
    </div>
  )
}

// =============================================================================
// 类管理面板
// =============================================================================

function ClassPanel({ ontologyId, addToast, onStatsChange }) {
  const [classes, setClasses] = useState([])
  const [objectProperties, setObjectProperties] = useState([])
  const [dataProperties, setDataProperties] = useState([])
  const [selectedClass, setSelectedClass] = useState(null)
  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState(false)
  const [formData, setFormData] = useState({ name: '', label: '', comment: '', parents: [], disjoint_with: [], equivalent_to: [], restrictions: [] })
  const [loading, setLoading] = useState(false)
  const [viewMode, setViewMode] = useState('tree')

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [classesData, objPropsData, dataPropsData] = await Promise.all([
        api.listOntologyClasses(ontologyId),
        api.listOntologyObjectProperties(ontologyId),
        api.listOntologyDataProperties(ontologyId)
      ])
      setClasses(classesData.classes || [])
      setObjectProperties(objPropsData.object_properties || [])
      setDataProperties(dataPropsData.data_properties || [])
    } catch (e) { addToast('加载失败: ' + e.message, 'error') }
    finally { setLoading(false) }
  }, [ontologyId, addToast])

  useEffect(() => { loadData() }, [loadData])

  const handleCreate = async () => {
    if (!formData.name.trim()) { addToast('类名不能为空', 'error'); return }
    try {
      await api.createOntologyClass(ontologyId, formData)
      addToast(`类 "${formData.name}" 已创建`, 'success')
      setShowCreate(false)
      setFormData({ name: '', label: '', comment: '', parents: [], disjoint_with: [], equivalent_to: [], restrictions: [] })
      loadData()
      onStatsChange()
    } catch (e) { addToast('创建失败: ' + e.message, 'error') }
  }

  const handleUpdate = async () => {
    if (!selectedClass) return
    try {
      await api.updateOntologyClass(ontologyId, selectedClass.name, formData)
      addToast('类已更新', 'success')
      setEditing(false)
      // 保持当前类的选中状态，更新 selectedClass 数据
      setSelectedClass(prev => ({ ...prev, ...formData }))
      loadData()
    } catch (e) { addToast('更新失败: ' + e.message, 'error') }
  }

  const handleDelete = async (className) => {
    if (!confirm(`确定要删除类 "${className}" 吗？`)) return
    try {
      await api.deleteOntologyClass(ontologyId, className)
      addToast('类已删除', 'success')
      if (selectedClass?.name === className) { setSelectedClass(null); setEditing(false) }
      loadData()
      onStatsChange()
    } catch (e) { addToast('删除失败: ' + e.message, 'error') }
  }

  const startEdit = (cls) => {
    setSelectedClass(cls)
    setFormData({
      name: cls.name,
      label: cls.label || '',
      comment: cls.comment || '',
      parents: Array.isArray(cls.parents) ? cls.parents : (cls.parents ? [cls.parents] : []),
      disjoint_with: Array.isArray(cls.disjoint_with) ? cls.disjoint_with : (cls.disjoint_with ? [cls.disjoint_with] : []),
      equivalent_to: Array.isArray(cls.equivalent_to) ? cls.equivalent_to : [],
      restrictions: Array.isArray(cls.restrictions) ? cls.restrictions : [],
    })
    setEditing(true)
  }

  const classOptions = classes.map(c => c.name)

  const buildTree = () => {
    const classMap = {}
    classes.forEach(c => { classMap[c.name] = { ...c, children: [] } })
    const roots = []
    classes.forEach(c => {
      const parents = c.parents || []
      if (parents.length === 0) {
        roots.push(classMap[c.name])
      } else {
        parents.forEach(p => {
          if (classMap[p]) {
            classMap[p].children.push(classMap[c.name])
          }
        })
      }
    })
    return roots
  }

  const [expandedNodes, setExpandedNodes] = useState({})

  const toggleNode = (nodeName) => {
    setExpandedNodes(prev => ({ ...prev, [nodeName]: !prev[nodeName] }))
  }

  const BASE_CLASSES = ['Thing']

  const renderTreeNode = (node, depth = 0) => {
    const isExpanded = expandedNodes[node.name]
    const hasChildren = node.children && node.children.length > 0
    const isBaseClass = BASE_CLASSES.includes(node.name)
    return (
      <div key={node.name}>
        <div
          className={`panel-item ${selectedClass?.name === node.name ? 'selected' : ''} ${isBaseClass ? 'base-class' : ''}`}
          style={{ paddingLeft: `${depth * 16 + 8}px` }}
          onClick={() => startEdit(node)}
        >
          <div className="panel-item-name" style={{ flex: 1 }}>
            {hasChildren && (
              <span
                className="tree-node-icon"
                style={{ marginRight: 4, cursor: 'pointer', userSelect: 'none', display: 'flex', alignItems: 'center' }}
                onClick={(e) => { e.stopPropagation(); toggleNode(node.name) }}
              >
                {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              </span>
            )}
            {!hasChildren && <span style={{ width: 16, display: 'inline-block' }} />}
            <span className="item-icon"><Box size={14} /></span>
            <span>{node.label || node.name}</span>
            {node.name !== node.label && <span className="item-name">({node.name})</span>}
          </div>
          <div className="panel-item-actions">
            {!isBaseClass && (
              <button className="btn btn-ghost btn-xs" onClick={e => { e.stopPropagation(); handleDelete(node.name) }}><Trash2 size={12} /></button>
            )}
          </div>
        </div>
        {hasChildren && isExpanded && node.children.map(child => renderTreeNode(child, depth + 1))}
      </div>
    )
  }

  const renderTree = () => {
    const tree = buildTree()
    return tree.map(node => renderTreeNode(node))
  }

  return (
    <div className="studio-panel">
      <div className="panel-layout">
        <div className="panel-list">
          <div className="panel-list-header">
            <span>类列表 ({classes.length})</span>
            <div style={{ display: 'flex', gap: 4 }}>
              <button
                className={`btn btn-sm ${viewMode === 'list' ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => setViewMode('list')}
                title="列表视图"
                style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}
              >
                <ChevronRight size={14} style={{ transform: 'rotate(90deg)' }} />
              </button>
              <button
                className={`btn btn-sm ${viewMode === 'tree' ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => setViewMode('tree')}
                title="树形视图"
                style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}
              >
                <GitBranch size={14} />
              </button>
              <button className="btn btn-primary btn-sm" onClick={() => {
                if (!showCreate) {
                  // 打开新建面板时重置表单
                  setFormData({ name: '', label: '', comment: '', parents: [], disjoint_with: [], equivalent_to: [], restrictions: [] })
                  setEditing(false)
                  setSelectedClass(null)
                }
                setShowCreate(!showCreate)
              }} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                {showCreate ? <X size={14} /> : <Plus size={14} />}
                {showCreate ? '取消' : '新建'}
              </button>
            </div>
          </div>

          {showCreate && (
            <div className="panel-form">
              <input className="form-input" placeholder="类名 *" value={formData.name}
                onChange={e => setFormData(p => ({ ...p, name: e.target.value }))} />
              <input className="form-input" placeholder="显示标签" value={formData.label}
                onChange={e => setFormData(p => ({ ...p, label: e.target.value }))} />
              <input className="form-input" placeholder="注释" value={formData.comment}
                onChange={e => setFormData(p => ({ ...p, comment: e.target.value }))} />
              <TreeMultiSelect label="父类" classes={classes} value={formData.parents}
                onChange={parents => setFormData(p => ({ ...p, parents }))} />
              <TreeMultiSelect label="不相交的类" classes={classes} value={formData.disjoint_with}
                onChange={disjoint_with => setFormData(p => ({ ...p, disjoint_with }))} />
              <button className="btn btn-success btn-sm" onClick={handleCreate} style={{ display: 'flex', alignItems: 'center', gap: 4, justifyContent: 'center' }}>
                <Check size={14} /> 创建
              </button>
            </div>
          )}

          <div className="panel-items">
            {viewMode === 'tree' ? renderTree() : classes.map(cls => {
              const isBaseClass = BASE_CLASSES.includes(cls.name)
              return (
                <div key={cls.name}
                  className={`panel-item ${selectedClass?.name === cls.name ? 'selected' : ''} ${isBaseClass ? 'base-class' : ''}`}
                  onClick={() => startEdit(cls)}>
                  <div className="panel-item-name">
                    <span className="item-icon"><Box size={14} /></span>
                    <span>{cls.label || cls.name}</span>
                    {cls.name !== cls.label && <span className="item-name">({cls.name})</span>}
                  </div>
                  <div className="panel-item-actions">
                    {!isBaseClass && (
                      <button className="btn btn-ghost btn-xs" onClick={e => { e.stopPropagation(); handleDelete(cls.name) }}><Trash2 size={12} /></button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {selectedClass && !editing && (
          <div className="panel-detail">
            <div className="panel-detail-header">
              <span>类详情: {selectedClass.name}</span>
              <button className="btn btn-ghost btn-sm" onClick={() => setSelectedClass(null)}>✕</button>
            </div>
            <div className="panel-form" style={{ pointerEvents: 'none' }}>
              <label>显示标签</label>
              <input className="form-input" value={selectedClass.label || ''} readOnly />
              <label>注释</label>
              <textarea className="form-input" rows={3} value={selectedClass.comment || ''} readOnly />
              <label>父类</label>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {(Array.isArray(selectedClass.parents) ? selectedClass.parents : []).map(p => (
                  <span key={p} className="tag">{p}</span>
                ))}
              </div>
              {selectedClass.equivalent_to && selectedClass.equivalent_to.length > 0 && (
                <>
                  <label>等价类 (Equivalent To)</label>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                    {selectedClass.equivalent_to.map((e, idx) => {
                      if (typeof e === 'string') {
                        return <span key={idx} className="tag tag-primary">{e}</span>
                      }
                      if (e.type === 'class') {
                        return <span key={idx} className="tag tag-primary">{e.class}</span>
                      }
                      if (e.type === 'intersection') {
                        const parts = (e.operands || []).map(op => {
                          if (op.type === 'class') return op.class
                          if (op.type === 'restriction') {
                            if (op.cardinalityType === 'value') return `${op.property} value "${op.value}"`
                            if (op.cardinalityType === 'some') return `${op.property} some ${op.filler || op.value}`
                            if (op.cardinalityType === 'only') return `${op.property} only ${op.filler || op.value}`
                            if (op.cardinalityType === 'min') return `${op.property} min ${op.cardinality} ${op.filler || op.value}`
                            if (op.cardinalityType === 'max') return `${op.property} max ${op.cardinality} ${op.filler || op.value}`
                            if (op.cardinalityType === 'exactly') return `${op.property} exactly ${op.cardinality} ${op.filler || op.value}`
                            return `${op.property} ${op.cardinalityType} ${op.value || op.filler}`
                          }
                          return JSON.stringify(op)
                        })
                        return <span key={idx} className="tag tag-primary">{parts.join(' and ')}</span>
                      }
                      if (e.type === 'union') {
                        const parts = (e.operands || []).map(op => {
                          if (op.type === 'class') return op.class
                          return JSON.stringify(op)
                        })
                        return <span key={idx} className="tag tag-primary">{parts.join(' or ')}</span>
                      }
                      return <span key={idx} className="tag tag-primary">{JSON.stringify(e)}</span>
                    })}
                  </div>
                </>
              )}
              {selectedClass.disjoint_with && selectedClass.disjoint_with.length > 0 && (
                <>
                  <label>不相交的类 (Disjoint With)</label>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                    {selectedClass.disjoint_with.map(d => (
                      <span key={d} className="tag tag-warning">{d}</span>
                    ))}
                  </div>
                </>
              )}
              {selectedClass.restrictions && selectedClass.restrictions.length > 0 && (
                <>
                  <label>限制条件 (Restrictions)</label>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {selectedClass.restrictions.map((r, idx) => {
                      const restType = r.cardinalityType || r.cardinality_type || 'some'
                      const restValue = r.value || r.filler || ''
                      const cardinality = r.cardinality !== undefined ? r.cardinality : ''
                      return (
                        <div key={idx} style={{ padding: 8, background: 'var(--bg-subtle)', borderRadius: 6, fontSize: 13 }}>
                          <code>
                            {r.property} {restType} {cardinality} {restValue}
                          </code>
                        </div>
                      )
                    })}
                  </div>
                </>
              )}
              <button className="btn btn-primary" style={{ pointerEvents: 'auto', marginTop: 12 }} onClick={() => startEdit(selectedClass)}>✏️ 编辑</button>
            </div>
          </div>
        )}

        {editing && selectedClass && (
          <div className="panel-detail">
            <div className="panel-detail-header">
              <span>编辑类: {selectedClass.name}</span>
              <button className="btn btn-ghost btn-sm" onClick={() => { setEditing(false); setSelectedClass(null) }}>✕</button>
            </div>
            <div className="panel-form">
              <label>显示标签</label>
              <input className="form-input" value={formData.label}
                onChange={e => setFormData(p => ({ ...p, label: e.target.value }))} />
              <label>注释</label>
              <textarea className="form-input" rows={3} value={formData.comment}
                onChange={e => setFormData(p => ({ ...p, comment: e.target.value }))} />
              <TreeMultiSelect label="父类" classes={classes} value={formData.parents}
                onChange={parents => setFormData(p => ({ ...p, parents }))} excludeName={selectedClass.name} />
              <TreeMultiSelect label="不相交的类" classes={classes} value={formData.disjoint_with}
                onChange={disjoint_with => setFormData(p => ({ ...p, disjoint_with }))} excludeName={selectedClass.name} />
              
              <label>等价类 (Equivalent To)</label>
              <EquivalentClassEditor 
                classes={classes}
                objectProperties={objectProperties}
                dataProperties={dataProperties}
                value={formData.equivalent_to}
                onChange={equivalent_to => setFormData(p => ({ ...p, equivalent_to }))}
                excludeName={selectedClass.name}
              />

              <label>限制条件 (Restrictions)</label>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {formData.restrictions.map((r, idx) => {
                  const restType = r.cardinalityType || r.cardinality_type || 'min'
                  const restValue = r.value || r.filler || ''
                  return (
                    <div key={idx} style={{ display: 'flex', gap: 8, alignItems: 'center', padding: 8, background: 'var(--bg-subtle)', borderRadius: 6 }}>
                      <select className="form-input" style={{ flex: 1 }} value={r.property || ''}
                        onChange={e => {
                          const newRestrictions = [...formData.restrictions]
                          newRestrictions[idx] = { ...newRestrictions[idx], property: e.target.value }
                          setFormData(p => ({ ...p, restrictions: newRestrictions }))
                        }}>
                        <option value="">选择属性</option>
                        {[...objectProperties.map(p => p.name), ...dataProperties.map(p => p.name)].map(n => <option key={n} value={n}>{n}</option>)}
                      </select>
                      <select className="form-input" style={{ width: 100 }} value={restType}
                        onChange={e => {
                          const newRestrictions = [...formData.restrictions]
                          newRestrictions[idx] = { ...newRestrictions[idx], cardinalityType: e.target.value }
                          setFormData(p => ({ ...p, restrictions: newRestrictions }))
                        }}>
                        <option value="some">some</option>
                        <option value="only">only</option>
                        <option value="min">min</option>
                        <option value="max">max</option>
                        <option value="exactly">exactly</option>
                        <option value="value">value</option>
                      </select>
                      {(restType === 'min' || restType === 'max' || restType === 'exactly') && (
                        <input className="form-input" style={{ width: 60 }} type="number" min="0" value={r.cardinality || 1}
                          onChange={e => {
                            const newRestrictions = [...formData.restrictions]
                            newRestrictions[idx] = { ...newRestrictions[idx], cardinality: parseInt(e.target.value) || 0 }
                            setFormData(p => ({ ...p, restrictions: newRestrictions }))
                          }} />
                      )}
                      {restType === 'value' ? (
                        <input className="form-input" style={{ flex: 1 }} value={restValue}
                          placeholder='值'
                          onChange={e => {
                            const newRestrictions = [...formData.restrictions]
                            newRestrictions[idx] = { ...newRestrictions[idx], value: e.target.value }
                            setFormData(p => ({ ...p, restrictions: newRestrictions }))
                          }} />
                      ) : (() => {
                        // 检查属性是对象属性还是数据属性
                        const isDataProp = dataProperties.map(p => p.name).includes(r.property)
                        const isObjProp = objectProperties.map(p => p.name).includes(r.property)
                        
                        if (isDataProp) {
                          // 数据属性：filler 是数据类型，用下拉框选择常见 XSD 类型
                          const xsdTypes = ['xsd:string', 'xsd:integer', 'xsd:float', 'xsd:boolean', 'xsd:dateTime', 'xsd:date', 'xsd:time', 'xsd:decimal', 'xsd:double', 'xsd:long', 'xsd:int', 'xsd:short', 'xsd:byte']
                          return (
                            <select className="form-input" style={{ flex: 1 }} value={restValue}
                              onChange={e => {
                                const newRestrictions = [...formData.restrictions]
                                newRestrictions[idx] = { ...newRestrictions[idx], value: e.target.value }
                                setFormData(p => ({ ...p, restrictions: newRestrictions }))
                              }}>
                              <option value="">选择数据类型</option>
                              {xsdTypes.map(t => <option key={t} value={t}>{t}</option>)}
                            </select>
                          )
                        } else if (isObjProp) {
                          // 对象属性：filler 是类名，用下拉框
                          return (
                            <select className="form-input" style={{ flex: 1 }} value={restValue}
                              onChange={e => {
                                const newRestrictions = [...formData.restrictions]
                                newRestrictions[idx] = { ...newRestrictions[idx], value: e.target.value }
                                setFormData(p => ({ ...p, restrictions: newRestrictions }))
                              }}>
                              <option value="">选择填充类</option>
                              {classOptions.map(n => <option key={n} value={n}>{n}</option>)}
                            </select>
                          )
                        } else {
                          // 未选择属性时，根据 value 判断
                          if (restValue.startsWith('xsd:')) {
                            return (
                              <input className="form-input" style={{ flex: 1 }} value={restValue}
                                placeholder='数据类型 (如: xsd:string)'
                                onChange={e => {
                                  const newRestrictions = [...formData.restrictions]
                                  newRestrictions[idx] = { ...newRestrictions[idx], value: e.target.value }
                                  setFormData(p => ({ ...p, restrictions: newRestrictions }))
                                }} />
                            )
                          } else {
                            return (
                              <select className="form-input" style={{ flex: 1 }} value={restValue}
                                onChange={e => {
                                  const newRestrictions = [...formData.restrictions]
                                  newRestrictions[idx] = { ...newRestrictions[idx], value: e.target.value }
                                  setFormData(p => ({ ...p, restrictions: newRestrictions }))
                                }}>
                                <option value="">选择填充类</option>
                                {classOptions.map(n => <option key={n} value={n}>{n}</option>)}
                              </select>
                            )
                          }
                        }
                      })()}
                      <button className="btn btn-ghost btn-xs" onClick={() => {
                        const newRestrictions = formData.restrictions.filter((_, i) => i !== idx)
                        setFormData(p => ({ ...p, restrictions: newRestrictions }))
                      }}>✕</button>
                    </div>
                  )
                })}
                <button className="btn btn-outline btn-sm" onClick={() => {
                  setFormData(p => ({ ...p, restrictions: [...p.restrictions, { property: '', cardinalityType: 'min', cardinality: 1, value: '' }] }))
                }}>➕ 添加限制条件</button>
              </div>
              <button className="btn btn-primary" onClick={handleUpdate}>💾 保存修改</button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// =============================================================================
// 对象属性面板
// =============================================================================

function ObjectPropertyPanel({ ontologyId, addToast, onStatsChange }) {
  const [properties, setProperties] = useState([])
  const [classes, setClasses] = useState([])
  const [selectedProp, setSelectedProp] = useState(null)
  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState(false)
  const [formData, setFormData] = useState({
    name: '', label: '', comment: '', domain: [], range: [],
    sub_property_of: '', characteristics: [], inverse_of: ''
  })
  const [loading, setLoading] = useState(false)
  const [viewMode, setViewMode] = useState('tree')

  const BASE_PROPERTIES = ['topObjectProperty']

  const CHARACTERISTICS = [
    'Functional', 'InverseFunctional', 'TransitiveProperty',
    'SymmetricProperty', 'AsymmetricProperty', 'ReflexiveProperty', 'IrreflexiveProperty'
  ]

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [propsData, classesData] = await Promise.all([
        api.listOntologyObjectProperties(ontologyId),
        api.listOntologyClasses(ontologyId)
      ])
      setProperties(propsData.object_properties || [])
      setClasses(classesData.classes || [])
    } catch (e) { addToast('加载失败: ' + e.message, 'error') }
    finally { setLoading(false) }
  }, [ontologyId, addToast])

  useEffect(() => { loadData() }, [loadData])

  const handleCreate = async () => {
    if (!formData.name.trim()) { addToast('属性名不能为空', 'error'); return }
    try {
      await api.createOntologyObjectProperty(ontologyId, formData)
      addToast(`对象属性 "${formData.name}" 已创建`, 'success')
      setShowCreate(false)
      setFormData({ name: '', label: '', comment: '', domain: [], range: [], sub_property_of: '', characteristics: [], inverse_of: '' })
      loadData()
      onStatsChange()
    } catch (e) { addToast('创建失败: ' + e.message, 'error') }
  }

  const handleUpdate = async () => {
    if (!selectedProp) return
    try {
      await api.updateOntologyObjectProperty(ontologyId, selectedProp.name, formData)
      addToast('对象属性已更新', 'success')
      setEditing(false)
      setSelectedProp(null)
      loadData()
    } catch (e) { addToast('更新失败: ' + e.message, 'error') }
  }

  const handleDelete = async (propName) => {
    if (!confirm(`确定要删除对象属性 "${propName}" 吗？`)) return
    try {
      await api.deleteOntologyObjectProperty(ontologyId, propName)
      addToast('对象属性已删除', 'success')
      if (selectedProp?.name === propName) { setSelectedProp(null); setEditing(false) }
      loadData()
      onStatsChange()
    } catch (e) { addToast('删除失败: ' + e.message, 'error') }
  }

  const startEdit = (prop) => {
    setSelectedProp(prop)
    setFormData({
      name: prop.name,
      label: prop.label || '',
      comment: prop.comment || '',
      domain: Array.isArray(prop.domain) ? prop.domain : (prop.domain ? [prop.domain] : []),
      range: Array.isArray(prop.range) ? prop.range : (prop.range ? [prop.range] : []),
      sub_property_of: prop.sub_property_of || '',
      characteristics: prop.characteristics || [],
      inverse_of: prop.inverse_of || '',
    })
    setEditing(true)
  }

  const classOptions = classes.map(c => c.name)
  const propOptions = properties.map(p => p.name)

  const buildPropertyTree = () => {
    const propMap = {}
    properties.forEach(p => { propMap[p.name] = { ...p, children: [] } })
    const roots = []
    properties.forEach(p => {
      const parent = p.sub_property_of
      if (!parent || !propMap[parent]) {
        roots.push(propMap[p.name])
      } else {
        propMap[parent].children.push(propMap[p.name])
      }
    })
    return roots
  }

  const [expandedNodes, setExpandedNodes] = useState({})

  // 当 properties 变化时，默认展开所有节点
  useEffect(() => {
    const expanded = {}
    properties.forEach(p => { expanded[p.name] = true })
    setExpandedNodes(expanded)
  }, [properties])

  const toggleNode = (nodeName) => {
    setExpandedNodes(prev => ({ ...prev, [nodeName]: !prev[nodeName] }))
  }

  const renderPropertyTreeNode = (node, depth = 0) => {
    const isExpanded = expandedNodes[node.name]
    const hasChildren = node.children && node.children.length > 0
    const isBaseProperty = BASE_PROPERTIES.includes(node.name)
    return (
      <div key={node.name}>
        <div
          className={`panel-item ${selectedProp?.name === node.name ? 'selected' : ''} ${isBaseProperty ? 'base-class' : ''}`}
          style={{ paddingLeft: `${depth * 16 + 8}px` }}
          onClick={() => startEdit(node)}
        >
          <div className="panel-item-name" style={{ flex: 1 }}>
            {hasChildren && (
              <span
                className="tree-node-icon"
                style={{ marginRight: 4, cursor: 'pointer', userSelect: 'none', display: 'flex', alignItems: 'center' }}
                onClick={(e) => { e.stopPropagation(); toggleNode(node.name) }}
              >
                {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              </span>
            )}
            {!hasChildren && <span style={{ width: 16, display: 'inline-block' }} />}
            <span className="item-icon"><LinkIcon size={14} /></span>
            <span>{node.label || node.name}</span>
            {node.name !== node.label && <span className="item-name">({node.name})</span>}
          </div>
          <div className="panel-item-actions">
            {!isBaseProperty && (
              <button className="btn btn-ghost btn-xs" onClick={e => { e.stopPropagation(); handleDelete(node.name) }}><Trash2 size={12} /></button>
            )}
          </div>
        </div>
        {hasChildren && isExpanded && node.children.map(child => renderPropertyTreeNode(child, depth + 1))}
      </div>
    )
  }

  const renderPropertyTree = () => {
    const tree = buildPropertyTree()
    return tree.map(node => renderPropertyTreeNode(node))
  }

  return (
    <div className="studio-panel">
      <div className="panel-layout">
        <div className="panel-list">
          <div className="panel-list-header">
            <span>对象属性 ({properties.length})</span>
            <div style={{ display: 'flex', gap: 4 }}>
              <button
                className={`btn btn-sm ${viewMode === 'list' ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => setViewMode('list')}
                title="列表视图"
                style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}
              >
                <ChevronRight size={14} style={{ transform: 'rotate(90deg)' }} />
              </button>
              <button
                className={`btn btn-sm ${viewMode === 'tree' ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => setViewMode('tree')}
                title="树形视图"
                style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}
              >
                <GitBranch size={14} />
              </button>
              <button className="btn btn-primary btn-sm" onClick={() => {
                if (!showCreate) {
                  setFormData({
                    name: '', label: '', comment: '', domain: [], range: [],
                    sub_property_of: '', characteristics: [], inverse_of: ''
                  })
                  setEditing(false)
                  setSelectedProp(null)
                }
                setShowCreate(!showCreate)
              }} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                {showCreate ? <X size={14} /> : <Plus size={14} />}
                {showCreate ? '取消' : '新建'}
              </button>
            </div>
          </div>

          {showCreate && (
            <div className="panel-form">
              <input className="form-input" placeholder="属性名 *" value={formData.name}
                onChange={e => setFormData(p => ({ ...p, name: e.target.value }))} />
              <input className="form-input" placeholder="显示标签" value={formData.label}
                onChange={e => setFormData(p => ({ ...p, label: e.target.value }))} />
              <input className="form-input" placeholder="注释" value={formData.comment}
                onChange={e => setFormData(p => ({ ...p, comment: e.target.value }))} />
              <TreeMultiSelect label="定义域 (Domain)" classes={classes} value={formData.domain}
                onChange={domain => setFormData(p => ({ ...p, domain }))} />
              <TreeMultiSelect label="值域 (Range)" classes={classes} value={formData.range}
                onChange={range => setFormData(p => ({ ...p, range }))} />
              <label>父属性</label>
              <select className="form-input" value={formData.sub_property_of}
                onChange={e => setFormData(p => ({ ...p, sub_property_of: e.target.value }))}>
                <option value="">无</option>
                {propOptions.map(n => <option key={n} value={n}>{n}</option>)}
              </select>
              <label>特性</label>
              <div className="checkbox-group">
                {CHARACTERISTICS.map(c => (
                  <label key={c} className="checkbox-label">
                    <input type="checkbox" checked={formData.characteristics.includes(c)}
                      onChange={e => {
                        const chars = e.target.checked
                          ? [...formData.characteristics, c]
                          : formData.characteristics.filter(x => x !== c)
                        setFormData(p => ({ ...p, characteristics: chars }))
                      }} />
                    <span>{c}</span>
                  </label>
                ))}
              </div>
              <label>逆属性</label>
              <select className="form-input" value={formData.inverse_of}
                onChange={e => setFormData(p => ({ ...p, inverse_of: e.target.value }))}>
                <option value="">无</option>
                {propOptions.filter(n => n !== formData.name).map(n => <option key={n} value={n}>{n}</option>)}
              </select>
              <button className="btn btn-success btn-sm" onClick={handleCreate} style={{ display: 'flex', alignItems: 'center', gap: 4, justifyContent: 'center' }}>
                <Check size={14} /> 创建
              </button>
            </div>
          )}

          <div className="panel-items">
            {viewMode === 'tree' ? renderPropertyTree() : properties.map(prop => {
              const isBaseProperty = BASE_PROPERTIES.includes(prop.name)
              return (
                <div key={prop.name}
                  className={`panel-item ${selectedProp?.name === prop.name ? 'selected' : ''} ${isBaseProperty ? 'base-class' : ''}`}
                  onClick={() => startEdit(prop)}>
                  <div className="panel-item-name">
                    <span className="item-icon"><LinkIcon size={14} /></span>
                    <span>{prop.label || prop.name}</span>
                    {prop.name !== prop.label && <span className="item-name">({prop.name})</span>}
                  </div>
                  <div className="panel-item-actions">
                    {!isBaseProperty && (
                      <button className="btn btn-ghost btn-xs" onClick={e => { e.stopPropagation(); handleDelete(prop.name) }}><Trash2 size={12} /></button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {selectedProp && !editing && (
          <div className="panel-detail">
            <div className="panel-detail-header">
              <span>对象属性详情: {selectedProp.name}</span>
              <button className="btn btn-ghost btn-sm" onClick={() => setSelectedProp(null)}><X size={14} /></button>
            </div>
            <div className="panel-form" style={{ pointerEvents: 'none' }}>
              <label>显示标签</label>
              <input className="form-input" value={selectedProp.label || ''} readOnly />
              <label>注释</label>
              <textarea className="form-input" rows={2} value={selectedProp.comment || ''} readOnly />
              <label>定义域 (Domain)</label>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {(Array.isArray(selectedProp.domain) ? selectedProp.domain : (selectedProp.domain ? [selectedProp.domain] : [])).map(d => (
                  <span key={d} className="tag">{d}</span>
                ))}
              </div>
              <label>值域 (Range)</label>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {(Array.isArray(selectedProp.range) ? selectedProp.range : (selectedProp.range ? [selectedProp.range] : [])).map(r => (
                  <span key={r} className="tag">{r}</span>
                ))}
              </div>
              {selectedProp.sub_property_of && (
                <>
                  <label>父属性</label>
                  <span className="tag">{selectedProp.sub_property_of}</span>
                </>
              )}
              {selectedProp.characteristics && selectedProp.characteristics.length > 0 && (
                <>
                  <label>特性</label>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                    {selectedProp.characteristics.map(c => (
                      <span key={c} className="tag tag-primary">{c}</span>
                    ))}
                  </div>
                </>
              )}
              {selectedProp.inverse_of && (
                <>
                  <label>逆属性 (Inverse Of)</label>
                  <span className="tag tag-warning">{selectedProp.inverse_of}</span>
                </>
              )}
              {selectedProp.disjoint_with && selectedProp.disjoint_with.length > 0 && (
                <>
                  <label>不相交属性</label>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                    {selectedProp.disjoint_with.map(d => (
                      <span key={d} className="tag tag-warning">{d}</span>
                    ))}
                  </div>
                </>
              )}
              <button className="btn btn-primary" style={{ pointerEvents: 'auto', marginTop: 12, display: 'flex', alignItems: 'center', gap: 4, justifyContent: 'center' }} onClick={() => startEdit(selectedProp)}>
                <MousePointer2 size={14} /> 编辑
              </button>
            </div>
          </div>
        )}

        {editing && selectedProp && (
          <div className="panel-detail">
            <div className="panel-detail-header">
              <span>编辑对象属性: {selectedProp.name}</span>
              <button className="btn btn-ghost btn-sm" onClick={() => { setEditing(false); setSelectedProp(null) }}><X size={14} /></button>
            </div>
            <div className="panel-form">
              <label>显示标签</label>
              <input className="form-input" value={formData.label}
                onChange={e => setFormData(p => ({ ...p, label: e.target.value }))} />
              <label>注释</label>
              <textarea className="form-input" rows={2} value={formData.comment}
                onChange={e => setFormData(p => ({ ...p, comment: e.target.value }))} />
              <TreeMultiSelect label="定义域 (Domain)" classes={classes} value={formData.domain}
                onChange={domain => setFormData(p => ({ ...p, domain }))} />
              <TreeMultiSelect label="值域 (Range)" classes={classes} value={formData.range}
                onChange={range => setFormData(p => ({ ...p, range }))} />
              <label>父属性</label>
              <select className="form-input" value={formData.sub_property_of}
                onChange={e => setFormData(p => ({ ...p, sub_property_of: e.target.value }))}>
                <option value="">无</option>
                {propOptions.filter(n => n !== selectedProp.name).map(n => <option key={n} value={n}>{n}</option>)}
              </select>
              <label>特性</label>
              <div className="checkbox-group">
                {CHARACTERISTICS.map(c => (
                  <label key={c} className="checkbox-label">
                    <input type="checkbox" checked={formData.characteristics.includes(c)}
                      onChange={e => {
                        const chars = e.target.checked
                          ? [...formData.characteristics, c]
                          : formData.characteristics.filter(x => x !== c)
                        setFormData(p => ({ ...p, characteristics: chars }))
                      }} />
                    <span>{c}</span>
                  </label>
                ))}
              </div>
              <label>逆属性</label>
              <select className="form-input" value={formData.inverse_of}
                onChange={e => setFormData(p => ({ ...p, inverse_of: e.target.value }))}>
                <option value="">无</option>
                {propOptions.filter(n => n !== selectedProp.name).map(n => <option key={n} value={n}>{n}</option>)}
              </select>
              <button className="btn btn-primary" onClick={handleUpdate} style={{ display: 'flex', alignItems: 'center', gap: 4, justifyContent: 'center' }}>
                <Check size={14} /> 保存修改
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// =============================================================================
// 数据属性面板
// =============================================================================

function DataPropertyPanel({ ontologyId, addToast, onStatsChange }) {
  const [properties, setProperties] = useState([])
  const [classes, setClasses] = useState([])
  const [selectedProp, setSelectedProp] = useState(null)
  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState(false)
  const [formData, setFormData] = useState({
    name: '', label: '', comment: '', domain: [], range: 'xsd:string', sub_property_of: '', characteristics: [], disjoint_with: []
  })
  const [loading, setLoading] = useState(false)
  const [viewMode, setViewMode] = useState('tree')

  const BASE_PROPERTIES = ['topDataProperty']

  const CHARACTERISTICS = [
    'Functional', 'InverseFunctional', 'TransitiveProperty',
    'SymmetricProperty', 'AsymmetricProperty', 'ReflexiveProperty', 'IrreflexiveProperty'
  ]

  const XSD_TYPES = ['xsd:string', 'xsd:integer', 'xsd:decimal', 'xsd:float', 'xsd:boolean', 'xsd:date', 'xsd:dateTime', 'xsd:anyURI']

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [propsData, classesData] = await Promise.all([
        api.listOntologyDataProperties(ontologyId),
        api.listOntologyClasses(ontologyId)
      ])
      setProperties(propsData.data_properties || [])
      setClasses(classesData.classes || [])
    } catch (e) { addToast('加载失败: ' + e.message, 'error') }
    finally { setLoading(false) }
  }, [ontologyId, addToast])

  useEffect(() => { loadData() }, [loadData])

  const handleCreate = async () => {
    if (!formData.name.trim()) { addToast('属性名不能为空', 'error'); return }
    try {
      await api.createOntologyDataProperty(ontologyId, formData)
      addToast(`数据属性 "${formData.name}" 已创建`, 'success')
      setShowCreate(false)
      setFormData({ name: '', label: '', comment: '', domain: [], range: 'xsd:string', sub_property_of: '' })
      loadData()
      onStatsChange()
    } catch (e) { addToast('创建失败: ' + e.message, 'error') }
  }

  const handleUpdate = async () => {
    if (!selectedProp) return
    try {
      await api.updateOntologyDataProperty(ontologyId, selectedProp.name, formData)
      addToast('数据属性已更新', 'success')
      setEditing(false)
      setSelectedProp(null)
      loadData()
    } catch (e) { addToast('更新失败: ' + e.message, 'error') }
  }

  const handleDelete = async (propName) => {
    if (!confirm(`确定要删除数据属性 "${propName}" 吗？`)) return
    try {
      await api.deleteOntologyDataProperty(ontologyId, propName)
      addToast('数据属性已删除', 'success')
      if (selectedProp?.name === propName) { setSelectedProp(null); setEditing(false) }
      loadData()
      onStatsChange()
    } catch (e) { addToast('删除失败: ' + e.message, 'error') }
  }

  const startEdit = (prop) => {
    setSelectedProp(prop)
    setFormData({
      name: prop.name,
      label: prop.label || '',
      comment: prop.comment || '',
      domain: Array.isArray(prop.domain) ? prop.domain : (prop.domain ? [prop.domain] : []),
      range: prop.range || 'xsd:string',
      sub_property_of: prop.sub_property_of || '',
      characteristics: prop.characteristics || [],
      disjoint_with: prop.disjoint_with || [],
    })
    setEditing(true)
  }

  const classOptions = classes.map(c => c.name)
  const propOptions = properties.map(p => p.name)

  const buildPropertyTree = () => {
    const propMap = {}
    properties.forEach(p => { propMap[p.name] = { ...p, children: [] } })
    const roots = []
    properties.forEach(p => {
      const parent = p.sub_property_of
      if (!parent || !propMap[parent]) {
        roots.push(propMap[p.name])
      } else {
        propMap[parent].children.push(propMap[p.name])
      }
    })
    return roots
  }

  const [expandedNodes, setExpandedNodes] = useState({})

  const toggleNode = (nodeName) => {
    setExpandedNodes(prev => ({ ...prev, [nodeName]: !prev[nodeName] }))
  }

  const renderPropertyTreeNode = (node, depth = 0) => {
    const isExpanded = expandedNodes[node.name]
    const hasChildren = node.children && node.children.length > 0
    const isBaseProperty = BASE_PROPERTIES.includes(node.name)
    return (
      <div key={node.name}>
        <div
          className={`panel-item ${selectedProp?.name === node.name ? 'selected' : ''} ${isBaseProperty ? 'base-class' : ''}`}
          style={{ paddingLeft: `${depth * 16 + 8}px` }}
          onClick={() => startEdit(node)}
        >
          <div className="panel-item-name" style={{ flex: 1 }}>
            {hasChildren && (
              <span
                className="tree-node-icon"
                style={{ marginRight: 4, cursor: 'pointer', userSelect: 'none', display: 'flex', alignItems: 'center' }}
                onClick={(e) => { e.stopPropagation(); toggleNode(node.name) }}
              >
                {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              </span>
            )}
            {!hasChildren && <span style={{ width: 16, display: 'inline-block' }} />}
            <span className="item-icon"><FileText size={14} /></span>
            <span>{node.label || node.name}</span>
            {node.name !== node.label && <span className="item-name">({node.name})</span>}
          </div>
          <div className="panel-item-actions">
            {!isBaseProperty && (
              <button className="btn btn-ghost btn-xs" onClick={e => { e.stopPropagation(); handleDelete(node.name) }}><Trash2 size={12} /></button>
            )}
          </div>
        </div>
        {hasChildren && isExpanded && node.children.map(child => renderPropertyTreeNode(child, depth + 1))}
      </div>
    )
  }

  const renderPropertyTree = () => {
    const tree = buildPropertyTree()
    return tree.map(node => renderPropertyTreeNode(node))
  }

  return (
    <div className="studio-panel">
      <div className="panel-layout">
        <div className="panel-list">
          <div className="panel-list-header">
            <span>数据属性 ({properties.length})</span>
            <div style={{ display: 'flex', gap: 4 }}>
              <button
                className={`btn btn-sm ${viewMode === 'list' ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => setViewMode('list')}
                title="列表视图"
                style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}
              >
                <ChevronRight size={14} style={{ transform: 'rotate(90deg)' }} />
              </button>
              <button
                className={`btn btn-sm ${viewMode === 'tree' ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => setViewMode('tree')}
                title="树形视图"
                style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}
              >
                <GitBranch size={14} />
              </button>
              <button className="btn btn-primary btn-sm" onClick={() => {
                if (!showCreate) {
                  setFormData({
                    name: '', label: '', comment: '', domain: [], range: 'xsd:string',
                    sub_property_of: '', characteristics: [], disjoint_with: []
                  })
                  setEditing(false)
                  setSelectedProp(null)
                }
                setShowCreate(!showCreate)
              }} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                {showCreate ? <X size={14} /> : <Plus size={14} />}
                {showCreate ? '取消' : '新建'}
              </button>
            </div>
          </div>

          {showCreate && (
            <div className="panel-form">
              <input className="form-input" placeholder="属性名 *" value={formData.name}
                onChange={e => setFormData(p => ({ ...p, name: e.target.value }))} />
              <input className="form-input" placeholder="显示标签" value={formData.label}
                onChange={e => setFormData(p => ({ ...p, label: e.target.value }))} />
              <input className="form-input" placeholder="注释" value={formData.comment}
                onChange={e => setFormData(p => ({ ...p, comment: e.target.value }))} />
              <TreeMultiSelect label="定义域 (Domain)" classes={classes} value={formData.domain}
                onChange={domain => setFormData(p => ({ ...p, domain }))} />
              <label>数据类型 (Range)</label>
              <select className="form-input" value={formData.range}
                onChange={e => setFormData(p => ({ ...p, range: e.target.value }))}>
                {XSD_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
              <label>父属性</label>
              <select className="form-input" value={formData.sub_property_of}
                onChange={e => setFormData(p => ({ ...p, sub_property_of: e.target.value }))}>
                <option value="">无</option>
                {propOptions.map(n => <option key={n} value={n}>{n}</option>)}
              </select>
              <label>特性</label>
              <div className="checkbox-group">
                {CHARACTERISTICS.map(c => (
                  <label key={c} className="checkbox-label">
                    <input type="checkbox" checked={formData.characteristics.includes(c)}
                      onChange={e => {
                        const chars = e.target.checked
                          ? [...formData.characteristics, c]
                          : formData.characteristics.filter(x => x !== c)
                        setFormData(p => ({ ...p, characteristics: chars }))
                      }} />
                    <span>{c}</span>
                  </label>
                ))}
              </div>
              <MultiSelect label="不相交属性" options={propOptions} value={formData.disjoint_with}
                onChange={disjoint_with => setFormData(p => ({ ...p, disjoint_with }))} />
              <button className="btn btn-success btn-sm" onClick={handleCreate} style={{ display: 'flex', alignItems: 'center', gap: 4, justifyContent: 'center' }}>
                <Check size={14} /> 创建
              </button>
            </div>
          )}

          <div className="panel-items">
            {viewMode === 'tree' ? renderPropertyTree() : properties.map(prop => {
              const isBaseProperty = BASE_PROPERTIES.includes(prop.name)
              return (
                <div key={prop.name}
                  className={`panel-item ${selectedProp?.name === prop.name ? 'selected' : ''} ${isBaseProperty ? 'base-class' : ''}`}
                  onClick={() => startEdit(prop)}>
                  <div className="panel-item-name">
                    <span className="item-icon"><FileText size={14} /></span>
                    <span>{prop.label || prop.name}</span>
                    {prop.name !== prop.label && <span className="item-name">({prop.name})</span>}
                    <span className="item-tag">{prop.range}</span>
                  </div>
                  <div className="panel-item-actions">
                    {!isBaseProperty && (
                      <button className="btn btn-ghost btn-xs" onClick={e => { e.stopPropagation(); handleDelete(prop.name) }}><Trash2 size={12} /></button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {selectedProp && !editing && (
          <div className="panel-detail">
            <div className="panel-detail-header">
              <span>数据属性详情: {selectedProp.name}</span>
              <button className="btn btn-ghost btn-sm" onClick={() => setSelectedProp(null)}><X size={14} /></button>
            </div>
            <div className="panel-form" style={{ pointerEvents: 'none' }}>
              <label>显示标签</label>
              <input className="form-input" value={selectedProp.label || ''} readOnly />
              <label>注释</label>
              <textarea className="form-input" rows={2} value={selectedProp.comment || ''} readOnly />
              <label>定义域 (Domain)</label>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {(Array.isArray(selectedProp.domain) ? selectedProp.domain : (selectedProp.domain ? [selectedProp.domain] : [])).map(d => (
                  <span key={d} className="tag">{d}</span>
                ))}
              </div>
              <label>数据类型 (Range)</label>
              <span className="tag tag-primary">{selectedProp.range || 'xsd:string'}</span>
              {selectedProp.sub_property_of && (
                <>
                  <label>父属性</label>
                  <span className="tag">{selectedProp.sub_property_of}</span>
                </>
              )}
              {selectedProp.disjoint_with && selectedProp.disjoint_with.length > 0 && (
                <>
                  <label>不相交属性</label>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                    {selectedProp.disjoint_with.map(d => (
                      <span key={d} className="tag tag-warning">{d}</span>
                    ))}
                  </div>
                </>
              )}
              <button className="btn btn-primary" style={{ pointerEvents: 'auto', marginTop: 12, display: 'flex', alignItems: 'center', gap: 4, justifyContent: 'center' }} onClick={() => startEdit(selectedProp)}>
                <MousePointer2 size={14} /> 编辑
              </button>
            </div>
          </div>
        )}

        {editing && selectedProp && (
          <div className="panel-detail">
            <div className="panel-detail-header">
              <span>编辑数据属性: {selectedProp.name}</span>
              <button className="btn btn-ghost btn-sm" onClick={() => { setEditing(false); setSelectedProp(null) }}><X size={14} /></button>
            </div>
            <div className="panel-form">
              <label>显示标签</label>
              <input className="form-input" value={formData.label}
                onChange={e => setFormData(p => ({ ...p, label: e.target.value }))} />
              <label>注释</label>
              <textarea className="form-input" rows={2} value={formData.comment}
                onChange={e => setFormData(p => ({ ...p, comment: e.target.value }))} />
              <TreeMultiSelect label="定义域 (Domain)" classes={classes} value={formData.domain}
                onChange={domain => setFormData(p => ({ ...p, domain }))} />
              <label>数据类型 (Range)</label>
              <select className="form-input" value={formData.range}
                onChange={e => setFormData(p => ({ ...p, range: e.target.value }))}>
                {XSD_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
              <label>父属性</label>
              <select className="form-input" value={formData.sub_property_of}
                onChange={e => setFormData(p => ({ ...p, sub_property_of: e.target.value }))}>
                <option value="">无</option>
                {propOptions.filter(n => n !== selectedProp.name).map(n => <option key={n} value={n}>{n}</option>)}
              </select>
              <label>特性</label>
              <div className="checkbox-group">
                {CHARACTERISTICS.map(c => (
                  <label key={c} className="checkbox-label">
                    <input type="checkbox" checked={formData.characteristics.includes(c)}
                      onChange={e => {
                        const chars = e.target.checked
                          ? [...formData.characteristics, c]
                          : formData.characteristics.filter(x => x !== c)
                        setFormData(p => ({ ...p, characteristics: chars }))
                      }} />
                    <span>{c}</span>
                  </label>
                ))}
              </div>
              <MultiSelect label="不相交属性" options={propOptions.filter(n => n !== selectedProp.name)}
                value={formData.disjoint_with}
                onChange={disjoint_with => setFormData(p => ({ ...p, disjoint_with }))} />
              <button className="btn btn-primary" onClick={handleUpdate} style={{ display: 'flex', alignItems: 'center', gap: 4, justifyContent: 'center' }}>
                <Check size={14} /> 保存修改
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// =============================================================================
// 注释属性面板
// =============================================================================

function AnnotationPropertyPanel({ ontologyId, addToast, onStatsChange }) {
  const [properties, setProperties] = useState([])
  const [showCreate, setShowCreate] = useState(false)
  const [formData, setFormData] = useState({ name: '', label: '', comment: '' })

  const loadData = useCallback(async () => {
    try {
      const data = await api.listOntologyAnnotationProperties(ontologyId)
      setProperties(data.annotation_properties || [])
    } catch (e) { addToast('加载失败: ' + e.message, 'error') }
  }, [ontologyId, addToast])

  useEffect(() => { loadData() }, [loadData])

  const handleCreate = async () => {
    if (!formData.name.trim()) { addToast('属性名不能为空', 'error'); return }
    try {
      await api.createOntologyAnnotationProperty(ontologyId, formData)
      addToast(`注释属性 "${formData.name}" 已创建`, 'success')
      setShowCreate(false)
      setFormData({ name: '', label: '', comment: '' })
      loadData()
      onStatsChange()
    } catch (e) { addToast('创建失败: ' + e.message, 'error') }
  }

  const handleDelete = async (propName) => {
    if (!confirm(`确定要删除注释属性 "${propName}" 吗？`)) return
    try {
      await api.deleteOntologyAnnotationProperty(ontologyId, propName)
      addToast('注释属性已删除', 'success')
      loadData()
      onStatsChange()
    } catch (e) { addToast('删除失败: ' + e.message, 'error') }
  }

  return (
    <div className="studio-panel">
      <div className="panel-list" style={{ maxWidth: 600 }}>
        <div className="panel-list-header">
          <span>注释属性 ({properties.length})</span>
          <button className="btn btn-primary btn-sm" onClick={() => {
            if (!showCreate) {
              setFormData({ name: '', label: '', comment: '' })
            }
            setShowCreate(!showCreate)
          }} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            {showCreate ? <X size={14} /> : <Plus size={14} />}
            {showCreate ? '取消' : '新建'}
          </button>
        </div>

        {showCreate && (
          <div className="panel-form">
            <input className="form-input" placeholder="属性名 *" value={formData.name}
              onChange={e => setFormData(p => ({ ...p, name: e.target.value }))} />
            <input className="form-input" placeholder="显示标签" value={formData.label}
              onChange={e => setFormData(p => ({ ...p, label: e.target.value }))} />
            <input className="form-input" placeholder="注释" value={formData.comment}
              onChange={e => setFormData(p => ({ ...p, comment: e.target.value }))} />
            <button className="btn btn-success btn-sm" onClick={handleCreate} style={{ display: 'flex', alignItems: 'center', gap: 4, justifyContent: 'center' }}>
              <Check size={14} /> 创建
            </button>
          </div>
        )}

        <div className="panel-items">
          {properties.map(prop => (
            <div key={prop.name} className="panel-item">
              <div className="panel-item-name">
                <span className="item-icon"><Tag size={14} /></span>
                <span>{prop.label || prop.name}</span>
                {prop.name !== prop.label && <span className="item-name">({prop.name})</span>}
              </div>
              <div className="panel-item-actions">
                <button className="btn btn-ghost btn-xs" onClick={() => handleDelete(prop.name)}><Trash2 size={12} /></button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// =============================================================================
// 个体/实例管理面板
// =============================================================================

function IndividualPanel({ ontologyId, addToast, onStatsChange }) {
  const [individuals, setIndividuals] = useState([])
  const [classes, setClasses] = useState([])
  const [dataProperties, setDataProperties] = useState([])
  const [objectProperties, setObjectProperties] = useState([])
  const [selectedInd, setSelectedInd] = useState(null)
  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState(false)
  const [formData, setFormData] = useState({
    name: '', label: '', comment: '', types: [],
    data_property_values: {}, object_property_values: {},
    same_as: [], different_from: []
  })
  const [loading, setLoading] = useState(false)

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [indsData, classesData, dpData, opData] = await Promise.all([
        api.listOntologyIndividuals(ontologyId),
        api.listOntologyClasses(ontologyId),
        api.listOntologyDataProperties(ontologyId),
        api.listOntologyObjectProperties(ontologyId),
      ])
      setIndividuals(indsData.individuals || [])
      setClasses(classesData.classes || [])
      setDataProperties(dpData.data_properties || [])
      setObjectProperties(opData.object_properties || [])
    } catch (e) { addToast('加载失败: ' + e.message, 'error') }
    finally { setLoading(false) }
  }, [ontologyId, addToast])

  useEffect(() => { loadData() }, [loadData])

  const handleCreate = async () => {
    if (!formData.name.trim()) { addToast('个体名不能为空', 'error'); return }
    if (formData.types.length === 0) { addToast('个体必须指定至少一个类型', 'error'); return }
    try {
      await api.createOntologyIndividual(ontologyId, formData)
      addToast(`个体 "${formData.name}" 已创建`, 'success')
      setShowCreate(false)
      setFormData({ name: '', label: '', comment: '', types: [], data_property_values: {}, object_property_values: {}, same_as: [], different_from: [] })
      loadData()
      onStatsChange()
    } catch (e) { addToast('创建失败: ' + e.message, 'error') }
  }

  const handleUpdate = async () => {
    if (!selectedInd) return
    try {
      await api.updateOntologyIndividual(ontologyId, selectedInd.name, formData)
      addToast('个体已更新', 'success')
      setEditing(false)
      setSelectedInd(null)
      loadData()
    } catch (e) { addToast('更新失败: ' + e.message, 'error') }
  }

  const handleDelete = async (indName) => {
    if (!confirm(`确定要删除个体 "${indName}" 吗？`)) return
    try {
      await api.deleteOntologyIndividual(ontologyId, indName)
      addToast('个体已删除', 'success')
      if (selectedInd?.name === indName) { setSelectedInd(null); setEditing(false) }
      loadData()
      onStatsChange()
    } catch (e) { addToast('删除失败: ' + e.message, 'error') }
  }

  const startEdit = (ind) => {
    setSelectedInd(ind)
    setFormData({
      name: ind.name,
      label: ind.label || '',
      comment: ind.comment || '',
      types: Array.isArray(ind.types) ? ind.types : (ind.types ? [ind.types] : []),
      data_property_values: ind.data_property_values || {},
      object_property_values: ind.object_property_values || {},
      same_as: Array.isArray(ind.same_as) ? ind.same_as : (ind.same_as ? [ind.same_as] : []),
      different_from: Array.isArray(ind.different_from) ? ind.different_from : (ind.different_from ? [ind.different_from] : []),
    })
    setEditing(true)
  }

  const classOptions = classes.map(c => c.name)
  const individualOptions = individuals.map(i => i.name)

  return (
    <div className="studio-panel">
      <div className="panel-layout">
        <div className="panel-list">
          <div className="panel-list-header">
            <span>个体 ({individuals.length})</span>
            <button className="btn btn-primary btn-sm" onClick={() => {
              if (!showCreate) {
                setFormData({
                  name: '', label: '', comment: '', types: [],
                  data_property_values: {}, object_property_values: {},
                  same_as: [], different_from: []
                })
                setEditing(false)
                setSelectedInd(null)
              }
              setShowCreate(!showCreate)
            }} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              {showCreate ? <X size={14} /> : <Plus size={14} />}
              {showCreate ? '取消' : '新建'}
            </button>
          </div>

          {showCreate && (
            <div className="panel-form">
              <input className="form-input" placeholder="个体名 *" value={formData.name}
                onChange={e => setFormData(p => ({ ...p, name: e.target.value }))} />
              <input className="form-input" placeholder="显示标签" value={formData.label}
                onChange={e => setFormData(p => ({ ...p, label: e.target.value }))} />
              <input className="form-input" placeholder="注释" value={formData.comment}
                onChange={e => setFormData(p => ({ ...p, comment: e.target.value }))} />
              <TreeMultiSelect label="类型 (Classes) *" classes={classes} value={formData.types}
                onChange={types => setFormData(p => ({ ...p, types }))} />
              <button className="btn btn-success btn-sm" onClick={handleCreate} style={{ display: 'flex', alignItems: 'center', gap: 4, justifyContent: 'center' }}>
                <Check size={14} /> 创建
              </button>
            </div>
          )}

          <div className="panel-items">
            {individuals.map(ind => (
              <div key={ind.name}
                className={`panel-item ${selectedInd?.name === ind.name ? 'selected' : ''}`}
                onClick={() => startEdit(ind)}>
                <div className="panel-item-name">
                  <span className="item-icon"><User size={14} /></span>
                  <span>{ind.label || ind.name}</span>
                  {ind.name !== ind.label && <span className="item-name">({ind.name})</span>}
                </div>
                <div className="panel-item-tags">
                  {(ind.types || []).slice(0, 2).map(t => <span key={t} className="item-tag">{t}</span>)}
                </div>
                <div className="panel-item-actions">
                  <button className="btn btn-ghost btn-xs" onClick={e => { e.stopPropagation(); handleDelete(ind.name) }}><Trash2 size={12} /></button>
                </div>
              </div>
            ))}
          </div>
        </div>

        {editing && selectedInd && (
          <div className="panel-detail">
            <div className="panel-detail-header">
              <span>编辑个体: {selectedInd.name}</span>
              <button className="btn btn-ghost btn-sm" onClick={() => { setEditing(false); setSelectedInd(null) }}><X size={14} /></button>
            </div>
            <div className="panel-form">
              <label>显示标签</label>
              <input className="form-input" value={formData.label}
                onChange={e => setFormData(p => ({ ...p, label: e.target.value }))} />
              <label>注释</label>
              <textarea className="form-input" rows={2} value={formData.comment}
                onChange={e => setFormData(p => ({ ...p, comment: e.target.value }))} />
              <TreeMultiSelect label="类型 (Classes)" classes={classes} value={formData.types}
                onChange={types => setFormData(p => ({ ...p, types }))} />

              <label>数据属性值</label>
              {dataProperties.map(dp => (
                <div key={dp.name} className="property-value-row">
                  <span className="property-label">{dp.name}</span>
                  <input className="form-input" value={formData.data_property_values[dp.name] || ''}
                    onChange={e => setFormData(p => ({
                      ...p,
                      data_property_values: { ...p.data_property_values, [dp.name]: e.target.value }
                    }))}
                    placeholder={dp.range || 'string'} />
                </div>
              ))}

              <label>对象属性值（关联其他个体）</label>
              {objectProperties.map(op => (
                <div key={op.name} className="property-value-row">
                  <span className="property-label">{op.name}</span>
                  <MultiSelect options={individualOptions.filter(n => n !== selectedInd.name)}
                    value={formData.object_property_values[op.name] || []}
                    onChange={values => setFormData(p => ({
                      ...p,
                      object_property_values: { ...p.object_property_values, [op.name]: values }
                    }))} />
                </div>
              ))}

              <MultiSelect label="相同个体 (Same As)" options={individualOptions.filter(n => n !== selectedInd.name)}
                value={formData.same_as}
                onChange={same_as => setFormData(p => ({ ...p, same_as }))} />
              <MultiSelect label="不同个体 (Different From)" options={individualOptions.filter(n => n !== selectedInd.name)}
                value={formData.different_from}
                onChange={different_from => setFormData(p => ({ ...p, different_from }))} />

              <button className="btn btn-primary" onClick={handleUpdate} style={{ display: 'flex', alignItems: 'center', gap: 4, justifyContent: 'center' }}>
                <Check size={14} /> 保存修改
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// =============================================================================
// 类层次结构可视化面板
// =============================================================================

function ClassHierarchyPanel({ ontologyId, addToast }) {
  const [hierarchy, setHierarchy] = useState([])
  const [stats, setStats] = useState({ total_classes: 0, root_classes: 0 })
  const [loading, setLoading] = useState(false)
  const [expandedNodes, setExpandedNodes] = useState({})

  useEffect(() => {
    loadHierarchy()
  }, [ontologyId])

  const loadHierarchy = async () => {
    setLoading(true)
    try {
      const data = await api.getOntologyClassHierarchy(ontologyId)
      setHierarchy(data.hierarchy || [])
      setStats({ total_classes: data.total_classes, root_classes: data.root_classes })
      
      const initialExpanded = {}
      const markExpanded = (node) => {
        initialExpanded[node.name] = true
        node.children?.forEach(markExpanded)
      }
      data.hierarchy?.forEach(markExpanded)
      setExpandedNodes(initialExpanded)
    } catch (e) { addToast('加载层次结构失败: ' + e.message, 'error') }
    finally { setLoading(false) }
  }

  const toggleNode = (nodeName) => {
    setExpandedNodes(prev => ({
      ...prev,
      [nodeName]: !prev[nodeName],
    }))
  }

  const renderTreeNode = (node, depth = 0) => {
    const isExpanded = expandedNodes[node.name]
    const hasChildren = node.children && node.children.length > 0

    return (
      <div key={node.name} className="tree-node">
        <div
          className={`tree-node-header ${hasChildren ? 'clickable' : ''}`}
          style={{ paddingLeft: `${depth * 20 + 8}px` }}
          onClick={() => hasChildren && toggleNode(node.name)}
        >
          {hasChildren && (
            <span className="tree-node-icon" style={{ display: 'flex', alignItems: 'center' }}>
              {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </span>
          )}
          {!hasChildren && <span className="tree-node-icon leaf" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}><Box size={10} /></span>}
          <span className="tree-node-label" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            {node.label || node.name}
            {node.name !== node.label && (
              <span className="tree-node-name">({node.name})</span>
            )}
          </span>
          {node.is_circular && <span className="tree-node-warning">⚠️ 循环引用</span>}
        </div>
        {hasChildren && isExpanded && (
          <div className="tree-node-children">
            {node.children.map(child => renderTreeNode(child, depth + 1))}
          </div>
        )}
      </div>
    )
  }

  if (loading) {
    return (
      <div className="studio-panel">
        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
          <RefreshCw size={24} className="spinning" style={{ marginBottom: 12 }} />
          <div>加载中...</div>
        </div>
      </div>
    )
  }

  return (
    <div className="studio-panel">
      <div className="panel-list-header">
        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}><GitBranch size={16} /> 类层次结构</span>
        <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>
          {stats.total_classes} 个类，{stats.root_classes} 个根类
        </span>
      </div>
      <div className="hierarchy-tree">
        {hierarchy.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
            暂无类层次结构数据，请先创建或导入本体
          </div>
        ) : (
          hierarchy.map(node => renderTreeNode(node))
        )}
      </div>
    </div>
  )
}

// =============================================================================
// 本体关系图面板
// =============================================================================

const NODE_COLORS = {
  class: '#f0ad4e',
  individual: '#5cb85c',
}
const EDGE_COLORS = {
  subClassOf: '#888',
  objectProperty: '#5bc0de',
  instanceOf: '#5cb85c',
  disjointWith: '#d9534f',
  equivalentTo: '#9b59b6',
}

function OntologyGraphPanel({ ontologyId, addToast, refreshKey }) {
  const [graphData, setGraphData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [selectedNode, setSelectedNode] = useState(null)
  const [search, setSearch] = useState('')
  const [showIndividuals, setShowIndividuals] = useState(true)
  const [showDisjoint, setShowDisjoint] = useState(true)
  const [showEquivalent, setShowEquivalent] = useState(true)
  const [usageData, setUsageData] = useState(null)
  const [showUsage, setShowUsage] = useState(false)
  const graphRef = useRef()
  const containerRef = useRef()
  const [dimensions, setDimensions] = useState({ width: 800, height: 500 })

  // 加载图形数据
  const loadGraph = useCallback(async () => {
    console.log('[OntologyGraphPanel] loadGraph called, ontologyId:', ontologyId)
    setLoading(true)
    try {
      const data = await api.getStudioGraph(ontologyId, {
        showIndividuals, showDisjoint, showEquivalent,
      })
      console.log('[OntologyGraphPanel] Graph API response:', data)
      console.log('[OntologyGraphPanel] Nodes count:', data.nodes?.length, 'Edges count:', data.edges?.length)
      if (data.nodes && data.nodes.length > 0) {
        console.log('[OntologyGraphPanel] First node:', data.nodes[0])
      }
      if (data.edges && data.edges.length > 0) {
        console.log('[OntologyGraphPanel] First edge:', data.edges[0])
      }
      // ForceGraph2D 需要 nodes 数组，links 中的 source/target 可以是字符串ID或对象引用
      // 这里使用字符串ID，ForceGraph2D 会自动解析
      const formattedData = {
        nodes: data.nodes || [],
        links: (data.edges || []).map(e => ({
          id: `${e.source}--${e.target}--${e.type}`,
          source: e.source,
          target: e.target,
          type: e.type,
          label: e.label,
        })),
      }
      console.log('[OntologyGraphPanel] Formatted graph data:', formattedData)
      setGraphData(formattedData)
    } catch (e) { 
      console.error('[OntologyGraphPanel] Graph loading error:', e)
      addToast('加载图形数据失败: ' + e.message, 'error') 
    }
    finally { setLoading(false) }
  }, [ontologyId, showIndividuals, showDisjoint, showEquivalent])

  useEffect(() => { 
    console.log('[OntologyGraphPanel] graphData state changed:', graphData ? `nodes=${graphData.nodes.length}, links=${graphData.links.length}` : 'null')
    loadGraph() 
  }, [loadGraph])

  useEffect(() => {
    console.log('[OntologyGraphPanel] refreshKey changed:', refreshKey)
    if (refreshKey > 0) {
      loadGraph()
    }
  }, [refreshKey])

  // 容器尺寸感知
  useEffect(() => {
    if (!containerRef.current) return
    const ro = new ResizeObserver(entries => {
      for (const entry of entries) {
        setDimensions({
          width: entry.contentRect.width || 800,
          height: entry.contentRect.height || 450,
        })
      }
    })
    ro.observe(containerRef.current)
    return () => ro.disconnect()
  }, [])

  // 加载实体使用统计
  const loadUsage = useCallback(async () => {
    try {
      const data = await api.getStudioEntityUsage(ontologyId)
      setUsageData(data)
    } catch (e) { addToast('加载使用统计失败: ' + e.message, 'error') }
  }, [ontologyId, addToast])

  useEffect(() => { if (showUsage && !usageData) loadUsage() }, [showUsage, usageData, loadUsage])

  // 搜索匹配
  const highlightNodes = useMemo(() => {
    if (!search || !graphData) return new Set()
    const s = search.toLowerCase()
    return new Set(graphData.nodes.filter(n =>
      n.name.toLowerCase().includes(s) || n.entityName.toLowerCase().includes(s)
    ).map(n => n.id))
  }, [search, graphData])

  // 节点渲染
  const paintNode = useCallback((node, ctx, globalScale) => {
    const isHighlighted = highlightNodes.size > 0 && highlightNodes.has(node.id)
    const isSelected = selectedNode && selectedNode.id === node.id
    const isDimmed = highlightNodes.size > 0 && !highlightNodes.has(node.id)
    const r = node.type === 'class' ? 6 : 4
    const color = NODE_COLORS[node.type] || '#aaa'

    ctx.beginPath()
    if (node.type === 'individual') {
      // 菱形
      ctx.moveTo(node.x, node.y - r)
      ctx.lineTo(node.x + r, node.y)
      ctx.lineTo(node.x, node.y + r)
      ctx.lineTo(node.x - r, node.y)
    } else {
      ctx.arc(node.x, node.y, r, 0, 2 * Math.PI)
    }
    ctx.fillStyle = isDimmed ? color + '40' : color
    ctx.fill()

    if (isSelected || isHighlighted) {
      ctx.strokeStyle = isSelected ? '#fff' : '#ff0'
      ctx.lineWidth = 2 / globalScale
      ctx.stroke()
    }

    // 标签
    const fontSize = Math.max(10 / globalScale, 2)
    ctx.font = `${fontSize}px sans-serif`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'top'
    ctx.fillStyle = isDimmed ? '#666' : '#e0e0e0'
    ctx.fillText(node.name, node.x, node.y + r + 2)
  }, [highlightNodes, selectedNode])

  // 边渲染
  const paintLink = useCallback((link, ctx) => {
    const color = EDGE_COLORS[link.type] || '#555'
    ctx.strokeStyle = color
    ctx.lineWidth = link.type === 'subClassOf' ? 1.5 : 1
    if (link.type === 'disjointWith') {
      ctx.setLineDash([4, 4])
    } else {
      ctx.setLineDash([])
    }
    ctx.beginPath()
    ctx.moveTo(link.source.x, link.source.y)
    ctx.lineTo(link.target.x, link.target.y)
    ctx.stroke()
    ctx.setLineDash([])
  }, [])

  const handleNodeClick = useCallback((node) => {
    setSelectedNode(prev => prev && prev.id === node.id ? null : node)
    if (graphRef.current) {
      graphRef.current.centerAt(node.x, node.y, 500)
      graphRef.current.zoom(3, 500)
    }
  }, [])

  const handleZoomToFit = () => {
    if (graphRef.current) graphRef.current.zoomToFit(400, 40)
  }

    return (
    <div className="ontology-graph-panel" style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0, overflow: 'hidden' }}>
      {/* 工具栏 */}
      <div className="panel-list-header" style={{ flexShrink: 0, flexWrap: 'wrap', gap: 6 }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}><Network size={16} /> 本体关系图</span>
        <div style={{ display: 'flex', gap: 4, alignItems: 'center', flexWrap: 'wrap' }}>
          <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
            <Search size={12} style={{ position: 'absolute', left: 8, color: 'var(--text-muted)' }} />
            <input
              type="text"
              placeholder="搜索节点..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              style={{ padding: '3px 8px 3px 24px', borderRadius: 4, border: '1px solid var(--border)', background: 'var(--bg-subtle)', color: 'var(--text)', fontSize: '0.75rem', width: 120 }}
            />
          </div>
          <label style={{ fontSize: '0.7rem', display: 'flex', alignItems: 'center', gap: 2, cursor: 'pointer' }}>
            <input type="checkbox" checked={showIndividuals} onChange={e => setShowIndividuals(e.target.checked)} /> 个体
          </label>
          <label style={{ fontSize: '0.7rem', display: 'flex', alignItems: 'center', gap: 2, cursor: 'pointer' }}>
            <input type="checkbox" checked={showDisjoint} onChange={e => setShowDisjoint(e.target.checked)} /> 不相交
          </label>
          <label style={{ fontSize: '0.7rem', display: 'flex', alignItems: 'center', gap: 2, cursor: 'pointer' }}>
            <input type="checkbox" checked={showEquivalent} onChange={e => setShowEquivalent(e.target.checked)} /> 等价
          </label>
          <button className="btn btn-outline btn-sm" onClick={handleZoomToFit} title="适应视图" style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <MousePointer2 size={12} /> 适应
          </button>
          <button className="btn btn-outline btn-sm" onClick={loadGraph} title="刷新" style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <RefreshCw size={12} /> 刷新
          </button>
        </div>
      </div>

      {/* 图例 */}
      <div style={{ display: 'flex', gap: 12, padding: '4px 12px', fontSize: '0.7rem', color: 'var(--text-muted)', borderBottom: '1px solid var(--border)', flexWrap: 'wrap' }}>
        <span><span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: '50%', background: NODE_COLORS.class, marginRight: 3 }}></span>类</span>
        <span><span style={{ display: 'inline-block', width: 10, height: 10, transform: 'rotate(45deg)', background: NODE_COLORS.individual, marginRight: 3 }}></span>个体</span>
        <span style={{ borderLeft: '1px solid var(--border)', paddingLeft: 8 }}>
          <span style={{ color: EDGE_COLORS.subClassOf }}>——</span> 继承
        </span>
        <span><span style={{ color: EDGE_COLORS.objectProperty }}>——</span> 属性</span>
        <span><span style={{ color: EDGE_COLORS.instanceOf }}>——</span> 类型</span>
        <span><span style={{ color: EDGE_COLORS.disjointWith }}>- -</span> 不相交</span>
        <span><span style={{ color: EDGE_COLORS.equivalentTo }}>——</span> 等价</span>
      </div>

      {/* 统计 */}
      {graphData && (
        <div style={{ display: 'flex', gap: 16, padding: '4px 12px', fontSize: '0.7rem', color: 'var(--text-muted)', borderBottom: '1px solid var(--border)' }}>
          <span>节点: {graphData.nodes.length}</span>
          <span>边: {graphData.links.length}</span>
          <span>类: {graphData.nodes.filter(n => n.type === 'class').length}</span>
          {showIndividuals && <span>个体: {graphData.nodes.filter(n => n.type === 'individual').length}</span>}
        </div>
      )}

      {/* 图形区域 */}
      <div ref={containerRef} style={{ flex: 1, minHeight: '200px', position: 'relative', background: '#1a1a2e', overflow: 'hidden' }}>
        {loading && (
          <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', color: '#fff', zIndex: 10, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
            <RefreshCw size={24} className="spinning" />
            <span>加载图形数据...</span>
          </div>
        )}

        {graphData && graphData.nodes.length > 0 && (
          <ForceGraph2D
            ref={graphRef}
            width={dimensions.width}
            height={dimensions.height}
            graphData={graphData}
            nodeCanvasObject={paintNode}
            linkCanvasObject={paintLink}
            onNodeClick={handleNodeClick}
            nodeLabel={n => `${n.type === 'class' ? '类' : '个体'} ${n.name} (${n.entityName})`}
            linkLabel={l => `${l.label || l.type}`}
            backgroundColor="#1a1a2e"
            linkDirectionalArrowLength={4}
            linkDirectionalArrowRelPos={0.8}
            cooldownTicks={80}
            onEngineStop={() => { if (graphRef.current) graphRef.current.zoomToFit(400, 40) }}
          />
        )}

        {graphData && graphData.nodes.length === 0 && !loading && (
          <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', color: 'var(--text-muted)', textAlign: 'center' }}>
            暂无图形数据，请先创建类或导入本体
          </div>
        )}

        {/* 节点详情侧栏 */}
        {selectedNode && (
          <div style={{
            position: 'absolute', top: 8, right: 8, width: 220, maxHeight: '90%', overflow: 'auto',
            background: 'rgba(30, 30, 50, 0.95)', border: '1px solid var(--border)', borderRadius: 8,
            padding: 12, fontSize: '0.75rem', color: '#e0e0e0', zIndex: 20,
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
              <strong>{selectedNode.type === 'class' ? '📦 类' : '👤 个体'}</strong>
              <button style={{ background: 'none', border: 'none', color: '#aaa', cursor: 'pointer', fontSize: 14 }} onClick={() => setSelectedNode(null)}>✕</button>
            </div>
            <div style={{ marginBottom: 6 }}>
              <div style={{ fontWeight: 600, fontSize: '0.85rem', color: NODE_COLORS[selectedNode.type] }}>{selectedNode.name}</div>
              <div style={{ color: '#888', fontSize: '0.7rem' }}>{selectedNode.entityName}</div>
            </div>
            {selectedNode.parents && selectedNode.parents.length > 0 && (
              <div style={{ marginBottom: 6 }}>
                <div style={{ color: '#888', marginBottom: 2 }}>父类:</div>
                {selectedNode.parents.map(p => (
                  <span key={p} style={{ display: 'inline-block', padding: '1px 6px', margin: '1px 2px', background: 'rgba(240,173,78,0.2)', borderRadius: 3, fontSize: '0.7rem' }}>{p}</span>
                ))}
              </div>
            )}
            {/* 显示与此节点相关的边 */}
            {graphData && (() => {
              const relatedLinks = graphData.links.filter(l =>
                (l.source.id || l.source) === selectedNode.id || (l.target.id || l.target) === selectedNode.id
              )
              return relatedLinks.length > 0 ? (
                <div>
                  <div style={{ color: '#888', marginBottom: 2 }}>关系 ({relatedLinks.length}):</div>
                  {relatedLinks.slice(0, 15).map((l, i) => {
                    const srcId = l.source.id || l.source
                    const tgtId = l.target.id || l.target
                    const isSource = srcId === selectedNode.id
                    const otherName = isSource ? (l.target.name || tgtId) : (l.source.name || srcId)
                    return (
                      <div key={i} style={{ fontSize: '0.68rem', padding: '2px 0', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                        <span style={{ color: EDGE_COLORS[l.type] || '#888' }}>{l.label || l.type}</span>
                        <span style={{ color: '#aaa' }}> {isSource ? '→' : '←'} </span>
                        <span>{otherName}</span>
                      </div>
                    )
                  })}
                  {relatedLinks.length > 15 && <div style={{ color: '#666', fontSize: '0.65rem' }}>...还有 {relatedLinks.length - 15} 个</div>}
                </div>
              ) : null
            })()}
          </div>
        )}
      </div>

      {/* 实体使用分析 */}
      <div style={{ borderTop: '1px solid var(--border)', background: 'var(--bg-surface)', flexShrink: 0 }}>
        <div
          style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 16px', cursor: 'pointer', fontSize: '0.85rem', fontWeight: 600 }}
          onClick={() => setShowUsage(!showUsage)}
        >
          <span>📊 实体使用分析</span>
          <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>{showUsage ? '收起 ▲' : '展开 ▼'}</span>
        </div>
        {showUsage && usageData && (
          <div style={{ padding: '0 16px 16px', maxHeight: '140px', overflowY: 'auto' }}>
            {/* 统计概览 */}
            <div style={{ display: 'flex', gap: 20, marginBottom: 12, fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
              <span>类: {usageData.stats.total_classes}</span>
              <span>属性: {usageData.stats.total_properties}</span>
              <span>个体: {usageData.stats.total_individuals}</span>
              {usageData.orphan_classes.length > 0 && (
                <span style={{ color: 'var(--warning)' }}>⚠ 孤立类: {usageData.orphan_classes.length}</span>
              )}
            </div>
            {/* 孤立类警告 */}
            {usageData.orphan_classes.length > 0 && (
              <div style={{ padding: '4px 8px', marginBottom: 8, background: 'rgba(217,83,79,0.15)', borderRadius: 4, fontSize: '0.7rem', color: 'var(--warning)' }}>
                ⚠ 以下类未被任何其他实体引用: {usageData.orphan_classes.join(', ')}
              </div>
            )}
            {/* 类使用排行 */}
            <table style={{ width: '100%', fontSize: '0.7rem', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)', color: 'var(--text-muted)' }}>
                  <th style={{ textAlign: 'left', padding: '3px 4px' }}>类名</th>
                  <th style={{ textAlign: 'center', padding: '3px 2px' }}>父类引用</th>
                  <th style={{ textAlign: 'center', padding: '3px 2px' }}>Domain</th>
                  <th style={{ textAlign: 'center', padding: '3px 2px' }}>Range</th>
                  <th style={{ textAlign: 'center', padding: '3px 2px' }}>个体</th>
                  <th style={{ textAlign: 'center', padding: '3px 2px' }}>总计</th>
                </tr>
              </thead>
              <tbody>
                {usageData.classes.slice(0, 20).map(cls => (
                  <tr key={cls.name} style={{ borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
                    <td style={{ padding: '3px 4px', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{cls.label || cls.name}</td>
                    <td style={{ textAlign: 'center', padding: '3px 2px' }}>{cls.as_parent || '-'}</td>
                    <td style={{ textAlign: 'center', padding: '3px 2px' }}>{cls.as_domain || '-'}</td>
                    <td style={{ textAlign: 'center', padding: '3px 2px' }}>{cls.as_range || '-'}</td>
                    <td style={{ textAlign: 'center', padding: '3px 2px' }}>{cls.individual_count || '-'}</td>
                    <td style={{ textAlign: 'center', padding: '3px 2px', fontWeight: 600, color: cls.total_refs === 0 ? 'var(--warning)' : 'var(--text)' }}>{cls.total_refs}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div style={{ height: '40px' }}></div>
            {usageData.classes.length > 20 && (
              <div style={{ textAlign: 'center', fontSize: '0.65rem', color: 'var(--text-muted)', marginTop: 4 }}>
                显示前 20 个，共 {usageData.classes.length} 个类
              </div>
            )}
          </div>
        )}
        {showUsage && !usageData && (
          <div style={{ padding: '8px 12px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.75rem' }}>
            ⏳ 加载中...
          </div>
        )}
      </div>
    </div>
  )
}

// =============================================================================
// 推理机面板
// =============================================================================

function ReasonerPanel({ ontologyId, addToast }) {
  const [reasoning, setReasoning] = useState(false)
  const [result, setResult] = useState(null)
  const [filter, setFilter] = useState('all')
  const [showLog, setShowLog] = useState(false)

  const handleReason = async () => {
    setReasoning(true)
    try {
      const data = await api.reasonOntology(ontologyId)
      setResult(data)
      if (data.from_cache) {
        addToast('返回缓存的推理结果', 'info')
      } else if (data.is_consistent) {
        addToast(`推理完成 (${data.duration_ms}ms, ${data.reasoner_type})，本体一致`, 'success')
      } else {
        addToast(`推理完成，发现 ${data.stats.errors} 个错误`, 'error')
      }
    } catch (e) { addToast('推理失败: ' + e.message, 'error') }
    finally { setReasoning(false) }
  }

  const handleClearCache = async () => {
    try {
      await api.clearReasonerCache(ontologyId)
      addToast('推理缓存已清除', 'success')
      setResult(null)
    } catch (e) { addToast('清除缓存失败: ' + e.message, 'error') }
  }

  const filteredRelations = result ? result.inferred_relations.filter(rel => {
    if (filter === 'all') return true
    if (filter === 'subClassOf') return rel.type === 'subClassOf'
    if (filter === 'instanceOf') return rel.type === 'instanceOf'
    return true
  }) : []

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      <div className="panel-list-header" style={{ flexShrink: 0 }}>
        <span>🔍 推理机</span>
        <div style={{ display: 'flex', gap: 4 }}>
          {result && (
            <button className="btn btn-outline btn-sm" onClick={handleClearCache} title="清除缓存">
              🗑️ 清除缓存
            </button>
          )}
          <button className="btn btn-primary btn-sm" onClick={handleReason} disabled={reasoning}>
            {reasoning ? '⏳ 推理中...' : '▶️ 开始推理'}
          </button>
        </div>
      </div>

      <div style={{ flex: 1, overflow: 'auto', padding: '16px' }}>

      {!result && !reasoning && (
        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
          点击"开始推理"对本体进行一致性检查和隐含关系推导
        </div>
      )}

      {result && (
        <div className="reasoner-results">
          {/* 一致性状态 + 元信息 */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
            <div className={`consistency-badge ${result.is_consistent ? 'consistent' : 'inconsistent'}`} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              {result.is_consistent ? <><CheckCircle size={14} /> 本体一致</> : <><XCircle size={14} /> 本体不一致</>}
            </div>
            <div style={{ display: 'flex', gap: 8, fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              {result.from_cache && (
                <span style={{ padding: '2px 6px', background: 'var(--warning)', color: '#000', borderRadius: 4, fontSize: 11 }}>缓存</span>
              )}
              <span>⏱ {result.duration_ms || 0}ms</span>
              <span>🧠 {result.reasoner_type === 'hermit' ? 'HermiT' : 'JSON Fallback'}</span>
            </div>
          </div>

          {/* 统计面板 */}
          <div className="reasoner-stats">
            <div className="reasoner-stat">
              <div className="stat-value">{result.stats.total_issues}</div>
              <div className="stat-label">问题总数</div>
            </div>
            <div className="reasoner-stat">
              <div className="stat-value" style={{ color: 'var(--danger)' }}>{result.stats.errors}</div>
              <div className="stat-label">错误</div>
            </div>
            <div className="reasoner-stat">
              <div className="stat-value" style={{ color: 'var(--warning)' }}>{result.stats.warnings}</div>
              <div className="stat-label">警告</div>
            </div>
            <div className="reasoner-stat">
              <div className="stat-value" style={{ color: 'var(--info)' }}>{result.stats.inferred_relations}</div>
              <div className="stat-label">推导关系</div>
            </div>
            {result.stats.inferred_subclasses !== undefined && (
              <div className="reasoner-stat">
                <div className="stat-value" style={{ color: 'var(--primary)' }}>{result.stats.inferred_subclasses}</div>
                <div className="stat-label">子类推导</div>
              </div>
            )}
            {result.stats.inferred_types !== undefined && (
              <div className="reasoner-stat">
                <div className="stat-value" style={{ color: 'var(--success)' }}>{result.stats.inferred_types}</div>
                <div className="stat-label">类型推导</div>
              </div>
            )}
          </div>

          {/* 问题列表 + 解释 */}
          {result.issues.length > 0 && (
            <div className="reasoner-section">
              <h4>🚨 问题列表</h4>
              <div className="issues-list">
                {result.issues.map((issue, idx) => (
                  <div key={idx} className={`issue-item issue-${issue.type}`}>
                    <span className="issue-icon">{issue.type === 'error' ? '❌' : '⚠️'}</span>
                    <div className="issue-content">
                      <div className="issue-message">{issue.message}</div>
                      <div className="issue-entity">实体: {issue.entity}</div>
                      {issue.explanation && (
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 4, fontStyle: 'italic', padding: '4px 8px', background: 'var(--bg-subtle)', borderRadius: 4 }}>
                          💡 {issue.explanation}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 推导关系 + 过滤器 */}
          {result.inferred_relations.length > 0 && (
            <div className="reasoner-section">
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                <h4 style={{ margin: 0 }}>💡 推导的关系</h4>
                <div style={{ display: 'flex', gap: 4, fontSize: '0.75rem' }}>
                  <button className={`btn btn-xs ${filter === 'all' ? 'btn-primary' : 'btn-outline'}`} onClick={() => setFilter('all')}>全部</button>
                  <button className={`btn btn-xs ${filter === 'subClassOf' ? 'btn-primary' : 'btn-outline'}`} onClick={() => setFilter('subClassOf')}>子类</button>
                  <button className={`btn btn-xs ${filter === 'instanceOf' ? 'btn-primary' : 'btn-outline'}`} onClick={() => setFilter('instanceOf')}>实例</button>
                </div>
              </div>
              <div className="inferred-list">
                {filteredRelations.slice(0, 30).map((rel, idx) => (
                  <div key={idx} className="inferred-item">
                    <span className="inferred-type">{rel.type === 'subClassOf' ? '子类' : '实例'}</span>
                    <span className="inferred-subject">{rel.subject}</span>
                    <span className="inferred-arrow">→</span>
                    <span className="inferred-object">{rel.object}</span>
                    <span className="inferred-reason">{rel.reason}</span>
                  </div>
                ))}
                {filteredRelations.length > 30 && (
                  <div className="inferred-more">
                    还有 {filteredRelations.length - 30} 个推导关系...
                  </div>
                )}
              </div>
            </div>
          )}

          {/* 推理日志 */}
          {result.log && (
            <div className="reasoner-section">
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer' }} onClick={() => setShowLog(!showLog)}>
                <h4 style={{ margin: 0 }}>📋 推理日志</h4>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{showLog ? '收起 ▲' : '展开 ▼'}</span>
              </div>
              {showLog && (
                <pre style={{
                  marginTop: 8, padding: 12, background: 'var(--bg-subtle)', borderRadius: 6,
                  fontSize: '0.7rem', maxHeight: 200, overflow: 'auto', whiteSpace: 'pre-wrap',
                  fontFamily: 'monospace', color: 'var(--text-muted)',
                }}>
                  {result.log || '（无日志）'}
                </pre>
              )}
            </div>
          )}
        </div>
      )}

      </div>
    </div>
  )
}

// =============================================================================
// 本体元数据面板
// =============================================================================

function MetadataPanel({ ontologyId, addToast }) {
  const [metadata, setMetadata] = useState({ ontology_iri: '', version_iri: '', annotations: [] })
  const [loading, setLoading] = useState(false)
  const [exportFormat, setExportFormat] = useState('turtle')
  const [versions, setVersions] = useState([])
  const [showVersionForm, setShowVersionForm] = useState(false)
  const [versionForm, setVersionForm] = useState({ version: '', comment: '' })
  const [creatingVersion, setCreatingVersion] = useState(false)

  useEffect(() => {
    loadMetadata()
    loadVersions()
  }, [ontologyId])

  const loadMetadata = async () => {
    setLoading(true)
    try {
      const data = await api.getOntologyMetadata(ontologyId)
      setMetadata(data)
    } catch (e) { addToast('加载元数据失败: ' + e.message, 'error') }
    finally { setLoading(false) }
  }

  const loadVersions = async () => {
    try {
      const data = await api.listOntologyVersions(ontologyId)
      setVersions(data.versions || [])
    } catch (e) { /* ignore */ }
  }

  const handleSave = async () => {
    try {
      await api.updateOntologyMetadata(ontologyId, metadata)
      addToast('本体元数据已保存', 'success')
    } catch (e) { addToast('保存失败: ' + e.message, 'error') }
  }

  const handleExport = async () => {
    try {
      const data = await api.exportOntology(ontologyId, exportFormat)
      const blob = new Blob([data.content], { type: 'text/plain' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = data.filename
      a.click()
      URL.revokeObjectURL(url)
      addToast(`本体已导出为 ${data.format} 格式 (${data.triple_count} 个三元组)`, 'success')
    } catch (e) { addToast('导出失败: ' + e.message, 'error') }
  }

  const handleCreateVersion = async () => {
    if (!versionForm.version.trim()) {
      addToast('版本号不能为空', 'error')
      return
    }
    setCreatingVersion(true)
    try {
      await api.createOntologyVersion(ontologyId, versionForm)
      addToast(`版本 ${versionForm.version} 已创建`, 'success')
      setVersionForm({ version: '', comment: '' })
      setShowVersionForm(false)
      loadVersions()
    } catch (e) { addToast('创建版本失败: ' + e.message, 'error') }
    finally { setCreatingVersion(false) }
  }

  const handleRestoreVersion = async (version) => {
    if (!confirm(`确定要恢复到版本 ${version} 吗？当前未保存的修改将丢失。`)) return
    try {
      await api.restoreOntologyVersion(ontologyId, version)
      addToast(`已恢复到版本 ${version}`, 'success')
      loadMetadata()
    } catch (e) { addToast('恢复版本失败: ' + e.message, 'error') }
  }

  const handleDeleteVersion = async (version) => {
    if (!confirm(`确定要删除版本 ${version} 吗？`)) return
    try {
      await api.deleteOntologyVersion(ontologyId, version)
      addToast(`版本 ${version} 已删除`, 'success')
      loadVersions()
    } catch (e) { addToast('删除版本失败: ' + e.message, 'error') }
  }

  return (
    <div className="studio-panel metadata-panel">
      <div className="panel-list-header">
        <span>⚙️ 本体元数据</span>
      </div>

      <div className="panel-form">
        <label>本体 IRI</label>
        <input className="form-input" value={metadata.ontology_iri}
          onChange={e => setMetadata(p => ({ ...p, ontology_iri: e.target.value }))}
          placeholder="http://ontology.example.com/my-ontology" />

        <label>版本 IRI</label>
        <input className="form-input" value={metadata.version_iri}
          onChange={e => setMetadata(p => ({ ...p, version_iri: e.target.value }))}
          placeholder="http://ontology.example.com/my-ontology/1.0" />

        <label>本体注释</label>
        <textarea className="form-input" rows={3}
          value={metadata.annotations.join('\n')}
          onChange={e => setMetadata(p => ({ ...p, annotations: e.target.value.split('\n').filter(Boolean) }))}
          placeholder="每行一个注释" />

        <button className="btn btn-primary" onClick={handleSave}>💾 保存元数据</button>
      </div>

      <div className="panel-section" style={{ marginTop: 24, paddingTop: 24, borderTop: '1px solid var(--border-color)' }}>
        <div className="panel-list-header">
          <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}><Download size={16} /> 导出本体</span>
        </div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 12 }}>
          <select className="form-input" style={{ width: 180 }} value={exportFormat}
            onChange={e => setExportFormat(e.target.value)}>
            <option value="turtle">Turtle (.ttl)</option>
            <option value="xml">RDF/XML (.owl)</option>
            <option value="rdf">RDF (.rdf)</option>
            <option value="n3">N3 (.n3)</option>
            <option value="nt">N-Triples (.nt)</option>
            <option value="json-ld">JSON-LD (.jsonld)</option>
          </select>
          <button className="btn btn-success" onClick={handleExport} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <Download size={14} /> 导出文件
          </button>
        </div>
      </div>

      <div className="panel-section" style={{ marginTop: 24, paddingTop: 24, borderTop: '1px solid var(--border-color)' }}>
        <div className="panel-list-header">
          <span>📦 版本管理</span>
          <button className="btn btn-outline btn-sm" onClick={() => setShowVersionForm(!showVersionForm)}>
            {showVersionForm ? '✕' : '➕ 创建版本'}
          </button>
        </div>

        {showVersionForm && (
          <div className="panel-form" style={{ marginTop: 12 }}>
            <input className="form-input" placeholder="版本号 * (如: 1.0.0)" value={versionForm.version}
              onChange={e => setVersionForm(p => ({ ...p, version: e.target.value }))} />
            <input className="form-input" placeholder="版本说明" value={versionForm.comment}
              onChange={e => setVersionForm(p => ({ ...p, comment: e.target.value }))} />
            <button className="btn btn-success btn-sm" onClick={handleCreateVersion} disabled={creatingVersion}>
              {creatingVersion ? '⏳ 创建中...' : '✅ 创建版本'}
            </button>
          </div>
        )}

        <div className="versions-list">
          {versions.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 20, color: 'var(--text-muted)', fontSize: 13 }}>
              暂无版本，点击上方按钮创建第一个版本
            </div>
          ) : (
            versions.map(v => (
              <div key={v.version} className="version-item">
                <div className="version-info">
                  <div className="version-number">v{v.version}</div>
                  <div className="version-comment">{v.comment || '无说明'}</div>
                  <div className="version-meta">
                    <span>{new Date(v.created_at).toLocaleString('zh-CN')}</span>
                    <span>{v.classes_count} 个类</span>
                    <span>{v.individuals_count} 个个体</span>
                  </div>
                </div>
                <div className="version-actions">
                  <button className="btn btn-outline btn-xs" onClick={() => handleRestoreVersion(v.version)}>
                    🔄 恢复
                  </button>
                  <button className="btn btn-ghost btn-xs" onClick={() => handleDeleteVersion(v.version)}>
                    🗑️
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}

// =============================================================================
// 多选组件
// =============================================================================

function MultiSelect({ label, options, value, onChange }) {
  const [showDropdown, setShowDropdown] = useState(false)
  const [search, setSearch] = useState('')
  const wrapperRef = useRef(null)

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target)) {
        setShowDropdown(false)
        setSearch('')
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [])

  const filtered = options.filter(o =>
    o.toLowerCase().includes(search.toLowerCase()) && !value.includes(o)
  )

  const handleSelect = (option) => {
    onChange([...value, option])
    setSearch('')
    setShowDropdown(false)
  }

  const handleRemove = (option) => {
    onChange(value.filter(v => v !== option))
  }

  return (
    <div className="multi-select" ref={wrapperRef}>
      {label && <label>{label}</label>}
      <div className="multi-select-tags">
        {value.map(v => (
          <span key={v} className="multi-tag">
            {v}
            <button className="multi-tag-remove" onClick={() => handleRemove(v)}>×</button>
          </span>
        ))}
        <div className="multi-select-input-wrapper">
          <input
            className="form-input multi-select-input"
            placeholder={value.length === 0 ? '选择或搜索...' : ''}
            value={search}
            onChange={e => { setSearch(e.target.value); setShowDropdown(true) }}
            onFocus={() => setShowDropdown(true)}
          />
          {showDropdown && filtered.length > 0 && (
            <div className="multi-select-dropdown">
              {filtered.slice(0, 10).map(opt => (
                <div key={opt} className="multi-select-option" onClick={() => handleSelect(opt)}>
                  {opt}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function EquivalentClassEditor({ classes, objectProperties, dataProperties, value, onChange, excludeName }) {
  const classOptions = classes.filter(c => c.name !== excludeName).map(c => c.name)
  const allProperties = [...objectProperties.map(p => p.name), ...dataProperties.map(p => p.name)]
  const xsdTypes = ['xsd:string', 'xsd:integer', 'xsd:float', 'xsd:boolean', 'xsd:dateTime', 'xsd:date', 'xsd:time', 'xsd:decimal', 'xsd:double', 'xsd:long', 'xsd:int', 'xsd:short', 'xsd:byte']

  const addSimpleClass = () => {
    onChange([...value, { type: 'class', class: '' }])
  }

  const addIntersection = () => {
    onChange([...value, { type: 'intersection', operands: [{ type: 'class', class: '' }] }])
  }

  const addUnion = () => {
    onChange([...value, { type: 'union', operands: [{ type: 'class', class: '' }] }])
  }

  const addRestriction = () => {
    onChange([...value, { type: 'restriction', property: '', cardinalityType: 'some', cardinality: 1, filler: '', value: '' }])
  }

  const addComplement = () => {
    onChange([...value, { type: 'complement', operand: { type: 'class', class: '' } }])
  }

  const removeItem = (idx) => {
    onChange(value.filter((_, i) => i !== idx))
  }

  const updateItem = (idx, updates) => {
    const newVal = [...value]
    newVal[idx] = { ...newVal[idx], ...updates }
    onChange(newVal)
  }

  const addOperand = (parentIdx, opType = 'class') => {
    const newVal = [...value]
    if (newVal[parentIdx].operands) {
      const newOp = opType === 'restriction'
        ? { type: 'restriction', property: '', cardinalityType: 'some', cardinality: 1, filler: '', value: '' }
        : { type: 'class', class: '' }
      newVal[parentIdx] = { ...newVal[parentIdx], operands: [...newVal[parentIdx].operands, newOp] }
    }
    onChange(newVal)
  }

  const removeOperand = (parentIdx, operandIdx) => {
    const newVal = [...value]
    if (newVal[parentIdx].operands) {
      newVal[parentIdx] = { ...newVal[parentIdx], operands: newVal[parentIdx].operands.filter((_, i) => i !== operandIdx) }
    }
    onChange(newVal)
  }

  const updateOperand = (parentIdx, operandIdx, updates) => {
    const newVal = [...value]
    if (newVal[parentIdx].operands) {
      newVal[parentIdx].operands[operandIdx] = { ...newVal[parentIdx].operands[operandIdx], ...updates }
    }
    onChange(newVal)
  }

  const renderClassSelector = (selectedValue, onChangeHandler) => (
    <select className="form-input" style={{ flex: 1 }} value={selectedValue || ''} onChange={e => onChangeHandler(e.target.value)}>
      <option value="">选择或搜索类...</option>
      {classOptions.map(n => <option key={n} value={n}>{n}</option>)}
    </select>
  )

  const renderRestrictionOperand = (op, updateHandler) => {
    const restType = op.cardinalityType || 'value'
    const restValue = op.value || op.filler || ''
    const isDataProp = dataProperties.map(p => p.name).includes(op.property)
    const isObjProp = objectProperties.map(p => p.name).includes(op.property)

    return (
      <div style={{ display: 'flex', gap: 4, alignItems: 'center', flex: 1 }}>
        <select className="form-input" style={{ width: 120 }} value={op.property || ''}
          onChange={e => updateHandler({ property: e.target.value })}>
          <option value="">选择属性</option>
          {allProperties.map(n => <option key={n} value={n}>{n}</option>)}
        </select>
        <select className="form-input" style={{ width: 80 }} value={restType}
          onChange={e => updateHandler({ cardinalityType: e.target.value })}>
          <option value="value">value</option>
          <option value="some">some</option>
          <option value="only">only</option>
          <option value="min">min</option>
          <option value="max">max</option>
          <option value="exactly">exactly</option>
        </select>
        {(restType === 'min' || restType === 'max' || restType === 'exactly') && (
          <input className="form-input" style={{ width: 50 }} type="number" min="0" value={op.cardinality || 1}
            onChange={e => updateHandler({ cardinality: parseInt(e.target.value) || 0 })} />
        )}
        {restType === 'value' ? (
          <input className="form-input" style={{ flex: 1 }} value={restValue}
            placeholder='值'
            onChange={e => updateHandler({ value: e.target.value })} />
        ) : isDataProp ? (
          <select className="form-input" style={{ flex: 1 }} value={restValue}
            onChange={e => updateHandler({ value: e.target.value })}>
            <option value="">选择数据类型</option>
            {xsdTypes.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        ) : (
          renderClassSelector(restValue, v => updateHandler({ value: v }))
        )}
      </div>
    )
  }

  const renderExpression = (item, idx) => {
    if (item.type === 'class') {
      return (
        <div key={idx} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <span style={{ color: 'var(--primary)', fontWeight: 600 }}>Class:</span>
          {renderClassSelector(item.class, v => updateItem(idx, { class: v }))}
          <button className="btn btn-ghost btn-xs" onClick={() => removeItem(idx)}>✕</button>
        </div>
      )
    }

    if (item.type === 'intersection') {
      return (
        <div key={idx} style={{ display: 'flex', flexDirection: 'column', gap: 4, padding: 8, background: 'var(--bg-subtle)', borderRadius: 6 }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <span style={{ color: 'var(--warning)', fontWeight: 600 }}>and (intersection):</span>
            <button className="btn btn-outline btn-xs" onClick={() => addOperand(idx, 'class')}>➕ 类</button>
            <button className="btn btn-outline btn-xs" onClick={() => addOperand(idx, 'restriction')}>➕ 限制</button>
            <button className="btn btn-ghost btn-xs" onClick={() => removeItem(idx)}>✕</button>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, paddingLeft: 16 }}>
            {item.operands.map((op, opIdx) => (
              <div key={opIdx} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                {opIdx === 0 ? (
                  <span style={{ color: 'var(--primary)', fontWeight: 600 }}>=</span>
                ) : (
                  <span style={{ color: 'var(--warning)', fontWeight: 600 }}>and</span>
                )}
                {op.type === 'class' ? (
                  renderClassSelector(op.class, v => updateOperand(idx, opIdx, { class: v }))
                ) : op.type === 'restriction' ? (
                  renderRestrictionOperand(op, updates => updateOperand(idx, opIdx, updates))
                ) : null}
                {opIdx > 0 && <button className="btn btn-ghost btn-xs" onClick={() => removeOperand(idx, opIdx)}>✕</button>}
              </div>
            ))}
          </div>
        </div>
      )
    }

    if (item.type === 'union') {
      return (
        <div key={idx} style={{ display: 'flex', flexDirection: 'column', gap: 4, padding: 8, background: 'var(--bg-subtle)', borderRadius: 6 }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <span style={{ color: 'var(--success)', fontWeight: 600 }}>or (union):</span>
            <button className="btn btn-outline btn-xs" onClick={() => addOperand(idx, 'class')}>➕ 类</button>
            <button className="btn btn-outline btn-xs" onClick={() => addOperand(idx, 'restriction')}>➕ 限制</button>
            <button className="btn btn-ghost btn-xs" onClick={() => removeItem(idx)}>✕</button>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, paddingLeft: 16 }}>
            {item.operands.map((op, opIdx) => (
              <div key={opIdx} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                {opIdx === 0 ? (
                  <span style={{ color: 'var(--primary)', fontWeight: 600 }}>=</span>
                ) : (
                  <span style={{ color: 'var(--success)', fontWeight: 600 }}>or</span>
                )}
                {op.type === 'class' ? (
                  renderClassSelector(op.class, v => updateOperand(idx, opIdx, { class: v }))
                ) : op.type === 'restriction' ? (
                  renderRestrictionOperand(op, updates => updateOperand(idx, opIdx, updates))
                ) : null}
                {opIdx > 0 && <button className="btn btn-ghost btn-xs" onClick={() => removeOperand(idx, opIdx)}>✕</button>}
              </div>
            ))}
          </div>
        </div>
      )
    }

    if (item.type === 'complement') {
      return (
        <div key={idx} style={{ display: 'flex', flexDirection: 'column', gap: 4, padding: 8, background: 'var(--bg-subtle)', borderRadius: 6, borderLeft: '3px solid var(--danger, #e53e3e)' }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <span style={{ color: 'var(--danger, #e53e3e)', fontWeight: 600 }}>not (complement):</span>
            <button className="btn btn-ghost btn-xs" onClick={() => removeItem(idx)}>✕</button>
          </div>
          <div style={{ paddingLeft: 16 }}>
            {item.operand && item.operand.type === 'class' ? (
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <span style={{ color: 'var(--danger, #e53e3e)', fontWeight: 600 }}>not</span>
                {renderClassSelector(item.operand.class, v => {
                  const newVal = [...value]
                  newVal[idx] = { ...newVal[idx], operand: { type: 'class', class: v } }
                  onChange(newVal)
                })}
              </div>
            ) : item.operand && item.operand.type === 'restriction' ? (
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <span style={{ color: 'var(--danger, #e53e3e)', fontWeight: 600 }}>not</span>
                {renderRestrictionOperand(item.operand, updates => {
                  const newVal = [...value]
                  newVal[idx] = { ...newVal[idx], operand: { ...newVal[idx].operand, ...updates } }
                  onChange(newVal)
                })}
              </div>
            ) : null}
            <div style={{ display: 'flex', gap: 4, marginTop: 4 }}>
              <button className="btn btn-outline btn-xs" onClick={() => {
                const newVal = [...value]
                newVal[idx] = { ...newVal[idx], operand: { type: 'class', class: '' } }
                onChange(newVal)
              }}>类</button>
              <button className="btn btn-outline btn-xs" onClick={() => {
                const newVal = [...value]
                newVal[idx] = { ...newVal[idx], operand: { type: 'restriction', property: '', cardinalityType: 'some', cardinality: 1, filler: '', value: '' } }
                onChange(newVal)
              }}>限制条件</button>
            </div>
          </div>
        </div>
      )
    }

    if (item.type === 'restriction') {
      return (
        <div key={idx} style={{ display: 'flex', flexDirection: 'column', gap: 4, padding: 8, background: 'var(--bg-subtle)', borderRadius: 6 }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <span style={{ color: 'var(--info)', fontWeight: 600 }}>Restriction:</span>
            <button className="btn btn-ghost btn-xs" onClick={() => removeItem(idx)}>✕</button>
          </div>
          <div style={{ paddingLeft: 16 }}>
            {renderRestrictionOperand(item, updates => updateItem(idx, updates))}
          </div>
        </div>
      )
    }

    return null
  }

  const formatExpression = (item) => {
    if (!item) return ''
    if (item.type === 'class') return item.class || '?'
    if (item.type === 'intersection') {
      const parts = (item.operands || []).map(o => formatExpression(o)).filter(Boolean)
      return parts.length > 1 ? `(${parts.join(' and ')})` : parts[0] || ''
    }
    if (item.type === 'union') {
      const parts = (item.operands || []).map(o => formatExpression(o)).filter(Boolean)
      return parts.length > 1 ? `(${parts.join(' or ')})` : parts[0] || ''
    }
    if (item.type === 'complement') {
      return `not (${formatExpression(item.operand)})`
    }
    if (item.type === 'restriction') {
      const prop = item.property || '?'
      const val = item.value || item.filler || '?'
      if (item.cardinalityType === 'value') return `(${prop} value ${val})`
      if (['min', 'max', 'exactly'].includes(item.cardinalityType)) return `(${prop} ${item.cardinalityType} ${item.cardinality || 1} ${val})`
      return `(${prop} ${item.cardinalityType || 'some'} ${val})`
    }
    return ''
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {value.map((item, idx) => (
        <div key={idx} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {renderExpression(item, idx)}
          {item.type !== 'class' && (
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontFamily: 'monospace', padding: '2px 8px', background: 'var(--bg-subtle)', borderRadius: 4 }}>
              ≡ {formatExpression(item)}
            </div>
          )}
        </div>
      ))}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button className="btn btn-outline btn-sm" onClick={addSimpleClass}>➕ 类</button>
        <button className="btn btn-outline btn-sm" onClick={addIntersection}>➕ and (交集)</button>
        <button className="btn btn-outline btn-sm" onClick={addUnion}>➕ or (并集)</button>
        <button className="btn btn-outline btn-sm" onClick={addComplement}>➕ not (补集)</button>
        <button className="btn btn-outline btn-sm" onClick={addRestriction}>➕ 限制条件</button>
      </div>
    </div>
  )
}

function TreeMultiSelect({ label, classes, value, onChange, excludeName }) {
  const [showDropdown, setShowDropdown] = useState(false)
  const [search, setSearch] = useState('')
  const [expandedNodes, setExpandedNodes] = useState({})
  const wrapperRef = useRef(null)
  const dropdownRef = useRef(null)
  const [dropdownStyle, setDropdownStyle] = useState({})

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (!wrapperRef.current || !dropdownRef.current) return
      
      const isOutsideWrapper = !wrapperRef.current.contains(event.target)
      const isOutsideDropdown = !dropdownRef.current.contains(event.target)
      
      if (isOutsideWrapper && isOutsideDropdown) {
        setShowDropdown(false)
        setSearch('')
      }
    }
    
    if (typeof document !== 'undefined') {
      document.addEventListener('mousedown', handleClickOutside)
      return () => {
        document.removeEventListener('mousedown', handleClickOutside)
      }
    }
  }, [])

  useEffect(() => {
    if (showDropdown && wrapperRef.current && typeof document !== 'undefined' && document.body) {
      const updatePosition = () => {
        const rect = wrapperRef.current.getBoundingClientRect()
        const viewportHeight = window.innerHeight
        const spaceBelow = viewportHeight - rect.bottom
        const spaceAbove = rect.top
        const dropdownHeight = 400 // 期望的最大高度
        
        // 如果下方空间不足，且上方空间比下方大，则在上方显示
        if (spaceBelow < dropdownHeight && spaceAbove > spaceBelow) {
          setDropdownStyle({
            position: 'fixed',
            top: 'auto',
            bottom: viewportHeight - rect.top + 4,
            left: rect.left,
            width: Math.max(rect.width, 320),
            maxHeight: Math.max(100, Math.min(dropdownHeight, spaceAbove - 16)) + 'px',
            zIndex: 10000,
          })
        } else {
          setDropdownStyle({
            position: 'fixed',
            top: rect.bottom + 4,
            bottom: 'auto',
            left: rect.left,
            width: Math.max(rect.width, 320),
            maxHeight: Math.max(100, Math.min(dropdownHeight, spaceBelow - 16)) + 'px',
            zIndex: 10000,
          })
        }
      }
      
      updatePosition()
      
      // 监听滚动事件来更新下拉框位置
      window.addEventListener('scroll', updatePosition, true)
      window.addEventListener('resize', updatePosition)
      
      return () => {
        window.removeEventListener('scroll', updatePosition, true)
        window.removeEventListener('resize', updatePosition)
      }
    }
  }, [showDropdown])

  const buildTree = () => {
    const classMap = {}
    const roots = []
    classes.forEach(cls => {
      classMap[cls.name] = { ...cls, children: [] }
    })
    classes.forEach(cls => {
      const node = classMap[cls.name]
      const parents = Array.isArray(cls.parents) ? cls.parents : (cls.parents ? [cls.parents] : [])
      // 不过滤 excludeName，保留完整树形结构
      const validParents = parents.filter(p => classMap[p])
      if (validParents.length === 0) {
        roots.push(node)
      } else {
        validParents.forEach(p => {
          if (classMap[p]) {
            classMap[p].children.push(node)
          }
        })
      }
    })
    return roots
  }

  const toggleNode = (name) => {
    setExpandedNodes(prev => ({ ...prev, [name]: !prev[name] }))
  }

  const selectedValues = Array.isArray(value) ? value : (value ? [value] : [])

  const isSelected = (name) => selectedValues.includes(name)

  const handleSelect = (name) => {
    if (name === excludeName) return // 不允许选择排除的类
    if (isSelected(name)) {
      // 取消选中
      onChange(selectedValues.filter(v => v !== name))
    } else {
      // 添加选中
      onChange([...selectedValues, name])
    }
    // 不关闭下拉框，保持打开状态
  }

  const handleClear = () => {
    onChange([])
  }

  const matchesSearch = (node) => {
    if (!search) return true
    const name = (node.label || node.name).toLowerCase()
    if (name.includes(search.toLowerCase())) return true
    return node.children.some(child => matchesSearch(child))
  }

  const renderTreeNode = (node, depth = 0) => {
    if (!matchesSearch(node)) return null
    const isExpanded = expandedNodes[node.name]
    const hasChildren = node.children && node.children.length > 0
    const selected = isSelected(node.name)
    const isExcluded = node.name === excludeName
    const visibleChildren = hasChildren ? node.children.filter(child => matchesSearch(child)) : []

    return (
      <div key={node.name}>
        <div
          className={`tree-select-item ${selected ? 'selected' : ''}`}
          style={{ 
            paddingLeft: `${depth * 16 + 8}px`,
            opacity: isExcluded ? 0.4 : 1,
            cursor: isExcluded ? 'not-allowed' : 'pointer'
          }}
          onClick={() => handleSelect(node.name)}
        >
          <span
            className="tree-select-toggle"
            onClick={(e) => {
              e.stopPropagation()
              if (hasChildren) toggleNode(node.name)
            }}
            style={{ cursor: hasChildren ? 'pointer' : 'default', minWidth: 16, userSelect: 'none' }}
          >
            {hasChildren ? (isExpanded ? '▾' : '▸') : '  '}
          </span>
          <span className="tree-select-radio" style={{ cursor: 'pointer', minWidth: 16, userSelect: 'none' }}>
            {isExcluded ? '⊘' : (selected ? '◉' : '○')}
          </span>
          <span className="tree-select-icon" style={{ userSelect: 'none', display: 'flex', alignItems: 'center' }}><Box size={12} /></span>
          <span className="tree-select-label" style={{ userSelect: 'none' }}>{node.label || node.name}</span>
          {node.name !== (node.label || node.name) && (
            <span className="tree-select-name" style={{ marginLeft: 4, opacity: 0.5, userSelect: 'none' }}>({node.name})</span>
          )}
        </div>
        {hasChildren && isExpanded && visibleChildren.map(child => renderTreeNode(child, depth + 1))}
      </div>
    )
  }

  const tree = buildTree()

  const dropdownContent = (
    <div 
      className="multi-select-dropdown tree-select-dropdown" 
      style={{
        background: '#1e1e2e',
        color: 'var(--text-primary)',
        border: '1px solid var(--border-color)',
        borderRadius: 'var(--radius-md)',
        boxShadow: '0 8px 32px rgba(0, 0, 0, 0.4)',
        height: 'auto',
        overflowY: 'auto',
        overflowX: 'hidden',
        padding: '4px',
        minWidth: '320px',
        zIndex: 99999,
        ...dropdownStyle,
      }} 
      ref={dropdownRef}
    >
      {tree.map(node => renderTreeNode(node))}
      {tree.length > 0 && tree.every(node => !matchesSearch(node)) && (
        <div className="multi-select-option" style={{ color: 'var(--text-muted)' }}>无匹配结果</div>
      )}
    </div>
  )

  const displayValues = selectedValues

  return (
    <div className="multi-select tree-multi-select" ref={wrapperRef}>
      {label && <label>{label}</label>}
      <div className="multi-select-tags">
        {displayValues.map(val => (
          <span key={val} className="multi-tag">
            {val}
            <button className="multi-tag-remove" onClick={() => {
              onChange(selectedValues.filter(v => v !== val))
            }}>×</button>
          </span>
        ))}
        <div className="multi-select-input-wrapper">
          <input
            className="form-input multi-select-input"
            placeholder={displayValues.length > 0 ? '' : '选择或搜索类...'}
            value={search}
            onChange={e => { setSearch(e.target.value); setShowDropdown(true) }}
            onFocus={() => setShowDropdown(true)}
          />
        </div>
      </div>
      {showDropdown && typeof document !== 'undefined' && document.body && createPortal(dropdownContent, document.body)}
    </div>
  )
}