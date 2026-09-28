"""Test Site authorization with an ephemeral account, then delete that account."""

import secrets
from urllib.parse import urlparse

from deploy_appwrite import DeployError, command


def verify_access(origin, directory, env):
    from playwright.sync_api import sync_playwright

    parsed = urlparse(origin)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.path not in ('', '/'):
        raise DeployError('Use a Site origin without a path for --site-url.')
    if parsed.scheme != 'https' and not parsed.hostname.endswith('.localhost') and parsed.hostname not in ('localhost', '127.0.0.1'):
        raise DeployError('Production Site verification requires HTTPS.')
    origin = origin.rstrip('/')
    ident = 'verify-' + secrets.token_hex(12)
    password = secrets.token_urlsafe(32)
    email = ident + '@example.invalid'
    created = False
    try:
        command(['users', 'create', '--user-id', ident, '--email', email, '--password', password,
                 '--name', 'Temporary deployment verification'], directory, env, private_values=(password,))
        created = True
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            page.goto(origin + '/dashboard', wait_until='networkidle', timeout=120000)
            if urlparse(page.url).path != '/login':
                raise DeployError('Anonymous dashboard access was not denied.')
            result = page.evaluate('''async credentials => {
                const response = await fetch('/api/auth/login', {method: 'POST',
                    headers: {'Content-Type': 'application/json'}, body: JSON.stringify(credentials)});
                return response.status;
            }''', {'email': email, 'password': password})
            if result != 403:
                raise DeployError('A non-admin account was not denied.')
            command(['users', 'update-labels', '--user-id', ident, '--labels', 'admin'], directory, env)
            result = page.evaluate('''async credentials => {
                const response = await fetch('/api/auth/login', {method: 'POST',
                    headers: {'Content-Type': 'application/json'}, body: JSON.stringify(credentials)});
                return response.status;
            }''', {'email': email, 'password': password})
            if result != 200:
                raise DeployError('Admin sign-in did not succeed.')
            for route, heading in (('/dashboard', 'Dashboard'), ('/system', 'System')):
                page.goto(origin + route, wait_until='networkidle', timeout=120000)
                if not page.get_by_role('heading', name=heading, exact=False).count():
                    raise DeployError(route + ' did not load authenticated data.')
            calls = command(['tablesdb', 'list-rows', '--database-id', 'call_grader', '--table-id', 'calls',
                             '--limit', '100', '--sort-desc', 'actual_started_at'], directory, env, json_output=True).get('rows', [])
            audio_call = next((call for call in calls if call.get('recording_storage_file_id') and not call.get('recording_deleted_at')), None)
            audio_path = '/api/proxy-audio/' + (audio_call['$id'] if audio_call else 'verification-no-recording')
            if audio_call:
                result = page.evaluate('''async path => {
                    const response = await fetch(path);
                    return {status: response.status, type: response.headers.get('content-type'),
                            bytes: (await response.arrayBuffer()).byteLength};
                }''', audio_path)
                if result['status'] != 200 or not result['type'].startswith('audio/') or result['bytes'] < 1000:
                    raise DeployError('Private recording playback failed.')
                print('PASS: admin-only private recording playback.', flush=True)
            else:
                print('SKIP: playback requires a real ingested recording; none is available in this project.', flush=True)
            command(['users', 'update-labels', '--user-id', ident, '--labels', 'revoked'], directory, env)
            status = page.evaluate('async path => (await fetch(path)).status', audio_path)
            if status != 403:
                raise DeployError('Revoking the admin label did not immediately deny recording access.')
            browser.close()
        print('PASS: anonymous/non-admin denial, admin sign-in, Dashboard/System, immediate label revocation.', flush=True)
    except DeployError:
        raise
    except Exception as exc:
        # Browser exceptions can include request cookies. Never print their trace.
        raise DeployError('Site access verification failed (' + type(exc).__name__ + ').') from None
    finally:
        if created:
            command(['users', 'delete', '--user-id', ident, '--force'], directory, env)
            print('Removed temporary verification account.', flush=True)
