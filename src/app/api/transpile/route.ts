import { NextResponse } from 'next/server';

export async function POST() {
  return NextResponse.json(
    { detail: 'The legacy transpile endpoint was removed. Use /api/translate.' },
    { status: 410 },
  );
}
