import queue
import subprocess
import tempfile
import unittest
from unittest.mock import Mock
from pathlib import Path

import ou_dedetai.constants as constants
import ou_dedetai.utils as utils
from . import REPODIR
from . import TESTDATADIR

class TestAppUtils(unittest.TestCase):
    def setUp(self):
        self.pidfile = TESTDATADIR / 'temp.pid'
        constants.PID_FILE = str(self.pidfile)
        self.app = Mock()
        self.app.conf = Mock()

    def test_compare_logos_linux_installer_version_custom(self):
        constants.LLI_CURRENT_VERSION = '4.0.1'
        self.app.conf.app_latest_version = '4.0.0-alpha.1'
        result = utils.compare_logos_linux_installer_version(self.app)
        self.assertEqual(result, utils.VersionComparison.DEVELOPMENT)

    def test_compare_logos_linux_installer_version_notset(self):
        constants.LLI_CURRENT_VERSION = None
        self.app.conf.app_latest_version = '4.0.1'
        self.assertRaises(
            TypeError,
            utils.compare_logos_linux_installer_version,
            self.app
        )

    def test_compare_logos_linux_installer_version_uptodate(self):
        constants.LLI_CURRENT_VERSION = '4.0.0-alpha.1'
        self.app.conf.app_latest_version = '4.0.0-alpha.1'
        result = utils.compare_logos_linux_installer_version(self.app)
        self.assertEqual(result, utils.VersionComparison.UP_TO_DATE)

    def test_compare_logos_linux_installer_version_yes(self):
        constants.LLI_CURRENT_VERSION = '4.0.0-alpha.1'
        self.app.conf.app_latest_version = '4.0.1'
        result = utils.compare_logos_linux_installer_version(self.app)
        self.assertEqual(result, utils.VersionComparison.OUT_OF_DATE)

    @unittest.skip("Needs functional wine binary.")
    def test_compare_recommended_appimage_version(self):
        self.app.conf.wine_appimage_recommended_version = '11'
        status, msg = utils.compare_recommended_appimage_version(self.app)
        self.assertEqual(status, 0)

    def test_die_if_running_nofile(self):
        utils.die_if_running(self.app)
        self.assertTrue(self.pidfile.is_file())

    def test_die_if_running_withfile(self):
        self.pidfile.touch()
        self.app.approve = Mock(return_value=False)
        utils.die_if_running(self.app)
        self.assertTrue(self.app.approve.called)

    def test_find_appimage_files(self):
        # TODO: As is, this test only proves that the function correctly rules
        # out non-wine appimages.
        self.app.conf._overrides.custom_binary_path = None
        self.app.conf.installer_binary_dir = '.'
        self.app.conf.download_dir = TESTDATADIR
        self.assertEqual(len(utils.find_appimage_files(self.app)), 0)

    @unittest.skip("Not practical.")
    def test_find_wine_binary_files(self):
        pass

    def test_get_wine_options(self):
        # TODO: Make more tests to fully test function.
        self.app.conf.wine_app_image_files = ['/home/user/wine-stable_10.0.AppImage']
        self.app.conf.wine_binary_files = ['/usr/bin/wine64']
        self.app.conf.installer_binary_dir = '/home/user/installdir'
        self.app.conf.wine_appimage_recommended_file_name = 'wine-stable_99.0.AppImage'
        options = [
            f"{self.app.conf.installer_binary_dir}/{self.app.conf.wine_appimage_recommended_file_name}",
            *self.app.conf.wine_app_image_files,
            *self.app.conf.wine_binary_files,
        ]
        self.assertEqual(utils.get_wine_options(self.app), options)

    def test_get_winebincode_appimage(self):
        # TODO: Make more tests to fully test function.
        binary = 'test.AppImage'
        code, _ = utils.get_winebin_code_and_desc(self.app, binary=binary)
        self.assertEqual('AppImage', code)

    def test_get_winebincode_pol(self):
        binary = 'test/PlayOnLinux/wine64.exe'
        code, _ = utils.get_winebin_code_and_desc(self.app, binary=binary)
        self.assertEqual('PlayOnLinux', code)

    def test_get_winebincode_proton(self):
        binary = 'test/Proton/wine64.exe'
        code, _ = utils.get_winebin_code_and_desc(self.app, binary=binary)
        self.assertEqual('Proton', code)

    def test_get_winebincode_recommended(self):
        binary = './wine-stable_10.0-x86_64.AppImage'
        code, _ = utils.get_winebin_code_and_desc(self.app, binary=binary)
        self.assertEqual('AppImage', code)

    def test_get_winebincode_system(self):
        binary = '/usr/bin/wine64.exe'
        code, _ = utils.get_winebin_code_and_desc(self.app, binary=binary)
        self.assertEqual('System', code)

    @unittest.skip("Test not feasible.")
    def test_set_appimage_symlink(self):
        pass

    @unittest.skip("Test not feasible.")
    def test_update_to_latest_recommended_appimage(self):
        pass

    def tearDown(self):
        self.pidfile.unlink(missing_ok=True)


class TestGeneralUtils(unittest.TestCase):
    def setUp(self):
        self.grepfile = TESTDATADIR / 'legacy_config.json'
        self.tiny_appimage = TESTDATADIR / 'wine_tiny_v2.AppImage'

    # @unittest.skip("Unused function")
    # def test_get_calling_function_name(self):
    #     pass

    def test_append_unique_no(self):
        nums = [1, 2, 3]
        utils.append_unique(nums, 3)
        self.assertEqual(len(nums), 3)

    def test_append_unique_yes(self):
        nums = [1, 2, 3]
        utils.append_unique(nums, 4)
        self.assertEqual(len(nums), 4)

    def test_check_appimage(self):
        # TODO: Need to add test for v1 appimage.
        self.assertTrue(utils.check_appimage(self.tiny_appimage))

    @unittest.skip("Not testing simple shell command.")
    def test_clean_all(self):
        pass

    def test_delete_symlink_exists(self):
        new_symlink = Path('symlink')
        if new_symlink.is_symlink():
            new_symlink.unlink()
        new_symlink.symlink_to(self.grepfile)
        if new_symlink.is_symlink():
            utils.delete_symlink(new_symlink)
            self.assertFalse(new_symlink.is_symlink())

    def test_delete_symlink_notexists(self):
        new_symlink = Path('symlink')
        utils.delete_symlink(new_symlink)
        self.assertFalse(new_symlink.is_symlink())

    @unittest.skip("Test not feasible.")
    def test_die(self):
        pass

    def test_enough_disk_space_false(self):
        self.assertFalse(utils.enough_disk_space(Path.home(), 1024**6))

    def test_enough_disk_space_true(self):
        self.assertTrue(utils.enough_disk_space(Path.home(), 1))

    def test_file_exists_false(self):
        self.assertFalse(utils.file_exists('~/NotGonnaFindIt.exe'))

    def test_file_exists_none(self):
        self.assertFalse(utils.file_exists(None))

    def test_file_exists_true(self):
        self.assertTrue(utils.file_exists('~/.bashrc'))


    def test_find_installed_product_exists(self):
        name = 'Logos'
        with tempfile.TemporaryDirectory() as prefix:
            drive_c = Path(prefix) / 'drive_c'
            drive_c.mkdir()
            logos_dir = drive_c / name
            logos_dir.mkdir()
            logos_exe = logos_dir / f"{name}.exe"
            logos_exe.touch()
            exe_path = utils.find_installed_product(name, prefix)
            self.assertTrue(Path(exe_path).is_file())

    def test_find_installed_product_none(self):
        name = 'Logos'
        with tempfile.TemporaryDirectory() as prefix:
            exe_path = utils.find_installed_product(name, prefix)
            self.assertIsNone(exe_path)

    def test_get_current_logos_version(self):
        with tempfile.TemporaryDirectory() as logos_dir:
            system = Path(logos_dir) / 'System'
            system.mkdir()
            deps_json = system / 'Logos.deps.json'
            deps_json.write_text(r'{"libraries": {"Logos/1.2.3.4": null}}')
            result = utils.get_current_logos_version(logos_dir)
        self.assertEqual(result, '1.2.3.4')

    def test_get_downloaded_file_path_found(self):
        p = Path(utils.get_downloaded_file_path(REPODIR, 'README.md'))
        self.assertEqual(p.parent.name, constants.REPO_NAME)

    def test_get_downloaded_file_path_notfound(self):
        self.assertIsNone(utils.get_downloaded_file_path(REPODIR, 'NothingToFind.exe'))

    def test_get_folder_group_size_queuebad(self):
        q = queue.Queue()
        utils.get_folder_group_size([Path('fake')], q)
        self.assertEqual(q.get(), 0)

    def test_get_folder_group_size_queuegood(self):
        q = queue.Queue()
        utils.get_folder_group_size([TESTDATADIR], q)
        self.assertIsNotNone(q.get())

    def test_get_folder_group_size_returnbad(self):
        r = utils.get_folder_group_size([Path('fake')])
        self.assertEqual(r, 0)

    def test_get_folder_group_size_returngood(self):
        r = utils.get_folder_group_size([TESTDATADIR])
        self.assertIsNotNone(r)

    @unittest.skip("Not tested; function just sorts names and returns last one.")
    def test_get_latest_folder(self):
        pass

    @unittest.skip("Must be tested on actual oudedetai binary.")
    def test_get_lli_release_version(self):
        pass

    def test_get_path_size_exists(self):
        cmd = ['du', '-sb', TESTDATADIR]
        size_du = int(subprocess.check_output(cmd).decode().split()[0])
        size_dir = 4096
        size = size_du + size_dir
        self.assertEqual(size, utils.get_path_size(TESTDATADIR))

    def test_get_path_size_notexists(self):
        self.assertEqual(0, utils.get_path_size('./no_dir'))

    # @unittest.skip("Unused function")
    # def test_get_procs_using_file(self):
    #     with tempfile.TemporaryFile() as tf:
    #         pids = utils.get_procs_using_file(tf)
    #     self.assertTrue(isinstance(pids, set))

    def test_get_relative_path(self):
        base_p = '/home/user/.config'
        p = f'{base_p}/test/dir'
        relpath = utils.get_relative_path(p, base_p)
        self.assertEqual(relpath, 'test/dir')

    @unittest.skip("Just returns formatted datetime text.")
    def test_get_timestamp(self):
        pass

    @unittest.skip("TODO")
    def test_get_user_downloads_dir(self):
        pass

    def test_grep_found(self):
        self.assertTrue(utils.grep(r'LOGOS_DIR', self.grepfile))

    def test_grep_nofile(self):
        with self.assertRaises(FileNotFoundError):
            utils.grep(r'test', 'thisfiledoesnotexist')

    def test_grep_notfound(self):
        self.assertFalse(utils.grep(r'TEST_NOT_IN_FILE', self.grepfile))

    @unittest.skip("Test requires OS manipulation")
    def test_install_dependencies(self):
        pass

    def test_is_appimage(self):
        result = utils.is_appimage(self.tiny_appimage)
        self.assertTrue(result[0])

    def test_is_relative_path_bad(self):
        p = '/home/user/dir/file.txt'
        result = utils.is_relative_path(p)
        self.assertFalse(result)

    def test_is_relative_path_good(self):
        p = 'dir/file.txt'
        result = utils.is_relative_path(p)
        self.assertTrue(result)

    def test_parse_bool_bad(self):
        for s in ["False", "FALSE", "No", "N", "n", "0"]:
            self.assertFalse(utils.parse_bool(s))

    def test_parse_bool_good(self):
        for s in ["True", "TRUE", "Yes", "Y", "y", "1"]:
            self.assertTrue(utils.parse_bool(s))

    @unittest.skip("Test requires oudedetai binary.")
    def test_restart_lli(self):
        pass

    @unittest.skip("Test not needed.")
    def test_stopwatch(self):
        pass

    @unittest.skip("TODO")
    def test_untar_file(self):
        pass

    @unittest.skip("Test requires oudedetai binary.")
    def test_update_to_latest_lli_release(self):
        pass
