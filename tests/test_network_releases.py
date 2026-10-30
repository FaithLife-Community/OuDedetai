import json
import unittest
from unittest.mock import Mock, patch

from ou_dedetai import network


REPO = 'FaithLife-Community/wine-appimages'


def release(name, date, assets, beta=False):
    return dict(tag_name=name, updated_at=date, prerelease=beta,
                assets=[dict(browser_download_url='https://example.invalid/' + asset) for asset in assets])


class TestWineReleaseAssets(unittest.TestCase):
    def fetch(self, releases, repository=REPO):
        with patch.object(network, '_net_get', return_value=json.dumps(releases).encode()):
            return network._get_release_data(repository)

    def test_archive_only_release_is_skipped(self):
        result = self.fetch([
            release('10.13-staging', '2026-10-30T00:00:00Z', ['wine.tar.xz']),
            release('10.13-devel', '2025-08-29T00:00:00Z', ['wine-devel.AppImage'], beta=True),
            release('10.8-staging', '2025-05-29T00:00:00Z', ['wine-staging.AppImage'])])
        self.assertEqual(result.pre_release.download_url, 'https://example.invalid/wine-devel.AppImage')
        self.assertEqual(result.latest.download_url, 'https://example.invalid/wine-staging.AppImage')

    def test_appimage_selected_even_when_not_first_asset(self):
        result = self.fetch([release('10.8', '2025-05-29T00:00:00Z',
                                     ['wine.tar.gz', 'checksums.txt', 'wine.AppImage'])])
        self.assertEqual(result.latest.download_url, 'https://example.invalid/wine.AppImage')

    def test_no_appimage_does_not_recommend_archive(self):
        result = self.fetch([release('10.13', '2026-10-30T00:00:00Z', ['wine.tar.xz'], beta=True)])
        self.assertIsNone(result.latest)
        self.assertIsNone(result.pre_release)

    def test_other_repositories_keep_their_asset_selection(self):
        result = self.fetch([release('1.0', '2025-05-29T00:00:00Z', ['icu.tar.gz'])], 'FaithLife-Community/icu')
        self.assertEqual(result.latest.download_url, 'https://example.invalid/icu.tar.gz')

    def test_cached_archive_is_refreshed_without_clearing_other_repositories(self):
        requests = object.__new__(network.NetworkRequests)
        requests._cache = network.CachedRequests(
            repository_latest_version={REPO: '10.8', 'other/repo': '1'},
            repository_latest_url={REPO: 'https://example.invalid/stable.AppImage', 'other/repo': 'other'},
            repository_latest_pre_release_version={REPO: '10.13'},
            repository_latest_pre_release_url={REPO: 'https://example.invalid/wine.tar.xz'})
        requests._cache._write = Mock()
        fresh = network.GithubSoftwareReleasesInfo(
            latest=network.SoftwareReleaseInfo('10.8', 'https://example.invalid/stable.AppImage'),
            pre_release=network.SoftwareReleaseInfo('10.13', 'https://example.invalid/devel.AppImage'))
        with patch.object(network, '_get_release_data', return_value=fresh) as fetch:
            result = requests.wine_appimage_versions()
        fetch.assert_called_once_with(REPO)
        self.assertEqual(result.pre_release.download_url, fresh.pre_release.download_url)
        self.assertEqual(requests._cache.repository_latest_url['other/repo'], 'other')
        self.assertEqual(requests._cache.repository_latest_pre_release_url[REPO], fresh.pre_release.download_url)
        requests._cache._write.assert_called_once()

    def test_valid_appimage_cache_does_not_trigger_network(self):
        requests = object.__new__(network.NetworkRequests)
        requests._cache = network.CachedRequests(repository_latest_version={REPO: '10.8'},
                                                repository_latest_url={REPO: 'https://example.invalid/wine.AppImage'})
        with patch.object(network, '_get_release_data') as fetch:
            self.assertEqual(requests.wine_appimage_versions().latest.version, '10.8')
        fetch.assert_not_called()
