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
