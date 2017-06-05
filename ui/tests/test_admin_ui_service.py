"""
Offline tests
"""
from unittest import TestCase
from mock import MagicMock

import sys
from os import path
sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))
from admin_ui import AdminUIService


class TestAdminUIService(TestCase):

    def setUp(self):
        self.admin_ui_service = AdminUIService("settings.py")
        self.admin_ui_service.settings = self.admin_ui_service.wrapper.load("settings.py")
        self.admin_ui_service.logger = MagicMock()

    def test_close(self):
        self.admin_ui_service.close()
        self.assertTrue(self.admin_ui_service.closed)

    # Routes ------------------

    def test_index(self):
        with self.admin_ui_service.app.test_request_context():
            res = self.admin_ui_service.index()
            d = "<title>Scrapy Cluster</title>"
            self.assertIn(d, res)
