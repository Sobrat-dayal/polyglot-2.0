'use client';

import { useCallback, useRef, useState } from 'react';

export interface TranslationResult {
  id: string;
  generated_code: string;
  source_language: string;
  target_language: string;
  provider: string;
  model: string;
  explanation: string | null;
  warnings: string[];
  duration_ms: number;
}

export function useTranslation() {
  const [sourceCode, setSourceCode] = useState('');
  const [targetCode, setTargetCode] = useState('');
  const [sourceLang, setSourceLang] = useState('python');
  const [targetLang, setTargetLang] = useState('javascript');
  const [provider, setProvider] = useState('gemini');
  const [mode, setMode] = useState('standard');
  const [routingStrategy, setRoutingStrategy] = useState('manual');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<TranslationResult | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const handleTranslate = useCallback(async () => {
    if (!sourceCode.trim() || isLoading) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/translate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_code: sourceCode,
          source_lang: sourceLang,
          target_lang: targetLang,
          provider,
          strategy: routingStrategy,
          mode,
          include_explanation: true,
        }),
        signal: controller.signal,
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? 'Translation failed.');
      setTargetCode(body.generated_code);
      setResult(body);
    } catch (requestError) {
      if (requestError instanceof DOMException && requestError.name === 'AbortError') return;
      setError(requestError instanceof Error ? requestError.message : 'Translation failed.');
    } finally {
      if (!controller.signal.aborted) setIsLoading(false);
    }
  }, [isLoading, mode, provider, routingStrategy, sourceCode, sourceLang, targetLang]);

  const swapLanguages = useCallback(() => {
    setSourceLang(targetLang);
    setTargetLang(sourceLang);
    setSourceCode(targetCode);
    setTargetCode(sourceCode);
    setError(null);
  }, [sourceCode, sourceLang, targetCode, targetLang]);

  return {
    sourceCode, setSourceCode, targetCode, sourceLang, setSourceLang,
    targetLang, setTargetLang, provider, setProvider, mode, setMode,
    routingStrategy, setRoutingStrategy,
    isLoading, error, result, swapLanguages, handleTranslate,
  };
}
