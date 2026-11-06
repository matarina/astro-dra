"""Isolated native HTTP/settings integration; model/worker boundary is captured, never called."""
import json,sys,threading,os
assert os.environ.get("ASTRO_ACCOUNTS_ISOLATED_TEST") == "1", "Run only in an isolated preview with disposable users"
from unittest.mock import patch,MagicMock
from sqlalchemy import text
from local_deep_research.web.app_factory import create_app
from local_deep_research.database.auth_db import auth_db_session
from local_deep_research.database.encrypted_db import db_manager
from local_deep_research.database.session_context import get_user_db_session
from local_deep_research.database.models import Setting,ResearchHistory
from local_deep_research.database.models.active_research import UserActiveResearch
from local_deep_research.settings import SettingsManager
from astro_accounts.store import AccountStore
from local_deep_research.chat.routes import _load_settings
credentials=json.load(sys.stdin)
created=create_app();app=created[0] if isinstance(created,tuple) else created
app.config.update(TESTING=True,WTF_CSRF_ENABLED=False)
store=AccountStore();user=next(a for a in store.list_accounts() if a.username.startswith('test_user_'))
with store.connection(write=True) as setup:
 setup.execute("UPDATE astro_account_access SET role='user',review_state='none' WHERE user_id=?",(user.id,))
client=app.test_client()
r=client.post('/auth/login',data={'username':user.username,'password':credentials['password'],'remember':'true'})
assert r.status_code in (302,303)
assert client.get('/').status_code==200
poison={'llm.model':'untrusted-old-choice','llm.openai_endpoint.url':'http://forged.invalid/v1','search.iterations':99}
with get_user_db_session(user.username,credentials['password']) as db:
 for key,value in poison.items():
  row=db.query(Setting).filter_by(key=key).first();assert row is not None;row.value=value
 db.commit()
 manager=SettingsManager(db_session=db)
 actual={key:manager.get_setting(key) for key in poison}
 assert all(actual[key]!=value for key,value in poison.items()),'legacy config bypassed role policy'
 snapshot=manager.get_settings_snapshot()
 assert all(snapshot[key]!=value for key,value in poison.items())
 assert snapshot['llm.model']==actual['llm.model']
 assert manager.get_setting('llm')['model']==actual['llm.model']
 assert manager.get_all_settings(include_environment_overrides=False)['llm.model']['value']!=poison['llm.model']
from flask import session
with client.session_transaction() as logged: sid=logged['session_id']
with app.test_request_context('/'):
 session['username']=user.username;session['session_id']=sid
 chat=_load_settings(user.username)
assert chat['llm.model']['value']==actual['llm.model']
assert chat['search.iterations']['value']==actual['search.iterations']
fake=MagicMock();fake.ident=threading.get_ident()
with patch('local_deep_research.web.routes.research_routes.start_research_process',return_value=fake) as spawn:
 r=client.post('/api/start_research',json={'query':'A general research integration fixture','mode':'quick'})
 assert r.status_code==200,(r.status_code,r.get_json())
 assert spawn.call_count==1
 params=spawn.call_args.kwargs
 assert params['model']==actual['llm.model']
 assert params['iterations']==actual['search.iterations']
 assert params['custom_endpoint']==actual['llm.openai_endpoint.url']
 assert params['settings_snapshot']['llm.model']['value']!=poison['llm.model']
 rid=r.get_json()['research_id']
from local_deep_research.news.flask_api import _call_start_research_internal
from astro_accounts.policy import managed_subscription
with app.test_request_context('/news/api/subscriptions/fixture/run'):
 session['username']=user.username;session['session_id']=sid
 with patch('local_deep_research.web.routes.research_routes.start_research_process',return_value=fake) as internal_spawn:
  internal=_call_start_research_internal({'query':'A subscription fixture','mode':'quick','model':'forged','model_provider':'forged','strategy':'forged','search_engine':'forged','metadata':{'is_news_search':True}})
  assert internal.get('status')=='success',internal
  assert internal_spawn.call_args.kwargs['model']==actual['llm.model']
  assert internal_spawn.call_args.kwargs['search_engine']!='forged'
  internal_rid=internal['research_id']
assert managed_subscription(user.username,{'id':'fixture','model':'forged','search_engine':'forged'})['model'] is None
with get_user_db_session(user.username,credentials['password']) as db:
 db.query(UserActiveResearch).filter_by(research_id=internal_rid).delete()
 db.query(ResearchHistory).filter_by(id=internal_rid).delete();db.commit()
with get_user_db_session(user.username,credentials['password']) as db:
 db.query(UserActiveResearch).filter_by(research_id=rid).delete()
 db.query(ResearchHistory).filter_by(id=rid).delete();db.commit()
# Exercise the native registration compensation path: both user and role
# rows must disappear when encrypted DB creation fails.
with patch('local_deep_research.web.auth.routes.db_manager.create_user_database',side_effect=RuntimeError('isolated fixture')):
 failed=client.post('/auth/register',data={'username':'test_failed_creation','password':credentials['password'],'confirm_password':credentials['password'],'account_type':'admin','acknowledge':'true'})
 assert failed.status_code==500
with store.connection() as conn:
 assert not conn.execute("SELECT 1 FROM users WHERE username='test_failed_creation'").fetchone()
 assert conn.execute('SELECT count(*) FROM astro_account_access WHERE user_id NOT IN (SELECT id FROM users)').fetchone()[0]==0
# Existing sessions and settings manager reads must respect a role change.
with store.connection(write=True) as conn:
 conn.execute("UPDATE astro_account_access SET requested_role='admin',review_state='pending' WHERE user_id=?",(user.id,))
store.review('root',user.id,'approve')
with get_user_db_session(user.username,credentials['password']) as db:
 assert SettingsManager(db_session=db).get_setting('llm.model',check_env=False)==poison['llm.model']
store.review('root',user.id,'revoke')
with get_user_db_session(user.username,credentials['password']) as db:
 assert SettingsManager(db_session=db).get_setting('llm.model')==actual['llm.model']
with app.app_context():
 rules=[{'rule':str(rule),'endpoint':rule.endpoint,'methods':sorted(rule.methods)} for rule in app.url_map.iter_rules() if any(t in rule.endpoint for t in ['settings','metric','benchmark','config','embedding','admin'])]
print('ACCOUNTS_RUNTIME_RESULT '+json.dumps({'passed':True,'legacyOverrideIgnored':True,'namespaceReadManaged':True,'chatSnapshotManaged':True,'researchSubmissionManaged':True,'capturedSpawnCount':2,'internalSubscriptionManaged':True,'scheduledSubscriptionManaged':True,'registrationFailureCleanedUp':True,'settingsRecheckRole':True,'registeredConfigRoutes':rules}))
