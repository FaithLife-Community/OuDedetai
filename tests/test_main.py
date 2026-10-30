import unittest
from unittest.mock import Mock, patch
from ou_dedetai.main import run
from ou_dedetai.main import get_parser


class TestRuntimeArgument(unittest.TestCase):
    def test_select_wine_argument(self):
        args = get_parser().parse_args(['--select-wine'])
        self.assertTrue(args.select_wine)
        self.assertIsNone(args.set_appimage)

    def test_select_wine_does_not_require_an_installed_product(self):
        action = Mock(__name__='select_wine')
        config = Mock()
        with patch('ou_dedetai.main.detect_and_recover'), \
                patch('ou_dedetai.main.is_app_installed') as installed:
            run(config, action)
        installed.assert_not_called()
        action.assert_called_once_with(config)
