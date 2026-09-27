"""Exercise first-install schema provisioning on disposable local Appwrite resources."""

import json
import secrets

from deploy_appwrite import ROOT, DeployError


def verify_fresh_schema(args):
    if not args.local:
        raise DeployError('--fresh-schema is restricted to the linked local project.')
    from appwrite.client import Client
    from appwrite.services.storage import Storage
    from appwrite.services.tables_db import TablesDB
    from bootstrap_appwrite import TABLES, ensure_bucket, ensure_table, seed, wait_available
    from dotenv import dotenv_values

    values = dotenv_values(ROOT / '.env')
    if not values.get('APPWRITE_API_KEY'):
        raise DeployError('Fresh local schema test requires the existing private local APPWRITE_API_KEY.')
    project = json.loads(args.config.read_text())['APPWRITE_PROJECT_ID']
    client = Client().set_endpoint('http://localhost/v1').set_project(project).set_key(values['APPWRITE_API_KEY'])
    tables, storage = TablesDB(client), Storage(client)
    ident = 'verify-' + secrets.token_hex(12)
    db_created = False
    try:
        tables.create(database_id=ident, name='Disposable schema verification')
        db_created = True
        for table_id, spec in TABLES.items():
            ensure_table(tables, ident, table_id, spec)
            wait_available(tables, ident, table_id, 'indexes', spec.get('indexes', []))
        ensure_bucket(storage, ident)
        seed(tables, ident)
        # A second bootstrap must preserve seeds and avoid conflicts.
        for table_id, spec in TABLES.items():
            ensure_table(tables, ident, table_id, spec)
        seed(tables, ident)
        print('PASS: fresh ten-table schema/index/bucket provisioning and idempotent seeds.', flush=True)
    finally:
        if db_created:
            tables.delete(database_id=ident)
        try:
            storage.delete_bucket(bucket_id=ident)
        except Exception as exc:
            if getattr(exc, 'code', None) != 404:
                raise
        print('Removed disposable schema resources; existing calls and recordings were preserved.', flush=True)
