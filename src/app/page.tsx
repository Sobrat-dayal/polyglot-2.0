'use client';

import { ArrowRightLeft, Copy, Download, FolderOpen, Moon, Plus, Search, Sparkles, Sun } from 'lucide-react';
import Editor from '@monaco-editor/react';
import { useEffect, useState } from 'react';
import type { ChangeEvent } from 'react';
import { useTranslation } from '@/hooks/useTranslation';

const LANGUAGES = ['python', 'javascript', 'typescript', 'java', 'c', 'c++', 'c#', 'go', 'rust', 'php', 'ruby', 'kotlin', 'swift', 'dart'];
const MODELS: Record<string, string> = {
  gemini: 'gemini-2.5-flash',
  nvidia: 'qwen/qwen2.5-coder-32b-instruct',
  groq: 'qwen/qwen3-32b',
};

export default function PolyglotPage() {
  const [dark, setDark] = useState(true);
  const [copied, setCopied] = useState(false);
  const translation = useTranslation();
  const [projects, setProjects] = useState<Array<{ id: string; name: string; file_count: number; source_type: string }>>([]);
  const [selectedProject, setSelectedProject] = useState<string | null>(null);
  const [files, setFiles] = useState<Array<{ relative_path: string; size_bytes: number; selected: number }>>([]);
  const [fileSearch, setFileSearch] = useState('');
  const [account, setAccount] = useState<string | null>(null);
  const [aiModels, setAiModels] = useState<Array<{ provider: string; model: string; status: string }>>([]);
  const [analysis, setAnalysis] = useState<{ analysis_id: string; symbols: number; dependencies: number; apis: number } | null>(null);
  const [searchResults, setSearchResults] = useState<Array<{ path: string; line: number; text: string }>>([]);
  const [stackForge, setStackForge] = useState({ framework: 'fastapi', language: 'python', database: 'postgresql', architecture: 'modular_monolith', api: 'rest' });
  const [stackForgeResult, setStackForgeResult] = useState<{ state: string; issues: Array<{ severity: string; explanation: string }> } | null>(null);
  const [transmuteResult, setTransmuteResult] = useState<{ status: string; warnings: string[]; validation: { status: string } } | null>(null);
  const [migrationStatus, setMigrationStatus] = useState<{ id: string; status: string; task_count?: number; metrics?: { files_generated?: number } } | null>(null);
  const [reforgeStatus, setReforgeStatus] = useState<{ status: string; operation: string } | null>(null);
  const [guardianStatus, setGuardianStatus] = useState<{ status: string; id: string } | null>(null);
  const apiUrl = process.env.NEXT_PUBLIC_POLYGLOT_API_URL ?? 'http://127.0.0.1:8000';
  const loadProjects = async () => {
    const response = await fetch(`${apiUrl}/api/v1/projects`);
    if (response.ok) setProjects(await response.json());
  };
  const openProject = async (id: string) => {
    setSelectedProject(id);
    const response = await fetch(`${apiUrl}/api/v1/projects/${id}/files`);
    if (response.ok) setFiles((await response.json()).files);
  };
  const createProject = async () => {
    const name = window.prompt('Project name');
    if (!name?.trim()) return;
    await fetch(`${apiUrl}/api/v1/projects`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    await loadProjects();
  };
  const importZip = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const response = await fetch(`${apiUrl}/api/v1/projects/import/zip?filename=${encodeURIComponent(file.name)}`, { method: 'POST', body: file });
    if (response.ok) await loadProjects();
    event.target.value = '';
  };
  const importGitHub = async () => {
    const repository = window.prompt('GitHub repository (owner/name or HTTPS URL)');
    if (!repository?.trim()) return;
    const response = await fetch(`${apiUrl}/api/v1/projects/import/github`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repository }),
    });
    if (response.ok) await loadProjects();
  };
  const signIn = async () => {
    const email = window.prompt('Email');
    const password = email ? window.prompt('Password (12+ characters)') : null;
    if (!email || !password) return;
    const response = await fetch(`${apiUrl}/api/v1/auth/login`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      credentials: 'include', body: JSON.stringify({ email, password }),
    });
    if (response.ok) setAccount(email);
  };
  const register = async () => {
    const email = window.prompt('Email for new account');
    const password = email ? window.prompt('Password (12+ characters)') : null;
    if (!email || !password) return;
    const response = await fetch(`${apiUrl}/api/v1/auth/register`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      credentials: 'include', body: JSON.stringify({ email, password }),
    });
    if (response.ok) setAccount(email);
  };
  const visibleFiles = files.filter((file) => file.relative_path.toLowerCase().includes(fileSearch.toLowerCase()));
  const runDeepScan = async () => {
    if (!selectedProject) return;
    const response = await fetch(`${apiUrl}/api/v1/projects/${selectedProject}/analysis`, { method: 'POST' });
    if (response.ok) setAnalysis(await response.json());
  };
  const searchCode = async () => {
    if (!selectedProject) return;
    const query = window.prompt('Search project source');
    if (!query?.trim()) return;
    const response = await fetch(`${apiUrl}/api/v1/projects/${selectedProject}/code-search`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query }),
    });
    if (response.ok) setSearchResults((await response.json()).matches);
  };
  const validateStack = async () => {
    if (!selectedProject) return;
    const target = {
      name: 'StackForge target',
      source_analysis_id: analysis?.analysis_id,
      architecture: stackForge.architecture,
      services: [{ id: 'api', name: 'API', language: stackForge.language, framework: stackForge.framework, api_protocol: stackForge.api, database_ids: ['primary'] }],
      databases: [{ id: 'primary', engine: stackForge.database }],
    };
    const response = await fetch(`${apiUrl}/api/v1/projects/${selectedProject}/stackforge/validate`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(target),
    });
    if (response.ok) setStackForgeResult(await response.json());
  };
  const saveStack = async () => {
    if (!selectedProject) return;
    const target = {
      name: 'StackForge target',
      source_analysis_id: analysis?.analysis_id,
      architecture: stackForge.architecture,
      services: [{ id: 'api', name: 'API', language: stackForge.language, framework: stackForge.framework, api_protocol: stackForge.api, database_ids: ['primary'] }],
      databases: [{ id: 'primary', engine: stackForge.database }],
    };
    const response = await fetch(`${apiUrl}/api/v1/projects/${selectedProject}/stackforge/configurations`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(target),
    });
    if (response.ok) setStackForgeResult(await response.json());
  };
  const runTransmute = async () => {
    if (!translation.sourceCode.trim()) return;
    const response = await fetch(`${apiUrl}/api/v1/transmute/translate`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source_code: translation.sourceCode, source_language: translation.sourceLang,
        target_language: translation.targetLang, mode: 'type-safe', validate: true,
      }),
    });
    if (response.ok) {
      const result = await response.json();
      translation.setTargetCode(result.generated_code);
      setTransmuteResult(result);
    }
  };
  const startMigration = async () => {
    if (!selectedProject || !analysis) return;
    const configurations = await fetch(`${apiUrl}/api/v1/projects/${selectedProject}/stackforge/configurations`);
    if (!configurations.ok) return;
    const versions = await configurations.json();
    const configuration = versions[0];
    if (!configuration) return;
    const response = await fetch(`${apiUrl}/api/v1/projects/${selectedProject}/metamorphosis`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: selectedProject, configuration_id: configuration.id, source_analysis_id: analysis.analysis_id, mode: 'selected', selected_paths: visibleFiles.map((file) => file.relative_path), source_language: translation.sourceLang, target_language: translation.targetLang }),
    });
    if (response.ok) {
      const created = await response.json();
      const executed = await fetch(`${apiUrl}/api/v1/metamorphosis/${created.id}/execute`, { method: 'POST' });
      if (executed.ok) setMigrationStatus(await executed.json());
    }
  };
  const generateReforgeContract = async () => {
    if (!selectedProject) return;
    const response = await fetch(`${apiUrl}/api/v1/projects/${selectedProject}/reforge`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: selectedProject, operation: 'api', mode: 'generate', target: 'graphql', source: 'GET /health', require_approval: true }),
    });
    if (response.ok) {
      const result = await response.json();
      setReforgeStatus({ status: result.status, operation: 'REST → GraphQL contract' });
    }
  };
  const runGuardian = async () => {
    if (!selectedProject) return;
    const response = await fetch(`${apiUrl}/api/v1/projects/${selectedProject}/guardian`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: selectedProject, mode: 'comprehensive', required_quality_gates: ['static_validation', 'test_discovery'] }),
    });
    if (response.ok) {
      const result = await response.json();
      setGuardianStatus({ status: result.status, id: result.id });
    }
  };
  useEffect(() => {
    fetch(`${apiUrl}/api/v1/ai/models`).then((response) => response.ok ? response.json() : []).then(setAiModels).catch(() => setAiModels([]));
  }, [apiUrl]);
  const copyOutput = async () => {
    await navigator.clipboard.writeText(translation.targetCode);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };
  const downloadOutput = () => {
    const blob = new Blob([translation.targetCode], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `translated.${translation.targetLang === 'c++' ? 'cpp' : translation.targetLang}`;
    anchor.click();
    URL.revokeObjectURL(url);
  };
  return (
    <main className={dark ? 'app dark' : 'app'}>
      <header className="topbar">
        <div className="brand"><Sparkles size={18} /><strong>Polyglot 2.0</strong><span>AI code translation</span></div>
        <div className="header-actions"><button className="account-button" onClick={account ? undefined : signIn}>{account ?? 'Sign in'}</button>{!account && <button className="account-button" onClick={register}>Register</button>}<button className="icon-button" onClick={() => setDark(!dark)} aria-label="Toggle theme">{dark ? <Sun size={18} /> : <Moon size={18} />}</button></div>
      </header>
      <section className="workspace">
        <aside className="project-sidebar">
          <div className="sidebar-heading"><span>Projects</span><button className="icon-button" onClick={createProject} title="Create project"><Plus size={16} /></button></div>
          <button className="load-projects" onClick={loadProjects}><FolderOpen size={15} /> Load projects</button>
          <label className="import-button">Import ZIP<input type="file" accept=".zip,application/zip" onChange={importZip} /></label>
          <button className="import-button" onClick={importGitHub}>Import GitHub</button>
          {projects.map((project) => <button className={`project-item ${selectedProject === project.id ? 'active' : ''}`} key={project.id} onClick={() => openProject(project.id)}><strong>{project.name}</strong><small>{project.file_count} files · {project.source_type}</small></button>)}
          {selectedProject && <div className="file-browser"><div className="sidebar-heading"><span>Source snapshot</span></div><button className="import-button" onClick={runDeepScan}>Run DeepScan</button><button className="import-button" onClick={searchCode}>Search source</button><button className="import-button" onClick={runGuardian}>Run Guardian static verification</button>{analysis && <div className="analysis-summary"><strong>Analysis complete</strong><small>{analysis.symbols} symbols · {analysis.dependencies} dependencies · {analysis.apis} APIs</small></div>}<div className="stackforge"><div className="sidebar-heading"><span>StackForge target</span></div><select value={stackForge.language} onChange={(event) => setStackForge({ ...stackForge, language: event.target.value })}><option value="python">Python</option><option value="typescript">TypeScript</option><option value="go">Go</option><option value="java">Java</option></select><select value={stackForge.framework} onChange={(event) => setStackForge({ ...stackForge, framework: event.target.value })}><option value="fastapi">FastAPI</option><option value="express">Express</option><option value="nestjs">NestJS</option><option value="spring-boot">Spring Boot</option></select><select value={stackForge.database} onChange={(event) => setStackForge({ ...stackForge, database: event.target.value })}><option value="postgresql">PostgreSQL</option><option value="mysql">MySQL</option><option value="mongodb">MongoDB</option></select><select value={stackForge.architecture} onChange={(event) => setStackForge({ ...stackForge, architecture: event.target.value })}><option value="modular_monolith">Modular monolith</option><option value="microservices">Microservices</option><option value="event_driven">Event-driven</option></select><button className="import-button" onClick={validateStack}>Validate target</button><button className="import-button" onClick={saveStack}>Save version</button><button className="import-button" onClick={generateReforgeContract}>Generate GraphQL contract</button>{analysis && <button className="import-button" onClick={startMigration}>Run Metamorphosis</button>}{stackForgeResult && <div className="analysis-summary"><strong>{stackForgeResult.state}</strong>{stackForgeResult.issues.map((issue) => <small key={issue.explanation}>{issue.severity}: {issue.explanation}</small>)}</div>}{migrationStatus && <div className="analysis-summary"><strong>Migration {migrationStatus.status}</strong><small>{migrationStatus.metrics?.files_generated ?? 0} files generated</small></div>}{reforgeStatus && <div className="analysis-summary"><strong>Reforge {reforgeStatus.status}</strong><small>{reforgeStatus.operation} requires review</small></div>}{guardianStatus && <div className="analysis-summary"><strong>Guardian {guardianStatus.status}</strong><small>Evidence {guardianStatus.id.slice(0, 8)} · dynamic execution not performed</small></div>}</div><div className="file-search"><Search size={14} /><input placeholder="Filter files" value={fileSearch} onChange={(event) => setFileSearch(event.target.value)} /></div>{visibleFiles.map((file) => <button className="file-item" key={file.relative_path} onClick={async () => { const response = await fetch(`${apiUrl}/api/v1/projects/${selectedProject}/files/${file.relative_path}`); if (response.ok) translation.setSourceCode((await response.json()).content); }}><code>{file.relative_path}</code><small>{file.size_bytes} bytes</small></button>)}{searchResults.map((match) => <button className="file-item" key={`${match.path}:${match.line}`} onClick={() => setFileSearch(match.path)}><code>{match.path}:{match.line}</code><small>{match.text}</small></button>)}</div>}
        </aside>
        <div className="translator-pane">
        <div className="toolbar">
          <label>Source<select value={translation.sourceLang} onChange={(event) => translation.setSourceLang(event.target.value)}>{LANGUAGES.map((language) => <option key={language}>{language}</option>)}</select></label>
          <button className="swap" onClick={translation.swapLanguages} title="Swap languages"><ArrowRightLeft size={17} /></button>
          <label>Target<select value={translation.targetLang} onChange={(event) => translation.setTargetLang(event.target.value)}>{LANGUAGES.map((language) => <option key={language}>{language}</option>)}</select></label>
          <label>Provider<select value={translation.provider} onChange={(event) => translation.setProvider(event.target.value)}>{Object.keys(MODELS).map((name) => <option key={name}>{name}</option>)}</select></label>
          <label>Mode<select value={translation.mode} onChange={(event) => translation.setMode(event.target.value)}>{['standard', 'idiomatic', 'educational', 'modernize', 'type-safe', 'performance-oriented'].map((mode) => <option key={mode}>{mode}</option>)}</select></label>
          <label>Routing<select value={translation.routingStrategy} onChange={(event) => translation.setRoutingStrategy(event.target.value)}>{['manual', 'balanced', 'fast', 'economy', 'quality', 'local_only'].map((strategy) => <option key={strategy}>{strategy}</option>)}</select></label>
          <button className="translate" disabled={translation.isLoading || !translation.sourceCode.trim()} onClick={translation.handleTranslate}>{translation.isLoading ? 'Translating…' : 'Translate'}</button>
          <button className="translate transmute-button" disabled={!translation.sourceCode.trim()} onClick={runTransmute}>Transmute</button>
        </div>
        <div className="model-note">Model: <code>{MODELS[translation.provider]}</code> · {aiModels.filter((model) => model.provider === translation.provider).length} discovered · Routing: {translation.routingStrategy} · Credentials stay on the API server</div>
        <div className="editors">
          <div className="editor-panel"><div className="panel-title">Source · {translation.sourceLang}</div><Editor height="calc(100vh - 220px)" theme={dark ? 'vs-dark' : 'light'} language={translation.sourceLang} value={translation.sourceCode} onChange={(value) => translation.setSourceCode(value ?? '')} options={{ minimap: { enabled: false }, wordWrap: 'on', padding: { top: 12 }, fontSize: 14 }} /></div>
          <div className="editor-panel"><div className="panel-title">Output · {translation.targetLang}</div><Editor height="calc(100vh - 220px)" theme={dark ? 'vs-dark' : 'light'} language={translation.targetLang} value={translation.targetCode} options={{ readOnly: true, minimap: { enabled: false }, wordWrap: 'on', padding: { top: 12 }, fontSize: 14 }} /></div>
        </div>
        {translation.error && <div className="error" role="alert">{translation.error}<button onClick={translation.handleTranslate}>Retry</button></div>}
        {translation.result && <div className="result-bar"><span>{translation.result.provider} / {translation.result.model} · {translation.result.duration_ms} ms</span><span>{translation.result.explanation ?? 'Translation completed.'}</span></div>}
        {transmuteResult && <div className="result-bar"><span>Transmute · {transmuteResult.status}</span><span>Validation: {transmuteResult.validation.status}{transmuteResult.warnings.length ? ` · ${transmuteResult.warnings.length} warning(s)` : ''}</span></div>}
        <footer><button onClick={copyOutput} disabled={!translation.targetCode}><Copy size={15} />{copied ? 'Copied' : 'Copy output'}</button><button onClick={downloadOutput} disabled={!translation.targetCode}><Download size={15} />Download</button></footer>
        </div>
      </section>
    </main>
  );
}
