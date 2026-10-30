import unittest
from unittest.mock import Mock, patch
from ou_dedetai.cli import CLI


class TestRuntimeMenu(unittest.TestCase):
    def test_cli_opens_shared_menu(self):
        app = Mock()
        with patch('ou_dedetai.runtime.select_runtime') as select:
            CLI.select_wine(app)
        select.assert_called_once_with(app)
