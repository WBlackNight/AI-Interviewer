import io
from datetime import timedelta
import pytest
from PIL import Image,PngImagePlugin
from sqlalchemy import select
from app.config import Settings
from app.models.entities import Account,AccountProfile,AuthChallenge
from app.services.accounts import AuthThrottle,now_utc
from app.services import account_security as security
from tests.test_ws_recovery import api
from tests.auth_helpers import register

PASSWORD='synthetic-password-2026'
NEW='another-password-2026'

def headers(user):return {'Authorization':'Bearer '+user['access_token']}
def payload(client,**changes):
    captcha=client.get('/api/auth/captcha').json()
    return dict(username='new_user',password=PASSWORD,password_confirm=PASSWORD,captcha_id=captcha['captcha_id'],captcha_code='TEST2',**changes)

def test_registration_requires_confirmation_and_real_single_use_captcha(api):
    client,factory=api
    assert client.post('/api/auth/register',json={'username':'new_user','password':PASSWORD}).status_code==422
    body=payload(client);body['password_confirm']=NEW
    assert client.post('/api/auth/register',json=body).json()['detail']=='两次输入的密码不一致'
    body['password_confirm']=PASSWORD;body['captcha_code']='WRONG'
    assert client.post('/api/auth/register',json=body).status_code==400
    body['captcha_code']='test2'
    result=client.post('/api/auth/register',json=body);assert result.status_code==200
    assert client.post('/api/auth/register',json=body).status_code==400
    duplicate=payload(client);duplicate['username']='NEW_USER'
    assert client.post('/api/auth/register',json=duplicate).status_code==409
    assert client.get('/api/auth/username-availability?username=NEW_USER').json()=={'available':False}
    with factory() as db:
        challenge=db.get(AuthChallenge,body['captcha_id']);assert 'TEST2' not in challenge.secret_hash

def test_captcha_expires_and_attempt_limit_persists(api):
    client,factory=api;body=payload(client)
    for _ in range(5):
        body['captcha_code']='WRONG';assert client.post('/api/auth/register',json=body).status_code==400
    body['captcha_code']='TEST2';assert client.post('/api/auth/register',json=body).status_code==400
    body=payload(client)
    with factory() as db:db.get(AuthChallenge,body['captcha_id']).expires_at=now_utc()-timedelta(seconds=1);db.commit()
    assert client.post('/api/auth/register',json=body).status_code==400

def test_profile_validation_isolation_and_legacy_account(api):
    client,factory=api
    a=register(client,json={'username':'user_a','password':PASSWORD}).json()
    b=register(client,json={'username':'user_b','password':PASSWORD}).json()
    assert client.patch('/api/account/profile',json={'nickname':'Test'}).status_code==401
    for name in ['',' '*3,'a'*33,'name\ncontrol']:
        assert client.patch('/api/account/profile',headers=headers(a),json={'nickname':name}).status_code==422
    name='<span>小明</span>'
    assert client.patch('/api/account/profile',headers=headers(a),json={'nickname':name}).json()['nickname']==name
    assert client.get('/api/auth/me',headers=headers(b)).json()['nickname']==''
    assert client.get('/api/auth/me',headers=headers(a)).json()['nickname']==name
    with factory() as db:assert db.get(Account,a['account']['id']).username=='user_a'

def image_bytes(format='PNG',size=(100,80)):
    out=io.BytesIO();img=Image.new('RGB',size,'#497958')
    if format=='PNG':
        meta=PngImagePlugin.PngInfo();meta.add_text('private','private-metadata');img.save(out,format=format,pnginfo=meta)
    else:img.save(out,format=format)
    return out.getvalue()

@pytest.mark.parametrize('format,media',[('PNG','image/png'),('JPEG','image/jpeg'),('WEBP','image/webp')])
def test_avatar_decoding_transcoding_and_owner_only(api,format,media):
    client,_=api;a=register(client,json={'username':'avatar_a','password':PASSWORD}).json();b=register(client,json={'username':'avatar_b','password':PASSWORD}).json()
    assert client.post('/api/account/avatar',content=image_bytes(format),headers={**headers(a),'Content-Type':media}).status_code==200
    response=client.get('/api/account/avatar',headers=headers(a));assert response.headers['cache-control']=='no-store'
    with Image.open(io.BytesIO(response.content)) as result:assert result.size==(256,256) and result.format=='PNG' and 'private' not in result.info
    assert b'private-metadata' not in response.content
    assert client.get('/api/account/avatar').status_code==401
    assert client.get('/api/account/avatar',headers=headers(b)).status_code==404
    assert client.delete('/api/account/avatar',headers=headers(a)).json()['avatar_version'] is None

@pytest.mark.parametrize('data,media,status',[(b'<svg/>','image/svg+xml',415),(b'x'*2097153,'image/png',413),(b'bad','image/png',422),(image_bytes('PNG',(16,16)),'image/png',422),(image_bytes('PNG'),'image/jpeg',422)],ids=['svg','oversize','corrupt','small','mismatch'])
def test_avatar_rejects_invalid_uploads(api,data,media,status):
    client,_=api;user=register(client,json={'username':'avatar_user','password':PASSWORD}).json()
    assert client.post('/api/account/avatar',content=data,headers={**headers(user),'Content-Type':media}).status_code==status

@pytest.fixture
def mail_api(api,monkeypatch):
    from app.api import account_profile
    client,factory=api;settings=Settings(_env_file=None,mail_mode='local_test',smtp_security='none')
    monkeypatch.setattr(account_profile,'get_settings',lambda:settings)
    sent=[];monkeypatch.setattr(security,'send_code',lambda settings,address,code,purpose:sent.append((address,code,purpose)))
    user=register(client,json={'username':'email_user','password':PASSWORD}).json()
    return client,factory,user,sent

def bind(mail_api):
    client,factory,user,sent=mail_api
    data={'purpose':'email_bind','email':'demo@example.test','current_password':PASSWORD}
    result=client.post('/api/account/email/code',json=data,headers=headers(user));assert result.status_code==200,result.text
    return data,result.json()['challenge_id'],sent[-1][1]

def test_email_verification_wrong_code_cooldown_and_one_time(mail_api):
    client,factory,user,sent=mail_api;data,identifier,code=bind(mail_api)
    assert code not in client.get('/api/auth/me',headers=headers(user)).text
    assert client.post('/api/account/email/code',json=data,headers=headers(user)).status_code==429
    assert client.post('/api/account/email/confirm',json={**data,'challenge_id':identifier,'code':'not-code'},headers=headers(user)).status_code==422
    wrong='000000' if code!='000000' else '111111'
    assert client.post('/api/account/email/confirm',json={**data,'challenge_id':identifier,'code':wrong},headers=headers(user)).status_code==400
    confirmed=client.post('/api/account/email/confirm',json={**data,'challenge_id':identifier,'code':code},headers=headers(user))
    assert confirmed.json()['email']=='demo@example.test' and confirmed.json()['email_verified']
    assert client.post('/api/account/email/confirm',json={**data,'challenge_id':identifier,'code':code},headers=headers(user)).status_code==400

def test_password_change_reauth_email_and_all_old_sessions_revoked(mail_api):
    client,factory,user,sent=mail_api;data,identifier,code=bind(mail_api)
    assert client.post('/api/account/email/confirm',json={**data,'challenge_id':identifier,'code':code},headers=headers(user)).status_code==200
    other=client.post('/api/auth/login',json={'username':'email_user','password':PASSWORD}).json()
    body={'current_password':PASSWORD,'new_password':NEW,'password_confirm':NEW}
    assert client.post('/api/account/password',json={**body,'password_confirm':PASSWORD},headers=headers(user)).status_code==422
    assert client.post('/api/account/password',json={**body,'current_password':'wrong-password-2026'},headers=headers(user)).status_code==403
    assert client.post('/api/account/password',json=body,headers=headers(user)).status_code==422
    with factory() as db:
        for row in db.scalars(select(AuthChallenge).where(AuthChallenge.account_id==user['account']['id'])):row.created_at-=timedelta(seconds=61)
        db.commit()
    otp=client.post('/api/account/email/code',json={'purpose':'password_change','current_password':PASSWORD},headers=headers(user)).json()
    changed=client.post('/api/account/password',json={**body,'challenge_id':otp['challenge_id'],'code':sent[-1][1]},headers=headers(user))
    assert changed.status_code==200,changed.text
    for old in (user,other):assert client.get('/api/auth/me',headers=headers(old)).status_code==401
    assert client.get('/api/auth/me',headers=headers(changed.json())).status_code==200
    assert client.post('/api/auth/login',json={'username':'email_user','password':PASSWORD}).status_code==401
    assert client.post('/api/auth/login',json={'username':'email_user','password':NEW}).status_code==200

def test_password_change_without_email_and_profile_cleanup(api):
    client,factory=api;user=register(client,json={'username':'plain_user','password':PASSWORD}).json()
    changed=client.post('/api/account/password',json={'current_password':PASSWORD,'new_password':NEW,'password_confirm':NEW},headers=headers(user))
    assert changed.status_code==200
    current=changed.json();client.patch('/api/account/profile',json={'nickname':'Demo'},headers=headers(current))
    assert client.request('DELETE','/api/account',json={'password':NEW},headers=headers(current)).status_code==200
    with factory() as db:assert db.get(AccountProfile,user['account']['id']) is None

def test_real_local_smtp_transport(monkeypatch):
    import sys,urllib.request,json
    sys.path.insert(0,str(__import__('pathlib').Path(__file__).resolve().parents[2]/'evals'))
    from local_test_mail import start_test_mail
    servers=start_test_mail(0,0)
    # HTTP inbox rejects arbitrary Host values, including DNS rebinding hosts.
    try:
        smtp_port=servers[0].server_address[1]
        settings=Settings(_env_file=None,mail_mode='local_test',smtp_host='127.0.0.1',smtp_port=smtp_port,smtp_security='none')
        security.send_code(settings,'demo@example.test','123456','email_bind')
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open('http://localhost:'+str(servers[1].server_port)+'/messages') as response:
            inbox=json.load(response)
        assert len(inbox)==1 and '123456' in inbox[0]['body'] and inbox[0]['to']=='demo@example.test'
    finally:
        for server in servers:server.shutdown();server.server_close()
