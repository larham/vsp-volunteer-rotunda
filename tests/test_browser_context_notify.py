import os
import sys
import unittest
from unittest.mock import patch, MagicMock, call

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import opportunities


class TestBrowserContextNotification(unittest.TestCase):

    def setUp(self):
        self.config_content = """[Opportunities]
username=testuser
password=testpass
login=https://example.com/login
home=https://example.com/home

[Cron]
param=entry.12345
url=https://docs.google.com/forms/d/e/test_form/formResponse
"""
        self.test_config_file = "/tmp/test_guild.properties"
        with open(self.test_config_file, "w") as f:
            f.write(self.config_content)

    def tearDown(self):
        if os.path.exists(self.test_config_file):
            os.remove(self.test_config_file)

    @patch("urllib.request.urlopen")
    @patch("os.path.exists")
    @patch("os.mkdir")
    def test_ensureDirs_sends_google_form_message_when_context_dir_missing(
        self, mock_mkdir, mock_exists, mock_urlopen
    ):
        # DOWNLOAD_DIR exists (True), CHROME_PROFILE_DIR does not exist (False)
        def exists_side_effect(path):
            if path == opportunities.DOWNLOAD_DIR:
                return True
            if path == opportunities.CHROME_PROFILE_DIR:
                return False
            if path == self.test_config_file:
                return True
            return False

        mock_exists.side_effect = exists_side_effect

        opportunities.ensureDirs(config_file=self.test_config_file)

        # Check os.mkdir was called for CHROME_PROFILE_DIR
        mock_mkdir.assert_called_once_with(opportunities.CHROME_PROFILE_DIR)

        # Check google form message was posted
        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(
            req.full_url,
            "https://docs.google.com/forms/d/e/test_form/formResponse",
        )
        expected_msg = (
            "The VSP scan tool is creating a browser context, perhaps after a reboot."
        )
        self.assertIn("entry.12345=", req.data.decode("utf-8"))
        self.assertIn("The+VSP+scan+tool+is+creating+a+browser+context%2C+perhaps+after+a+reboot.", req.data.decode("utf-8"))

    @patch("urllib.request.urlopen")
    @patch("os.path.exists")
    @patch("os.mkdir")
    def test_ensureDirs_does_not_send_message_when_context_dir_exists(
        self, mock_mkdir, mock_exists, mock_urlopen
    ):
        # Both DOWNLOAD_DIR and CHROME_PROFILE_DIR exist
        mock_exists.return_value = True

        opportunities.ensureDirs(config_file=self.test_config_file)

        mock_mkdir.assert_not_called()
        mock_urlopen.assert_not_called()

    @patch("urllib.request.urlopen")
    @patch("os.path.exists")
    @patch("os.mkdir")
    def test_ensureDirs_handles_missing_cron_section_gracefully(
        self, mock_mkdir, mock_exists, mock_urlopen
    ):
        no_cron_config = "/tmp/no_cron.properties"
        with open(no_cron_config, "w") as f:
            f.write("[Opportunities]\nusername=foo\n")

        def exists_side_effect(path):
            if path == opportunities.DOWNLOAD_DIR:
                return True
            if path == opportunities.CHROME_PROFILE_DIR:
                return False
            if path == no_cron_config:
                return True
            return False

        mock_exists.side_effect = exists_side_effect

        try:
            opportunities.ensureDirs(config_file=no_cron_config)
            mock_mkdir.assert_called_once_with(opportunities.CHROME_PROFILE_DIR)
            mock_urlopen.assert_not_called()
        finally:
            if os.path.exists(no_cron_config):
                os.remove(no_cron_config)


if __name__ == "__main__":
    unittest.main()
