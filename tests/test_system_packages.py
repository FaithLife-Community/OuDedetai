import unittest
from unittest.mock import patch

from ou_dedetai.system import get_package_manager


class TestAptPackageNames(unittest.TestCase):
    def packages(self, os_name, major):
        with patch('ou_dedetai.system.distro.id', return_value=os_name), \
                patch('ou_dedetai.system.distro.major_version', return_value=major), \
                patch('ou_dedetai.system.shutil.which', side_effect=lambda command: '/usr/bin/apt'
                      if command == 'apt' else None):
            return set(get_package_manager().packages.split())

    def test_ubuntu_and_kubuntu_26_use_available_packages(self):
        for os_name in ('ubuntu', 'kubuntu'):
            with self.subTest(os_name=os_name):
                packages = self.packages(os_name, '26')
                self.assertTrue({'7zip', 'libfuse3-4', 'cabextract', 'winbind'} <= packages)
                self.assertNotIn('p7zip-full', packages)
                self.assertNotIn('libfuse3-3', packages)

    def test_ubuntu_24_keeps_existing_packages(self):
        packages = self.packages('ubuntu', '24')
        self.assertTrue({'p7zip-full', 'libfuse3-3'} <= packages)
        self.assertNotIn('7zip', packages)

    def test_ubuntu_22_keeps_fuse2(self):
        self.assertTrue({'p7zip-full', 'libfuse2'} <= self.packages('ubuntu', '22'))

    def test_other_apt_distributions_keep_existing_packages(self):
        for os_name, version, fuse in [('debian', '13', 'libfuse3-4'), ('linuxmint', '22', 'libfuse3-3')]:
            with self.subTest(os_name=os_name):
                self.assertTrue({'p7zip-full', fuse} <= self.packages(os_name, version))
