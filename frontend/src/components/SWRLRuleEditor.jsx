import React, { useState, useEffect } from 'react';
import { api } from '../api';
import './SWRLRuleEditor.css'; // Optional: for custom styling

function SWRLRuleEditor({ sceneId }) {
    const [rules, setRules] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [editingRule, setEditingRule] = useState(null);

    // Form state
    const [name, setName] = useState('');
    const [label, setLabel] = useState('');
    const [comment, setComment] = useState('');
    const [body, setBody] = useState('');
    const [head, setHead] = useState('');
    const [enabled, setEnabled] = useState(true);

    useEffect(() => {
        if (sceneId) {
            loadRules();
        }
    }, [sceneId]);

    const loadRules = async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await api.getSwrlRules(sceneId);
            setRules(data.rules || []);
        } catch (err) {
            setError(err.message || '加载规则失败');
        } finally {
            setLoading(false);
        }
    };

    const handleEdit = (rule) => {
        setEditingRule(rule);
        setName(rule.name);
        setLabel(rule.label || '');
        setComment(rule.comment || '');
        setBody(rule.body || '');
        setHead(rule.head || '');
        setEnabled(rule.enabled !== false);
    };

    const handleCreateNew = () => {
        setEditingRule({ isNew: true });
        setName('');
        setLabel('');
        setComment('');
        setBody('');
        setHead('');
        setEnabled(true);
    };

    const handleSave = async () => {
        if (!name) {
            alert('规则名称不能为空');
            return;
        }
        setLoading(true);
        try {
            const ruleData = {
                name,
                label,
                comment,
                body,
                head,
                enabled
            };
            await api.createSwrlRule(sceneId, ruleData);
            setEditingRule(null);
            loadRules();
        } catch (err) {
            alert(err.message || '保存规则失败');
        } finally {
            setLoading(false);
        }
    };

    const handleDelete = async (ruleName) => {
        if (!window.confirm(`确定要删除规则 ${ruleName} 吗？`)) return;
        setLoading(true);
        try {
            await api.deleteSwrlRule(sceneId, ruleName);
            loadRules();
        } catch (err) {
            alert(err.message || '删除规则失败');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="swrl-rule-editor">
            <div className="swrl-header">
                <h3>SWRL 规则管理</h3>
                {!editingRule && (
                    <button className="btn btn-primary" onClick={handleCreateNew}>
                        ➕ 新建规则
                    </button>
                )}
            </div>

            {error && <div className="error-message" style={{ color: 'var(--danger)', marginBottom: '10px', padding: '10px', background: 'var(--danger-bg)', borderRadius: '4px' }}>{error}</div>}
            {loading && <div style={{ color: 'var(--text-secondary)', marginBottom: '10px' }}>加载中...</div>}

            {!editingRule ? (
                <div className="rule-list-container">
                    {rules.length === 0 ? (
                        <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '40px' }}>暂无 SWRL 规则，请创建。</p>
                    ) : (
                        <table className="rule-list">
                            <thead>
                                <tr>
                                    <th style={{ width: '60px' }}>状态</th>
                                    <th>名称</th>
                                    <th>前提条件 (Body)</th>
                                    <th>结论 (Head)</th>
                                    <th style={{ width: '120px' }}>操作</th>
                                </tr>
                            </thead>
                            <tbody>
                                {rules.map(rule => (
                                    <tr key={rule.name}>
                                        <td style={{ textAlign: 'center' }}>{rule.enabled !== false ? '✅' : '❌'}</td>
                                        <td><strong>{rule.name}</strong></td>
                                        <td><code style={{ background: 'var(--bg-muted)', color: 'var(--primary)', padding: '4px 8px', borderRadius: 4, fontSize: '0.85rem' }}>{rule.body}</code></td>
                                        <td><code style={{ background: 'var(--bg-muted)', color: 'var(--success)', padding: '4px 8px', borderRadius: 4, fontSize: '0.85rem' }}>{rule.head}</code></td>
                                        <td>
                                            <div style={{ display: 'flex', gap: '8px' }}>
                                                <button className="btn btn-ghost btn-xs" onClick={() => handleEdit(rule)}>编辑</button>
                                                <button className="btn btn-ghost btn-xs" style={{ color: 'var(--danger)' }} onClick={() => handleDelete(rule.name)}>删除</button>
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </div>
            ) : (
                <div className="rule-editor-form">
                    <div className="form-group">
                        <label className="form-label">名称 (Name)</label>
                        <input 
                            type="text" 
                            className="form-input"
                            value={name} 
                            onChange={e => setName(e.target.value)} 
                            disabled={!editingRule.isNew} 
                        />
                    </div>
                    <div className="form-group">
                        <label className="form-label">标签 (Label)</label>
                        <input type="text" className="form-input" value={label} onChange={e => setLabel(e.target.value)} />
                    </div>
                    <div className="form-group">
                        <label className="form-label">前提条件 (Body)</label>
                        <textarea 
                            className="form-input"
                            style={{ height: 100, fontFamily: 'var(--font-mono)' }} 
                            value={body} 
                            onChange={e => setBody(e.target.value)} 
                            placeholder="例如: Person(?p) ^ hasAge(?p, ?age) ^ swrlb:greaterThan(?age, 18)"
                        />
                    </div>
                    <div className="form-group">
                        <label className="form-label">结论 (Head)</label>
                        <textarea 
                            className="form-input"
                            style={{ height: 100, fontFamily: 'var(--font-mono)' }} 
                            value={head} 
                            onChange={e => setHead(e.target.value)} 
                            placeholder="例如: Adult(?p)"
                        />
                    </div>
                    <div className="form-group">
                        <label className="form-label">注释 (Comment)</label>
                        <input type="text" className="form-input" value={comment} onChange={e => setComment(e.target.value)} />
                    </div>
                    <div style={{ marginBottom: 20 }}>
                        <label style={{ fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-primary)', cursor: 'pointer' }}>
                            <input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} />
                            启用此规则
                        </label>
                    </div>
                    
                    <div style={{ display: 'flex', gap: 12 }}>
                        <button className="btn btn-primary" onClick={handleSave}>保存规则</button>
                        <button className="btn btn-ghost" onClick={() => setEditingRule(null)}>取消</button>
                    </div>
                </div>
            )}
        </div>
    );
}

export default SWRLRuleEditor;
