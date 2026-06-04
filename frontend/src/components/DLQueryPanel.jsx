import React, { useState } from 'react'
import { api } from '../api'

export default function DLQueryPanel({ ontologyId }) {
    const [query, setQuery] = useState('')
    const [results, setResults] = useState(null)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState('')
    const [history, setHistory] = useState([])
    const [options, setOptions] = useState({
        include_instances: true,
        include_subclasses: true,
        include_superclasses: false,
        include_equivalent: false
    })

    const handleQuery = async () => {
        if (!query.trim()) return;
        setLoading(true)
        setError('')
        try {
            const response = await api.dlQuery(ontologyId, query, options)
            if (response.success) {
                setResults(response.results)
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

    const handleOptionChange = (e) => {
        const { name, checked } = e.target;
        setOptions(prev => ({
            ...prev,
            [name]: checked
        }));
    }

    const renderResultSection = (title, items) => {
        if (!items || items.length === 0) return null;
        return (
            <div style={{ marginBottom: '15px' }}>
                <h5 style={{ margin: '0 0 8px 0', color: 'var(--primary)' }}>{title} ({items.length})</h5>
                <ul style={{ margin: 0, paddingLeft: '20px' }}>
                    {items.map((result, idx) => (
                        <li key={idx} style={{ padding: '2px 0' }}>{result}</li>
                    ))}
                </ul>
            </div>
        );
    }

    const hasAnyResults = results && (
        (results.instances && results.instances.length > 0) ||
        (results.subclasses && results.subclasses.length > 0) ||
        (results.superclasses && results.superclasses.length > 0) ||
        (results.equivalent_classes && results.equivalent_classes.length > 0)
    );

    return (
        <div className="dl-query-panel">
            <div className="query-input-section">
                <h4 style={{ marginTop: 0 }}>DL Query 表达式</h4>
                <div className="query-input">
                    <textarea
                        className="form-control"
                        value={query}
                        onChange={e => setQuery(e.target.value)}
                        placeholder="输入 DL Query，例如：Person and (hasChild some Person)"
                        style={{ height: '120px', fontFamily: 'monospace', marginBottom: '10px' }}
                    />
                    
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '15px', padding: '10px 0', borderBottom: '1px solid var(--border-color)', marginBottom: '10px' }}>
                        <label style={{ display: 'flex', alignItems: 'center', gap: '5px', cursor: 'pointer', color: 'var(--text-primary)', fontSize: '0.85rem' }}>
                            <input type="checkbox" name="include_instances" checked={options.include_instances} onChange={handleOptionChange} />
                            Instances
                        </label>
                        <label style={{ display: 'flex', alignItems: 'center', gap: '5px', cursor: 'pointer', color: 'var(--text-primary)', fontSize: '0.85rem' }}>
                            <input type="checkbox" name="include_subclasses" checked={options.include_subclasses} onChange={handleOptionChange} />
                            Sub classes
                        </label>
                        <label style={{ display: 'flex', alignItems: 'center', gap: '5px', cursor: 'pointer', color: 'var(--text-primary)', fontSize: '0.85rem' }}>
                            <input type="checkbox" name="include_superclasses" checked={options.include_superclasses} onChange={handleOptionChange} />
                            Super classes
                        </label>
                        <label style={{ display: 'flex', alignItems: 'center', gap: '5px', cursor: 'pointer', color: 'var(--text-primary)', fontSize: '0.85rem' }}>
                            <input type="checkbox" name="include_equivalent" checked={options.include_equivalent} onChange={handleOptionChange} />
                            Equivalent classes
                        </label>
                    </div>

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
                    <h4 style={{ margin: 0 }}>查询结果</h4>
                    <div className="query-results-wrapper">
                        {hasAnyResults ? (
                            <div>
                                {renderResultSection('Instances', results.instances)}
                                {renderResultSection('Sub classes', results.subclasses)}
                                {renderResultSection('Super classes', results.superclasses)}
                                {renderResultSection('Equivalent classes', results.equivalent_classes)}
                            </div>
                        ) : (
                            <div style={{ color: 'var(--text-muted)', textAlign: 'center', marginTop: '80px' }}>
                                暂无结果
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
                                    wordBreak: 'break-all',
                                    fontSize: '0.85rem',
                                    borderRadius: 'var(--radius-sm)'
                                }}
                                className="history-item-hover"
                                onClick={() => setQuery(item)}
                            >
                                {item}
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
