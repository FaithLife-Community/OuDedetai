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


class TestStartingState(unittest.TestCase):
    """A monitor() call while Wine is still starting Logos must not stop it."""

    def manager(self):
        app = mock.Mock()
        app.conf.logos_exe = "/x/Logos.exe"
        app.conf.logos_system_exe_windows_path = "C:\\x\\System\\Logos.exe"
        app.conf.logos_cef_exe_windows_path = "C:\\x\\System\\LogosCEF.exe"
        app.conf.logos_indexer_exe_windows_path = "C:\\x\\System\\LogosIndexer.exe"
        manager = logos.LogosManager(app)
        manager.stop = mock.Mock()
        return manager

    def processes(self, manager, *exes):
        running = mock.Mock()
        running.is_running.return_value = True
        manager.existing_processes = {exe: [running] for exe in exes}

    def test_no_processes_yet_while_starting(self):
        manager = self.manager()
        manager.logos_state = logos.State.STARTING
        manager.starting_since = logos.time.monotonic()
        self.processes(manager)  # Wine hasn't started Logos.exe yet
        manager.monitor_logos()
        manager.stop.assert_not_called()
        self.assertEqual(manager.logos_state, logos.State.STARTING)

    def test_running_once_logos_appears(self):
        manager = self.manager()
        manager.logos_state = logos.State.STARTING
        manager.starting_since = logos.time.monotonic()
        self.processes(manager, manager.app.conf.logos_system_exe_windows_path)
        manager.monitor_logos()
        self.assertEqual(manager.logos_state, logos.State.RUNNING)

    def test_gives_up_when_logos_never_appears(self):
        manager = self.manager()
        manager.logos_state = logos.State.STARTING
        manager.starting_since = logos.time.monotonic() - logos.STARTING_TIMEOUT - 1
        self.processes(manager)
        manager.monitor_logos()
        self.assertEqual(manager.logos_state, logos.State.STOPPED)
        manager.stop.assert_not_called()

    def test_splash_keeps_a_slow_start_going(self):
        manager = self.manager()
        manager.logos_state = logos.State.STARTING
        manager.starting_since = logos.time.monotonic() - logos.STARTING_TIMEOUT - 1
        self.processes(manager, manager.app.conf.logos_exe)
        manager.monitor_logos()
        self.assertEqual(manager.logos_state, logos.State.STARTING)

    def test_start_leaves_logos_starting(self):
        manager = self.manager()
        manager.app.start_thread = lambda fn, daemon_bool=True: fn() if fn.__name__ == "run_logos" else None
        with mock.patch.object(logos.wine, "get_wine_release", return_value=("11.22", None)), \
                mock.patch.object(logos.wine, "check_wine_rules", return_value=(True, None)), \
                mock.patch.object(logos.wine, "wineserver_kill"), \
                mock.patch.object(logos.wine, "wine_supports_logos_updates", return_value=True), \
                mock.patch.object(logos.wine, "allow_logos_updates"), \
                mock.patch.object(logos.wine, "run_wine_application", return_value=mock.Mock()), \
                mock.patch.object(manager, "set_auto_updates"):
            manager.start()
        self.assertEqual(manager.logos_state, logos.State.STARTING)
        self.assertGreater(manager.starting_since, 0)

    def test_running_logos_without_processes_still_stops(self):
        manager = self.manager()
        manager.logos_state = logos.State.RUNNING
        self.processes(manager)
        manager.monitor_logos()
        manager.stop.assert_called_once()


class TestPoliteClose(unittest.TestCase):
    def test_close_asks_logos_and_never_kills(self):
        from ou_dedetai import logos as logos_mod
        app = mock.Mock()
        app.conf.logos_exe = "/x/Logos.exe"
        manager = logos_mod.LogosManager(app)
        manager.logos_state = logos_mod.State.RUNNING
        states = iter([logos_mod.State.RUNNING, logos_mod.State.STOPPED])

        def monitor():
            manager.logos_state = next(states)
        process = mock.Mock()
        with mock.patch.object(manager, "monitor", side_effect=monitor), \
                mock.patch.object(logos_mod.wine, "run_wine_process", return_value=process) as run, \
                mock.patch.object(logos_mod.time, "sleep"), \
                mock.patch.object(manager, "stop") as stop:
            self.assertTrue(manager.close())
        self.assertEqual(run.call_args.kwargs["exe"], "taskkill")
        self.assertEqual(run.call_args.kwargs["exe_args"], ["/IM", "Logos.exe"])
        stop.assert_not_called()

    def test_close_gives_up_without_forcing(self):
        from ou_dedetai import logos as logos_mod
        app = mock.Mock()
        app.conf.logos_exe = "/x/Logos.exe"
        manager = logos_mod.LogosManager(app)
        manager.logos_state = logos_mod.State.RUNNING
        with mock.patch.object(manager, "monitor"), \
                mock.patch.object(logos_mod.wine, "run_wine_process"), \
                mock.patch.object(logos_mod.time, "sleep"), \
                mock.patch.object(manager, "stop") as stop:
            self.assertFalse(manager.close(timeout=0.01))
        stop.assert_not_called()


class TestCloseOrForce(unittest.TestCase):
    def manager(self, assume_yes=False, approve=False):
        from ou_dedetai import logos as logos_mod
        app = mock.Mock()
        app.conf._overrides.assume_yes = assume_yes
        app.approve.return_value = approve
        return logos_mod.LogosManager(app)

    def test_closed_politely_never_forces(self):
        m = self.manager()
        with mock.patch.object(m, "close", return_value=True), mock.patch.object(m, "stop") as stop:
            m.close_or_force()
        stop.assert_not_called()
        m.app.approve.assert_not_called()

    def test_forces_only_when_the_user_agrees(self):
        for approve in (False, True):
            m = self.manager(approve=approve)
            with mock.patch.object(m, "close", return_value=False), mock.patch.object(m, "stop") as stop:
                m.close_or_force()
            self.assertEqual(stop.called, approve)

    def test_unattended_never_forces(self):
        m = self.manager(assume_yes=True, approve=True)
        with mock.patch.object(m, "close", return_value=False), mock.patch.object(m, "stop") as stop:
            m.close_or_force()
        stop.assert_not_called()

    def test_busy_logos_keeps_the_wait_going(self):
        m = self.manager()
        busy = iter([True, True, False, False])
        clock = iter([0, 0, 100, 100, 100, 200, 300, 400, 500])
        from ou_dedetai import logos as logos_mod
        with mock.patch.object(m, "_closed", side_effect=[False, False, False, False, False]), \
                mock.patch.object(m, "request_close"), \
                mock.patch.object(m, "busy", side_effect=lambda: next(busy)), \
                mock.patch.object(logos_mod.time, "monotonic", side_effect=lambda: next(clock)):
            self.assertFalse(m.close(timeout=150))
