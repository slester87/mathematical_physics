import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from analyze import (HERE, YIELD_UNIT, analyze, count_photons, limits, poisson_lower,
                     response, source_distribution, window_probability)


class EventTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = HERE / "example/event.json"
        cls.event = json.loads(cls.path.read_text())
        cls.sensor = cls.event["sensor"]
        cls.table = HERE / "lattice.csv"

    def test_fixture_and_quadrature_convergence(self):
        coarse = list(analyze(self.path, self.table, 48))
        fine = list(analyze(self.path, self.table, 96))
        self.assertEqual(len(coarse), 9)
        excluded = {(r["group"], r["sqrt_sigma_MeV"]) for r in coarse if r["status"] == "excluded_point"}
        self.assertEqual(excluded, {("SU(2)", 0.9), ("SU(3)", 1.0), ("SU(4)", 1.1)})
        for a, b in zip(coarse, fine):
            self.assertEqual(a["n_observed"], 2)
            self.assertEqual(a["limit_status"], b["limit_status"])
            self.assertEqual(a["status"], b["status"])
            self.assertLess(abs(a["lower_tail"] - b["lower_tail"]), 1e-8)
            if b["upper_photons"] is not None:
                self.assertLess(abs(a["upper_photons"] / b["upper_photons"] - 1), 2e-6)

    def test_zero_count_analytic_limit_and_scale(self):
        # exp[-(b + y r)] = alpha at the upper limit.
        for rate in (2., 1e25):
            _, upper, _, _ = limits(0, 0.5, np.array([rate]), np.ones(1), 1., 100., 0.05)
            expected = (-math.log(0.05) - 0.5) / rate * YIELD_UNIT
            self.assertAlmostEqual(upper / expected, 1., places=12)

    def test_invert_mixture_not_mean_rate(self):
        rates, weights = np.array([1., 9.]), np.array([0.5, 0.5])
        p, _, _, _ = limits(0, 0., rates, weights, 1., 100., 0.05)
        self.assertAlmostEqual(p, (math.exp(-1) + math.exp(-9)) / 2)
        self.assertGreater(p, math.exp(-5))

    def test_discrete_test_size(self):
        rates, weights = np.array([1., 9.]), np.array([0.5, 0.5])
        means = 1 + 3 * rates
        size = 0.
        for n in range(25):
            if float(weights @ poisson_lower(n, means)) <= 0.05:
                size += float(weights @ np.exp(-means + n * np.log(means) - math.lgamma(n + 1)))
        self.assertGreater(size, 0.)
        self.assertLessEqual(size, 0.05)

    def test_degenerate_mass_scale_and_distance(self):
        z = np.array([0.01])
        at_40 = (np.array([40.]), z, np.ones(1))
        at_80 = (np.array([80.]), z, np.ones(1))
        a = response(at_40, self.sensor, 3.405, 0., 1., 8)
        b = response(at_80, self.sensor, 3.781, 0., 3.405 / 3.781, 8)
        self.assertAlmostEqual(a[2], b[2])
        np.testing.assert_allclose(a[0], 4 * b[0], rtol=1e-12)

    def test_off_band_and_background(self):
        source = (np.array([40.]), np.array([0.01]), np.ones(1))
        rate, w, _ = response(source, self.sensor, 3.4, 0, 100, 8)
        self.assertTrue(np.all(rate == 0))
        self.assertEqual(limits(2, 1., rate, w, 1., 100., .05)[1:],
                         (None, "retained_point", "above_scan_max"))
        self.assertEqual(limits(0, 10., rate, w, 1., 100., .05)[2], "background_tension")
        self.assertAlmostEqual(window_probability(0., -1., 1., 1.), 0.6826894921370859)

    def test_source_update(self):
        path = self.path.parent / self.event["gw"]["samples"]
        _, z, weights = source_distribution(path, self.event["host"], self.event["event_id"])
        self.assertGreater(weights[z == 0.01].sum(), 0.4)
        self.assertAlmostEqual(weights.sum(), 1.)

    def test_exposure_event_ids_and_window_edges(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.csv"
            header = "event_id,photon_id,dt_s,energy_MeV\n"
            path.write_text(header + "e,a,0,1.66\ne,b,2,1.70\ne,c,1,1.84\n")
            self.assertEqual(count_photons(path, self.sensor, "e"), 1)
            with self.assertRaisesRegex(ValueError, "different event"):
                count_photons(path, self.sensor, "other")
            with self.assertRaisesRegex(ValueError, "exposure"):
                count_photons(path, dict(self.sensor, continuous_live_interval_s=[0, 0.5]), "e")
            path.write_text(header + "e,a,0.1,1.7\ne,a,0.1,1.7\n")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                count_photons(path, self.sensor, "e")
            path.write_text("")
            with self.assertRaisesRegex(ValueError, "columns"):
                count_photons(path, self.sensor, "e")
            path.write_text(header)
            self.assertEqual(count_photons(path, self.sensor, "e"), 0)


if __name__ == "__main__":
    unittest.main()
