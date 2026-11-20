"""Small known-answer tests for the post-collection estimands."""
import unittest
from .analyze_risk_final import aggregate, capped, paired_stats


class AnalysisTests(unittest.TestCase):
    def row(self, outcome, elapsed):
        return dict(outcome=outcome, elapsed_wall_s=elapsed, time_limit_s=240,
                    tracking_loss_wall_s=0, clutch_calibrations=1, reason='timeout')

    def test_failures_and_stalled_timeouts_have_full_time_penalty(self):
        self.assertEqual(capped(self.row('failure', 9)), 240)
        self.assertEqual(capped(self.row('failure', 597)), 240)
        self.assertEqual(capped(self.row('success', 89)), 89)

    def test_efficiency_uses_real_window_and_includes_failure(self):
        a = aggregate([self.row('success', 100), self.row('failure', 500)])
        self.assertEqual(a['success_rate'], .5)
        self.assertEqual(a['mean_capped_time_s'], 170)
        self.assertEqual(a['successes_per_600s'], 1)
        self.assertEqual(a['mean_success_only_time_s'], 100)

    def test_exact_small_sample_resolution(self):
        self.assertEqual(paired_stats([1, 1, 1, 1, 1])['sign_flip_two_sided_p'], .0625)
        self.assertEqual(paired_stats([0, 0, 0, 0, 0])['sign_flip_two_sided_p'], 1)
        self.assertEqual(paired_stats([0, -.25, 0, .5, 0])['sign_flip_two_sided_p'], 1)

    def test_known_t_interval(self):
        r = paired_stats([-2, -1, 0, 1, 2])
        self.assertEqual(r['mean_difference'], 0)
        self.assertAlmostEqual(r['t_interval_95'][1], 1.96324316, places=6)


if __name__ == '__main__':
    unittest.main()
