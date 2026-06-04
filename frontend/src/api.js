const API_BASE = '/api';

function getToken() {
  return localStorage.getItem('auth_token');
}

async function request(path, options = {}) {
  const token = getToken();
  const headers = { 'Content-Type': 'application/json', ...options.headers };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  // Remove Content-Type for FormData
  if (options.body instanceof FormData) {
    delete headers['Content-Type'];
  }

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (res.status === 401) {
    localStorage.removeItem('auth_token');
    localStorage.removeItem('auth_user');
    window.location.hash = '#/login';
    throw new Error('认证已过期，请重新登录');
  }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || `请求失败 (${res.status})`);
  }
  return res.json();
}

export const api = {
  // Auth
  login: (username, password) =>
    request('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }),
  getMe: () => request('/auth/me'),
  listUsers: () => request('/auth/users'),
  createUser: (user) =>
    request('/auth/users', { method: 'POST', body: JSON.stringify(user) }),
  updateUser: (username, updates) =>
    request(`/auth/users/${encodeURIComponent(username)}`, { method: 'PUT', body: JSON.stringify(updates) }),
  deleteUser: (username) =>
    request(`/auth/users/${encodeURIComponent(username)}`, { method: 'DELETE' }),
  changePassword: (current_password, new_password) =>
    request('/auth/me/password', { method: 'PUT', body: JSON.stringify({ current_password, new_password }) }),

  // Config
  getEnvConfig: () => request('/config/env'),
  updateEnvConfig: (content) =>
    request('/config/env', { method: 'PUT', body: JSON.stringify({ content }) }),
  getMappingConfig: () => request('/config/mapping'),
  updateMappingConfig: (content) =>
    request('/config/mapping', { method: 'PUT', body: JSON.stringify({ content }) }),
  updateOntologyDir: (ontology_dir) =>
    request('/config/ontology-dir', { method: 'PUT', body: JSON.stringify({ ontology_dir }) }),

  // Sync
  syncOntology: (ontology_dir) =>
    request('/sync/ontology', { method: 'POST', body: JSON.stringify({ ontology_dir: ontology_dir || null }) }),
  syncDatabase: () => request('/sync/database', { method: 'POST' }),
  getSyncStatus: () => request('/sync/status'),
  fetchRemoteOntology: (url) =>
    request('/sync/fetch-remote', { method: 'POST', body: JSON.stringify({ url }) }),
  readOntologyFile: (filename) =>
    request(`/config/ontology-file?filename=${encodeURIComponent(filename)}`),

  // System
  getSystemStatus: () => request('/system/status'),
  getGraphStats: () => request('/system/graph-stats'),
  getAuditEvents: (params = {}) => {
    const qs = new URLSearchParams();
    if (params.limit) qs.set('limit', params.limit);
    if (params.username) qs.set('event_username', params.username);
    if (params.action) qs.set('action', params.action);
    if (params.status) qs.set('status', params.status);
    if (params.since) qs.set('since', params.since);
    if (params.until) qs.set('until', params.until);
    return request(`/admin/audit?${qs.toString()}`);
  },
  exportAuditEvents: async (params = {}, exportFormat = 'csv') => {
    const token = getToken();
    const qs = new URLSearchParams();
    qs.set('export_format', exportFormat);
    if (params.limit) qs.set('limit', params.limit);
    if (params.username) qs.set('event_username', params.username);
    if (params.action) qs.set('action', params.action);
    if (params.status) qs.set('status', params.status);
    if (params.since) qs.set('since', params.since);
    if (params.until) qs.set('until', params.until);
    const res = await fetch(`${API_BASE}/admin/audit/export?${qs.toString()}`, {
      headers: { 'Authorization': `Bearer ${token}` },
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || `导出失败 (${res.status})`);
    }
    const disposition = res.headers.get('Content-Disposition') || '';
    const match = disposition.match(/filename=([^;]+)/);
    return {
      blob: await res.blob(),
      filename: match ? match[1].replaceAll('"', '') : `audit-events.${exportFormat}`,
    };
  },
  adoptSceneGraph: (scene_id, dry_run = true) =>
    request('/admin/graph/adopt-scene', { method: 'POST', body: JSON.stringify({ scene_id, dry_run }) }),

  // Graph Explorer
  exploreGraph: (params = {}) => {
    const qs = new URLSearchParams();
    if (params.label) qs.set('label', params.label);
    if (params.rel_type) qs.set('rel_type', params.rel_type);
    if (params.scene_id) qs.set('scene_id', params.scene_id);
    if (params.limit) qs.set('limit', params.limit);
    if (params.scope) qs.set('scope', params.scope);
    return request(`/graph/explore?${qs.toString()}`);
  },
  getNodeNeighbors: (nodeId) => request(`/graph/node/${encodeURIComponent(nodeId)}/neighbors`),
  getNodeOntologyInfo: (nodeId) => request(`/graph/node/${encodeURIComponent(nodeId)}/ontology-info`),

  // Agent
  initAgent: (scene_id = null) => request('/agent/init', { method: 'POST', body: JSON.stringify({ scene_id }) }),
  getAgentStatus: (scene_id = null) => {
    const qs = scene_id ? `?scene_id=${encodeURIComponent(scene_id)}` : '';
    return request(`/agent/status${qs}`);
  },
  resetAgent: (scene_id = null) => {
    const qs = scene_id ? `?scene_id=${encodeURIComponent(scene_id)}` : '';
    return request(`/agent/reset${qs}`, { method: 'POST' });
  },

  // Chat Sessions
  listSessions: () => request('/chat/sessions'),
  createSession: (title, scene_id = null) =>
    request('/chat/sessions', { method: 'POST', body: JSON.stringify({ title, scene_id }) }),
  getSession: (id) => request(`/chat/sessions/${id}`),
  deleteSession: (id) => request(`/chat/sessions/${id}`, { method: 'DELETE' }),
  renameSession: (id, title) =>
    request(`/chat/sessions/${id}/title`, { method: 'PUT', body: JSON.stringify({ title }) }),
  exportSession: async (id) => {
    const token = getToken();
    const res = await fetch(`${API_BASE}/chat/sessions/${id}/export`, {
      headers: { 'Authorization': `Bearer ${token}` },
    });
    if (!res.ok) throw new Error('导出失败');
    return res.text();
  },
  scoreSession: (id, scoreName, value, comment = '') =>
    request(`/chat/sessions/${id}/score`, {
      method: 'POST',
      body: JSON.stringify({ score_name: scoreName, value, comment }),
    }),

  // Chat (SSE streaming)
  chatStream: async function* (message, sessionId, sceneId = null) {
    const token = getToken();
    const res = await fetch(`${API_BASE}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({ message, session_id: sessionId || null, scene_id: sceneId || null }),
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || `请求失败 (${res.status})`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith('data: ')) {
          try {
            const data = JSON.parse(trimmed.slice(6));
            yield data;
          } catch (e) { /* skip non-json */ }
        }
      }
    }
  },

  // ==== NEW: LLM Configuration ====
  getLLMConfig: () => request('/llm/config'),
  updateLLMConfig: (config) =>
    request('/llm/config', { method: 'PUT', body: JSON.stringify(config) }),
  testLLM: (config) =>
    request('/llm/test', { method: 'POST', body: JSON.stringify(config) }),
  testEmbedding: (config) =>
    request('/llm/test-embedding', { method: 'POST', body: JSON.stringify(config) }),

  // ==== NEW: Ontology Query ====
  dlQuery: (sceneId, query, options = {}) => request(`/scene/${encodeURIComponent(sceneId)}/studio/dl-query`, { 
    method: 'POST', 
    body: JSON.stringify({ 
      query, 
      include_instances: options.include_instances ?? true,
      include_subclasses: options.include_subclasses ?? false,
      include_superclasses: options.include_superclasses ?? false,
      include_equivalent: options.include_equivalent ?? false
    }) 
  }),
  sparqlQuery: (sceneId, query) => request(`/scene/${encodeURIComponent(sceneId)}/studio/sparql`, { method: 'POST', body: JSON.stringify({ query }) }),

  // ==== NEW: SWRL Rules ====
  getSwrlRules: (sceneId) => request(`/scene/${encodeURIComponent(sceneId)}/studio/swrl-rules`),
  createSwrlRule: (sceneId, rule) => request(`/scene/${encodeURIComponent(sceneId)}/studio/swrl-rules`, { method: 'POST', body: JSON.stringify(rule) }),
  deleteSwrlRule: (sceneId, ruleName) => request(`/scene/${encodeURIComponent(sceneId)}/studio/swrl-rules/${encodeURIComponent(ruleName)}`, { method: 'DELETE' }),

  // ==== NEW: Ontology File Management ====
  listOntologyFiles: () => request('/ontology/files'),
  uploadOntologyFile: (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return request('/ontology/upload', { method: 'POST', body: formData });
  },
  deleteOntologyFile: (filename) =>
    request(`/ontology/files/${encodeURIComponent(filename)}`, { method: 'DELETE' }),

  // ==== NEW: Multi-Datasource ====
  listDatasources: () => request('/datasource/list'),
  addDatasource: (ds) =>
    request('/datasource/add', { method: 'POST', body: JSON.stringify(ds) }),
  deleteDatasource: (id) =>
    request(`/datasource/${id}`, { method: 'DELETE' }),
  testDatasource: (config) =>
    request('/datasource/test', { method: 'POST', body: JSON.stringify(config) }),
  getDatasourceTables: (id) => request(`/datasource/${id}/tables`),
  getDatasourceColumns: (id, table) =>
    request(`/datasource/${id}/tables/${encodeURIComponent(table)}/columns`),
  previewDatasourceTable: (id, table, limit = 50) =>
    request(`/datasource/${id}/tables/${encodeURIComponent(table)}/preview?limit=${limit}`),

  // ==== NEW: Validation ====
  runValidation: (params = {}) =>
    request('/validation/check', { method: 'POST', body: JSON.stringify(params) }),

  // ==== Scene Management ====
  listScenes: () => request('/scene/list'),
  createScene: (name, description = '', data_mode = 'import') =>
    request('/scene/create', { method: 'POST', body: JSON.stringify({ name, description, data_mode }) }),
  getScene: (id) => request(`/scene/${id}`),
  updateScene: (id, updates) =>
    request(`/scene/${id}`, { method: 'PUT', body: JSON.stringify(updates) }),
  deleteScene: (id) => request(`/scene/${id}`, { method: 'DELETE' }),

  // Scene Ontology
  uploadSceneOntology: (sceneId, file) => {
    const formData = new FormData();
    formData.append('file', file);
    return request(`/scene/${sceneId}/ontology/upload`, { method: 'POST', body: formData });
  },
  parseSceneOntology: (sceneId) => request(`/scene/${sceneId}/ontology/parse`),
  deleteSceneOntology: (sceneId) => request(`/scene/${sceneId}/ontology`, { method: 'DELETE' }),

  // Scene Mapping
  getSceneMapping: (sceneId) => request(`/scene/${sceneId}/mapping`),
  updateSceneMapping: (sceneId, content) =>
    request(`/scene/${sceneId}/mapping`, { method: 'PUT', body: JSON.stringify({ content }) }),

  // Scene Few Shots
  getSceneFewShots: (sceneId) => request(`/scene/${sceneId}/few-shots`),
  updateSceneFewShots: (sceneId, content) =>
    request(`/scene/${sceneId}/few-shots`, { method: 'PUT', body: JSON.stringify({ content }) }),

  // Scene Rules
  getSceneRules: (sceneId) => request(`/scene/${sceneId}/rules`),
  updateSceneRules: (sceneId, content) =>
    request(`/scene/${sceneId}/rules`, { method: 'PUT', body: JSON.stringify({ content }) }),

  // Scene Aliases
  getSceneAliases: (sceneId) => request(`/scene/${sceneId}/aliases`),
  updateSceneAliases: (sceneId, content) =>
    request(`/scene/${sceneId}/aliases`, { method: 'PUT', body: JSON.stringify({ content }) }),

  // Scene Routing
  getSceneRouting: (sceneId) => request(`/scene/${sceneId}/routing`),
  updateSceneRouting: (sceneId, content) =>
    request(`/scene/${sceneId}/routing`, { method: 'PUT', body: JSON.stringify({ content }) }),

  // Scene Datasources
  updateSceneDatasources: (sceneId, datasource_ids) =>
    request(`/scene/${sceneId}/datasources`, { method: 'PUT', body: JSON.stringify({ datasource_ids }) }),

  // Scene Sync & Validate
  syncScene: (sceneId, clearExisting = false) =>
    request(`/scene/${sceneId}/sync`, { method: 'POST', body: JSON.stringify({ clear_existing: clearExisting }) }),
  clearSceneGraph: (sceneId) => request(`/scene/${sceneId}/graph`, { method: 'DELETE' }),
  getSceneSyncLog: (sceneId) => request(`/scene/${sceneId}/sync-log`),
  getSceneQaHealth: (sceneId) => request(`/scene/${sceneId}/qa-health`),
  validateScene: (sceneId) => request(`/scene/${sceneId}/validate`, { method: 'POST' }),

  // Mapping Builder
  getMappingBuilderData: (sceneId) => request(`/scene/${sceneId}/mapping/builder-data`),
  saveMappingFromVisual: (sceneId, config) =>
    request(`/scene/${sceneId}/mapping/from-visual`, { method: 'POST', body: JSON.stringify(config) }),
  autoSuggestMapping: (sceneId) =>
    request(`/scene/${sceneId}/mapping/auto-suggest`, { method: 'POST' }),

  // ==== Ontology Management (多本体管理) ====
  listAllOntologies: () => request('/ontologies'),
  createOntology: (data) =>
    request('/ontologies', { method: 'POST', body: JSON.stringify(data) }),
  getOntology: (ontologyId) => request(`/ontologies/${encodeURIComponent(ontologyId)}`),
  deleteOntology: (ontologyId) =>
    request(`/ontologies/${encodeURIComponent(ontologyId)}`, { method: 'DELETE' }),
  updateOntology: (ontologyId, data) =>
    request(`/ontologies/${encodeURIComponent(ontologyId)}`, { method: 'PUT', body: JSON.stringify(data) }),
  importOntology: async (ontologyId, file) => {
    const token = getToken();
    const formData = new FormData();
    formData.append('file', file);
    
    const res = await fetch(`${API_BASE}/scene/${encodeURIComponent(ontologyId)}/studio/import`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` },
      body: formData,
    });
    
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || `导入失败 (${res.status})`);
    }
    return res.json();
  },
  exportOntology: (ontologyId, format = 'turtle') =>
    request(`/scene/${encodeURIComponent(ontologyId)}/studio/export?format=${format}`),
  getOntologyStats: (ontologyId) => request(`/scene/${encodeURIComponent(ontologyId)}/studio/stats`),
  getOntologyMetadata: (ontologyId) => request(`/scene/${encodeURIComponent(ontologyId)}/studio/metadata`),
  updateOntologyMetadata: (ontologyId, metadata) =>
    request(`/scene/${encodeURIComponent(ontologyId)}/studio/metadata`, { method: 'PUT', body: JSON.stringify(metadata) }),
  listOntologyClasses: (ontologyId) => request(`/scene/${encodeURIComponent(ontologyId)}/studio/classes`),
  createOntologyClass: (ontologyId, classData) =>
    request(`/scene/${encodeURIComponent(ontologyId)}/studio/classes`, { method: 'POST', body: JSON.stringify(classData) }),
  updateOntologyClass: (ontologyId, className, classData) =>
    request(`/scene/${encodeURIComponent(ontologyId)}/studio/classes/${encodeURIComponent(className)}`, { method: 'PUT', body: JSON.stringify(classData) }),
  deleteOntologyClass: (ontologyId, className) =>
    request(`/scene/${encodeURIComponent(ontologyId)}/studio/classes/${encodeURIComponent(className)}`, { method: 'DELETE' }),
  listOntologyObjectProperties: (ontologyId) => request(`/scene/${encodeURIComponent(ontologyId)}/studio/object-properties`),
  createOntologyObjectProperty: (ontologyId, propData) =>
    request(`/scene/${encodeURIComponent(ontologyId)}/studio/object-properties`, { method: 'POST', body: JSON.stringify(propData) }),
  updateOntologyObjectProperty: (ontologyId, propName, propData) =>
    request(`/scene/${encodeURIComponent(ontologyId)}/studio/object-properties/${encodeURIComponent(propName)}`, { method: 'PUT', body: JSON.stringify(propData) }),
  deleteOntologyObjectProperty: (ontologyId, propName) =>
    request(`/scene/${encodeURIComponent(ontologyId)}/studio/object-properties/${encodeURIComponent(propName)}`, { method: 'DELETE' }),
  listOntologyDataProperties: (ontologyId) => request(`/scene/${encodeURIComponent(ontologyId)}/studio/data-properties`),
  createOntologyDataProperty: (ontologyId, propData) =>
    request(`/scene/${encodeURIComponent(ontologyId)}/studio/data-properties`, { method: 'POST', body: JSON.stringify(propData) }),
  updateOntologyDataProperty: (ontologyId, propName, propData) =>
    request(`/scene/${encodeURIComponent(ontologyId)}/studio/data-properties/${encodeURIComponent(propName)}`, { method: 'PUT', body: JSON.stringify(propData) }),
  deleteOntologyDataProperty: (ontologyId, propName) =>
    request(`/scene/${encodeURIComponent(ontologyId)}/studio/data-properties/${encodeURIComponent(propName)}`, { method: 'DELETE' }),
  listOntologyAnnotationProperties: (ontologyId) => request(`/scene/${encodeURIComponent(ontologyId)}/studio/annotation-properties`),
  createOntologyAnnotationProperty: (ontologyId, propData) =>
    request(`/scene/${encodeURIComponent(ontologyId)}/studio/annotation-properties`, { method: 'POST', body: JSON.stringify(propData) }),
  deleteOntologyAnnotationProperty: (ontologyId, propName) =>
    request(`/scene/${encodeURIComponent(ontologyId)}/studio/annotation-properties/${encodeURIComponent(propName)}`, { method: 'DELETE' }),
  listOntologyIndividuals: (ontologyId) => request(`/scene/${encodeURIComponent(ontologyId)}/studio/individuals`),
  createOntologyIndividual: (ontologyId, indData) =>
    request(`/scene/${encodeURIComponent(ontologyId)}/studio/individuals`, { method: 'POST', body: JSON.stringify(indData) }),
  updateOntologyIndividual: (ontologyId, indName, indData) =>
    request(`/scene/${encodeURIComponent(ontologyId)}/studio/individuals/${encodeURIComponent(indName)}`, { method: 'PUT', body: JSON.stringify(indData) }),
  deleteOntologyIndividual: (ontologyId, indName) =>
    request(`/scene/${encodeURIComponent(ontologyId)}/studio/individuals/${encodeURIComponent(indName)}`, { method: 'DELETE' }),
  getOntologyClassHierarchy: (ontologyId) => request(`/scene/${encodeURIComponent(ontologyId)}/studio/class-hierarchy`),
  reasonOntology: (ontologyId) =>
    request(`/scene/${encodeURIComponent(ontologyId)}/studio/reason`, { method: 'POST' }),
  createOntologyVersion: (ontologyId, versionData) =>
    request(`/scene/${encodeURIComponent(ontologyId)}/studio/version`, { method: 'POST', body: JSON.stringify(versionData) }),
  listOntologyVersions: (ontologyId) => request(`/scene/${encodeURIComponent(ontologyId)}/studio/versions`),
  getOntologyVersion: (ontologyId, version) => request(`/scene/${encodeURIComponent(ontologyId)}/studio/version/${version}`),
  restoreOntologyVersion: (ontologyId, version) =>
    request(`/scene/${encodeURIComponent(ontologyId)}/studio/version/${version}/restore`, { method: 'POST' }),
  deleteOntologyVersion: (ontologyId, version) =>
    request(`/scene/${encodeURIComponent(ontologyId)}/studio/version/${version}`, { method: 'DELETE' }),

  // ==== Ontology Studio (本体工坊 - 旧版，保留兼容) ====
  getStudioMetadata: (sceneId) => request(`/scene/${sceneId}/studio/metadata`),
  updateStudioMetadata: (sceneId, metadata) =>
    request(`/scene/${sceneId}/studio/metadata`, { method: 'PUT', body: JSON.stringify(metadata) }),

  listStudioClasses: (sceneId) => request(`/scene/${sceneId}/studio/classes`),
  createStudioClass: (sceneId, classData) =>
    request(`/scene/${sceneId}/studio/classes`, { method: 'POST', body: JSON.stringify(classData) }),
  updateStudioClass: (sceneId, className, classData) =>
    request(`/scene/${sceneId}/studio/classes/${encodeURIComponent(className)}`, { method: 'PUT', body: JSON.stringify(classData) }),
  deleteStudioClass: (sceneId, className) =>
    request(`/scene/${sceneId}/studio/classes/${encodeURIComponent(className)}`, { method: 'DELETE' }),

  listStudioObjectProperties: (sceneId) => request(`/scene/${sceneId}/studio/object-properties`),
  createStudioObjectProperty: (sceneId, propData) =>
    request(`/scene/${sceneId}/studio/object-properties`, { method: 'POST', body: JSON.stringify(propData) }),
  updateStudioObjectProperty: (sceneId, propName, propData) =>
    request(`/scene/${sceneId}/studio/object-properties/${encodeURIComponent(propName)}`, { method: 'PUT', body: JSON.stringify(propData) }),
  deleteStudioObjectProperty: (sceneId, propName) =>
    request(`/scene/${sceneId}/studio/object-properties/${encodeURIComponent(propName)}`, { method: 'DELETE' }),

  listStudioDataProperties: (sceneId) => request(`/scene/${sceneId}/studio/data-properties`),
  createStudioDataProperty: (sceneId, propData) =>
    request(`/scene/${sceneId}/studio/data-properties`, { method: 'POST', body: JSON.stringify(propData) }),
  updateStudioDataProperty: (sceneId, propName, propData) =>
    request(`/scene/${sceneId}/studio/data-properties/${encodeURIComponent(propName)}`, { method: 'PUT', body: JSON.stringify(propData) }),
  deleteStudioDataProperty: (sceneId, propName) =>
    request(`/scene/${sceneId}/studio/data-properties/${encodeURIComponent(propName)}`, { method: 'DELETE' }),

  listStudioAnnotationProperties: (sceneId) => request(`/scene/${sceneId}/studio/annotation-properties`),
  createStudioAnnotationProperty: (sceneId, propData) =>
    request(`/scene/${sceneId}/studio/annotation-properties`, { method: 'POST', body: JSON.stringify(propData) }),
  deleteStudioAnnotationProperty: (sceneId, propName) =>
    request(`/scene/${sceneId}/studio/annotation-properties/${encodeURIComponent(propName)}`, { method: 'DELETE' }),

  listStudioIndividuals: (sceneId) => request(`/scene/${sceneId}/studio/individuals`),
  createStudioIndividual: (sceneId, indData) =>
    request(`/scene/${sceneId}/studio/individuals`, { method: 'POST', body: JSON.stringify(indData) }),
  updateStudioIndividual: (sceneId, indName, indData) =>
    request(`/scene/${sceneId}/studio/individuals/${encodeURIComponent(indName)}`, { method: 'PUT', body: JSON.stringify(indData) }),
  deleteStudioIndividual: (sceneId, indName) =>
    request(`/scene/${sceneId}/studio/individuals/${encodeURIComponent(indName)}`, { method: 'DELETE' }),

  getStudioStats: (sceneId) => request(`/scene/${sceneId}/studio/stats`),
  importStudioOntology: async (sceneId, file) => {
    const token = getToken();
    const formData = new FormData();
    formData.append('file', file);
    
    const res = await fetch(`${API_BASE}/scene/${sceneId}/studio/import`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` },
      body: formData,
    });
    
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || `导入失败 (${res.status})`);
    }
    return res.json();
  },
  exportStudioOntology: (sceneId, format = 'turtle') =>
    request(`/scene/${sceneId}/studio/export?format=${format}`),
  getClassHierarchy: (sceneId) => request(`/scene/${sceneId}/studio/class-hierarchy`),
  reasonOntology: (sceneId) =>
    request(`/scene/${sceneId}/studio/reason`, { method: 'POST' }),
  clearReasonerCache: (sceneId) =>
    request(`/scene/${sceneId}/studio/reason/cache`, { method: 'DELETE' }),
  getReasonerCacheInfo: (sceneId) =>
    request(`/scene/${sceneId}/studio/reason/cache`),
  getStudioGraph: (sceneId, options = {}) => {
    const params = new URLSearchParams()
    if (options.showIndividuals !== undefined) params.set('show_individuals', options.showIndividuals)
    if (options.showDisjoint !== undefined) params.set('show_disjoint', options.showDisjoint)
    if (options.showEquivalent !== undefined) params.set('show_equivalent', options.showEquivalent)
    const qs = params.toString()
    return request(`/scene/${sceneId}/studio/graph${qs ? '?' + qs : ''}`)
  },
  getStudioEntityUsage: (sceneId) =>
    request(`/scene/${sceneId}/studio/entity-usage`),
  createStudioVersion: (sceneId, versionData) =>
    request(`/scene/${sceneId}/studio/version`, { method: 'POST', body: JSON.stringify(versionData) }),
  listStudioVersions: (sceneId) => request(`/scene/${sceneId}/studio/versions`),
  getStudioVersion: (sceneId, version) => request(`/scene/${sceneId}/studio/version/${version}`),
  restoreStudioVersion: (sceneId, version) =>
    request(`/scene/${sceneId}/studio/version/${version}/restore`, { method: 'POST' }),
  deleteStudioVersion: (sceneId, version) =>
    request(`/scene/${sceneId}/studio/version/${version}`, { method: 'DELETE' }),
};
