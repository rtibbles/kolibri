import atexit
import os
import sys
import tempfile

import django
from django.core.management import call_command
from django.test import LiveServerTestCase
from django.test.utils import setup_databases
from django.test.utils import setup_test_environment
from six.moves import BaseHTTPServer


routes = ["setUp", "tearDown"]


class LiveTestCase(LiveServerTestCase):
    __name__ = "LiveTestCase"
    host = "127.0.0.1"
    port = 8000

    def runTest(self):
        pass


class LiveServerControlHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.replace("/", "")
        if path in routes:
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write("Done!")
            self.server[path]()
            return
        self.send_response(404)


class LiveServerControlServer(BaseHTTPServer.HTTPServer, object):

    def __init__(self, *args, **kwargs):
        os.environ['DJANGO_SETTINGS_MODULE'] = 'kolibri.deployment.default.settings.dev'
        super(LiveServerControlServer, self).__init__(*args, **kwargs)
        home_dir = tempfile.mkdtemp()
        os.mkdir(os.path.join(home_dir, "content"))
        os.environ['KOLIBRI_HOME'] = home_dir
        django.setup()
        call_command("collectstatic", interactive=False, verbosity=0)
        setup_test_environment(debug=True)
        setup_databases(0, False)
        self.test_case = LiveTestCase()
        self.test_case.setUpClass()

    def setUp(self):
        sys.stdout.write("setup")
        return self.test_case._pre_setup()

    def tearDown(self):
        sys.stdout.write("teardown")
        return self.test_case._post_teardown()

    def stop(self):
        try:
            self.test_case.tearDownClass()
        except:  # noqa
            pass
        self.server_close()
        return sys.exit(0)


def main():
    server = LiveServerControlServer(("127.0.0.1", 4242), LiveServerControlHandler)
    atexit.register(server.stop)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.stop()


if __name__ == "__main__":
    main()
