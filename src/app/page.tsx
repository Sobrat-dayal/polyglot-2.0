'use client';

import { ArrowRightLeft, Copy, Download, FolderOpen, Moon, Plus, Search, Sparkles, Sun } from 'lucide-react';
import Editor from '@monaco-editor/react';
import { useState } from 'react';
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
          {selectedProject && <div className="file-browser"><div className="sidebar-heading"><span>Source snapshot</span></div><div className="file-search"><Search size={14} /><input placeholder="Filter files" value={fileSearch} onChange={(event) => setFileSearch(event.target.value)} /></div>{visibleFiles.map((file) => <button className="file-item" key={file.relative_path} onClick={async () => { const response = await fetch(`${apiUrl}/api/v1/projects/${selectedProject}/files/${file.relative_path}`); if (response.ok) translation.setSourceCode((await response.json()).content); }}><code>{file.relative_path}</code><small>{file.size_bytes} bytes</small></button>)}</div>}
        </aside>
        <div className="translator-pane">
        <div className="toolbar">
          <label>Source<select value={translation.sourceLang} onChange={(event) => translation.setSourceLang(event.target.value)}>{LANGUAGES.map((language) => <option key={language}>{language}</option>)}</select></label>
          <button className="swap" onClick={translation.swapLanguages} title="Swap languages"><ArrowRightLeft size={17} /></button>
          <label>Target<select value={translation.targetLang} onChange={(event) => translation.setTargetLang(event.target.value)}>{LANGUAGES.map((language) => <option key={language}>{language}</option>)}</select></label>
          <label>Provider<select value={translation.provider} onChange={(event) => translation.setProvider(event.target.value)}>{Object.keys(MODELS).map((name) => <option key={name}>{name}</option>)}</select></label>
          <label>Mode<select value={translation.mode} onChange={(event) => translation.setMode(event.target.value)}>{['standard', 'idiomatic', 'educational', 'modernize', 'type-safe', 'performance-oriented'].map((mode) => <option key={mode}>{mode}</option>)}</select></label>
          <button className="translate" disabled={translation.isLoading || !translation.sourceCode.trim()} onClick={translation.handleTranslate}>{translation.isLoading ? 'Translating…' : 'Translate'}</button>
        </div>
        <div className="model-note">Model: <code>{MODELS[translation.provider]}</code> · Credentials stay on the API server</div>
        <div className="editors">
          <div className="editor-panel"><div className="panel-title">Source · {translation.sourceLang}</div><Editor height="calc(100vh - 220px)" theme={dark ? 'vs-dark' : 'light'} language={translation.sourceLang} value={translation.sourceCode} onChange={(value) => translation.setSourceCode(value ?? '')} options={{ minimap: { enabled: false }, wordWrap: 'on', padding: { top: 12 }, fontSize: 14 }} /></div>
          <div className="editor-panel"><div className="panel-title">Output · {translation.targetLang}</div><Editor height="calc(100vh - 220px)" theme={dark ? 'vs-dark' : 'light'} language={translation.targetLang} value={translation.targetCode} options={{ readOnly: true, minimap: { enabled: false }, wordWrap: 'on', padding: { top: 12 }, fontSize: 14 }} /></div>
        </div>
        {translation.error && <div className="error" role="alert">{translation.error}<button onClick={translation.handleTranslate}>Retry</button></div>}
        {translation.result && <div className="result-bar"><span>{translation.result.provider} / {translation.result.model} · {translation.result.duration_ms} ms</span><span>{translation.result.explanation ?? 'Translation completed.'}</span></div>}
        <footer><button onClick={copyOutput} disabled={!translation.targetCode}><Copy size={15} />{copied ? 'Copied' : 'Copy output'}</button><button onClick={downloadOutput} disabled={!translation.targetCode}><Download size={15} />Download</button></footer>
        </div>
      </section>
    </main>
  );
}
