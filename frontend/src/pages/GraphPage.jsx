import { useState, useEffect, useRef, useCallback } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import { Network, MousePointer2, RefreshCw, ArrowRight, ArrowLeft, X } from 'lucide-react'
import { api } from '../api'
import { useToast, useTheme } from '../App'

const LABEL_COLORS = [
  '#6366f1', '#ec4899', '#34d399', '#fbbf24', '#60a5fa',
  '#f87171', '#a78bfa', '#2dd4bf', '#fb923c', '#818cf8',
  '#f472b6', '#4ade80', '#facc15', '#38bdf8', '#e879f9',
]

export default function GraphPage() {
  const [graphData, setGraphData] = useState({ nodes: [], links: [] })
  const [loading, setLoading] = useState(false)
  const [labels, setLabels] = useState([])
  const [relTypes, setRelTypes] = useState([])
  const [filterLabel, setFilterLabel] = useState('')
  const [filterRel, setFilterRel] = useState('')
  const [limit, setLimit] = useState(200)
  const [graphScope, setGraphScope] = useState('data')
  const [labelDisplayMap, setLabelDisplayMap] = useState({})
  const [relDisplayMap, setRelDisplayMap] = useState({})
  const [selectedNode, setSelectedNode] = useState(null)
  const [labelColorMap, setLabelColorMap] = useState({})
  const [neighbors, setNeighbors] = useState([])
  const [ontologyInfo, setOntologyInfo] = useState(null)

  // 显示开关
  const [showNodeInfo, setShowNodeInfo] = useState(true)
  const [showRelLabels, setShowRelLabels] = useState(false)
  const [showConstraints, setShowConstraints] = useState(true)

  const graphRef = useRef()
  const addToast = useToast()
  const { theme } = useTheme()

  useEffect(() => {
    // 只有在业务图谱模式下才加载统计信息作为下拉默认值
    if (graphScope === 'data') {
      api.getGraphStats().then(stats => {
        setLabels(stats.labels || [])
        setRelTypes(stats.rel_types || [])
      }).catch(() => {})
    }
  }, [graphScope])

  const loadGraph = async () => {
    setLoading(true)
    setSelectedNode(null)
    setNeighbors([])
    setOntologyInfo(null)
    try {
      const data = await api.exploreGraph({
        label: filterLabel || undefined,
        rel_type: filterRel || undefined,
        limit,
        scope: graphScope,
      })
      const uniqueLabels = [...new Set(data.nodes.map(n => n.label))]
      const cmap = {}
      uniqueLabels.forEach((lbl, i) => { cmap[lbl] = LABEL_COLORS[i % LABEL_COLORS.length] })
      setLabelColorMap(cmap)
      setGraphData(data)
      setLabelDisplayMap(data.label_display || {})
      setRelDisplayMap(data.rel_display || {})
      
      // 如果后端返回了显式的选项（通常是根据当前范围筛选后的结果），则更新下拉
      if (data.label_options && data.label_options.length > 0) {
        setLabels(data.label_options.map(l => ({ label: l, count: '' })))
      }
      if (data.rel_options && data.rel_options.length > 0) {
        setRelTypes(data.rel_options.map(r => ({ type: r, count: '' })))
      }
      
      addToast(`已加载 ${data.total_nodes} 个节点, ${data.total_links} 条关系`, 'success')
    } catch (err) {
      addToast('图谱加载失败: ' + err.message, 'error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadGraph() }, [graphScope])

  const handleZoomFit = () => {
    if (graphRef.current) graphRef.current.zoomToFit(400, 40)
  }

  const handleNodeClick = useCallback(async (node) => {
    setSelectedNode(node)
    // 异步加载邻居和本体信息
    try {
      const [nbData, ontoData] = await Promise.all([
        api.getNodeNeighbors(node.id),
        api.getNodeOntologyInfo(node.id),
      ])
      setNeighbors(nbData.neighbors || [])
      setOntologyInfo(ontoData)
    } catch (e) {
      console.error('加载节点详情失败:', e)
    }
  }, [])

  const nodeCanvasObject = useCallback((node, ctx, globalScale) => {
    const label = node.name || labelDisplayMap[node.label] || node.label || node.id || ''
    const fontSize = Math.max(12 / globalScale, 4)
    const radius = 6

    const baseColor = labelColorMap[node.label] || '#6366f1'

    // Neon Halo
    ctx.shadowColor = baseColor
    ctx.shadowBlur = 10 / globalScale
    ctx.beginPath()
    ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI, false)
    ctx.fillStyle = baseColor
    ctx.fill()
    ctx.shadowBlur = 0

    // Selected highlight
    if (selectedNode && selectedNode.id === node.id) {
      ctx.strokeStyle = (theme === 'light' || theme === 'glass') ? '#000000' : '#ffffff'
      ctx.lineWidth = 3 / globalScale
      ctx.stroke()
      ctx.beginPath()
      ctx.arc(node.x, node.y, radius + 4, 0, 2 * Math.PI, false)
      ctx.strokeStyle = (theme === 'light' || theme === 'glass') ? `rgba(0, 0, 0, 0.4)` : `rgba(255, 255, 255, 0.4)`
      ctx.stroke()
    }

    // Texts - controlled by showNodeInfo toggle
    if (showNodeInfo && globalScale > 0.6) {
      ctx.font = `600 ${fontSize}px Inter, sans-serif`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'top'
      ctx.fillStyle = selectedNode && selectedNode.id === node.id 
        ? ((theme === 'light' || theme === 'glass') ? '#000000' : '#ffffff') 
        : ((theme === 'light' || theme === 'glass') ? 'rgba(15, 23, 42, 0.9)' : 'rgba(232,234,237,0.9)')
      ctx.fillText(label.slice(0, 15) + (label.length > 15 ? '...' : ''), node.x, node.y + radius + 4)
    }
  }, [labelColorMap, labelDisplayMap, selectedNode, showNodeInfo, theme])

  // Relationship label rendering
  const linkCanvasObjectMode = showRelLabels ? () => 'after' : undefined
  const linkCanvasObject = showRelLabels ? (link, ctx, globalScale) => {
    const fontSize = Math.max(10 / globalScale, 3)
    const midX = (link.source.x + link.target.x) / 2
    const midY = (link.source.y + link.target.y) / 2
    ctx.font = `${fontSize}px Inter, sans-serif`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillStyle = (theme === 'light' || theme === 'glass') ? 'rgba(0,0,0,0.5)' : 'rgba(255,255,255,0.5)'
    ctx.fillText(relDisplayMap[link.type] || link.type || '', midX, midY - 4)
  } : undefined

  return (
    <div className="graph-page">
      {/* 顶部工具栏 */}
      <div className="graph-toolbar">
        <h2 className="graph-toolbar-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}><Network size={20} /> 知识图谱浏览器</h2>
        <div className="graph-toolbar-actions">
          {/* 显示开关 */}
          <label className="toggle-label">
            <input type="checkbox" checked={showNodeInfo} onChange={e => setShowNodeInfo(e.target.checked)} />
            <span>节点名称</span>
          </label>
          <label className="toggle-label">
            <input type="checkbox" checked={showRelLabels} onChange={e => setShowRelLabels(e.target.checked)} />
            <span>关系注释</span>
          </label>
          <label className="toggle-label">
            <input type="checkbox" checked={showConstraints} onChange={e => setShowConstraints(e.target.checked)} />
            <span>本体约束</span>
          </label>
          <div style={{ width: 1, height: 24, background: 'var(--border-default)', margin: '0 4px' }} />
          <button className="btn btn-outline btn-sm" onClick={handleZoomFit} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <MousePointer2 size={14} /> 适合画布
          </button>
          <button className="btn btn-primary btn-sm" onClick={loadGraph} disabled={loading} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            {loading ? <RefreshCw size={14} className="spinning" /> : <RefreshCw size={14} />}
            {loading ? '加载中...' : '刷新图谱'}
          </button>
        </div>
      </div>

      <div className="graph-body">
        {/* 左侧筛选面板 */}
        <div className="graph-filter-panel">
          <div className="filter-section">
            <div className="filter-title">图谱范围</div>
            <select className="form-select" value={graphScope} onChange={e => {
              setGraphScope(e.target.value)
              setFilterLabel('')
              setFilterRel('')
            }}>
              <option value="data">业务图谱</option>
              <option value="ontology">本体图谱</option>
            </select>
          </div>

          <div className="filter-section">
            <div className="filter-title">节点标签筛选</div>
            <select className="form-select" value={filterLabel} onChange={e => setFilterLabel(e.target.value)}>
              <option value="">全部标签</option>
              {labels.map(l => <option key={l.label} value={l.label}>{labelDisplayMap[l.label] || l.label} {l.count ? `(${l.count})` : ''}</option>)}
            </select>
          </div>

          <div className="filter-section">
            <div className="filter-title">关系类型筛选</div>
            <select className="form-select" value={filterRel} onChange={e => setFilterRel(e.target.value)}>
              <option value="">全部关系</option>
              {relTypes.map(r => <option key={r.type} value={r.type}>{relDisplayMap[r.type] || r.type} {r.count ? `(${r.count})` : ''}</option>)}
            </select>
          </div>

          <div className="filter-section">
            <div className="filter-title">节点上限</div>
            <input
              type="range" min="10" max="1000" step="10"
              value={limit}
              onChange={e => setLimit(Number(e.target.value))}
              className="form-range"
            />
            <div className="filter-value">{limit} 个节点</div>
          </div>

          <button className="btn btn-primary btn-full btn-sm" onClick={loadGraph} disabled={loading}>
            应用筛选条件
          </button>

          {/* 图例 */}
          {Object.keys(labelColorMap).length > 0 && (
            <div className="filter-section">
              <div className="filter-title">图例</div>
              <div className="legend-list">
                {Object.entries(labelColorMap).map(([lbl, color]) => (
                  <div key={lbl} className="legend-item">
                    <span className="legend-dot" style={{ background: color }} />
                    <span>{labelDisplayMap[lbl] || lbl}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* 图谱画布 */}
        <div className="graph-canvas-wrapper">
          {loading ? (
            <div className="graph-loading">
              <div className="spinner spinner-lg" />
              <p>正在加载图谱数据...</p>
            </div>
          ) : (
            <ForceGraph2D
              ref={graphRef}
              graphData={graphData}
              nodeId="id"
              nodeCanvasObject={nodeCanvasObject}
              nodePointerAreaPaint={(node, color, ctx) => {
                ctx.beginPath()
                ctx.arc(node.x, node.y, 8, 0, 2 * Math.PI)
                ctx.fillStyle = color
                ctx.fill()
              }}
              linkColor={() => (theme === 'light' || theme === 'glass') ? 'rgba(0,0,0,0.12)' : 'rgba(255,255,255,0.12)'}
              linkWidth={1}
              linkDirectionalArrowLength={4}
              linkDirectionalArrowRelPos={1}
              linkCanvasObjectMode={linkCanvasObjectMode}
              linkCanvasObject={linkCanvasObject}
              onNodeClick={handleNodeClick}
              backgroundColor="transparent"
              cooldownTicks={100}
              warmupTicks={50}
            />
          )}
        </div>

        {/* 右侧详情抽屉 - 增强版 */}
        {selectedNode && (
          <div className="graph-detail-drawer">
            <div className="drawer-header">
              <div className="drawer-title">节点详情</div>
              <button className="btn btn-ghost btn-sm" onClick={() => { setSelectedNode(null); setNeighbors([]); setOntologyInfo(null) }}>✕</button>
            </div>
            <div className="drawer-body">
              <div className="detail-row">
                <span className="detail-key">标签</span>
                <span className="label-tag">{selectedNode.label}</span>
              </div>
              <div className="detail-row">
                <span className="detail-key">名称</span>
                <span className="detail-val">{selectedNode.name}</span>
              </div>
              <div className="detail-divider" />

              {/* 全部属性 */}
              <div className="detail-section-title">全部属性</div>
              {selectedNode.properties && Object.entries(selectedNode.properties).map(([k, v]) => (
                <div key={k} className="detail-row">
                  <span className="detail-key">{k}</span>
                  <span className="detail-val">{v}</span>
                </div>
              ))}

              {/* 关系列表（新增） */}
              {neighbors.length > 0 && (
                <>
                  <div className="detail-divider" />
                  <div className="detail-section-title">关联关系 ({neighbors.length})</div>
                  {neighbors.map((nb, i) => (
                    <div key={i} className="neighbor-item">
                      <span className="neighbor-direction">{nb.direction === 'outgoing' ? <ArrowRight size={12} /> : <ArrowLeft size={12} />}</span>
                      <span className="neighbor-rel">{relDisplayMap[nb.rel_type] || nb.rel_type}</span>
                      <span className="neighbor-target">{nb.name || nb.id || '?'}</span>
                      <span className="neighbor-label-badge">{labelDisplayMap[nb.labels?.[0]] || nb.labels?.[0] || '?'}</span>
                    </div>
                  ))}
                </>
              )}

              {/* 本体约束（新增） */}
              {showConstraints && ontologyInfo?.class_info?.length > 0 && (
                <>
                  <div className="detail-divider" />
                  <div className="detail-section-title">本体信息</div>
                  {ontologyInfo.class_info.map((ci, i) => (
                    <div key={i} className="ontology-class-info">
                      <div className="detail-row">
                        <span className="detail-key">类</span>
                        <span className="label-tag">{ci.class_name}</span>
                      </div>
                      {ci.comment && (
                        <div className="ontology-comment">{ci.comment}</div>
                      )}
                      {ci.parents?.length > 0 && (
                        <div className="detail-row">
                          <span className="detail-key">父类</span>
                          <span className="detail-val">{ci.parents.join(' → ')}</span>
                        </div>
                      )}
                    </div>
                  ))}
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
