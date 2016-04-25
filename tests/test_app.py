"""from ctf import create_app
from ctf.models import db, Team, Fleg
from ctf.routes import is_safe_url
import os
import pytest
import tempfile


@pytest.fixture
def app():
    os.environ['DATABASE_URL'] = 'sqlite:///%s' % tempfile.mktemp()
    app = create_app()
    app.debug = True
    return app


@pytest.fixture
def client(app):
    with app.test_client() as client:
        return client


def get_token(client):
    rv = client.get('/login/')
    token = rv.data.split(b'name="token" value="', 1)[1]
    return token.split(b'"', 1)[0].decode('utf-8')


def auth(client):
    team = Team(name='Abc', password='def')
    db.session.add(team)
    db.session.commit()
    data = {
        'name': 'abc',
        'password': 'def',
        'token': get_token(client),
    }
    client.post('/auth_team', data=data)


def test_is_safe_url(app):
    with app.test_request_context('/url'):
        assert is_safe_url('')
        assert is_safe_url('/')
        assert is_safe_url('/abc')
        assert not is_safe_url('/url')
        assert not is_safe_url('//example.com')
        assert not is_safe_url('http://abc')
        assert not is_safe_url('http://example.com')
        assert not is_safe_url('http://example.com/abc')
        assert not is_safe_url('http://localhost:1234/abc')
        assert not is_safe_url('http://localhost/')
        assert not is_safe_url('http://localhost')
        assert not is_safe_url('ftp://localhost/abc')
        assert not is_safe_url('http://localhost/abc')


def test_error(app):
    @app.route('/internal')
    def cause_a_problem():
        1 / 0

    app.debug = False

    with app.test_client() as client:
        for url, code in (('/asdf', 404), ('/teams', 405), ('/internal', 500)):
            rv = client.get(url)
            assert b'https://http.cat/%d' % code in rv.data
            assert rv.status_code == code


def test_static_pages(client):
    rv = client.get('/login/')
    assert rv.status_code == 200


def test_team_404(client):
    for url in ('/teams/1/', '/teams/0/', '/teams/-1/', '/teams/a',
                '/teams/a/'):
        rv = client.get(url)
        assert rv.status_code == 404


def test_bad_csrf(client):
    rv = client.post('/teams', data={'name': 'My team name'})
    assert rv.status_code == 400
    assert b'Missing or incorrect CSRF token.' in rv.data

    rv = client.post('/teams', data={'name': 'My team name', 'token': 'abc'})
    assert rv.status_code == 400
    assert b'Missing or incorrect CSRF token.' in rv.data


def test_new_team(client):
    rv = client.post('/teams?next=http%3A%2F%2Fexample.com', data={
        'name': 'Sgt. Pepper\'s Lonely Hearts Club Band',
        'token': get_token(client),
    })
    assert rv.status_code == 303
    assert rv.headers['Location'] == 'http://localhost/teams/1/'

    rv = client.get('/teams/1/')
    assert b'Team successfully created.' in rv.data
    assert b'>Sgt. Pepper&#39;s Lonely Hearts Club Band<' in rv.data


def test_new_team_missing_name(client):
    rv = client.post('/teams', data={'token': get_token(client)})
    assert rv.status_code == 303
    assert rv.headers['Location'] == 'http://localhost/login/'
    assert b'You must supply a team name.' in client.get('/').data


def test_new_team_duplicate(client):
    data = {
        'name': 'Some Team Name',
        'token': get_token(client),
    }
    rv = client.post('/teams', data=data)
    data['name'] = 'sOmE tEaM nAme'
    rv = client.post('/teams', data=data)
    assert rv.status_code == 303
    assert rv.headers['Location'] == 'http://localhost/login/'
    assert b'That team name is taken.' in client.get('/').data


def test_login(client):
    token = get_token(client)

    def assert_bad_login(data, message):
        data['token'] = token
        rv = client.post('/auth_team', data=data)
        assert rv.status_code == 303
        assert rv.headers['Location'] == 'http://localhost/login/'
        assert message in client.get('/').data

    assert_bad_login({}, b'No team exists with that name.')
    assert_bad_login({'username': 'abc'}, b'No team exists with that name.')
    assert_bad_login({'username': 'abc', 'password': 'abc'},
                     b'No team exists with that name.')

    client.post('/teams', data={'name': 'Abc', 'token': token})
    assert_bad_login({'name': 'ABC', 'password': 'abc'},
                     b'Incorrect team password.')

    password = Team.query.filter_by(id=1).first().password
    data = {
        'name': 'ABC',
        'password': password,
        'token': token,
    }
    rv = client.post('/auth_team?next=http%3A%2F%2Fexample.com', data=data)
    assert rv.headers['Location'] == 'http://localhost/teams/1/'

    rv = client.post('/auth_team?next=%2F', data=data)
    assert rv.headers['Location'] == 'http://localhost/'


def test_logout_unauthed(client):
    rv = client.get('/logout/')
    assert rv.status_code == 303
    assert rv.headers['Location'] == ('http://localhost/login/'
                                      '?next=%2Flogout%2F')


def test_logout_bad_token(client):
    auth(client)
    rv = client.get('/logout/')
    assert rv.status_code == 400
    assert b'Missing or incorrect CSRF token.' in rv.data

    rv = client.get('/logout/?token=abc')
    assert rv.status_code == 400
    assert b'Missing or incorrect CSRF token.' in rv.data


def test_logout(client):
    auth(client)
    token = get_token(client)

    rv = client.get('/logout/?token=%s' % token)
    assert rv.status_code == 303
    assert rv.headers['Location'] == 'http://localhost/'

    assert get_token(client) != token


def test_submit_page(client):
    rv = client.get('/submit/')
    assert rv.status_code == 303
    assert rv.headers['Location'] == ('http://localhost/login/'
                                      '?next=%2Fsubmit%2F')

    auth(client)

    rv = client.get('/submit/')
    assert rv.status_code == 200


def test_justice(client):
    auth(client)
    token = get_token(client)
    rv = client.post('/flags', data={'flag': 'V375BrzPaT', 'token': token})
    assert rv.status_code == 303
    assert 'youtube.com' in rv.headers['Location']

    rv = client.get('/passwords.zip')
    assert rv.status_code == 303
    assert 'youtube.com' in rv.headers['Location']


def test_fleg_submission(client):
    token = get_token(client)

    def assert_fleg(fleg, msg):
        rv = client.post('/flags', data={'flag': fleg, 'token': token})
        assert rv.status_code == 303
        assert rv.headers['Location'] == 'http://localhost/submit/'
        assert msg in client.get('/').data

    # SHA-256 of "fleg1" and "fleg2"
    sha1 = '2625b4dc22b2a45b2e97dad4b015023a5edbca79672d44c962f783e3ca3cb2a4'
    sha2 = 'b4426795bb1d1285d51c9371ff92eb048a55f5662877ca59d6cf0759c3c143da'
    bandit = Category(name='Bandit', enforce=True)
    leviathan = Category(name='Leviathan', enforce=True)
    level1 = Level(points=10, category=bandit, level=0)
    level2 = Level(points=20, category=bandit, level=1)
    level3 = Level(points=10, category=leviathan, level=0)
    fleg1 = Fleg(hash=sha1, level=level1)
    fleg2 = Fleg(hash=sha2, level=level2)
    fleg3 = Fleg(hash='whatever', level=level3)
    db.session.add(bandit)
    db.session.add(leviathan)
    db.session.add(fleg1)
    db.session.add(fleg2)
    db.session.add(fleg3)
    db.session.commit()

    auth(client)

    rv = client.get('/')
    assert b'<td>0</td>' in rv.data

    assert_fleg('fleg2', b'You must complete all previous challenges first!')
    assert_fleg('abc', b'Sorry, the flag you entered is not correct.')
    assert_fleg('fleg1', b'Correct! You have earned 10 points for your team.')
    assert_fleg('fleg1', b'You&#39;ve already entered that flag.')

    rv = client.get('/')
    assert b'<td>10</td>' in rv.data

    assert_fleg('fleg2', b'Correct! You have earned 20 points for your team.')
    assert_fleg('fleg2', b'You&#39;ve already entered that flag.')

    rv = client.get('/')
    assert b'<td>30</td>' in rv.data
"""
