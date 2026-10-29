# Polyglot CLI

The portable CLI is a thin client of the existing FastAPI contracts:

```powershell
python cli/polyglot.py --help
python cli/polyglot.py --json --endpoint http://127.0.0.1:8000 doctor
python cli/polyglot.py capabilities
python cli/polyglot.py projects
python cli/polyglot.py verify PROJECT_ID --mode comprehensive
```

`POLYGLOT_API_URL` and `POLYGLOT_CONFIG` are supported. The current CLI
intentionally uses the backend's existing cookie/session boundary; it does not
store or print long-lived provider credentials. Commands return stable exit
codes: `0` success, `2` validation/API error, `3` authentication/authorization,
and `4` network failure. Unsupported operations remain explicit in API
capability responses.
