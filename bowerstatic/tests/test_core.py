import bowerstatic
from webtest import TestApp as Client
import os


def test_wrap():
    bower = bowerstatic.Bower()

    components = bower.components('components', os.path.join(
        os.path.dirname(__file__), 'bower_components'))

    def wsgi(environ, start_response):
        start_response('200 OK', [('Content-Type', 'text/html;charset=UTF-8')])
        include = components.includer(environ)
        include('jquery/dist/jquery.js')
        return ['<html><head></head><body>Hello!</body></html>']

    wrapped = bower.wrap(wsgi)

    c = Client(wrapped)

    response = c.get('/')
    assert response.body == (
        b'<html><head>'
        b'<script type="text/javascript" '
        b'src="/bowerstatic/components/jquery/2.1.1/dist/jquery.js">'
        b'</script></head><body>Hello!</body></html>')

    response = c.get('/bowerstatic/components/jquery/2.1.1/dist/jquery.js')
    assert response.body == b'/* jquery.js 2.1.1 */\n'


def test_component_url():
    bower = bowerstatic.Bower()

    components = bower.components('components', os.path.join(
        os.path.dirname(__file__), 'bower_components'))

    assert (components.component('jquery').url() ==
            '/bowerstatic/components/jquery/2.1.1/')
