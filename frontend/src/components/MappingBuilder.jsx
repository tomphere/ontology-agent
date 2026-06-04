import { useState, useEffect } from 'react'
import {
  ArrowRight,
  Box,
  Check,
  ChevronDown,
  ChevronRight,
  Database,
  FileText,
  GitBranch,
  Key,
  Link as LinkIcon,
  Pin,
  RefreshCw,
  Save,
  Trash2,
  Type,
} from 'lucide-react'
import { api } from '../api'

const TOP_ONTOLOGY_CLASSES = new Set(['Thing', 'Nothing', 'owl:Thing', 'owl:Nothing'])
const TOP_OBJECT_PROPERTIES = new Set(['topObjectProperty', 'owl:topObjectProperty'])
const TOP_DATA_PROPERTIES = new Set(['topDataProperty', 'owl:topDataProperty'])

function isBusinessOntologyClass(name) {
  return Boolean(name) && !TOP_ONTOLOGY_CLASSES.has(name)
}

function isBusinessObjectProperty(name) {
  return Boolean(name) && !TOP_OBJECT_PROPERTIES.has(name)
}

function isBusinessDataProperty(name) {
  return Boolean(name) && !TOP_DATA_PROPERTIES.has(name)
}

function getPropertyDomains(prop) {
  if (Array.isArray(prop.domains)) return prop.domains.filter(Boolean)
  if (Array.isArray(prop.domain)) return prop.domain.filter(Boolean)
  return prop.domain ? [prop.domain] : []
}

// =============================================================================
// 可视化映射构建器组件
// 支持三层映射：表→类、字段→数据属性、外键→对象属性(关系)
// 新增支持：关系映射模式（纯关系桥表，如转账、通话等）
// =============================================================================

export default function MappingBuilder({ sceneId, addToast, onYamlGenerated }) {
  // 数据状态
  const [datasources, setDatasources] = useState([])
  const [selectedDs, setSelectedDs] = useState(null)
  const [tables, setTables] = useState([])
  const [expandedTable, setExpandedTable] = useState(null)
  const [tableColumns, setTableColumns] = useState({})
  const [ontologyData, setOntologyData] = useState(null)

  // 映射状态 - 每张表一个映射配置
  const [tableMappings, setTableMappings] = useState([])
  // 每个 tableMapping:
  // {
  //   table, ontologyClass, primaryKey,
  //   classStrategy: 'static' | 'dynamic' | 'relationship',
  //   classStrategyColumn,
  //   fieldMappings: [{ column, ontologyProperty }],
  //   objectProperties: [{ foreignKeyColumn, targetLabel, ontologyProperty, direction }],
  //   vectorizeFields: [],
  //   // 关系映射模式专用字段
  //   relSourceColumn, relSourceClass, relTargetColumn, relTargetClass, relOntologyProperty,
  // }

  // UI 状态
  const [activeField, setActiveField] = useState(null)   // 左栏选中的字段
  const [mappingMode, setMappingMode] = useState('data')   // 'data' | 'object'
  const [saving, setSaving] = useState(false)
  const [restoredFromSave, setRestoredFromSave] = useState(false) // 是否已从后端恢复过
  // 搜索过滤
  const [searchLeft, setSearchLeft] = useState('')
  const [searchCenter, setSearchCenter] = useState('')
  const [searchRight, setSearchRight] = useState('')
  // 新增关系配置弹窗
  const [showRelDialog, setShowRelDialog] = useState(false)
  const [relForm, setRelForm] = useState({ foreignKeyColumn: '', targetLabel: '', ontologyProperty: '', direction: 'OUTGOING' })

  // 加载场景关联的数据源
  useEffect(() => {
    const load = async () => {
      try {
        const sceneData = await api.getScene(sceneId)
        const dsIds = sceneData.datasource_ids || []
        if (dsIds.length > 0) {
          const allDs = await api.listDatasources()
          const filtered = (allDs.datasources || []).filter(d => dsIds.includes(d.id))
          setDatasources(filtered)
          if (filtered.length > 0) setSelectedDs(filtered[0].id)
        }
      } catch (e) { /* ignore */ }
    }
    load()
  }, [sceneId])

  // 加载本体数据
  useEffect(() => {
    const load = async () => {
      try {
        const data = await api.parseSceneOntology(sceneId)
        setOntologyData(data)
      } catch (e) { /* 尚未上传本体文件 */ }
    }
    load()
  }, [sceneId])

  // ---- 从后端加载已保存的映射配置并还原为 tableMappings ----
  useEffect(() => {
    if (restoredFromSave) return
    const restoreSavedMapping = async () => {
      try {
        const data = await api.getSceneMapping(sceneId)
        if (!data.parsed || !data.parsed.mappings || data.parsed.mappings.length === 0) return
        const restored = data.parsed.mappings.map(m => {
          const tm = {
            table: m.table_name || '',
            ontologyClass: '',
            primaryKey: m.node_id_column || 'id',
            classStrategy: 'static',
            classStrategyColumn: '',
            fieldMappings: [],
            objectProperties: [],
            vectorizeFields: m.vectorize_fields || [],
            // 关系映射模式专用
            relSourceColumn: '', relSourceClass: '', relTargetColumn: '', relTargetClass: '', relOntologyProperty: '',
          }
          // 类映射策略
          const strategy = m.entity_class_strategy
          if (strategy) {
            if (strategy.type === 'dynamic_column') {
              tm.classStrategy = 'dynamic'
              tm.classStrategyColumn = strategy.column || ''
            } else if (strategy.type === 'relationship') {
              tm.classStrategy = 'relationship'
              tm.relSourceColumn = strategy.source_column || ''
              tm.relSourceClass = strategy.source_class || ''
              tm.relTargetColumn = strategy.target_column || ''
              tm.relTargetClass = strategy.target_class || ''
              tm.relOntologyProperty = strategy.ontology_property || ''
            } else {
              tm.classStrategy = 'static'
              tm.ontologyClass = strategy.class_name || ''
            }
          }
          // 数据属性映射
          if (m.data_properties) {
            tm.fieldMappings = m.data_properties.map(dp => ({
              column: dp.column,
              ontologyProperty: dp.ontology_property,
            }))
          }
          // 对象属性（关系）映射
          if (m.object_properties) {
            tm.objectProperties = m.object_properties.map(op => ({
              foreignKeyColumn: op.foreign_key_column,
              targetLabel: op.target_label,
              ontologyProperty: op.ontology_property,
              direction: op.direction || 'OUTGOING',
            }))
          }
          return tm
        })
        setTableMappings(restored)
      } catch (e) { /* 无已保存映射，忽略 */ }
      finally { setRestoredFromSave(true) }
    }
    restoreSavedMapping()
  }, [sceneId, restoredFromSave])

  // 选择数据源后加载表列表
  useEffect(() => {
    if (!selectedDs) return
    const load = async () => {
      try {
        const data = await api.getDatasourceTables(selectedDs)
        setTables(data.tables || [])
      } catch (e) { addToast('加载数据表失败: ' + e.message, 'error') }
    }
    load()
  }, [selectedDs])

  // 加载某张表的字段
  const loadColumns = async (table) => {
    if (tableColumns[table]) return
    try {
      const data = await api.getDatasourceColumns(selectedDs, table)
      setTableColumns(prev => ({ ...prev, [table]: data.columns || [] }))
    } catch (e) { addToast('加载字段失败', 'error') }
  }

  const toggleTable = (table) => {
    if (expandedTable === table) {
      setExpandedTable(null)
    } else {
      setExpandedTable(table)
      loadColumns(table)
    }
  }

  const getTableMapping = (table) => tableMappings.find(m => m.table === table)

  const ensureTableMapping = (table) => {
    let mapping = tableMappings.find(m => m.table === table)
    if (!mapping) {
      mapping = {
        table, ontologyClass: '', primaryKey: '', classStrategy: 'static',
        classStrategyColumn: '', fieldMappings: [], objectProperties: [], vectorizeFields: [],
        relSourceColumn: '', relSourceClass: '', relTargetColumn: '', relTargetClass: '', relOntologyProperty: '',
      }
      setTableMappings(prev => [...prev, mapping])
      return mapping
    }
    return mapping
  }

  // ---- 表 → 类映射 ----
  const handleClassClick = (className) => {
    if (!expandedTable) {
      addToast('请先在左侧展开一张数据表，再点击本体类进行映射', 'info')
      return
    }
    setTableMappings(prev => {
      const exists = prev.find(m => m.table === expandedTable)
      if (!exists) {
        return [...prev, {
          table: expandedTable, ontologyClass: className, primaryKey: '', classStrategy: 'static',
          classStrategyColumn: '', fieldMappings: [], objectProperties: [], vectorizeFields: [],
          relSourceColumn: '', relSourceClass: '', relTargetColumn: '', relTargetClass: '', relOntologyProperty: '',
        }]
      }
      return prev.map(m => m.table === expandedTable ? { ...m, ontologyClass: className } : m)
    })
    addToast(`表映射: ${expandedTable} → ${className}`, 'success')
  }

  // ---- 字段 → 数据属性映射 ----
  const handleFieldClick = (table, column) => {
    setActiveField({ table, column })
    setMappingMode('data')
  }

  const handleOntologyPropClick = (propName) => {
    if (!activeField) {
      addToast('请先点击左侧数据库字段，再点击右侧本体属性', 'info')
      return
    }
    const { table, column } = activeField
    setTableMappings(prev => {
      let updated = [...prev]
      let mapping = updated.find(m => m.table === table)
      if (!mapping) {
        mapping = {
          table, ontologyClass: '', primaryKey: '', classStrategy: 'static',
          classStrategyColumn: '', fieldMappings: [], objectProperties: [], vectorizeFields: [],
          relSourceColumn: '', relSourceClass: '', relTargetColumn: '', relTargetClass: '', relOntologyProperty: '',
        }
        updated.push(mapping)
      }
      const exists = mapping.fieldMappings.find(f => f.column === column && f.ontologyProperty === propName)
      if (!exists) {
        mapping.fieldMappings = [...mapping.fieldMappings, { column, ontologyProperty: propName }]
      }
      return updated.map(m => m.table === table ? { ...mapping } : m)
    })
    addToast(`字段映射: ${table}.${column} → ${propName}`, 'success')
    setActiveField(null)
  }

  // ---- 外键 → 对象属性（关系）映射 ----
  const handleFkClick = (table, column) => {
    ensureTableMapping(table)
    setRelForm({ foreignKeyColumn: column, targetLabel: '', ontologyProperty: '', direction: 'OUTGOING' })
    setShowRelDialog(true)
    setActiveField({ table, column })
  }

  const saveRelMapping = () => {
    if (!activeField || !relForm.targetLabel || !relForm.ontologyProperty) {
      addToast('请填写完整的关系映射配置', 'error')
      return
    }
    const { table } = activeField
    setTableMappings(prev => {
      let updated = [...prev]
      let mapping = updated.find(m => m.table === table)
      if (!mapping) {
        mapping = {
          table, ontologyClass: '', primaryKey: '', classStrategy: 'static',
          classStrategyColumn: '', fieldMappings: [], objectProperties: [], vectorizeFields: [],
          relSourceColumn: '', relSourceClass: '', relTargetColumn: '', relTargetClass: '', relOntologyProperty: '',
        }
        updated.push(mapping)
      }
      const exists = mapping.objectProperties.find(o => o.foreignKeyColumn === relForm.foreignKeyColumn)
      if (exists) {
        // 更新已有的
        mapping.objectProperties = mapping.objectProperties.map(o =>
          o.foreignKeyColumn === relForm.foreignKeyColumn ? { ...relForm } : o
        )
      } else {
        mapping.objectProperties = [...mapping.objectProperties, { ...relForm }]
      }
      return updated.map(m => m.table === table ? { ...mapping } : m)
    })
    addToast(`关系映射: ${table}.${relForm.foreignKeyColumn} → ${relForm.ontologyProperty} → ${relForm.targetLabel}`, 'success')
    setShowRelDialog(false)
    setActiveField(null)
  }

  // 删除映射
  const removeTableMapping = (table) => {
    setTableMappings(prev => prev.filter(m => m.table !== table))
  }

  const removeFieldMapping = (table, column, prop) => {
    setTableMappings(prev => prev.map(m => {
      if (m.table !== table) return m
      return { ...m, fieldMappings: m.fieldMappings.filter(f => !(f.column === column && f.ontologyProperty === prop)) }
    }))
  }

  const removeRelMapping = (table, fkColumn) => {
    setTableMappings(prev => prev.map(m => {
      if (m.table !== table) return m
      return { ...m, objectProperties: m.objectProperties.filter(o => o.foreignKeyColumn !== fkColumn) }
    }))
  }

  // 更新表级配置
  const updateTableConfig = (table, key, value) => {
    setTableMappings(prev => {
      const exists = prev.find(m => m.table === table)
      if (!exists) {
        return [...prev, {
          table, ontologyClass: '', primaryKey: '', classStrategy: 'static',
          classStrategyColumn: '', fieldMappings: [], objectProperties: [], vectorizeFields: [],
          relSourceColumn: '', relSourceClass: '', relTargetColumn: '', relTargetClass: '', relOntologyProperty: '',
          [key]: value,
        }]
      }
      return prev.map(m => m.table === table ? { ...m, [key]: value } : m)
    })
  }

  // 切换向量化
  const toggleVectorize = (table, column) => {
    setTableMappings(prev => prev.map(m => {
      if (m.table !== table) return m
      const vf = m.vectorizeFields || []
      return { ...m, vectorizeFields: vf.includes(column) ? vf.filter(f => f !== column) : [...vf, column] }
    }))
  }

  // 生成 YAML
  const generateYaml = () => {
    const mappings = tableMappings.filter(m =>
      m.ontologyClass || m.classStrategy === 'relationship' || m.fieldMappings.length > 0 || m.objectProperties.length > 0
    )
    if (mappings.length === 0) {
      addToast('暂无映射规则可保存', 'error')
      return null
    }
    let yaml = '# 自动生成的映射配置\nmappings:\n'
    for (const m of mappings) {
      yaml += `\n  - table_name: "${m.table}"\n`
      yaml += `    node_id_column: "${m.primaryKey || 'id'}"\n`

      if (m.classStrategy === 'relationship') {
        // 关系映射模式：纯关系边表
        yaml += `    entity_class_strategy:\n      type: "relationship"\n`
        yaml += `      source_column: "${m.relSourceColumn || ''}"\n`
        yaml += `      source_class: "${m.relSourceClass || ''}"\n`
        yaml += `      target_column: "${m.relTargetColumn || ''}"\n`
        yaml += `      target_class: "${m.relTargetClass || ''}"\n`
        yaml += `      ontology_property: "${m.relOntologyProperty || ''}"\n`
      } else if (m.classStrategy === 'dynamic' && m.classStrategyColumn) {
        yaml += `    entity_class_strategy:\n      type: "dynamic_column"\n      column: "${m.classStrategyColumn}"\n`
      } else {
        yaml += `    entity_class_strategy:\n      type: "static"\n      class_name: "${m.ontologyClass}"\n`
      }

      if (m.fieldMappings.length > 0) {
        yaml += '    data_properties:\n'
        for (const f of m.fieldMappings) {
          yaml += `      - column: "${f.column}"\n        ontology_property: "${f.ontologyProperty}"\n`
        }
      }
      if (m.vectorizeFields?.length > 0) {
        yaml += `    vectorize_fields: [${m.vectorizeFields.map(v => `"${v}"`).join(', ')}]\n`
      }
      if (m.objectProperties?.length > 0) {
        yaml += '    object_properties:\n'
        for (const op of m.objectProperties) {
          yaml += `      - foreign_key_column: "${op.foreignKeyColumn}"\n`
          yaml += `        target_label: "${op.targetLabel}"\n`
          yaml += `        ontology_property: "${op.ontologyProperty}"\n`
          yaml += `        direction: "${op.direction || 'OUTGOING'}"\n`
        }
      }
    }
    return yaml
  }

  const handleSave = async () => {
    const yaml = generateYaml()
    if (!yaml) return
    setSaving(true)
    try {
      await api.updateSceneMapping(sceneId, yaml)
      addToast('映射配置已保存', 'success')
      if (onYamlGenerated) onYamlGenerated(yaml)
    } catch (e) { addToast('保存失败: ' + e.message, 'error') }
    finally { setSaving(false) }
  }

  const totalDataMappings = tableMappings.reduce((sum, m) => sum + m.fieldMappings.length, 0)
  const totalRelMappings = tableMappings.reduce((sum, m) => sum + (m.objectProperties?.length || 0), 0)
  const totalTableMappings = tableMappings.filter(m => m.ontologyClass || m.classStrategy === 'relationship').length

  // 获取所有本体类名（供下拉选择）
  const businessClasses = (ontologyData?.classes || []).filter(c => isBusinessOntologyClass(c.name))
  const businessDataProperties = (ontologyData?.data_properties || []).filter(p => isBusinessDataProperty(p.name))
  const businessObjectProperties = (ontologyData?.object_properties || []).filter(p => isBusinessObjectProperty(p.name))
  const classParentMap = Object.fromEntries(businessClasses.map(c => [c.name, c.parents || []]))
  const classMatchesDomain = (className, domain) => {
    if (!className || !domain) return false
    if (className === domain) return true
    const seen = new Set()
    const stack = [...(classParentMap[className] || [])]
    while (stack.length) {
      const current = stack.pop()
      if (!current || seen.has(current)) continue
      if (current === domain) return true
      seen.add(current)
      stack.push(...(classParentMap[current] || []))
    }
    return false
  }
  const propertyAppliesToClass = (prop, className) => {
    const domains = getPropertyDomains(prop)
    return domains.length > 0 && domains.some(domain => classMatchesDomain(className, domain))
  }
  const commonDataProperties = businessDataProperties.filter(p => getPropertyDomains(p).length === 0)
  const commonObjectProperties = businessObjectProperties.filter(p => getPropertyDomains(p).length === 0)
  const allClassNames = businessClasses.map(c => c.name)
  // 获取所有对象属性名
  const allObjProps = businessObjectProperties.map(p => p.name)

  return (
    <div className="mapping-builder">
      {/* ========== 左栏 - 数据库浏览器 ========== */}
      <div className="mapping-source-panel">
        <div className="mapping-panel-header">
          <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}><Database size={16} /> 数据库</span>
          {datasources.length > 1 && (
            <select className="form-input" style={{ fontSize: 12, padding: '2px 6px' }}
              value={selectedDs || ''} onChange={e => setSelectedDs(e.target.value)}>
              {datasources.map(ds => (
                <option key={ds.id} value={ds.id}>{ds.label || ds.database}</option>
              ))}
            </select>
          )}
        </div>
        <div className="mapping-search-bar">
          <input className="mapping-search-input" placeholder="搜索表名或字段..."
            value={searchLeft} onChange={e => setSearchLeft(e.target.value)} />
          {searchLeft && <button className="mapping-search-clear" onClick={() => setSearchLeft('')}>✕</button>}
        </div>

        {datasources.length === 0 ? (
          <div className="mapping-empty">此场景尚未关联数据源<br/>请先在"数据源"标签页中关联</div>
        ) : tables.length === 0 ? (
          <div className="mapping-empty">正在加载数据表...</div>
        ) : (
          <div className="mapping-tree">
            {tables.filter(t => !searchLeft || t.toLowerCase().includes(searchLeft.toLowerCase())).map(table => {
              const mapping = getTableMapping(table)
              const isExpanded = expandedTable === table
              const isRelMode = mapping?.classStrategy === 'relationship'
              return (
                <div key={table} className="mapping-table-group">
                  <div className={`mapping-table-header ${isExpanded ? 'expanded' : ''} ${mapping?.ontologyClass || isRelMode ? 'has-mapping' : ''}`}
                    onClick={() => toggleTable(table)}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />} 
                      <FileText size={14} /> {table}
                    </span>
                    {mapping?.ontologyClass && !isRelMode && (
                      <span className="mapping-class-badge" style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                        <ArrowRight size={12} /> {mapping.ontologyClass}
                      </span>
                    )}
                    {isRelMode && (
                      <span className="mapping-class-badge" style={{ background: 'rgba(168,85,247,0.15)', color: '#a855f7' }}>⇌ 关系映射</span>
                    )}
                  </div>
                  {isExpanded && tableColumns[table] && (
                    <div className="mapping-field-list">
                      {/* 表级配置 */}
                      <div className="mapping-table-config">
                        <div className="mapping-config-row">
                          <label>主键字段</label>
                          <select className="form-input form-input-sm"
                            value={mapping?.primaryKey || ''}
                            onChange={e => updateTableConfig(table, 'primaryKey', e.target.value)}>
                            <option value="">请选择...</option>
                            {tableColumns[table].map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
                          </select>
                        </div>
                        <div className="mapping-config-row" style={{ marginTop: 6 }}>
                          <label>映射模式</label>
                          <select className="form-input form-input-sm"
                            value={mapping?.classStrategy || 'static'}
                            onChange={e => updateTableConfig(table, 'classStrategy', e.target.value)}>
                            <option value="static">静态映射（整表同一个类）</option>
                            <option value="dynamic">动态映射（按字段值决定类）</option>
                            <option value="relationship">关系映射（纯关系边表）</option>
                          </select>
                        </div>
                        {mapping?.classStrategy === 'dynamic' && (
                          <div className="mapping-config-row" style={{ marginTop: 6 }}>
                            <label>动态列</label>
                            <select className="form-input form-input-sm"
                              value={mapping?.classStrategyColumn || ''}
                              onChange={e => updateTableConfig(table, 'classStrategyColumn', e.target.value)}>
                              <option value="">请选择...</option>
                              {tableColumns[table].map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
                            </select>
                          </div>
                        )}
                        {/* ========== 关系映射模式专用配置 ========== */}
                        {mapping?.classStrategy === 'relationship' && (
                          <div className="mapping-rel-config">
                            <div className="mapping-rel-config-title">⇌ 关系飞线配置</div>
                            <div className="mapping-config-row" style={{ marginTop: 6 }}>
                              <label>起点列</label>
                              <select className="form-input form-input-sm"
                                value={mapping?.relSourceColumn || ''}
                                onChange={e => updateTableConfig(table, 'relSourceColumn', e.target.value)}>
                                <option value="">请选择源列...</option>
                                {tableColumns[table].map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
                              </select>
                            </div>
                            <div className="mapping-config-row" style={{ marginTop: 4 }}>
                              <label>起点类</label>
                              <select className="form-input form-input-sm"
                                value={mapping?.relSourceClass || ''}
                                onChange={e => updateTableConfig(table, 'relSourceClass', e.target.value)}>
                                <option value="">请选择本体类...</option>
                                {allClassNames.map(c => <option key={c} value={c}>{c}</option>)}
                              </select>
                            </div>
                            <div className="mapping-config-row" style={{ marginTop: 6 }}>
                              <label>终点列</label>
                              <select className="form-input form-input-sm"
                                value={mapping?.relTargetColumn || ''}
                                onChange={e => updateTableConfig(table, 'relTargetColumn', e.target.value)}>
                                <option value="">请选择目标列...</option>
                                {tableColumns[table].map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
                              </select>
                            </div>
                            <div className="mapping-config-row" style={{ marginTop: 4 }}>
                              <label>终点类</label>
                              <select className="form-input form-input-sm"
                                value={mapping?.relTargetClass || ''}
                                onChange={e => updateTableConfig(table, 'relTargetClass', e.target.value)}>
                                <option value="">请选择本体类...</option>
                                {allClassNames.map(c => <option key={c} value={c}>{c}</option>)}
                              </select>
                            </div>
                            <div className="mapping-config-row" style={{ marginTop: 6 }}>
                              <label>对象属性</label>
                              <select className="form-input form-input-sm"
                                value={mapping?.relOntologyProperty || ''}
                                onChange={e => updateTableConfig(table, 'relOntologyProperty', e.target.value)}>
                                <option value="">请选择对象属性...</option>
                                {allObjProps.map(p => <option key={p} value={p}>{p}</option>)}
                              </select>
                            </div>
                          </div>
                        )}
                      </div>
                      {/* 字段列表 */}
                      {tableColumns[table].filter(c => !searchLeft || c.name.toLowerCase().includes(searchLeft.toLowerCase()) || table.toLowerCase().includes(searchLeft.toLowerCase())).map(col => {
                        const isActive = activeField?.table === table && activeField?.column === col.name
                        const isMapped = mapping?.fieldMappings?.some(f => f.column === col.name)
                        const hasRel = mapping?.objectProperties?.some(o => o.foreignKeyColumn === col.name)
                        const isVector = mapping?.vectorizeFields?.includes(col.name)
                        const isPri = col.key === 'PRI'
                        return (
                          <div key={col.name}
                            className={`mapping-field-item ${isActive ? 'active' : ''} ${isMapped ? 'mapped' : ''} ${hasRel ? 'mapped' : ''}`}>
                            <div className="mapping-field-name"
                              onClick={() => handleFieldClick(table, col.name)}
                              title="点击后再点击右侧属性进行数据属性映射"
                              style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                              {isPri && <Key size={12} title="主键" />}
                              {col.name}
                            </div>
                            <div className="mapping-field-meta">
                              <span className="mapping-type-badge">{col.type?.split('(')[0]}</span>
                              {/* 所有非主键字段均可配置关系映射 */}
                              {!isPri && (
                                <button className={`mapping-rel-btn ${hasRel ? 'active' : ''}`}
                                  onClick={e => { e.stopPropagation(); handleFkClick(table, col.name) }}
                                  title="配置关系映射（对象属性）">
                                  <LinkIcon size={12} />
                                </button>
                              )}
                              <button className={`mapping-vectorize-btn ${isVector ? 'active' : ''}`}
                                onClick={e => { e.stopPropagation(); toggleVectorize(table, col.name) }}
                                title={isVector ? '取消向量化' : '启用向量化'}>
                                <Type size={12} />
                              </button>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* ========== 中栏 - 映射规则汇总 ========== */}
      <div className="mapping-link-panel">
        <div className="mapping-panel-header">
          <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}><LinkIcon size={16} /> 映射规则</span>
          <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
            表:{totalTableMappings} 属性:{totalDataMappings} 关系:{totalRelMappings}
          </span>
        </div>
        <div className="mapping-search-bar">
          <input className="mapping-search-input" placeholder="搜索映射..."
            value={searchCenter} onChange={e => setSearchCenter(e.target.value)} />
          {searchCenter && <button className="mapping-search-clear" onClick={() => setSearchCenter('')}>✕</button>}
        </div>

        {activeField && (
          <div className="mapping-active-hint">
            请点击右侧本体属性，映射 <strong>{activeField.table}.{activeField.column}</strong>
          </div>
        )}

        {tableMappings.length === 0 ? (
          <div className="mapping-empty">
            <div style={{ marginBottom: 8, display: 'flex', justifyContent: 'center' }}><LinkIcon size={32} /></div>
            <div>
              <p><strong>操作说明:</strong></p>
              <p>1. 展开左侧表 → 点击右侧类 = 表映射</p>
              <p>2. 点击左侧字段 → 点击右侧属性 = 数据属性映射</p>
              <p>3. 点击字段旁按钮 = 关系映射</p>
              <p>4. 切换"关系映射"模式 = 纯关系边表</p>
            </div>
          </div>
        ) : (
          <div className="mapping-links-list">
            {tableMappings.filter(m => !searchCenter || m.table.toLowerCase().includes(searchCenter.toLowerCase()) || m.ontologyClass?.toLowerCase().includes(searchCenter.toLowerCase()) || m.fieldMappings.some(f => f.column.toLowerCase().includes(searchCenter.toLowerCase()) || f.ontologyProperty.toLowerCase().includes(searchCenter.toLowerCase()))).map(m => (
              <div key={m.table} className="mapping-link-group" style={{ 
                background: 'var(--bg-elevated)', 
                borderRadius: '12px', 
                padding: '16px', 
                marginBottom: '20px', 
                border: '1px solid var(--border-subtle)', 
                boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)' 
              }}>
                {/* 表→类映射 */}
                {m.classStrategy === 'relationship' ? (
                  <div className="mapping-link-group-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: '#a855f7', fontSize: '1rem', borderBottom: '1px solid rgba(168,85,247,0.2)', paddingBottom: '12px', marginBottom: '16px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <FileText size={18} />
                      {m.table} 
                      <span style={{ margin: '0 4px', opacity: 0.6 }}>⇌</span>
                      关系边表映射
                      {m.relOntologyProperty && (
                        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', background: 'rgba(168,85,247,0.05)', padding: '6px 12px', borderRadius: 6, display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                          {m.relSourceClass} <ArrowRight size={10} />[{m.relOntologyProperty}] <ArrowRight size={10} /> {m.relTargetClass}
                        </div>
                      )}
                    </div>
                    <button className="btn btn-ghost btn-sm" style={{ color: 'var(--error)' }} onClick={() => removeTableMapping(m.table)} title={`移除 ${m.table} 的所有映射`}>
                      <Trash2 size={18} />
                    </button>
                  </div>
                ) : (
                  <div className="mapping-link-group-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '1rem', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '12px', marginBottom: '16px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <FileText size={18} />
                      <span style={{ fontWeight: 600 }}>{m.table}</span>
                      <span style={{ color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 6 }}>映射至 <ArrowRight size={14} /></span>
                      <Box size={18} />
                      {m.classStrategy === 'dynamic' ? (
                        <>
                          <span style={{ color: 'var(--warning)', fontWeight: 600 }}>[ 动态决定实体类型 ]</span>
                          <span style={{ fontSize: '0.8rem', color: 'var(--text-primary)', marginLeft: 4, background: 'rgba(245, 158, 11, 0.1)', border: '1px solid rgba(245, 158, 11, 0.3)', padding: '2px 8px', borderRadius: 6, display: 'inline-flex', alignItems: 'center' }}>
                            依据字段: <span style={{ fontWeight: 600, color: 'var(--warning)', marginLeft: 6 }}>{m.classStrategyColumn}</span>
                          </span>
                        </>
                      ) : (
                        <span style={{ color: m.ontologyClass ? 'var(--primary)' : 'var(--text-muted)', fontWeight: 600 }}>{m.ontologyClass || '(未配置实体映射)'}</span>
                      )}
                    </div>
                    <button className="btn btn-ghost btn-sm" style={{ color: 'var(--error)' }} onClick={() => removeTableMapping(m.table)} title={`移除 ${m.table} 的所有映射`}>
                      <Trash2 size={18} />
                    </button>
                  </div>
                )}

                {/* 关系映射模式的飞线可视化 */}
                {m.classStrategy === 'relationship' && m.relSourceColumn && m.relTargetColumn && (
                  <div className="mapping-link-card" style={{ borderColor: 'rgba(168, 85, 247, 0.3)', background: 'rgba(168, 85, 247, 0.05)' }}>
                    <div className="mapping-link-content">
                      <span className="mapping-link-source">{m.relSourceColumn}</span>
                      <span className="mapping-link-arrow">→</span>
                      <span style={{ color: 'var(--text-muted)', fontSize: '0.72rem' }}>{m.relSourceClass}</span>
                      <span style={{ color: '#a855f7', fontFamily: 'var(--font-mono)', fontSize: '0.78rem', margin: '0 4px' }}>
                        —[{m.relOntologyProperty || '?'}]→
                      </span>
                      <span style={{ color: 'var(--text-muted)', fontSize: '0.72rem' }}>{m.relTargetClass}</span>
                      <span className="mapping-link-arrow">←</span>
                      <span className="mapping-link-target">{m.relTargetColumn}</span>
                    </div>
                  </div>
                )}

                {/* 数据属性映射 */}
                {m.fieldMappings.length > 0 && (
                  <div style={{ marginLeft: 8, paddingLeft: 16, borderLeft: '2px solid rgba(255,255,255,0.08)', marginTop: 16 }}>
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-primary)', padding: '4px 0', display: 'flex', alignItems: 'center', marginBottom: 12 }}>
                      <span style={{ background: 'rgba(255,255,255,0.1)', padding: '4px 8px', borderRadius: 6, marginRight: 8, fontWeight: 600 }}>🔸 数据属性 (实体字段)</span>
                    </div>
                    {m.fieldMappings.map((f, i) => (
                      <div key={i} style={{ display: 'flex', alignItems: 'stretch', background: 'var(--bg)', borderRadius: 8, overflow: 'hidden', border: '1px solid var(--border-subtle)', marginBottom: 8 }}>
                        {/* Source Side */}
                        <div style={{ flex: 1, padding: '10px 16px', background: 'var(--bg-elevated)', borderRight: '1px dashed var(--border-subtle)' }}>
                          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: 4, fontWeight: 600, letterSpacing: '0.5px' }}>SOURCE TABLE</div>
                          <div style={{ fontSize: '0.9rem', color: 'var(--text-primary)', display: 'flex', alignItems: 'center' }}>
                            <span style={{opacity: 0.6, marginRight: 4}}>{m.table}.</span>
                            <span style={{color: 'var(--info)', fontWeight: 600}}>{f.column}</span>
                          </div>
                        </div>

                        {/* Arrow */}
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0 20px', background: 'var(--bg-secondary)', color: 'var(--text-muted)' }}>
                          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14"></path><path d="m12 5 7 7-7 7"></path></svg>
                        </div>

                        {/* Target Side */}
                        <div style={{ flex: '1.2', padding: '10px 16px', background: 'rgba(16, 185, 129, 0.05)', borderLeft: '1px dashed var(--border-subtle)' }}>
                          <div style={{ fontSize: '0.7rem', color: 'var(--success)', marginBottom: 4, fontWeight: 600, letterSpacing: '0.5px', opacity: 0.8 }}>GLOBAL ONTOLOGY</div>
                          <div style={{ fontSize: '0.9rem', color: 'var(--text-primary)', display: 'flex', alignItems: 'center' }}>
                            <span style={{opacity: 0.6, marginRight: 4}}>
                              {m.classStrategy === 'relationship' ? `[${m.relOntologyProperty || '?'}]` 
                                : m.classStrategy === 'dynamic' ? `<动态实体>` 
                                : (m.ontologyClass || '?')}.
                            </span>
                            <span style={{color: 'var(--success)', fontWeight: 600}}>{f.ontologyProperty}</span>
                          </div>
                        </div>

                        {/* Actions */}
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0 12px', borderLeft: '1px solid var(--border-subtle)' }}>
                           <button className="btn btn-ghost btn-sm" style={{ color: 'var(--error)' }} onClick={() => removeFieldMapping(m.table, f.column, f.ontologyProperty)}>
                             <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"></path><path d="m6 6 12 12"></path></svg>
                           </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* 对象属性（关系）映射 */}
                {m.objectProperties?.length > 0 && (
                  <div style={{ marginLeft: 8, paddingLeft: 16, borderLeft: '2px solid rgba(168, 85, 247, 0.4)', marginTop: 16 }}>
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-primary)', padding: '4px 0', display: 'flex', alignItems: 'center', marginBottom: 12 }}>
                      <span style={{ background: 'rgba(168, 85, 247, 0.15)', color: '#a855f7', padding: '4px 8px', borderRadius: 6, marginRight: 8, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}><LinkIcon size={14} /> 对象关系 (实体与实体间的连接)</span>
                    </div>
                    {m.objectProperties.map((op, i) => (
                      <div key={i} style={{ display: 'flex', alignItems: 'stretch', background: 'var(--bg)', borderRadius: 8, overflow: 'hidden', border: '1px solid rgba(168, 85, 247, 0.4)', marginBottom: 8 }}>
                        {/* FK Side */}
                        <div style={{ flex: 1, padding: '10px 16px', background: 'rgba(168, 85, 247, 0.05)', borderRight: '1px dashed rgba(168, 85, 247, 0.3)' }}>
                          <div style={{ fontSize: '0.7rem', color: '#a855f7', marginBottom: 4, fontWeight: 600, opacity: 0.8, letterSpacing: '0.5px' }}>FOREIGN KEY (SOURCE)</div>
                          <div style={{ fontSize: '0.9rem', color: 'var(--text-primary)', display: 'flex', alignItems: 'center' }}>
                            <span style={{opacity: 0.6, marginRight: 4}}>{m.table}.</span>
                            <span style={{color: '#a855f7', fontWeight: 600}}>{op.foreignKeyColumn}</span>
                          </div>
                        </div>

                        {/* Arrow */}
                        <div style={{ display: 'flex', alignItems: 'center', flexDirection: 'column', justifyContent: 'center', padding: '0 16px', background: 'rgba(168, 85, 247, 0.1)', color: '#a855f7', textAlign: 'center', minWidth: '120px' }}>
                           <div style={{ fontSize: '0.7rem', fontWeight: 700, marginBottom: 2 }}>{op.ontologyProperty}</div>
                           <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ transform: op.direction==='INCOMING' ? 'rotate(180deg)' : 'none' }}><path d="M5 12h14"></path><path d="m12 5 7 7-7 7"></path></svg>
                        </div>

                        {/* Target Entity Side */}
                        <div style={{ flex: '1.2', padding: '10px 16px', background: 'var(--bg-elevated)', borderLeft: '1px dashed rgba(168, 85, 247, 0.3)' }}>
                          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: 4, fontWeight: 600, letterSpacing: '0.5px' }}>TARGET ENTITY</div>
                          <div style={{ fontSize: '0.9rem', color: 'var(--text-primary)', fontWeight: 600, display: 'flex', alignItems: 'center'}}>
                            <span style={{opacity: 0.8}}>{op.targetLabel}</span>
                          </div>
                        </div>
                        
                        {/* Actions */}
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0 12px', borderLeft: '1px solid rgba(168, 85, 247, 0.3)', background: 'rgba(168, 85, 247, 0.05)' }}>
                           <button className="btn btn-ghost btn-sm" style={{ color: 'var(--error)' }} onClick={() => removeRelMapping(m.table, op.foreignKeyColumn)}>
                             <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"></path><path d="m6 6 12 12"></path></svg>
                           </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* 向量化字段 */}
                {m.vectorizeFields?.length > 0 && (
                  <div style={{ fontSize: '0.72rem', color: 'var(--info)', padding: '4px 8px', marginTop: 4 }}>
                    🔤 向量化: {m.vectorizeFields.join(', ')}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* 底部工具栏 */}
        <div className="mapping-toolbar">
          <button className="btn btn-success btn-sm" onClick={handleSave} disabled={saving} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            {saving ? <RefreshCw size={14} className="spinning" /> : <Save size={14} />}
            {saving ? '保存中...' : '保存映射'}
          </button>
          <button className="btn btn-outline btn-sm" onClick={() => {
            const yaml = generateYaml()
            if (yaml) { alert(yaml) }
          }} style={{ display: 'flex', alignItems: 'center', gap: 4 }}><FileText size={14} /> 查看YAML</button>
        </div>
      </div>

      {/* ========== 右栏 - 本体浏览器 ========== */}
      <div className="mapping-target-panel">
        <div className="mapping-panel-header">
          <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}><GitBranch size={16} /> 本体结构</span>
        </div>
        <div className="mapping-search-bar">
          <input className="mapping-search-input" placeholder="搜索类或属性..."
            value={searchRight} onChange={e => setSearchRight(e.target.value)} />
          {searchRight && <button className="mapping-search-clear" onClick={() => setSearchRight('')}>✕</button>}
        </div>

        {/* 自定义属性入口 */}
        <div style={{ padding: '10px 12px', background: 'rgba(56, 189, 248, 0.05)', borderBottom: '1px dashed var(--border-subtle)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>本体未定义的边属性/字段？</span>
          <button className="btn btn-outline btn-sm" style={{ padding: '4px 10px', fontSize: '0.75rem' }} onClick={() => {
            if (!activeField) {
              addToast('请先在左侧点击选中一个要映射的字段 👈', 'info')
              return
            }
            const p = prompt(`正在为 [${activeField.table}.${activeField.column}] 映射...\n请输入自定义的本体属性名称（如 amount）：`)
            if (p && p.trim()) {
              handleOntologyPropClick(p.trim())
            }
          }}>+ 手动录入</button>
        </div>

        {!ontologyData ? (
          <div className="mapping-empty">此场景尚未加载本体文件</div>
        ) : (
          <div className="mapping-tree">
            {(commonDataProperties.length > 0 || commonObjectProperties.length > 0) && (
              <div className="mapping-onto-group">
                <div className="mapping-onto-class" title="未设置 Domain 的通用属性，不重复挂到每个类下面" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Pin size={14} /> 通用属性
                  <span className="mapping-onto-label">未限定 Domain</span>
                </div>
                {commonDataProperties.map(p => (
                  <div key={p.name} className="mapping-onto-prop data"
                    onClick={() => handleOntologyPropClick(p.name)}
                    title="点击映射选中的数据库字段到此通用数据属性"
                    style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <FileText size={12} /> {p.name}
                    <span className="mapping-type-badge">{p.range || 'string'}</span>
                  </div>
                ))}
                {commonObjectProperties.map(p => (
                  <div key={p.name} className="mapping-onto-prop object"
                    title={`通用对象属性: ${p.range ? '→ ' + p.range : '未限定'}`}
                    style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <LinkIcon size={12} /> {p.name}
                    <span className="mapping-type-badge">→ {p.range || '?'}</span>
                  </div>
                ))}
              </div>
            )}
            {businessClasses.filter(cls => !searchRight || cls.name.toLowerCase().includes(searchRight.toLowerCase()) || cls.label?.toLowerCase().includes(searchRight.toLowerCase())).map(cls => (
              <div key={cls.name} className="mapping-onto-group">
                <div className="mapping-onto-class" onClick={() => handleClassClick(cls.name)}
                  title="点击将当前展开的表映射到此类"
                  style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Box size={14} /> {cls.name}
                  {cls.label !== cls.name && <span className="mapping-onto-label">{cls.label}</span>}
                </div>
                {/* 该类的数据属性 */}
                {businessDataProperties
                  ?.filter(p => propertyAppliesToClass(p, cls.name))
                  .map(p => (
                    <div key={p.name} className="mapping-onto-prop data"
                      onClick={() => handleOntologyPropClick(p.name)}
                      title="点击映射选中的数据库字段到此数据属性"
                      style={{ display: 'flex', alignItems: 'center', gap: 6, paddingLeft: 24 }}>
                      <FileText size={12} /> {p.name}
                      <span className="mapping-type-badge">{p.range || 'string'}</span>
                    </div>
                  ))
                }
                {/* 该类的对象属性 */}
                {businessObjectProperties
                  ?.filter(p => propertyAppliesToClass(p, cls.name))
                  .map(p => (
                    <div key={p.name} className="mapping-onto-prop object"
                      title={`对象属性: ${p.domain || '?'} → ${p.range || '?'}`}
                      style={{ display: 'flex', alignItems: 'center', gap: 6, paddingLeft: 24 }}>
                      <LinkIcon size={12} /> {p.name}
                      <span className="mapping-type-badge">→ {p.range || '?'}</span>
                    </div>
                  ))
                }
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ========== 关系映射配置弹窗 ========== */}
      {showRelDialog && (
        <div className="modal-overlay" onClick={() => setShowRelDialog(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <span className="card-title">🔗 配置关系映射（对象属性）</span>
              <button className="btn btn-ghost btn-sm" onClick={() => setShowRelDialog(false)}>✕</button>
            </div>
            <div className="ds-form" style={{ padding: 16 }}>
              <div className="ds-form-row">
                <label>关联字段</label>
                <input className="form-input" value={relForm.foreignKeyColumn} disabled />
              </div>
              <div className="ds-form-row">
                <label>目标本体类 *</label>
                <select className="form-input" value={relForm.targetLabel}
                  onChange={e => setRelForm(p => ({ ...p, targetLabel: e.target.value }))}>
                  <option value="">请选择目标类...</option>
                  {allClassNames.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div className="ds-form-row">
                <label>对象属性名 *</label>
                <select className="form-input" value={relForm.ontologyProperty}
                  onChange={e => setRelForm(p => ({ ...p, ontologyProperty: e.target.value }))}>
                  <option value="">请选择对象属性...</option>
                  {allObjProps.map(p => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
              <div className="ds-form-row">
                <label>关系方向</label>
                <div style={{ display: 'flex', gap: 16 }}>
                  <label className="radio-label">
                    <input type="radio" checked={relForm.direction === 'OUTGOING'}
                      onChange={() => setRelForm(p => ({ ...p, direction: 'OUTGOING' }))} />
                    <span>OUTGOING (当前表 → 目标)</span>
                  </label>
                  <label className="radio-label">
                    <input type="radio" checked={relForm.direction === 'INCOMING'}
                      onChange={() => setRelForm(p => ({ ...p, direction: 'INCOMING' }))} />
                    <span>INCOMING (目标 → 当前表)</span>
                  </label>
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                <button className="btn btn-success" onClick={saveRelMapping} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <Check size={16} /> 确认
                </button>
                <button className="btn btn-outline" onClick={() => setShowRelDialog(false)}>取消</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
