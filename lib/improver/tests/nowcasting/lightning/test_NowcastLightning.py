# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# (C) British Crown Copyright 2017-2018 Met Office.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
#
# * Neither the name of the copyright holder nor the names of its
#   contributors may be used to endorse or promote products derived from
#   this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
"""Unit tests for the nowcast.lightning.NowcastLightning plugin."""


import unittest

from iris.util import squeeze
from iris.coords import DimCoord
from iris.cube import Cube, CubeList
from iris.tests import IrisTest
from iris.exceptions import CoordinateNotFoundError, ConstraintMismatchError
import numpy as np
import cf_units

from improver.nowcasting.lightning import NowcastLightning as Plugin
from improver.tests.nbhood.nbhood.test_BaseNeighbourhoodProcessing import (
    set_up_cube, set_up_cube_with_no_realizations)
from improver.tests.ensemble_calibration.ensemble_calibration.helper_functions\
    import add_forecast_reference_time_and_forecast_period


class Test__init__(IrisTest):

    """Test the __init__ method accepts keyword arguments."""

    def test_with_radius(self):
        """
        Test that the radius keyword is accepted.
        """
        radius = 20000.
        plugin = Plugin(radius=radius)
        self.assertEqual(plugin.radius, radius)


class Test__repr__(IrisTest):

    """Test the repr method."""

    def test_basic(self):
        """Test that the __repr__ returns the expected string."""
        # Have to pass in a lambda to ensure two strings match the same
        # function address.
        def local_function(mins):
            """To ensure plugin lambda function is expressed fairly in repr."""
            return lambda mins: mins
        set_lightning_thresholds = local_function
        plugin = Plugin()
        plugin.lrt_lev1 = set_lightning_thresholds
        result = str(plugin)
        msg = ("""<NowcastLightning: radius={radius},
 lightning mapping (lightning rate in "min^-1"):
   upper: lightning rate {lthru} => min lightning prob {lprobu}
   lower: lightning rate {lthrl} => min lightning prob {lprobl}
>""".format(radius=10000.,
            lthru=set_lightning_thresholds, lthrl=0.,
            lprobu=1., lprobl=0.25,
            precu=0.1, precm=0.05, precl=0.0,
            lprecu=1., lprecm=0.2, lprecl=0.0067,
            pphvy=0.4, ppint=0.2,
            viiu=2.0, viim=1.0,
            viil=0.5,
            lviiu=0.9, lviim=0.5,
            lviil=0.1)
              )
        self.assertEqual(result, msg)


class Test__update_metadata(IrisTest):

    """Test the _update_metadata method."""

    def setUp(self):
        """Create a cube with a single non-zero point like this:
     precipitation_amount / (kg m^-2)
     Dimension coordinates:
        realization: 1;
        time: 1;
        projection_y_coordinate: 16;
        projection_x_coordinate: 16;
     Auxiliary coordinates:
          forecast_period (on time coord): 4.0 hours
     Scalar coordinates:
          forecast_reference_time: 2015-11-23 03:00:00
          threshold: 0.5 mm hr-1
     Data:
          All points contain float(1.) except the
          zero point [0, 0, 7, 7] which is float(0.)
"""
        self.cube = add_forecast_reference_time_and_forecast_period(
            set_up_cube())
        coord = DimCoord(0.5, long_name="threshold", units='mm hr^-1')
        self.cube.add_aux_coord(coord)

    def test_basic(self):
        """Test that the method returns the expected cube type
        and that the metadata are as expected.
        We expect a new name and the threshold coord to be removed."""
        plugin = Plugin()
        result = plugin._update_metadata(self.cube)
        self.assertIsInstance(result, Cube)
        self.assertEqual(result.name(), "lightning_probability")
        msg = ("Expected to find exactly 1 threshold coordinate, but found "
               "none.")
        with self.assertRaisesRegex(CoordinateNotFoundError, msg):
            result.coord('threshold')

    def test_input(self):
        """Test that the method does not modify the input cube data."""
        plugin = Plugin()
        incube = self.cube.copy()
        plugin._update_metadata(incube)
        self.assertArrayAlmostEqual(incube.data, self.cube.data)
        self.assertEqual(incube.metadata, self.cube.metadata)

    def test_missing_threshold_coord(self):
        """Test that the method raises an error in Iris if the cube doesn't
        have a threshold coordinate to remove."""
        self.cube.remove_coord('threshold')
        plugin = Plugin()
        msg = ("Expected to find exactly 1 threshold coordinate, but found no")
        with self.assertRaisesRegex(CoordinateNotFoundError, msg):
            plugin._update_metadata(self.cube)


class Test__modify_first_guess(IrisTest):

    """Test the _modify_first_guess method."""

    def setUp(self):
        """Create cubes with a single zero prob(precip) point.
        The cubes look like this:
     precipitation_amount / (kg m^-2)
     Dimension coordinates:
        time: 1;
        projection_y_coordinate: 16;
        projection_x_coordinate: 16;
     Auxiliary coordinates:
          forecast_period (on time coord): 4.0 hours (simulates UM data)
     Scalar coordinates:
          forecast_reference_time: 2015-11-23 03:00:00
     Data:
       self.cube:
          forecast_period (on time coord): 0.0 hours (simulates nowcast data)
          All points contain float(1.) except the
          zero point [0, 0, 7, 7] which is float(0.)
       self.fg_cube:
          All points contain float(1.)
       self.ltng_cube:
          forecast_period (on time coord): 0.0 hours (simulates nowcast data)
          All points contain float(1.)
       self.precip_cube:
          With extra coordinate of length(3) "threshold" containing
          points [0.5, 7., 35.] mm hr-1.
          All points contain float(1.) except the
          zero point [0, 0, 7, 7] which is float(0.)
          and [1:, 0, ...] which are float(0.)
       self.vii_cube:
          With extra coordinate of length(3) "threshold" containing
          points [0.5, 1., 2.] kg m^-2.
          forecast_period (on time coord): 0.0 hours (simulates nowcast data)
          Time and forecast_period dimensions "sqeezed" to be Scalar coords.
          All points contain float(0.)
"""
        self.cube = add_forecast_reference_time_and_forecast_period(
            set_up_cube_with_no_realizations(), fp_point=0.0)
        self.fg_cube = add_forecast_reference_time_and_forecast_period(
            set_up_cube_with_no_realizations(zero_point_indices=[]))
        self.ltng_cube = add_forecast_reference_time_and_forecast_period(
            set_up_cube_with_no_realizations(zero_point_indices=[]),
            fp_point=0.0)
        self.precip_cube = (
            add_forecast_reference_time_and_forecast_period(
                set_up_cube(num_realization_points=3), fp_point=0.0))
        threshold_coord = self.precip_cube.coord('realization')
        threshold_coord.points = [0.5, 7.0, 35.0]
        threshold_coord.rename('threshold')
        threshold_coord.units = cf_units.Unit('mm hr-1')
        self.precip_cube.data[1:, 0, ...] = 0.
        # iris.util.queeze is applied here to demote the singular coord "time"
        # to a scalar coord.
        self.vii_cube = squeeze(
            add_forecast_reference_time_and_forecast_period(
                set_up_cube(num_realization_points=3,
                            zero_point_indices=[]),
                fp_point=0.0))
        threshold_coord = self.vii_cube.coord('realization')
        threshold_coord.points = [0.5, 1.0, 2.0]
        threshold_coord.rename('threshold')
        threshold_coord.units = cf_units.Unit('kg m^-2')
        self.vii_cube.data = np.zeros_like(self.vii_cube.data)

    def test_basic(self):
        """Test that the method returns the expected cube type"""
        plugin = Plugin()
        result = plugin._modify_first_guess(self.cube,
                                            self.fg_cube,
                                            self.ltng_cube,
                                            self.precip_cube,
                                            None)
        self.assertIsInstance(result, Cube)

    def test_basic_with_vii(self):
        """Test that the method returns the expected cube type"""
        plugin = Plugin()
        result = plugin._modify_first_guess(self.cube,
                                            self.fg_cube,
                                            self.ltng_cube,
                                            self.precip_cube,
                                            self.vii_cube)
        self.assertIsInstance(result, Cube)

    def test_input(self):
        """Test that the method does not modify the input cubes."""
        plugin = Plugin()
        cube_a = self.cube.copy()
        cube_b = self.fg_cube.copy()
        cube_c = self.ltng_cube.copy()
        cube_d = self.precip_cube.copy()
        plugin._modify_first_guess(cube_a, cube_b, cube_c, cube_d, None)
        self.assertArrayAlmostEqual(cube_a.data, self.cube.data)
        self.assertArrayAlmostEqual(cube_b.data, self.fg_cube.data)
        self.assertArrayAlmostEqual(cube_c.data, self.ltng_cube.data)
        self.assertArrayAlmostEqual(cube_d.data, self.precip_cube.data)

    def test_input_with_vii(self):
        """Test that the method does not modify the input cubes."""
        plugin = Plugin()
        cube_a = self.cube.copy()
        cube_b = self.fg_cube.copy()
        cube_c = self.ltng_cube.copy()
        cube_d = self.precip_cube.copy()
        cube_e = self.vii_cube.copy()
        plugin._modify_first_guess(cube_a, cube_b, cube_c, cube_d, cube_e)
        self.assertArrayAlmostEqual(cube_a.data, self.cube.data)
        self.assertArrayAlmostEqual(cube_b.data, self.fg_cube.data)
        self.assertArrayAlmostEqual(cube_c.data, self.ltng_cube.data)
        self.assertArrayAlmostEqual(cube_d.data, self.precip_cube.data)
        self.assertArrayAlmostEqual(cube_e.data, self.vii_cube.data)

    def test_missing_lightning(self):
        """Test that the method raises an error if the lightning cube doesn't
        match the meta-data cube time coordinate."""
        self.ltng_cube.coord('time').points = [1.0]
        plugin = Plugin()
        msg = ("No matching lightning cube for")
        with self.assertRaisesRegex(ConstraintMismatchError, msg):
            plugin._modify_first_guess(self.cube,
                                       self.fg_cube,
                                       self.ltng_cube,
                                       self.precip_cube,
                                       None)

    def test_missing_first_guess(self):
        """Test that the method raises an error if the first-guess cube doesn't
        match the meta-data cube time coordinate."""
        self.fg_cube.coord('time').points = [1.0]
        plugin = Plugin()
        msg = ("No matching first-guess cube for")
        with self.assertRaisesRegex(ConstraintMismatchError, msg):
            plugin._modify_first_guess(self.cube,
                                       self.fg_cube,
                                       self.ltng_cube,
                                       self.precip_cube,
                                       None)

    def test_cube_has_no_time_coord(self):
        """Test that the method raises an error if the meta-data cube has no
        time coordinate."""
        self.cube.remove_coord('time')
        plugin = Plugin()
        msg = ("Expected to find exactly 1 time coordinate, but found none.")
        with self.assertRaisesRegex(CoordinateNotFoundError, msg):
            plugin._modify_first_guess(self.cube,
                                       self.fg_cube,
                                       self.ltng_cube,
                                       self.precip_cube,
                                       None)

    def test_precip_zero(self):
        """Test that apply_precip is being called"""
        # Set lightning data to "no-data" so it has a Null impact
        self.ltng_cube.data = np.full_like(self.ltng_cube.data, -1.)
        # No halo - we're only testing this method.
        plugin = Plugin(0.)
        expected = set_up_cube_with_no_realizations()
        # expected.data contains all ones except:
        expected.data[0, 7, 7] = 0.0067
        result = plugin._modify_first_guess(self.cube,
                                            self.fg_cube,
                                            self.ltng_cube,
                                            self.precip_cube,
                                            None)
        self.assertArrayAlmostEqual(result.data, expected.data)

    def test_vii_large(self):
        """Test that ApplyIce is being called"""
        # Set lightning data to zero so it has a Null impact
        self.vii_cube.data[:, 7, 7] = 1.
        self.ltng_cube.data[0, 7, 7] = -1.
        self.fg_cube.data[0, 7, 7] = 0.
        # No halo - we're only testing this method.
        plugin = Plugin(0.)
        expected = set_up_cube_with_no_realizations()
        # expected.data contains all ones except:
        expected.data[0, 7, 7] = 0.9
        result = plugin._modify_first_guess(self.cube,
                                            self.fg_cube,
                                            self.ltng_cube,
                                            self.precip_cube,
                                            self.vii_cube)
        self.assertArrayAlmostEqual(result.data, expected.data)

    def test_null(self):
        """Test that large precip probs and -1 lrates have no impact"""
        # Set prob(precip) data for lowest threshold to to 0.1, the highest
        # value that has no impact.
        self.precip_cube.data[0, 0, 7, 7] = 0.1
        # Set lightning data to -1 so it has a Null impact
        self.ltng_cube.data = np.full_like(self.ltng_cube.data, -1.)
        # No halo - we're only testing this method.
        plugin = Plugin(0.)
        expected = self.fg_cube.copy()
        # expected.data should be an unchanged copy of fg_cube.
        result = plugin._modify_first_guess(self.cube,
                                            self.fg_cube,
                                            self.ltng_cube,
                                            self.precip_cube,
                                            None)
        self.assertArrayAlmostEqual(result.data, expected.data)

    def test_lrate_large(self):
        """Test that large lightning rates increase lightning risk"""
        # Set precip data to 1. so it has a Null impact
        # Set prob(precip) data for lowest threshold to to 1., so it has a Null
        # impact when lightning is present.
        self.precip_cube.data[0, 0, 7, 7] = 1.
        # Set first-guess data zero point that will be increased
        self.fg_cube.data[0, 7, 7] = 0.
        # No halo - we're only testing this method.
        plugin = Plugin(0.)
        expected = set_up_cube_with_no_realizations(zero_point_indices=[])
        # expected.data contains all ones.
        result = plugin._modify_first_guess(self.cube,
                                            self.fg_cube,
                                            self.ltng_cube,
                                            self.precip_cube,
                                            None)
        self.assertArrayAlmostEqual(result.data, expected.data)

    def test_lrate_halo(self):
        """Test that zero lightning rates increase lightning risk"""
        # Set prob(precip) data for lowest threshold to to 1., so it has a Null
        # impact when lightning is present.
        self.precip_cube.data[0, 0, 7, 7] = 1.
        # Set lightning data to zero to represent the data halo
        self.ltng_cube.data[0, 7, 7] = 0.
        # Set first-guess data zero point that will be increased
        self.fg_cube.data[0, 7, 7] = 0.
        # No halo - we're only testing this method.
        plugin = Plugin(0.)
        expected = set_up_cube_with_no_realizations()
        # expected.data contains all ones except:
        expected.data[0, 7, 7] = 0.25
        result = plugin._modify_first_guess(self.cube,
                                            self.fg_cube,
                                            self.ltng_cube,
                                            self.precip_cube,
                                            None)
        self.assertArrayAlmostEqual(result.data, expected.data)


class Test_apply_precip(IrisTest):

    """Test the apply_precip method."""

    def setUp(self):
        """Create cubes with a single zero prob(precip) point.
        The cubes look like this:
     precipitation_amount / (kg m^-2)
     Dimension coordinates:
        time: 1;
        projection_y_coordinate: 16;
        projection_x_coordinate: 16;
     Auxiliary coordinates:
          forecast_period (on time coord): 4.0 hours (simulates UM data)
     Scalar coordinates:
          forecast_reference_time: 2015-11-23 03:00:00
     Data:
       self.fg_cube:
          forecast_period (on time coord): 0.0 hours (simulates nowcast data)
          All points contain float(1.)
          Cube name is "probability_of_lightning".
       self.precip_cube:
          With extra coordinate of length(3) "threshold" containing
          points [0.5, 7., 35.] mm hr-1.
          All points contain float(1.) except the
          zero point [0, 0, 7, 7] which is float(0.)
          and [1:, 0, ...] which are float(0.)
          Cube name is "probability_of_precipitation".
          Cube has added attribute {'relative_to_threshold': 'above'}
"""
        self.fg_cube = add_forecast_reference_time_and_forecast_period(
            set_up_cube_with_no_realizations(zero_point_indices=[]),
            fp_point=0.0)
        self.fg_cube.rename("probability_of_lightning")
        self.precip_cube = (
            add_forecast_reference_time_and_forecast_period(
                set_up_cube(num_realization_points=3)))
        threshold_coord = self.precip_cube.coord('realization')
        threshold_coord.points = [0.5, 7.0, 35.0]
        threshold_coord.rename('threshold')
        threshold_coord.units = cf_units.Unit('mm hr-1')
        self.precip_cube.rename("probability_of_precipitation")
        self.precip_cube.attributes.update({'relative_to_threshold': 'above'})
        self.precip_cube.data[1:, 0, ...] = 0.

    def test_basic(self):
        """Test that the method returns the expected cube type"""
        plugin = Plugin()
        result = plugin.apply_precip(self.fg_cube, self.precip_cube)
        self.assertIsInstance(result, Cube)

    def test_input(self):
        """Test that the method does not modify the input cubes."""
        plugin = Plugin()
        cube_a = self.fg_cube.copy()
        cube_b = self.precip_cube.copy()
        plugin.apply_precip(cube_a, cube_b)
        self.assertArrayAlmostEqual(cube_a.data, self.fg_cube.data)
        self.assertArrayAlmostEqual(cube_b.data, self.precip_cube.data)

    def test_missing_threshold_low(self):
        """Test that the method raises an error if the precip_cube doesn't
        have a threshold coordinate for 0.5."""
        self.precip_cube.coord('threshold').points = [1.0, 7., 35.]
        plugin = Plugin()
        msg = ("No matching any precip cube for")
        with self.assertRaisesRegex(ConstraintMismatchError, msg):
            plugin.apply_precip(self.fg_cube, self.precip_cube)

    def test_missing_threshold_mid(self):
        """Test that the method raises an error if the precip_cube doesn't
        have a threshold coordinate for 7.0."""
        self.precip_cube.coord('threshold').points = [0.5, 8., 35.]
        plugin = Plugin()
        msg = ("No matching high precip cube for")
        with self.assertRaisesRegex(ConstraintMismatchError, msg):
            plugin.apply_precip(self.fg_cube, self.precip_cube)

    def test_missing_threshold_high(self):
        """Test that the method raises an error if the precip_cube doesn't
        have a threshold coordinate for 35.0."""
        self.precip_cube.coord('threshold').points = [0.5, 7., 20.]
        plugin = Plugin()
        msg = ("No matching intense precip cube for")
        with self.assertRaisesRegex(ConstraintMismatchError, msg):
            plugin.apply_precip(self.fg_cube, self.precip_cube)

    def test_precip_zero(self):
        """Test that zero precip probs reduce lightning risk"""
        plugin = Plugin()
        expected = set_up_cube_with_no_realizations()
        # expected.data contains all ones except:
        expected.data[0, 7, 7] = 0.0067
        result = plugin.apply_precip(self.fg_cube, self.precip_cube)
        self.assertArrayAlmostEqual(result.data, expected.data)

    def test_precip_small(self):
        """Test that small precip probs reduce lightning risk"""
        self.precip_cube.data[:, 0, 7, 7] = 0.
        self.precip_cube.data[0, 0, 7, 7] = 0.075
        plugin = Plugin()
        expected = set_up_cube_with_no_realizations()
        # expected.data contains all ones except:
        expected.data[0, 7, 7] = 0.625
        result = plugin.apply_precip(self.fg_cube, self.precip_cube)
        self.assertArrayAlmostEqual(result.data, expected.data)

    def test_precip_heavy(self):
        """Test that prob of heavy precip increases lightning risk"""
        self.precip_cube.data[0, 0, 7, 7] = 1.0
        self.precip_cube.data[1, 0, 7, 7] = 0.5
        # Set first-guess to zero
        self.fg_cube.data[0, 7, 7] = 0.0
        plugin = Plugin()
        expected = set_up_cube_with_no_realizations()
        # expected.data contains all ones except:
        expected.data[0, 7, 7] = 0.25
        result = plugin.apply_precip(self.fg_cube, self.precip_cube)
        self.assertArrayAlmostEqual(result.data, expected.data)

    def test_precip_heavy_null(self):
        """Test that low prob of heavy precip does not increase
        lightning risk"""
        self.precip_cube.data[0, 0, 7, 7] = 1.0
        self.precip_cube.data[1, 0, 7, 7] = 0.3
        # Set first-guess to zero
        self.fg_cube.data[0, 7, 7] = 0.1
        plugin = Plugin()
        expected = set_up_cube_with_no_realizations()
        # expected.data contains all ones except:
        expected.data[0, 7, 7] = 0.1
        result = plugin.apply_precip(self.fg_cube, self.precip_cube)
        self.assertArrayAlmostEqual(result.data, expected.data)

    def test_precip_intense(self):
        """Test that prob of intense precip increases lightning risk"""
        self.precip_cube.data[0, 0, 7, 7] = 1.0
        self.precip_cube.data[1, 0, 7, 7] = 1.0
        self.precip_cube.data[2, 0, 7, 7] = 0.5
        # Set first-guess to zero
        self.fg_cube.data[0, 7, 7] = 0.0
        plugin = Plugin()
        expected = set_up_cube_with_no_realizations()
        # expected.data contains all ones except:
        expected.data[0, 7, 7] = 1.0
        result = plugin.apply_precip(self.fg_cube, self.precip_cube)
        self.assertArrayAlmostEqual(result.data, expected.data)

    def test_precip_intense_null(self):
        """Test that low prob of intense precip does not increase
        lightning risk"""
        self.precip_cube.data[0, 0, 7, 7] = 1.0
        self.precip_cube.data[1, 0, 7, 7] = 1.0
        self.precip_cube.data[2, 0, 7, 7] = 0.1
        # Set first-guess to zero
        self.fg_cube.data[0, 7, 7] = 0.1
        plugin = Plugin()
        expected = set_up_cube_with_no_realizations()
        # expected.data contains all ones except:
        expected.data[0, 7, 7] = 0.25  # Heavy-precip result only
        result = plugin.apply_precip(self.fg_cube, self.precip_cube)
        self.assertArrayAlmostEqual(result.data, expected.data)


class Test_apply_ice(IrisTest):

    """Test the apply_ice method."""

    def setUp(self):
        """Create cubes with a single zero prob(precip) point.
        The cubes look like this:
     precipitation_amount / (kg m^-2)
     Dimension coordinates:
        time: 1;
        projection_y_coordinate: 16;
        projection_x_coordinate: 16;
     Auxiliary coordinates:
          forecast_period (on time coord): 0.0 hours (simulates nowcast data)
     Scalar coordinates:
          forecast_reference_time: 2015-11-23 03:00:00
     Data:
       self.fg_cube:
          All points contain float(1.)
          Cube name is "probability_of_lightning".
       self.ice_cube:
          With extra coordinate of length(3) "threshold" containing
          points [0.5, 1., 2.] kg m^-2.
          Time and forecast_period dimensions "sqeezed" to be Scalar coords.
          All points contain float(0.)
          Cube name is "probability_of_vertical_integral_of_ice".
"""
        self.fg_cube = add_forecast_reference_time_and_forecast_period(
            set_up_cube_with_no_realizations(zero_point_indices=[]),
            fp_point=0.0)
        self.fg_cube.rename("probability_of_lightning")
        self.ice_cube = squeeze(
            add_forecast_reference_time_and_forecast_period(
                set_up_cube(num_realization_points=3,
                            zero_point_indices=[]),
                fp_point=0.0))
        threshold_coord = self.ice_cube.coord('realization')
        threshold_coord.points = [0.5, 1.0, 2.0]
        threshold_coord.rename('threshold')
        threshold_coord.units = cf_units.Unit('kg m^-2')
        self.ice_cube.data = np.zeros_like(self.ice_cube.data)
        self.ice_cube.rename("probability_of_vertical_integral_of_ice")

    def test_basic(self):
        """Test that the method returns the expected cube type"""
        plugin = Plugin()
        result = plugin.apply_ice(self.fg_cube, self.ice_cube)
        self.assertIsInstance(result, Cube)

    def test_input(self):
        """Test that the method does not modify the input cubes."""
        plugin = Plugin()
        cube_a = self.fg_cube.copy()
        cube_b = self.ice_cube.copy()
        plugin.apply_ice(cube_a, cube_b)
        self.assertArrayAlmostEqual(cube_a.data, self.fg_cube.data)
        self.assertArrayAlmostEqual(cube_b.data, self.ice_cube.data)

    def test_missing_threshold_low(self):
        """Test that the method raises an error if the ice_cube doesn't
        have a threshold coordinate for 0.5."""
        self.ice_cube.coord('threshold').points = [0.4, 1., 2.]
        plugin = Plugin()
        msg = ("No matching prob\(Ice\) cube for threshold 0.5")
        with self.assertRaisesRegex(ConstraintMismatchError, msg):
            plugin.apply_ice(self.fg_cube, self.ice_cube)

    def test_missing_threshold_mid(self):
        """Test that the method raises an error if the ice_cube doesn't
        have a threshold coordinate for 1.0."""
        self.ice_cube.coord('threshold').points = [0.5, 0.9, 2.]
        plugin = Plugin()
        msg = ("No matching prob\(Ice\) cube for threshold 1.")
        with self.assertRaisesRegex(ConstraintMismatchError, msg):
            plugin.apply_ice(self.fg_cube, self.ice_cube)

    def test_missing_threshold_high(self):
        """Test that the method raises an error if the ice_cube doesn't
        have a threshold coordinate for 2.0."""
        self.ice_cube.coord('threshold').points = [0.5, 1., 4.]
        plugin = Plugin()
        msg = ("No matching prob\(Ice\) cube for threshold 2.")
        with self.assertRaisesRegex(ConstraintMismatchError, msg):
            plugin.apply_ice(self.fg_cube, self.ice_cube)

    def test_ice_null(self):
        """Test that small VII probs do not increase lightning risk"""
        self.ice_cube.data[:, 7, 7] = 0.
        self.ice_cube.data[0, 7, 7:9] = 0.5
        self.fg_cube.data[0, 7, 7] = 0.25
        plugin = Plugin()
        expected = set_up_cube_with_no_realizations()
        # expected.data contains all ones except:
        expected.data[0, 7, 7] = 0.25
        result = plugin.apply_ice(self.fg_cube,
                                  self.ice_cube)
        self.assertArrayAlmostEqual(result.data, expected.data)

    def test_ice_zero(self):
        """Test that zero VII probs do not increase lightning risk"""
        self.ice_cube.data[:, 7, 7] = 0.
        self.fg_cube.data[0, 7, 7] = 0.
        plugin = Plugin()
        expected = set_up_cube_with_no_realizations()
        # expected.data contains all ones except:
        expected.data[0, 7, 7] = 0.
        result = plugin.apply_ice(self.fg_cube,
                                  self.ice_cube)
        self.assertArrayAlmostEqual(result.data, expected.data)

    def test_ice_small(self):
        """Test that small VII probs do increase lightning risk"""
        self.ice_cube.data[:, 7, 7] = 0.
        self.ice_cube.data[0, 7, 7] = 0.5
        self.fg_cube.data[0, 7, 7] = 0.
        plugin = Plugin()
        expected = set_up_cube_with_no_realizations()
        # expected.data contains all ones except:
        expected.data[0, 7, 7] = 0.05
        result = plugin.apply_ice(self.fg_cube,
                                  self.ice_cube)
        self.assertArrayAlmostEqual(result.data, expected.data)

    def test_ice_large(self):
        """Test that large VII probs do increase lightning risk"""
        self.ice_cube.data[:, 7, 7] = 1.
        self.fg_cube.data[0, 7, 7] = 0.
        plugin = Plugin()
        expected = set_up_cube_with_no_realizations()
        # expected.data contains all ones except:
        expected.data[0, 7, 7] = 0.9
        result = plugin.apply_ice(self.fg_cube,
                                  self.ice_cube)
        self.assertArrayAlmostEqual(result.data, expected.data)

    def test_ice_large_long_fc(self):
        """Test that large VII probs do not increase lightning risk when
        forecast lead time is large"""
        self.ice_cube.data[:, 7, 7] = 1.
        self.fg_cube.data[0, 7, 7] = 0.
        self.fg_cube.coord('forecast_period').points = [3.]
        plugin = Plugin()
        expected = set_up_cube_with_no_realizations()
        # expected.data contains all ones except:
        expected.data[0, 7, 7] = 0.0
        result = plugin.apply_ice(self.fg_cube,
                                  self.ice_cube)
        self.assertArrayAlmostEqual(result.data, expected.data)


class Test_process(IrisTest):

    """Test the nowcast lightning plugin."""

    def setUp(self):
        """Create cubes with a single zero prob(precip) point.
        The cubes look like this:
     precipitation_amount / (kg m^-2)
     Dimension coordinates:
        time: 1;
        projection_y_coordinate: 16;
        projection_x_coordinate: 16;
     Auxiliary coordinates:
          forecast_period (on time coord): 4.0 hours (simulates UM data)
     Scalar coordinates:
          forecast_reference_time: 2015-11-23 03:00:00
     Data:
       self.fg_cube:
          All points contain float(1.)
          Cube name is "probability_of_lightning".
       self.ltng_cube:
          forecast_period (on time coord): 0.0 hours (simulates nowcast data)
          All points contain float(1.)
          Cube name is "rate_of_lightning".
          Cube units are "min^-1".
       self.precip_cube:
          With extra coordinate of length(3) "threshold" containing
          points [0.5, 7., 35.] mm hr-1.
          All points contain float(1.) except the
          zero point [0, 0, 7, 7] which is float(0.)
          and [1:, 0, ...] which are float(0.)
          Cube name is "probability_of_precipitation".
          Cube has added attribute {'relative_to_threshold': 'above'}
       self.vii_cube:
          forecast_period (on time coord): 0.0 hours (simulates nowcast data)
          With extra coordinate of length(3) "threshold" containing
          points [0.5, 1., 2.] kg m^-2.
          forecast_period (on time coord): 0.0 hours (simulates nowcast data)
          Time and forecast_period dimensions "sqeezed" to be Scalar coords.
          All points contain float(0.)
          Cube name is "probability_of_vertical_integral_of_ice".
"""
        self.fg_cube = add_forecast_reference_time_and_forecast_period(
            set_up_cube_with_no_realizations(zero_point_indices=[]))
        self.fg_cube.rename("probability_of_lightning")
        self.ltng_cube = add_forecast_reference_time_and_forecast_period(
            set_up_cube_with_no_realizations(zero_point_indices=[]),
            fp_point=0.0)
        self.ltng_cube.rename("rate_of_lightning")
        self.ltng_cube.units = cf_units.Unit("min^-1")
        self.precip_cube = (
            add_forecast_reference_time_and_forecast_period(
                set_up_cube(num_realization_points=3)))
        threshold_coord = self.precip_cube.coord('realization')
        threshold_coord.points = [0.5, 7.0, 35.0]
        threshold_coord.rename('threshold')
        threshold_coord.units = cf_units.Unit('mm hr-1')
        self.precip_cube.rename("probability_of_precipitation")
        self.precip_cube.attributes.update({'relative_to_threshold': 'above'})
        self.precip_cube.data[1:, 0, ...] = 0.
        self.vii_cube = squeeze(
            add_forecast_reference_time_and_forecast_period(
                set_up_cube(num_realization_points=3,
                            zero_point_indices=[]),
                fp_point=0.0))
        threshold_coord = self.vii_cube.coord('realization')
        threshold_coord.points = [0.5, 1.0, 2.0]
        threshold_coord.rename('threshold')
        threshold_coord.units = cf_units.Unit('kg m^-2')
        self.vii_cube.data = np.zeros_like(self.vii_cube.data)
        self.vii_cube.rename("probability_of_vertical_integral_of_ice")

    def set_up_vii_input_output(self):
        """Used to modify setUp() to set up four standard VII tests."""

        # Repeat all tests relating to vii from Test__modify_first_guess
        expected = set_up_cube_with_no_realizations()
        # expected.data contains all ones except where modified below:

        # Set up precip_cube with increasing intensity along x-axis
        # y=5; no precip
        self.precip_cube.data[:, 0, 5:9, 5] = 0.
        # y=6; light precip
        self.precip_cube.data[0, 0, 5:9, 6] = 0.1
        self.precip_cube.data[1, 0:, 5:9, 6] = 0.
        # y=7; heavy precip
        self.precip_cube.data[:2, 0, 5:9, 7] = 1.
        self.precip_cube.data[2, 0, 5:9, 7] = 0.
        # y=8; intense precip
        self.precip_cube.data[:, 0, 5:9, 8] = 1.

        # test_vii_null - with lightning-halo
        self.vii_cube.data[:, 5, 5:9] = 0.
        self.vii_cube.data[0, 5, 5:9] = 0.5
        self.ltng_cube.data[0, 5, 5:9] = 0.
        self.fg_cube.data[0, 5, 5:9] = 0.
        expected.data[0, 5, 5:9] = [0.05, 0.25, 0.25, 1.]

        # test_vii_zero
        self.vii_cube.data[:, 6, 5:9] = 0.
        self.ltng_cube.data[0, 6, 5:9] = -1.
        self.fg_cube.data[0, 6, 5:9] = 0.
        expected.data[0, 6, 5:9] = [0., 0., 0.25, 1.]

        # test_vii_small
        # Set lightning data to -1 so it has a Null impact
        self.vii_cube.data[:, 7, 5:9] = 0.
        self.vii_cube.data[0, 7, 5:9] = 0.5
        self.ltng_cube.data[0, 7, 5:9] = -1.
        self.fg_cube.data[0, 7, 5:9] = 0.
        expected.data[0, 7, 5:9] = [0.05, 0.05, 0.25, 1.]

        # test_vii_large
        # Set lightning data to -1 so it has a Null impact
        self.vii_cube.data[:, 8, 5:9] = 1.
        self.ltng_cube.data[0, 8, 5:9] = -1.
        self.fg_cube.data[0, 8, 5:9] = 0.
        expected.data[0, 8, 5:9] = [0.9, 0.9, 0.9, 1.]
        return expected

    def test_basic(self):
        """Test that the method returns the expected cube type"""
        plugin = Plugin()
        result = plugin.process(CubeList([
            self.fg_cube,
            self.ltng_cube,
            self.precip_cube]))
        self.assertIsInstance(result, Cube)

    def test_basic_with_vii(self):
        """Test that the method returns the expected cube type when vii is
        present"""
        plugin = Plugin()
        result = plugin.process(CubeList([
            self.fg_cube,
            self.ltng_cube,
            self.precip_cube,
            self.vii_cube]))
        self.assertIsInstance(result, Cube)

    def test_no_first_guess_cube(self):
        """Test that the method raises an error if the first_guess cube is
        omitted from the cubelist"""
        plugin = Plugin()
        msg = ("Got 0 cubes for constraint Constraint\(name=\'probability_of_"
               "lightning\'\), expecting 1.")
        with self.assertRaisesRegex(ConstraintMismatchError, msg):
            plugin.process(CubeList([
                self.ltng_cube,
                self.precip_cube]))

    def test_no_lightning_cube(self):
        """Test that the method raises an error if the lightning cube is
        omitted from the cubelist"""
        plugin = Plugin()
        msg = ("Got 0 cubes for constraint Constraint\(name=\'rate_of_"
               "lightning\'\), expecting 1.")
        with self.assertRaisesRegex(ConstraintMismatchError, msg):
            plugin.process(CubeList([
                self.fg_cube,
                self.precip_cube]))

    def test_no_precip_cube(self):
        """Test that the method raises an error if the precip cube is
        omitted from the cubelist"""
        plugin = Plugin()
        msg = ("Got 0 cubes for constraint Constraint\(name=\'probability_of_"
               "precipitation\'\), expecting 1.")
        with self.assertRaisesRegex(ConstraintMismatchError, msg):
            plugin.process(CubeList([
                self.fg_cube,
                self.ltng_cube]))

    def test_precip_has_no_thresholds(self):
        """Test that the method raises an error if the threshold coord is
        omitted from the precip_cube"""
        self.precip_cube.remove_coord('threshold')
        plugin = Plugin()
        msg = ("Cannot find prob\(precip > 0.5\) cube in cubelist.")
        with self.assertRaisesRegex(ConstraintMismatchError, msg):
            plugin.process(CubeList([
                self.fg_cube,
                self.ltng_cube,
                self.precip_cube]))

    def test_result_with_vii(self):
        """Test that the method returns the expected data when vii is
        present"""
        # Set precip_cube forecast period to be zero.
        self.precip_cube.coord('forecast_period').points = [0.]
        expected = self.set_up_vii_input_output()

        # No halo - we're only testing this method.
        plugin = Plugin(2000.)
        result = plugin.process(CubeList([
            self.fg_cube,
            self.ltng_cube,
            self.precip_cube,
            self.vii_cube]))
        self.assertIsInstance(result, Cube)
        self.assertArrayAlmostEqual(result.data, expected.data)

    def test_result_with_vii_longfc(self):
        """Test that the method returns the expected data when vii is
        present and forecast time is 4 hours"""
        expected = self.set_up_vii_input_output()

        # test_vii_null with no precip will now return 0.0067
        expected.data[0, 5, 5] = 0.0067

        # test_vii_small with no and light precip will now return zero
        expected.data[0, 7, 5:7] = 0.

        # test_vii_large with no and light precip now return zero
        # and 0.25 for heavy precip
        expected.data[0, 8, 5:8] = [0., 0., 0.25]
        # No halo - we're only testing this method.
        plugin = Plugin(2000.)
        result = plugin.process(CubeList([
            self.fg_cube,
            self.ltng_cube,
            self.precip_cube,
            self.vii_cube]))
        self.assertIsInstance(result, Cube)
        self.assertArrayAlmostEqual(result.data, expected.data)


if __name__ == '__main__':
    unittest.main()