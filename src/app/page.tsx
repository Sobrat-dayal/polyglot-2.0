'use client';

import { ArrowRightLeft, Copy, Download, Moon, Sparkles, Sun } from 'lucide-react';
import Editor from '@monaco-editor/react';
import { useState } from 'react';
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
        <button className="icon-button" onClick={() => setDark(!dark)} aria-label="Toggle theme">{dark ? <Sun size={18} /> : <Moon size={18} />}</button>
      </header>
      <section className="workspace">
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
      </section>
    </main>
  );
}
