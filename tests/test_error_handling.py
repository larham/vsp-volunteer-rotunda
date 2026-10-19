import datetime
import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch, MagicMock
from selenium.common.exceptions import TimeoutException, WebDriverException
from urllib3.exceptions import ReadTimeoutError

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import opportunities


def make_rotunda_html(num_events=12, extra_event_ids=None):
    """Build realistic Rotunda VSP schedule HTML with ministry-group-view cells."""
    event_ids = [f"/da/2000000/ministry_schedule?id={i}" for i in range(1, num_events + 1)]
    if extra_event_ids:
        event_ids.extend(extra_event_ids)

    rows = []
    for idx, href in enumerate(event_ids):
        rows.append(
            f"""
            <td class="modui-base ministry-group-view label">
                <a href="{href}">Sat, 6:30 PM - 9:00 PM ({idx:02d})</a>
                - at null(Band {idx})
            </td>
            """
        )
    return f"""
    <html>
      <body>
        <div class="minister">Usher</div>
        <div class="modui-base mass-group-view">
          <div class="mass-group-label">Oct 1 - Oct 31</div>
          <table><tr>{''.join(rows)}</tr></table>
        </div>
      </body>
    </html>
    """


class TestTransientErrorHandling(unittest.TestCase):

    def setUp(self):
        self.errors_file = "/tmp/test_vsp_errors.json"
        self.failed_login_file = "/tmp/test_vsp_post_login.html"
        self.first_page_file = "/tmp/test_vsp_first_page.html"
        for f in (self.errors_file, self.failed_login_file, self.first_page_file):
            if os.path.exists(f):
                os.remove(f)

    def tearDown(self):
        for f in (self.errors_file, self.failed_login_file, self.first_page_file):
            if os.path.exists(f):
                os.remove(f)

    # -------------------------------------------------------------------------
    # 1. Cron Simulation: 2-Day Consistency & 30-Day Retention for Graphing
    # -------------------------------------------------------------------------

    def test_cron_every_30_min_suppresses_until_exceeding_two_full_days(self):
        """
        Simulate cron running every 30 minutes during an outage:
        - Run 0 succeeds.
        - Runs 1..96 (48 hours) fail with transient errors -> all exit with ERR_CODE_TIMEOUT (33).
        - Run 97 (48 hours 30 minutes) fails -> exits with 1 to trigger notification.
        """
        t0 = datetime.datetime(2026, 10, 1, 9, 0, 0)
        opportunities.record_success(now=t0, errors_file=self.errors_file)

        first_fail = t0 + datetime.timedelta(minutes=30)
        # 96 intervals of 30 minutes from first_fail covers 0h00m to 47h30m, plus 48h00m (step 96)
        for step in range(0, 97):
            current_time = first_fail + datetime.timedelta(minutes=30 * step)
            with self.assertRaises(SystemExit) as cm:
                opportunities.handle_transient_error(
                    f"net::ERR_ADDRESS_UNREACHABLE at step {step}",
                    now=current_time,
                    errors_file=self.errors_file,
                )
            self.assertEqual(
                cm.exception.code,
                opportunities.ERR_CODE_TIMEOUT,
                f"Expected transient suppression at +{step * 0.5}h, got exit {cm.exception.code}",
            )

        # At 48h30m after first_fail, the error has repeated for > 2 days consistently
        over_two_days = first_fail + datetime.timedelta(days=2, minutes=30)
        with self.assertRaises(SystemExit) as cm:
            opportunities.handle_transient_error(
                "net::ERR_ADDRESS_UNREACHABLE after >2 days",
                now=over_two_days,
                errors_file=self.errors_file,
            )
        self.assertEqual(cm.exception.code, 1)

        data = opportunities.load_error_data(self.errors_file)
        self.assertEqual(len(data["errors"]), 98)

    def test_intermittent_daily_glitches_over_a_week_never_notify_and_preserve_graph_data(self):
        """
        If transient errors happen a few times every day for 7 days, but successful runs
        occur in between, the script must NEVER exit(1), yet must keep all transient
        error records across the week so they can be graphed later.
        """
        base = datetime.datetime(2026, 10, 1, 9, 0, 0)
        total_expected_errors = 0

        for day in range(7):
            day_start = base + datetime.timedelta(days=day)
            # 3 hours of transient failures each morning (6 runs)
            for half_hour in range(6):
                t = day_start + datetime.timedelta(minutes=30 * half_hour)
                with self.assertRaises(SystemExit) as cm:
                    opportunities.handle_transient_error(
                        f"ReadTimeoutError on day {day} run {half_hour}",
                        now=t,
                        errors_file=self.errors_file,
                    )
                self.assertEqual(cm.exception.code, opportunities.ERR_CODE_TIMEOUT)
                total_expected_errors += 1

            # Followed by a successful run at 12:00 PM
            t_ok = day_start + datetime.timedelta(hours=3)
            opportunities.record_success(now=t_ok, errors_file=self.errors_file)

        data = opportunities.load_error_data(self.errors_file)
        self.assertEqual(len(data["errors"]), total_expected_errors)

    def test_recovery_after_two_day_outage_resets_alert_state_on_next_glitch(self):
        """
        Once an outage exceeds 2 days (exiting 1), a single successful run resets
        the streak so a subsequent transient glitch is suppressed (exits 33) again.
        """
        start = datetime.datetime(2026, 10, 1, 9, 0, 0)
        opportunities.record_transient_error("outage start", now=start, errors_file=self.errors_file)

        # Outage crosses 2 days -> exits 1
        day2_plus = start + datetime.timedelta(days=2, hours=1)
        with self.assertRaises(SystemExit) as cm:
            opportunities.handle_transient_error("still down", now=day2_plus, errors_file=self.errors_file)
        self.assertEqual(cm.exception.code, 1)

        # Service recovers 30 mins later
        recovery_time = day2_plus + datetime.timedelta(minutes=30)
        opportunities.record_success(now=recovery_time, errors_file=self.errors_file)

        # New transient glitch 1 hour after recovery -> suppressed (exit 33)
        new_glitch_time = recovery_time + datetime.timedelta(hours=1)
        with self.assertRaises(SystemExit) as cm:
            opportunities.handle_transient_error("brief glitch", now=new_glitch_time, errors_file=self.errors_file)
        self.assertEqual(cm.exception.code, opportunities.ERR_CODE_TIMEOUT)

        # All 3 transient errors are still in errors.json for graphing
        data = opportunities.load_error_data(self.errors_file)
        self.assertEqual(len(data["errors"]), 3)

    def test_rolling_30_day_window_prunes_only_expired_records(self):
        start = datetime.datetime(2026, 9, 1, 12, 0, 0)
        # Record 1 error per day for 45 days
        for day in range(45):
            now = start + datetime.timedelta(days=day)
            opportunities.record_transient_error(f"err-day-{day}", now=now, errors_file=self.errors_file)

        # At day 44, cutoff is day 14 (44 - 30 = 14), so days 14..44 inclusive (31 records) remain
        data = opportunities.load_error_data(self.errors_file)
        self.assertEqual(len(data["errors"]), 31)
        self.assertEqual(data["errors"][0]["error"], "err-day-14")
        self.assertEqual(data["errors"][-1]["error"], "err-day-44")

    def test_corrupted_errors_json_recovers_gracefully(self):
        with open(self.errors_file, "w") as f:
            f.write("{corrupted json!!!")

        now = datetime.datetime(2026, 10, 19, 9, 0, 0)
        with self.assertRaises(SystemExit) as cm:
            opportunities.handle_transient_error("first error after corruption", now=now, errors_file=self.errors_file)
        self.assertEqual(cm.exception.code, opportunities.ERR_CODE_TIMEOUT)

        data = opportunities.load_error_data(self.errors_file)
        self.assertEqual(len(data["errors"]), 1)

    # -------------------------------------------------------------------------
    # 2. Error Classification in main() and get_browser():
    #    Transient Network Errors vs Immediate Structural/Auth Errors
    # -------------------------------------------------------------------------

    @patch("opportunities.ERRORS_FILE", "/tmp/test_vsp_errors.json")
    @patch("opportunities.get_previously_downloaded_events", return_value=None)
    @patch("opportunities.get_browser")
    @patch("opportunities.ensureDirs")
    @patch("opportunities.get_user_pass", return_value=("u", "p", "http://login", "http://home"))
    def test_main_catches_webdriver_exception_err_address_unreachable(
        self, mock_creds, mock_dirs, mock_get_browser, mock_prev
    ):
        mock_browser = MagicMock()
        mock_browser.get.side_effect = WebDriverException(
            "Message: unknown error: net::ERR_ADDRESS_UNREACHABLE\n  (Session info: chrome=155.0.8059.79)"
        )
        mock_get_browser.return_value = mock_browser

        with self.assertRaises(SystemExit) as cm:
            opportunities.main()

        self.assertEqual(cm.exception.code, opportunities.ERR_CODE_TIMEOUT)
        data = opportunities.load_error_data(self.errors_file)
        self.assertEqual(len(data["errors"]), 1)
        self.assertIn("ERR_ADDRESS_UNREACHABLE", data["errors"][0]["error"])

    @patch("opportunities.ERRORS_FILE", "/tmp/test_vsp_errors.json")
    @patch("opportunities.get_previously_downloaded_events", return_value=None)
    @patch("opportunities.get_browser")
    @patch("opportunities.ensureDirs")
    @patch("opportunities.get_user_pass", return_value=("u", "p", "http://login", "http://home"))
    def test_main_catches_read_timeout_error_and_records_transient(
        self, mock_creds, mock_dirs, mock_get_browser, mock_prev
    ):
        mock_browser = MagicMock()
        mock_browser.get.side_effect = ReadTimeoutError(None, "http://home", "Read timed out.")
        mock_get_browser.return_value = mock_browser

        with self.assertRaises(SystemExit) as cm:
            opportunities.main()

        self.assertEqual(cm.exception.code, opportunities.ERR_CODE_TIMEOUT)
        data = opportunities.load_error_data(self.errors_file)
        self.assertEqual(len(data["errors"]), 1)
        self.assertIn("Read timed out", data["errors"][0]["error"])

    @patch("opportunities.ERRORS_FILE", "/tmp/test_vsp_errors.json")
    @patch("opportunities.ChromeDriverManager")
    @patch("opportunities.webdriver.Chrome")
    def test_get_browser_oserror_or_webdriver_error_is_tracked_as_transient(
        self, mock_chrome, mock_driver_mgr
    ):
        mock_chrome.side_effect = WebDriverException("chrome failed to start")
        with self.assertRaises(SystemExit) as cm:
            opportunities.get_browser()

        self.assertEqual(cm.exception.code, opportunities.ERR_CODE_TIMEOUT)
        data = opportunities.load_error_data(self.errors_file)
        self.assertEqual(len(data["errors"]), 1)
        self.assertIn("chrome failed to start", data["errors"][0]["error"])

    @patch("opportunities.ERRORS_FILE", "/tmp/test_vsp_errors.json")
    @patch("opportunities.FAILED_LOGIN_RESULT", "/tmp/test_vsp_post_login.html")
    @patch("opportunities.login")
    @patch("opportunities.wait_for_schedule", return_value=False)
    @patch("opportunities.get_previously_downloaded_events", return_value=None)
    @patch("opportunities.get_browser")
    @patch("opportunities.ensureDirs")
    @patch("opportunities.get_user_pass", return_value=("u", "p", "http://login", "http://home"))
    def test_login_failure_notifies_immediately_and_is_not_recorded_as_transient(
        self, mock_creds, mock_dirs, mock_get_browser, mock_prev, mock_wait, mock_login
    ):
        """
        If the login page still shows "Don't have an account yet?" after attempting login,
        it must immediately exit(1) (so notify.py alerts right away) and NOT record a transient error.
        """
        mock_browser = MagicMock()
        mock_browser.page_source = "<html><body>Don't have an account yet?</body></html>"
        mock_get_browser.return_value = mock_browser

        with self.assertRaises(SystemExit) as cm:
            opportunities.main()

        self.assertEqual(cm.exception.code, 1)
        self.assertTrue(os.path.exists(self.failed_login_file))
        self.assertFalse(os.path.exists(self.errors_file))

    @patch("opportunities.ERRORS_FILE", "/tmp/test_vsp_errors.json")
    @patch("opportunities.VSP_FIRST_PAGE", "/tmp/test_vsp_first_page.html")
    @patch("opportunities.wait_for_schedule", return_value=False)
    @patch("opportunities.get_previously_downloaded_events", return_value=None)
    @patch("opportunities.get_browser")
    @patch("opportunities.ensureDirs")
    @patch("opportunities.get_user_pass", return_value=("u", "p", "http://login", "http://home"))
    def test_missing_schedule_when_logged_in_notifies_immediately(
        self, mock_creds, mock_dirs, mock_get_browser, mock_prev, mock_wait
    ):
        """
        If we are logged in (not on login page) but schedule element is missing (layout changed),
        it must immediately exit(1) and NOT record a transient error.
        """
        mock_browser = MagicMock()
        mock_browser.page_source = "<html><body>Welcome, User! New layout without schedule.</body></html>"
        mock_get_browser.return_value = mock_browser

        with self.assertRaises(SystemExit) as cm:
            opportunities.main()

        self.assertEqual(cm.exception.code, 1)
        self.assertTrue(os.path.exists(self.first_page_file))
        self.assertFalse(os.path.exists(self.errors_file))

    @patch("opportunities.ERRORS_FILE", "/tmp/test_vsp_errors.json")
    @patch("opportunities.wait_for_schedule", return_value=True)
    @patch("opportunities.get_previously_downloaded_events", return_value=None)
    @patch("opportunities.get_browser")
    @patch("opportunities.ensureDirs")
    @patch("opportunities.get_user_pass", return_value=("u", "p", "http://login", "http://home"))
    def test_too_few_events_notifies_immediately_and_does_not_record_success(
        self, mock_creds, mock_dirs, mock_get_browser, mock_prev, mock_wait
    ):
        """
        If fewer than 10 events are found on the schedule page (e.g. HTML table format changed),
        it must immediately exit(1) and must NOT record a success or transient error.
        """
        mock_browser = MagicMock()
        mock_browser.page_source = make_rotunda_html(num_events=3)
        mock_get_browser.return_value = mock_browser

        with self.assertRaises(SystemExit) as cm:
            opportunities.main()

        self.assertEqual(cm.exception.code, 1)
        self.assertFalse(os.path.exists(self.errors_file))

    # -------------------------------------------------------------------------
    # 3. End-to-End Opportunity Diffing & Success Tracking in main()
    # -------------------------------------------------------------------------

    @patch("opportunities.ERRORS_FILE", "/tmp/test_vsp_errors.json")
    @patch("opportunities.save_page")
    @patch("opportunities.wait_for_schedule", return_value=True)
    @patch("opportunities.get_previously_downloaded_events")
    @patch("opportunities.get_browser")
    @patch("opportunities.ensureDirs")
    @patch("opportunities.get_user_pass", return_value=("u", "p", "http://login", "http://home"))
    def test_main_detects_new_opportunities_and_updates_last_success(
        self, mock_creds, mock_dirs, mock_get_browser, mock_prev, mock_wait, mock_save
    ):
        prev_html = make_rotunda_html(num_events=10)
        curr_html = make_rotunda_html(
            num_events=10,
            extra_event_ids=["/da/2000000/ministry_schedule?id=999"],
        )
        mock_prev.return_value = prev_html
        mock_browser = MagicMock()
        mock_browser.page_source = curr_html
        mock_get_browser.return_value = mock_browser

        stdout_buf = io.StringIO()
        with redirect_stdout(stdout_buf):
            opportunities.main()

        output = stdout_buf.getvalue()
        self.assertIn("https://secure.rotundasoftware.com/da/2000000/ministry_schedule?id=999", output)
        self.assertIn("Oct 1 - Oct 31", output)
        mock_save.assert_called_once_with(curr_html)

        data = opportunities.load_error_data(self.errors_file)
        self.assertIsNotNone(data["last_success"])
        self.assertEqual(data["errors"], [])

    @patch("opportunities.ERRORS_FILE", "/tmp/test_vsp_errors.json")
    @patch("opportunities.save_page")
    @patch("opportunities.wait_for_schedule", return_value=True)
    @patch("opportunities.get_previously_downloaded_events")
    @patch("opportunities.get_browser")
    @patch("opportunities.ensureDirs")
    @patch("opportunities.get_user_pass", return_value=("u", "p", "http://login", "http://home"))
    def test_main_ignores_expired_events_and_outputs_nothing_to_stdout(
        self, mock_creds, mock_dirs, mock_get_browser, mock_prev, mock_wait, mock_save
    ):
        """
        When events in prev_content expire (so current has 10 events that were all in prev's 12 events),
        no diff should be reported, stdout must be empty, and save_page must not be called.
        """
        prev_html = make_rotunda_html(num_events=12)
        curr_html = make_rotunda_html(num_events=10)
        mock_prev.return_value = prev_html
        mock_browser = MagicMock()
        mock_browser.page_source = curr_html
        mock_get_browser.return_value = mock_browser

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            opportunities.main()

        self.assertEqual(stdout_buf.getvalue(), "")
        self.assertIn("no change", stderr_buf.getvalue())
        mock_save.assert_not_called()

        data = opportunities.load_error_data(self.errors_file)
        self.assertIsNotNone(data["last_success"])

    # -------------------------------------------------------------------------
    # 4. Newly Hardened Transient vs Immediate Cases
    # -------------------------------------------------------------------------

    @patch("opportunities.ERRORS_FILE", "/tmp/test_vsp_errors.json")
    @patch("opportunities.ChromeDriverManager")
    def test_get_browser_catches_urllib3_http_error_from_chromedriver_manager(
        self, mock_driver_mgr
    ):
        from urllib3.exceptions import MaxRetryError
        mock_driver_mgr.return_value.install.side_effect = MaxRetryError(
            None, "https://chromedriver.storage.googleapis.com"
        )
        with self.assertRaises(SystemExit) as cm:
            opportunities.get_browser()

        self.assertEqual(cm.exception.code, opportunities.ERR_CODE_TIMEOUT)
        data = opportunities.load_error_data(self.errors_file)
        self.assertEqual(len(data["errors"]), 1)

    @patch("opportunities.ERRORS_FILE", "/tmp/test_vsp_errors.json")
    @patch("opportunities.WebDriverWait")
    def test_login_post_click_redirect_timeout_is_treated_as_transient(
        self, mock_wait
    ):
        """
        When the login button and form inputs are found and clicked, but waiting
        for EC.url_changes times out due to a slow server response, it should be
        recorded as a transient error (exit 33).
        """
        mock_submit = MagicMock()
        # First WebDriverWait (finding button) succeeds; second (url_changes) times out
        mock_wait.return_value.until.side_effect = [
            mock_submit,
            TimeoutException("timed out waiting for url change"),
        ]
        mock_browser = MagicMock()

        with self.assertRaises(SystemExit) as cm:
            opportunities.login(mock_browser, "http://login", "user", "pass")

        self.assertEqual(cm.exception.code, opportunities.ERR_CODE_TIMEOUT)
        data = opportunities.load_error_data(self.errors_file)
        self.assertEqual(len(data["errors"]), 1)
        self.assertIn("login timed out after clicking login button", data["errors"][0]["error"])

    @patch("opportunities.ERRORS_FILE", "/tmp/test_vsp_errors.json")
    @patch("opportunities.FAILED_LOGIN_RESULT", "/tmp/test_vsp_post_login.html")
    @patch("opportunities.WebDriverWait")
    @patch("opportunities.wait_for_schedule", return_value=False)
    @patch("opportunities.get_previously_downloaded_events", return_value=None)
    @patch("opportunities.get_browser")
    @patch("opportunities.ensureDirs")
    @patch("opportunities.get_user_pass", return_value=("u", "p", "http://login", "http://home"))
    def test_login_missing_input_element_notifies_immediately_not_transient(
        self, mock_creds, mock_dirs, mock_get_browser, mock_prev, mock_wait_sched, mock_wd_wait
    ):
        """
        If the login page HTML changed such that By.NAME 'username' raises NoSuchElementException
        (a subclass of WebDriverException), it must NOT be swallowed as a transient network error;
        it must immediately exit(1).
        """
        from selenium.common.exceptions import NoSuchElementException
        mock_wd_wait.return_value.until.return_value = MagicMock()
        mock_browser = MagicMock()
        mock_browser.page_source = "<html><body>Don't have an account yet?</body></html>"
        mock_browser.find_element.side_effect = NoSuchElementException("no username input")
        mock_get_browser.return_value = mock_browser

        with self.assertRaises(SystemExit) as cm:
            opportunities.main()

        self.assertEqual(cm.exception.code, 1)
        self.assertTrue(os.path.exists(self.failed_login_file))
        self.assertFalse(os.path.exists(self.errors_file))

    @patch("opportunities.ERRORS_FILE", "/tmp/test_vsp_errors.json")
    @patch("opportunities.wait_for_schedule", side_effect=[False, True])
    @patch("opportunities.get_previously_downloaded_events")
    @patch("opportunities.get_browser")
    @patch("opportunities.ensureDirs")
    @patch("opportunities.get_user_pass", return_value=("u", "p", "http://login", "http://home"))
    def test_main_retries_schedule_once_before_failing(
        self, mock_creds, mock_dirs, mock_get_browser, mock_prev, mock_wait
    ):
        """
        If the async XHR loading the schedule tab times out on the first attempt
        but succeeds on retry, main() succeeds normally.
        """
        html = make_rotunda_html(num_events=10)
        mock_prev.return_value = html
        mock_browser = MagicMock()
        mock_browser.page_source = html
        mock_get_browser.return_value = mock_browser

        opportunities.main()

        self.assertEqual(mock_wait.call_count, 2)
        data = opportunities.load_error_data(self.errors_file)
        self.assertIsNotNone(data["last_success"])
        self.assertEqual(data["errors"], [])

    @patch("opportunities.ERRORS_FILE", "/tmp/test_vsp_errors.json")
    @patch("opportunities.wait_for_schedule", return_value=False)
    @patch("opportunities.get_previously_downloaded_events", return_value=None)
    @patch("opportunities.get_browser")
    @patch("opportunities.ensureDirs")
    @patch("opportunities.get_user_pass", return_value=("u", "p", "http://login", "http://home"))
    def test_502_bad_gateway_page_is_treated_as_transient_not_layout_change(
        self, mock_creds, mock_dirs, mock_get_browser, mock_prev, mock_wait
    ):
        """
        If Rotunda returns a 502 Bad Gateway or blank page, wait_for_schedule returns False
        and 'Don't have an account yet?' is absent, but it is a transient server error (exit 33),
        not a layout change.
        """
        mock_browser = MagicMock()
        mock_browser.page_source = "<html><head><title>502 Bad Gateway</title></head><body><h1>502 Bad Gateway</h1></body></html>"
        mock_get_browser.return_value = mock_browser

        with self.assertRaises(SystemExit) as cm:
            opportunities.main()

        self.assertEqual(cm.exception.code, opportunities.ERR_CODE_TIMEOUT)
        data = opportunities.load_error_data(self.errors_file)
        self.assertEqual(len(data["errors"]), 1)
        self.assertIn("transient empty/gateway error page", data["errors"][0]["error"])


if __name__ == "__main__":
    unittest.main()

