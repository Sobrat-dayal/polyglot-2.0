import { NextResponse } from 'next/server';

const backendUrl = process.env.POLYGLOT_API_URL ?? 'http://127.0.0.1:8000';

export async function POST(request: Request) {
  try {
    const response = await fetch(`${backendUrl}/api/v1/translate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: await request.text(),
      signal: request.signal,
    });
    const body = await response.json();
    return NextResponse.json(body, { status: response.status });
  } catch {
    return NextResponse.json(
      { detail: 'Translation service is unavailable.' },
      { status: 503 },
    );
  }
}
