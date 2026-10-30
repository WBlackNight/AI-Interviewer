"""Deterministic CAPTCHA is injected only by isolated test fixtures."""
def register(client,**options):
    body=dict(options.pop('json'))
    challenge=client.get('/api/auth/captcha').json()
    body.update(password_confirm=body.get('password',''),captcha_id=challenge['captcha_id'],captcha_code='TEST2')
    return client.post('/api/auth/register',json=body,**options)
