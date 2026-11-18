import io
import pytest
from PIL import Image
from app.models.entities import AccountProfile,AuthChallenge
from app.config import Settings
from tests.test_ws_recovery import api
from tests.test_accounts import users, auth, PASSWORD
from tests.test_account_security import image_bytes


@pytest.mark.parametrize('size',[128,256,512])
def test_selected_avatar_size_is_preserved(users,size):
    client,_,user,_=users
    response=client.post(f'/api/account/avatar?size={size}',content=image_bytes(),
        headers={**auth(user),'Content-Type':'image/png'})
    assert response.status_code==200
    with Image.open(io.BytesIO(client.get('/api/account/avatar',headers=auth(user)).content)) as image:
        assert image.size==(size,size)
    assert client.post('/api/account/avatar?size=192',content=image_bytes(),
        headers={**auth(user),'Content-Type':'image/png'}).status_code==422


def test_recovery_requires_bound_email_and_single_use_code_and_revokes_sessions(users,monkeypatch):
    from app.api import account_recovery as recovery
    from app.services import account_security as security
    client,factory,user,other=users
    with factory() as db:
        db.add(AccountProfile(account_id=user['account']['id'],nickname='',email='owner@example.test'))
        db.commit()
    sent=[]
    monkeypatch.setattr(recovery,'get_settings',lambda:Settings(_env_file=None,mail_mode='local_test',smtp_security='none'))
    monkeypatch.setattr(security,'send_code',lambda settings,email,code,purpose:sent.append((email,code,purpose)))
    def send(username,email):
        captcha=client.get('/api/auth/captcha').json()
        return client.post('/api/auth/recovery/code',json={'username':username,'email':email,
            'captcha_id':captcha['captcha_id'],'captcha_code':'TEST2'})
    unknown=send('unknown_user','unknown@example.test')
    assert unknown.status_code==200 and not sent
    issued=send('USER_A','OWNER@example.test')
    assert issued.status_code==200 and len(sent)==1
    assert set(unknown.json())==set(issued.json())
    body={'username':'user_a','email':'owner@example.test','challenge_id':issued.json()['challenge_id'],
          'code':'not-six-digits','new_password':'replacement-password-2026','password_confirm':'replacement-password-2026'}
    assert client.post('/api/auth/recovery/reset',json=body).status_code==422
    body['code']=sent[0][1]
    assert client.post('/api/auth/recovery/reset',json={**body,'username':'user_b'}).status_code==400
    assert client.post('/api/auth/recovery/reset',json=body).status_code==200
    assert client.get('/api/auth/me',headers=auth(user)).status_code==401
    assert client.get('/api/auth/me',headers=auth(other)).status_code==200
    assert client.post('/api/auth/login',json={'username':'user_a','password':PASSWORD}).status_code==401
    assert client.post('/api/auth/login',json={'username':'user_a','password':body['new_password']}).status_code==200
    assert client.post('/api/auth/recovery/reset',json=body).status_code==400
    monkeypatch.setattr(recovery,'get_settings',lambda:Settings(_env_file=None,mail_mode='disabled'))
    assert send('user_a','owner@example.test').status_code==503


def test_email_change_requires_password_and_new_email_verification(users,monkeypatch):
    from app.api import account_profile
    from app.services import account_security as security
    client,factory,user,_=users
    with factory() as db:
        db.add(AccountProfile(account_id=user['account']['id'],nickname='',email='old@example.test'));db.commit()
    sent=[]
    monkeypatch.setattr(account_profile,'get_settings',lambda:Settings(_env_file=None,mail_mode='local_test',smtp_security='none'))
    monkeypatch.setattr(security,'send_code',lambda settings,email,code,purpose:sent.append((email,code,purpose)))
    body={'purpose':'email_change','email':'new@example.test','current_password':PASSWORD}
    assert client.post('/api/account/email/code',headers=auth(user),json={**body,'current_password':'wrong-password-2026'}).status_code==403
    issued=client.post('/api/account/email/code',headers=auth(user),json=body)
    assert issued.status_code==200 and sent[0][0]=='new@example.test'
    confirm={**body,'challenge_id':issued.json()['challenge_id'],'code':sent[0][1]}
    assert client.post('/api/account/email/confirm',headers=auth(user),json={**confirm,'email':'wrong@example.test'}).status_code==400
    result=client.post('/api/account/email/confirm',headers=auth(user),json=confirm)
    assert result.status_code==200 and result.json()['email']=='new@example.test'
    assert client.post('/api/account/email/confirm',headers=auth(user),json=confirm).status_code==400
