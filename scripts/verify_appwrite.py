"""Verify deployed Appwrite resources without invoking Jazz or billed AI work."""

import json
import sys
import tempfile
from pathlib import Path

from deploy_appwrite import ROOT, DeployError, command, configuration, execute

sys.path.insert(0, str(ROOT / 'services/backend'))
from app.appwrite.schema import TABLES


def require(condition, message):
    if not condition:
        raise DeployError('Verification failed: ' + message)


def verify_resources(directory, env, private_values, *, paused=False):
    template = json.loads((ROOT / 'appwrite.config.json').read_text())
    for expected in template['functions']:
        ident = expected['$id']
        actual = command(['functions', 'get', '--function-id', ident], directory, env, json_output=True)
        require(actual.get('enabled') and actual.get('deploymentId'), ident + ' has no enabled active deployment')
        require(not actual.get('execute') and not actual.get('events'), ident + ' must be private')
        require(actual.get('schedule', '') == ('' if paused else expected['schedule']), ident + ' schedule differs')
        scopes = expected['scopes'] if paused or ident != 'call-grader-bootstrap' else ['databases.read']
        require(set(actual.get('scopes', [])) == set(scopes), ident + ' scopes differ')
        for key in ('runtime', 'timeout', 'entrypoint', 'commands', 'deploymentRetention'):
            require(actual.get(key) == expected[key], ident + ' ' + key + ' differs')
        deployment = command(['functions', 'get-deployment', '--function-id', ident,
                              '--deployment-id', actual['deploymentId']], directory, env, json_output=True)
        require(deployment.get('status') == 'ready', ident + ' build is not ready')
        variables = command(['functions', 'list-variables', '--function-id', ident, '--limit', '100'],
                            directory, env, json_output=True)['variables']
        keys = {item['key'] for item in variables}
        needed = {'APPWRITE_ENDPOINT', 'APPWRITE_PROJECT_ID', 'APPWRITE_SYNC_FUNCTION_ID', 'APPWRITE_WORKER_FUNCTION_ID'}
        if ident in ('call-grader-sync', 'call-grader-worker'):
            needed |= {'JAZZ_UAN', 'JAZZ_PASSWORD'}
        if ident == 'call-grader-worker':
            needed.add('OPENAI_API_KEY')
        if ident == 'call-grader-api':
            needed.add('INTERNAL_API_TOKEN')
        require(needed <= keys, ident + ' is missing environment variables')
    print('PASS: six private Functions, active builds, role scopes, variables and Karachi schedules.', flush=True)
    for ident, spec in TABLES.items():
        table = command(['tablesdb', 'get-table', '--database-id', 'call_grader', '--table-id', ident],
                        directory, env, json_output=True)
        require(table.get('enabled') and not table.get('$permissions'), ident + ' must be enabled and private')
        columns = command(['tablesdb', 'list-columns', '--database-id', 'call_grader', '--table-id', ident, '--limit', '100'],
                          directory, env, json_output=True)['columns']
        available = {item['key'] for item in columns if item.get('status') == 'available'}
        require({item['key'] for item in spec['attributes']} <= available, ident + ' columns are unavailable')
        indexes = command(['tablesdb', 'list-indexes', '--database-id', 'call_grader', '--table-id', ident],
                          directory, env, json_output=True)['indexes']
        available = {item['key'] for item in indexes if item.get('status') == 'available'}
        require({item['key'] for item in spec.get('indexes', [])} <= available, ident + ' indexes are unavailable')
    bucket = command(['storage', 'get-bucket', '--bucket-id', 'call_recordings'], directory, env, json_output=True)
    require(bucket.get('enabled') and not bucket.get('$permissions') and not bucket.get('fileSecurity'),
            'recording bucket permits client access or is disabled')
    print('PASS: ten private tables, all required columns/indexes, private recording bucket.', flush=True)
    expected = template['sites'][0]
    site = command(['sites', 'get', '--site-id', expected['$id']], directory, env, json_output=True)
    require(site.get('enabled') and site.get('deploymentId'), 'Site has no active deployment')
    for key in ('framework', 'adapter', 'buildRuntime', 'installCommand', 'buildCommand', 'outputDirectory'):
        require(site.get(key) == expected[key], 'Site ' + key + ' differs')
    require(set(site.get('scopes', [])) == set(expected['scopes']), 'Site server scopes differ')
    build = command(['sites', 'get-deployment', '--site-id', expected['$id'], '--deployment-id', site['deploymentId']],
                    directory, env, json_output=True)
    require(build.get('status') == 'ready', 'Site build is not ready')
    variables = command(['sites', 'list-variables', '--site-id', expected['$id'], '--limit', '100'],
                        directory, env, json_output=True)['variables']
    require({'APPWRITE_BACKEND_FUNCTION_ID', 'APPWRITE_ENDPOINT', 'APPWRITE_PROJECT_ID', 'INTERNAL_API_TOKEN'}
            <= {item['key'] for item in variables}, 'Site is missing connection variables')
    print('PASS: Next.js SSR Site build, scoped credentials and private API connection variables.', flush=True)


def verify(args):
    values, env = configuration(args)
    with tempfile.TemporaryDirectory(prefix='call-grader-verify-') as temporary:
        directory = Path(temporary)
        (directory / 'appwrite.config.json').write_text(json.dumps({
            'projectId': values['APPWRITE_PROJECT_ID'], 'endpoint': values['APPWRITE_ENDPOINT']}))
        verify_resources(directory, env, tuple(values.values()))
        result = execute('call-grader-api', {}, directory, env, tuple(values.values()), readiness=True)
        require(result.get('ok') is True and result.get('appwrite') is True, 'API cannot read its database')
        print('PASS: deployed API reads Appwrite successfully.', flush=True)
        for ident in ('call-grader-worker', 'call-grader-sync', 'call-grader-catchup'):
            result = execute(ident, {'action': 'runtime-check'}, directory, env, tuple(values.values()))
            require(all(result.get(key) for key in ('pipeline_import', 'chromium', 'ffmpeg', 'ffprobe')),
                    ident + ' native tools failed')
            print('PASS: ' + ident + ' private execution and native runtime.', flush=True)
        if getattr(args, 'site_url', None):
            from verify_site_access import verify_access
            verify_access(args.site_url, directory, env)
        if getattr(args, 'fresh_schema', False):
            from verify_bootstrap import verify_fresh_schema
            verify_fresh_schema(args)
    print('Deployment verification passed. Check admin sign-in and playback at the selected Site domain.')
    print('This check does not call OpenAI; valid credentials with funded API quota are required for fresh AI results.')
