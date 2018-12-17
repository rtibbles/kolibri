import sys

import django
from django.test import LiveServerTestCase
from six.moves import BaseHTTPServer


routes = ['setUp', 'tearDown', 'stop']


class LiveTestCase(LiveServerTestCase):
    __name__ = 'LiveTestCase'
    host = '127.0.0.1'
    port = 8000

    def runTest(self):
        pass


class LiveServerControlHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.replace('/', '')
        if path in routes:
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write('Done!')
            return
        self.send_response(404)


class LiveServerControlServer(BaseHTTPServer.HTTPServer, object):
    def __init__(self, *args, **kwargs):
        super(LiveServerControlServer, self).__init__(*args, **kwargs)
        django.setup()
        self.test_case = LiveTestCase()
        self.test_case.setUpClass()
        sys.stderr.write('ready')

    def setUp(self):
        return self.test_case._pre_setup()

    def tearDown(self):
        return self.test_case._post_teardown()

    def stop(self):
        self.test_case.tearDownClass()
        self.server_close()
        return sys.exit(0)


def main():
    server = LiveServerControlServer(('127.0.0.1', 4242), LiveServerControlHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == '__main__':
    main()
