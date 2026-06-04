import { useState, useEffect, useRef } from 'react'
import { 
  Send, Brain, Plus, Download, Trash2, ChevronRight, ChevronDown, 
  Wrench, BarChart2, Paperclip, XCircle, CheckCircle2, Hourglass,
  MessageSquare, Check
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api } from '../api'
import { useToast } from '../App'

// 辅助函数：格式化思考步骤的值
function stringifyStepValue(value) {
  if (typeof value === 'object' && value !== null) {
    const parts = []
    if (value.tool) parts.push(`工具: ${value.tool}`)
    if (value.input) parts.push(`输入: ${stringifyStepValue(value.input)}`)
    if (value.content) parts.push(`内容: ${stringifyStepValue(value.content)}`)
    return parts.length ? parts.join('；') : JSON.stringify(value, null, 2)
  }
  return String(value)
}

function stepKey(step) {
  return JSON.stringify({
    type: step?.type,
    tool: step?.tool,
    input: step?.input,
    content: step?.content,
  })
}

function appendUniqueStep(steps, event) {
  const key = stepKey(event)
  if (steps.some(step => stepKey(step) === key)) return steps
  return [...steps, event]
}

function formatDuration(ms) {
  if (ms === undefined || ms === null || Number.isNaN(Number(ms))) return ''
  const value = Number(ms)
  if (value < 1000) return `${value}ms`
  if (value < 60000) return `${(value / 1000).toFixed(value < 10000 ? 1 : 0)}s`
  const minutes = Math.floor(value / 60000)
  const seconds = Math.round((value % 60000) / 1000)
  return `${minutes}m ${seconds}s`
}

// 思考链步骤组件（带加载动画）
function ThoughtStep({ step, isActive, isLast }) {
  const [open, setOpen] = useState(isActive || isLast)

  const iconMap = {
    status: <Brain size={14} />,
    tool_call: <Wrench size={14} />,
    tool_result: <BarChart2 size={14} />,
    evidence: <Paperclip size={14} />,
    error: <XCircle size={14} />,
  }

  const titleMap = {
    status: '智能体状态',
    tool_call: `调用工具: ${step.tool}`,
    tool_result: `工具执行结果: ${step.tool}`,
    evidence: '结构化证据',
    error: '执行错误',
  }

  const durationText = step.duration_ms !== undefined ? `耗时 ${formatDuration(step.duration_ms)}` : ''
  const elapsedText = step.elapsed_ms !== undefined ? `T+${formatDuration(step.elapsed_ms)}` : ''
  const timingText = [durationText, elapsedText].filter(Boolean).join(' · ')

  return (
    <div className={`thought-step ${step.type === 'error' ? 'error' : ''}`}>
      <div className="thought-step-header" onClick={() => setOpen(!open)}>
        <span className="step-icon">
          {isActive ? <Hourglass size={14} className="spinning" /> : (iconMap[step.type] || <Brain size={14} />)}
        </span>
        <span className="step-title">{titleMap[step.type] || step.type}</span>
        {timingText && <span className="step-timing">{timingText}</span>}
        <span className="step-arrow">{open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}</span>
      </div>
      {open && (
        <div className="thought-step-body">
          {step.input && (
            <div className="step-detail">
              <div className="step-detail-label">参数</div>
              <code>{step.input}</code>
            </div>
          )}
          {step.content && (
            <div className="step-detail">
              <div className="step-detail-label">{step.type === 'tool_result' ? '过程与结果' : '内容'}</div>
              <pre>{step.content}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function AnswerMetrics({ metrics }) {
  if (!metrics) return null
  const totalText = formatDuration(metrics.total_ms)
  const agentText = formatDuration(metrics.agent_ms)
  const stepCount = metrics.step_count
  if (!totalText && !agentText && stepCount === undefined) return null

  return (
    <div className="answer-metrics">
      {totalText && <span>总耗时：{totalText}</span>}
      {agentText && <span>Agent：{agentText}</span>}
      {stepCount !== undefined && <span>步骤：{stepCount}</span>}
    </div>
  )
}

function StepGroup({ steps, isStreaming }) {
  const [expanded, setExpanded] = useState(isStreaming)

  useEffect(() => {
    setExpanded(isStreaming)
  }, [isStreaming])

  if (!steps || steps.length === 0) return null

  return (
    <div className="step-group">
      <div className="step-group-header" onClick={() => setExpanded(!expanded)}>
        <span className="step-group-icon">{isStreaming ? <Hourglass size={14} className="spinning" /> : <CheckCircle2 size={14} />}</span>
        <span className="step-group-title">
          {isStreaming ? '正在执行...' : `${steps.length} 个推理步骤`}
        </span>
        <span className="step-group-toggle">{expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}</span>
      </div>
      {expanded && (
        <div className="step-group-content">
          {steps.map((step, i) => (
            <ThoughtStep 
              key={i} 
              step={step} 
              isActive={isStreaming && i === steps.length - 1}
              isLast={i === steps.length - 1} 
            />
          ))}
        </div>
      )}
    </div>
  )
}

function ResultArtifact({ artifact }) {
  if (!artifact) return null
  const { type, data, rows, columns, title } = artifact

  if (type === 'table') {
    const safeColumns = Array.isArray(columns) ? columns : []
    const safeData = Array.isArray(data) ? data : (Array.isArray(rows) ? rows : [])

    if (safeColumns.length === 0 || safeData.length === 0) return null

    return (
      <div className="result-artifact artifact-table">
        {title && <div className="artifact-title">{title}</div>}
        <div className="table-container">
          <table>
            <thead>
              <tr>{safeColumns.map(c => <th key={c}>{c}</th>)}</tr>
            </thead>
            <tbody>
              {safeData.map((row, i) => (
                <tr key={i}>{safeColumns.map(c => <td key={c}>{row[c]}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    )
  }

  if (type === 'chart') {
    return (
      <div className="result-artifact artifact-chart">
        <div className="artifact-title">{title || '统计图表'}</div>
        <div style={{ padding: '20px', textAlign: 'center', color: 'var(--text-muted)' }}>
           [ 图表渲染组件：{artifact.chart_type} ]
        </div>
      </div>
    )
  }

  return null
}

function EvidencePanel({ evidence }) {
  const [open, setOpen] = useState(false)

  if (!evidence) return null
  const cypher = evidence.cypher || evidence.query || ''
  const detailEntries = Object.entries(evidence).filter(([key, value]) =>
    !['cypher', 'query', 'row_count', 'elapsed_ms'].includes(key) &&
    value !== undefined && value !== null && value !== ''
  )
  return (
    <div className="query-evidence-panel">
      <div 
        className="query-evidence-header" 
        onClick={() => setOpen(!open)}
        style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}
      >
        <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Paperclip size={14} /> {cypher ? '知识提取证据 (Cypher)' : '知识提取证据'}
        </span>
        <span>
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>
      </div>
      {open && (
        <>
          {cypher && (
            <div className="query-evidence-body">
              <pre><code>{cypher}</code></pre>
            </div>
          )}
          {!cypher && detailEntries.length > 0 && (
            <div className="query-evidence-body">
              <pre><code>{JSON.stringify(Object.fromEntries(detailEntries), null, 2)}</code></pre>
            </div>
          )}
          {(evidence.row_count !== undefined || evidence.elapsed_ms !== undefined) && (
            <div className="query-evidence-footer">
              {evidence.elapsed_ms !== undefined && (
                <div className="query-evidence-meta">耗时：{evidence.elapsed_ms}ms</div>
              )}
              {evidence.row_count !== undefined && (
                <div className="query-evidence-meta">返回行数：{evidence.row_count}</div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default function ChatPage() {
  const [sessions, setSessions] = useState([])
  const [scenes, setScenes] = useState([])
  const [selectedSceneId, setSelectedSceneId] = useState('')
  const [currentSessionId, setCurrentSessionId] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [activeStreams, setActiveStreams] = useState(0)
  const isStreaming = activeStreams > 0
  const [agentReady, setAgentReady] = useState(false)
  const [agentLoading, setAgentLoading] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [scoredMsgIds, setScoredMsgIds] = useState(new Set())
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)
  const addToast = useToast()
  const visibleSessions = sessions.filter(s => selectedSceneId ? s.scene_id === selectedSceneId : !s.scene_id)

  useEffect(() => {
    checkAgent()
    loadSessions()
    loadScenes()
  }, [])

  useEffect(() => {
    checkAgent()
  }, [selectedSceneId])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const checkAgent = async () => {
    try {
      const st = await api.getAgentStatus(selectedSceneId || null)
      setAgentReady(st.initialized)
    } catch { setAgentReady(false) }
  }

  const loadSessions = async () => {
    try {
      const data = await api.listSessions()
      setSessions(data.sessions || [])
    } catch { /* ignore */ }
  }

  const loadScenes = async () => {
    try {
      const data = await api.listScenes()
      setScenes(data.scenes || [])
    } catch { /* ignore */ }
  }

  const handleInitAgent = async () => {
    setAgentLoading(true)
    try {
      await api.initAgent(selectedSceneId || null)
      setAgentReady(true)
      addToast(selectedSceneId ? '场景智能体初始化成功！' : '智能体初始化成功！', 'success')
    } catch (err) {
      addToast('初始化失败: ' + err.message, 'error')
    } finally {
      setAgentLoading(false)
    }
  }

  const handleNewChat = async () => {
    try {
      const session = await api.createSession('新对话', selectedSceneId || null)
      await loadSessions()
      setCurrentSessionId(session.id)
      setMessages([])
      setScoredMsgIds(new Set())
    } catch (err) {
      addToast('创建会话失败: ' + err.message, 'error')
    }
  }

  const handleSelectSession = async (sid) => {
    setCurrentSessionId(sid)
    try {
      const data = await api.getSession(sid)
      const scoredIds = new Set()
      const msgs = (data.messages || []).map((m, i) => ({
        id: i,
        role: m.role,
        content: m.content,
        steps: m.steps || [],
        artifacts: m.artifacts || [],
        evidence: m.evidence || null,
        metrics: m.metrics || null,
        langfuse_trace_id: m.langfuse_trace_id || null,
        scores: m.scores || [],
        streaming: false,
      }))
      msgs.forEach(m => {
        if (m.role === 'agent' && m.scores?.length) scoredIds.add(m.id)
      })
      setMessages(msgs)
      setScoredMsgIds(scoredIds)
    } catch (err) {
      setCurrentSessionId(null)
      setMessages([])
      setScoredMsgIds(new Set())
      loadSessions()
      addToast('加载会话失败: ' + err.message, 'error')
    }
  }

  const handleDeleteSession = async (sid, e) => {
    e.stopPropagation()
    if (!confirm('确定删除此对话？')) return
    try {
      await api.deleteSession(sid)
      addToast('对话已删除', 'success')
      if (currentSessionId === sid) {
        setCurrentSessionId(null)
        setMessages([])
        setScoredMsgIds(new Set())
      }
      loadSessions()
    } catch (err) { addToast('删除失败: ' + err.message, 'error') }
  }

  const handleExportSession = async (sid, e) => {
    e.stopPropagation()
    try {
      const mdContent = await api.exportSession(sid)
      const blob = new Blob([mdContent], { type: 'text/markdown;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `chat_${sid}.md`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      addToast('对话已导出为 Markdown 文件', 'success')
    } catch (err) {
      addToast('导出失败: ' + err.message, 'error')
    }
  }

  const handleScore = async (msgId, scoreValue) => {
    if (!currentSessionId) return
    const msg = messages.find(m => m.id === msgId)
    const traceId = msg?.langfuse_trace_id
    if (!traceId) {
      addToast('未找到 Langfuse Trace ID，无法评分', 'error')
      return
    }
    const scoreName = scoreValue > 0 ? 'answer_quality' : 'answer_quality'
    try {
      await api.scoreSession(traceId, scoreName, scoreValue, scoreValue > 0 ? '回答准确' : '回答不准确')
      setScoredMsgIds(prev => new Set(prev).add(msgId))
      addToast(scoreValue > 0 ? '已点赞' : '已踩', 'success')
    } catch (err) {
      addToast('评分失败: ' + err.message, 'error')
    }
  }


  const handleSend = async () => {
    const text = input.trim()
    if (!text) return

    let targetSessionId = currentSessionId

    const userMsg = { role: 'user', content: text, id: Date.now(), steps: [], artifacts: [], evidence: null, metrics: null, streaming: false }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setActiveStreams(prev => prev + 1)

    const agentMsgId = Date.now() + 1
    const agentMsg = { role: 'agent', id: agentMsgId, steps: [], artifacts: [], evidence: null, metrics: null, content: '', streaming: true }
    setMessages(prev => [...prev, agentMsg])

    try {
      for await (const event of api.chatStream(text, targetSessionId, selectedSceneId || null)) {
        if (event.type === 'session_id' && event.content) {
          // 后端自动创建的会话 ID
          if (!targetSessionId) {
            targetSessionId = event.content
            setCurrentSessionId(event.content)
            loadSessions()
          }
          continue
        }

        if (event.type === 'done') {
          setMessages(prev => prev.map(m =>
            m.id === agentMsgId ? { ...m, streaming: false } : m
          ))
          loadSessions()
          break
        }

        if (event.type === 'langfuse_trace_id' && event.content) {
          setMessages(prev => prev.map(m =>
            m.id === agentMsgId ? { ...m, langfuse_trace_id: event.content } : m
          ))
          continue
        }

        if (event.type === 'metrics' && event.content) {
          setMessages(prev => prev.map(m =>
            m.id === agentMsgId ? { ...m, metrics: event.content } : m
          ))
          continue
        }

        if (event.type === 'error') {
          setMessages(prev => prev.map(m =>
            m.id === agentMsgId
              ? { ...m, streaming: false, steps: appendUniqueStep(m.steps || [], event), content: m.content || '发生错误: ' + event.content }
              : m
          ))
          break
        }

        if (event.type === 'answer') {
          setMessages(prev => prev.map(m =>
            m.id === agentMsgId ? { ...m, content: event.content } : m
          ))
        } else if (event.type === 'token') {
          setMessages(prev => prev.map(m =>
            m.id === agentMsgId ? { ...m, content: (m.content || '') + event.content } : m
          ))
        } else if (event.type === 'artifact') {
          setMessages(prev => prev.map(m =>
            m.id === agentMsgId ? { ...m, artifacts: [...(m.artifacts || []), event.content] } : m
          ))
        } else if (event.type === 'query_evidence') {
          setMessages(prev => prev.map(m =>
            m.id === agentMsgId ? { ...m, evidence: event.content } : m
          ))
        } else {
          setMessages(prev => prev.map(m =>
            m.id === agentMsgId ? { ...m, steps: appendUniqueStep(m.steps || [], event) } : m
          ))
        }
      }
    } catch (err) {
      setMessages(prev => prev.map(m =>
        m.id === agentMsgId
          ? { ...m, streaming: false, content: '请求失败: ' + err.message }
          : m
      ))
      addToast('对话请求失败: ' + err.message, 'error')
    } finally {
      setActiveStreams(prev => Math.max(0, prev - 1))
      inputRef.current?.focus()
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="chat-page-layout">
      {/* 左侧会话侧栏 */}
      <div className={`chat-sidebar ${sidebarOpen ? 'open' : 'collapsed'}`}>
        <div className="chat-sidebar-header">
          <button className="btn btn-primary btn-sm btn-full" onClick={handleNewChat} style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
            <Plus size={16} /> 新建对话
          </button>
        </div>

        <div className="session-list">
          {visibleSessions.map(s => (
            <div
              key={s.id}
              className={`session-item ${currentSessionId === s.id ? 'active' : ''}`}
              onClick={() => handleSelectSession(s.id)}
            >
              <div className="session-item-content">
                <div className="session-title">{s.title || '未命名'}</div>
                <div className="session-meta">{s.message_count || 0} 条消息</div>
              </div>
              <div className="session-actions">
                <button className="btn btn-ghost btn-xs" onClick={(e) => handleExportSession(s.id, e)} title="导出"><Download size={14}/></button>
                <button className="btn btn-ghost btn-xs" onClick={(e) => handleDeleteSession(s.id, e)} title="删除" style={{ color: 'var(--danger-color)' }}><Trash2 size={14}/></button>
              </div>
            </div>
          ))}
          {visibleSessions.length === 0 && (
            <div className="session-empty">暂无历史对话</div>
          )}
        </div>
        <div className="chat-sidebar-toggle" onClick={() => setSidebarOpen(!sidebarOpen)}>
          {sidebarOpen ? <ChevronDown size={16}/> : <ChevronRight size={16}/>}
        </div>
      </div>

      {/* 右侧对话区 */}
      <div className="chat-container">
        <div className="chat-context-bar">
          <label className="form-label">对话场景</label>
          <select
            className="form-select"
            value={selectedSceneId}
            onChange={e => {
              setSelectedSceneId(e.target.value)
              setCurrentSessionId(null)
              setMessages([])
            }}
            disabled={isStreaming}
          >
            <option value="">全局图谱</option>
            {scenes.map(scene => (
              <option key={scene.id} value={scene.id}>{scene.name}</option>
            ))}
          </select>
        </div>

        <div className="chat-messages">
          {messages.length === 0 && (
            <div className="empty-state">
              <div className="empty-icon"><MessageSquare size={40} /></div>
              <div className="empty-text">开始与本体智能体对话吧</div>
              <p style={{ color: 'var(--text-muted)', fontSize: '0.82rem', marginTop: 8 }}>
                支持图谱查询、拓扑分析、工单检索、管控指令下发等
              </p>
            </div>
          )}

          {messages.map(msg => (
            <div key={msg.id} className={`chat-msg-wrapper ${msg.role}`}>
              <div className={`chat-msg ${msg.role}`}>
                {msg.role === 'agent' && msg.steps?.length > 0 && (
                  <StepGroup steps={msg.steps} isStreaming={msg.streaming} />
                )}

                {msg.role === 'user' ? (
                  <div className="chat-msg-bubble">{msg.content}</div>
                ) : (
                  <>
                    {msg.streaming && !msg.content && (
                      <div className="chat-msg-bubble">
                        <div className="typing-indicator">
                          <span /><span /><span />
                        </div>
                      </div>
                    )}
                    {msg.content && (
                      <div className={`chat-msg-bubble markdown-body ${msg.streaming ? 'streaming-content' : ''}`}>
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                      </div>
                    )}
                    {msg.artifacts?.map((artifact, i) => (
                      <ResultArtifact key={i} artifact={artifact} />
                    ))}
                    <EvidencePanel evidence={msg.evidence} />
                    <AnswerMetrics metrics={msg.metrics} />
                    {!msg.streaming && msg.content && msg.langfuse_trace_id && !scoredMsgIds.has(msg.id) && (
                      <div className="score-buttons">
                        <button
                          className="score-btn score-btn-like"
                          onClick={() => handleScore(msg.id, 1.0)}
                          title="回答准确"
                        >
                          有用
                        </button>
                        <button
                          className="score-btn score-btn-dislike"
                          onClick={() => handleScore(msg.id, -1.0)}
                          title="回答不准确"
                        >
                          无用
                        </button>
                      </div>
                    )}
                    {!msg.streaming && msg.content && scoredMsgIds.has(msg.id) && (
                      <div className="score-buttons scored">
                        <span className="scored-label">已评分 <Check size={14} /></span>
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        <div className="chat-input-area">
          <div className="chat-input-wrapper">
            <textarea
              ref={inputRef}
              className="chat-input"
              rows={1}
              placeholder={'输入问题... (Enter 发送, Shift+Enter 换行)'}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
            />
            <button
              className="chat-send-btn"
              onClick={handleSend}
              disabled={!input.trim()}
              style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}
            >
              <Send size={18} />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
