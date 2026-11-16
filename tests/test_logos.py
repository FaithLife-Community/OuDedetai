import unittest
from unittest import mock

from ou_dedetai import logos


class TestMonitorForPotentialIssues(unittest.TestCase):
    def test_returns_once_logos_has_stopped(self):
        app = mock.Mock()
        app.conf._logos_appdata_dir = "/fake/appdata"
        manager = logos.LogosManager(app)
        manager.logos_state = logos.State.RUNNING
        sleeps = []

        def fake_sleep(seconds):
            sleeps.append(seconds)
            if len(sleeps) == 2:
                manager.logos_state = logos.State.STOPPED  # Logos closes
            if len(sleeps) > 10:
                raise AssertionError("still looping after Logos stopped")

        with mock.patch.object(logos.time, "sleep", side_effect=fake_sleep), \
                mock.patch.object(logos, "get_logos_user_id", return_value="user"):
            manager.monitor_for_potential_issues()  # must return, not loop forever
        self.assertEqual(len(sleeps), 2)


if __name__ == "__main__":
    unittest.main()


class TestReapFinished(unittest.TestCase):
    def test_ended_processes_are_collected(self):
        from unittest import mock
        from ou_dedetai import logos
        manager = logos.LogosManager(mock.Mock())
        ended, running = mock.Mock(), mock.Mock()
        ended.poll.return_value = 0
        running.poll.return_value = None
        manager.processes = {"Logos.exe": ended, "Indexer.exe": running}
        manager.reap_finished()
        self.assertEqual(list(manager.processes), ["Indexer.exe"])


class TestLinkHandOff(unittest.TestCase):
    def manager(self, running):
        from unittest import mock
        from ou_dedetai import logos
        app = mock.Mock()
        app.conf._overrides.logos_link = "logos4:Signin?code=1"
        m = logos.LogosManager(app)
        m.monitor = mock.Mock(side_effect=lambda: setattr(
            m, "logos_state", logos.State.RUNNING if running else logos.State.STOPPED))
        return m, app

    def test_running_logos_gets_the_link_directly(self):
        from unittest import mock
        from ou_dedetai import logos
        m, app = self.manager(running=True)
        with mock.patch.object(logos.wine, "run_wine_process") as run:
            self.assertTrue(m.hand_off_link())
        self.assertEqual(run.call_args.kwargs["exe_args"], ["logos4:Signin?code=1"])
        self.assertIsNone(app.conf._overrides.logos_link)

    def test_not_running_starts_normally(self):
        from unittest import mock
        from ou_dedetai import logos
        m, app = self.manager(running=False)
        with mock.patch.object(logos.wine, "run_wine_process") as run:
            self.assertFalse(m.hand_off_link())
        run.assert_not_called()
        self.assertEqual(app.conf._overrides.logos_link, "logos4:Signin?code=1")  # for start()


class TestRunInstalledAppLink(unittest.TestCase):
    def test_parser_keeps_the_link(self):
        from unittest import mock
        from ou_dedetai import cli_parser
        parser = cli_parser.get_parser()
        for argv, link in ((["--run-installed-app"], None),
                           (["--run-installed-app", "logos4:Signin?x=1"], "logos4:Signin?x=1")):
            args = parser.parse_args(argv)
            with mock.patch.object(cli_parser.EphemeralConfiguration, "load",
                                   return_value=cli_parser.EphemeralConfiguration.load_from_path("/nonexistent")):
                config, action = cli_parser.od_parse_args(args, parser)
            self.assertEqual(action.__name__, "run_installed_app")
            self.assertEqual(config.logos_link, link)


class TestSettingFlags(unittest.TestCase):
    def test_set_flags_reach_the_cli(self):
        from unittest import mock
        from ou_dedetai import cli_parser
        parser = cli_parser.get_parser()
        for argv, action, value in ((["--set-wine-channel", "dev"], "set_wine_channel", "dev"),
                                    (["--set-offline", "on"], "set_offline", "on"),
                                    (["--set-renderer", "dxvk"], "set_renderer", "dxvk")):
            args = parser.parse_args(argv)
            with mock.patch.object(cli_parser.EphemeralConfiguration, "load",
                                   return_value=cli_parser.EphemeralConfiguration.load_from_path("/nonexistent")):
                config, run = cli_parser.od_parse_args(args, parser)
            self.assertEqual(run.__name__, action)
            self.assertEqual(config.cli_choice, value)

    def test_media_toggle_is_gone(self):
        from ou_dedetai import cli_parser
        with self.assertRaises(SystemExit):
            cli_parser.get_parser().parse_args(["--toggle-media-support"])
