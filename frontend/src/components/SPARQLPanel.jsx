import React, { useState } from 'react'
import { api } from '../api'

export default function SPARQLPanel({ ontologyId }) {
    const [query, setQuery] = useState('SELECT ?s ?p ?o\nWHERE {\n  ?s ?p ?o .\n}\nLIMIT 10')
    const [results, setResults] = useState([])
    const [columns, setColumns] = useState([])
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState('')
    const [history, setHistory] = useState([])

    const handleQuery = async () => {
        if (!query.trim()) return;
        setLoading(true)
        setError('')
        setResults([])
        setColumns([])
        
        try {
            const response = await api.sparqlQuery(ontologyId, query)
            if (response.success) {
                setResults(response.results)
                if (response.results.length > 0) {
                    setColumns(Object.keys(response.results[0]))
                }
                setHistory(prev => {
                    const newHistory = [query, ...prev.filter(q => q !== query)].slice(0, 10)
                    return newHistory
                })
            } else {
                setError(response.error || '查询执行失败')
            }
        } catch (e) {
            setError(e.message)
        } finally {
            setLoading(false)
        }
    }

    return (
        <div className="sparql-panel">
            <div className="query-input-section" style={{ flex: 3 }}>
                <h4 style={{ marginTop: 0 }}>SPARQL 查询编辑器</h4>
                <div className="query-input">
                    <textarea
                        className="form-control"
                        value={query}
                        onChange={e => setQuery(e.target.value)}
                        style={{ height: '200px', fontFamily: 'monospace', whiteSpace: 'pre', marginBottom: '10px' }}
                    />
                    <button 
                        className="btn btn-primary" 
                        onClick={handleQuery} 
                        disabled={loading}
                    >
                        {loading ? '查询中...' : '🚀 执行查询'}
                    </button>
                </div>
                
                {error && <div className="alert alert-danger" style={{ marginTop: '20px' }}>{error}</div>}
                
                <div className="query-results" style={{ marginTop: '20px' }}>
                    <h4 style={{ margin: '0 0 10px 0' }}>查询结果 ({results.length})</h4>
                    <div className="query-results-wrapper" style={{ minHeight: 'auto', padding: 0, overflow: 'hidden' }}>
                        {results.length > 0 ? (
                            <div style={{ overflowX: 'auto' }}>
                                <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '14px' }}>
                                    <thead>
                                        <tr style={{ background: 'var(--bg-muted)' }}>
                                            {columns.map(col => (
                                                <th key={col} style={{ padding: '12px 16px', borderBottom: '1px solid var(--border-color)', color: 'var(--text-primary)' }}>
                                                    {col}
                                                </th>
                                            ))}
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {results.map((row, idx) => (
                                            <tr key={idx} className="table-row-hover">
                                                {columns.map(col => (
                                                    <td key={col} style={{ padding: '10px 16px', borderBottom: '1px solid var(--border-color)', maxWidth: '300px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--text-secondary)' }} title={row[col]}>
                                                        {row[col]}
                                                    </td>
                                                ))}
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        ) : (
                            <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '60px 0' }}>
                                暂无数据
                            </div>
                        )}
                    </div>
                </div>
            </div>

            <div className="query-history-section">
                <h4 style={{ marginTop: 0 }}>查询历史</h4>
                {history.length > 0 ? (
                    <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                        {history.map((item, idx) => (
                            <li 
                                key={idx} 
                                style={{ 
                                    padding: '10px', 
                                    borderBottom: '1px solid var(--border-color)',
                                    cursor: 'pointer',
                                    color: 'var(--primary)',
                                    fontSize: '12px',
                                    fontFamily: 'monospace',
                                    whiteSpace: 'pre-wrap',
                                    wordBreak: 'break-all',
                                    borderRadius: 'var(--radius-sm)'
                                }}
                                className="history-item-hover"
                                onClick={() => setQuery(item)}
                            >
                                {item.length > 100 ? item.substring(0, 100) + '...' : item}
                            </li>
                        ))}
                    </ul>
                ) : (
                    <div style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>无历史记录</div>
                )}
            </div>
        </div>
    )
}
