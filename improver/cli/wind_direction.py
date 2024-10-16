#!/usr/bin/env python
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# (C) British Crown copyright. The Met Office.
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
"""Script to calculate mean wind direction from ensemble realizations."""

from improver import cli


@cli.clizefy
@cli.with_output
def process(wind_direction: cli.inputcube, *, backup_method="neighbourhood"):
    """Calculates mean wind direction from ensemble realization.

    Create a cube containing the wind direction averaged over the ensemble
    realizations.

    Args:
        wind_direction (iris.cube.Cube):
            Cube containing the wind direction from multiple ensemble
            realizations.
        backup_method (str):
            Backup method to use if the complex numbers approach has low
            confidence.
            "neighbourhood" (default) recalculates using the complex numbers
            approach with additional realization extracted from neighbouring
            grid points from all available realizations.
            "first_realization" uses the value of realization zero, and should
            only be used with global lat-lon data.

    Returns:
        iris.cube.Cube:
            Cube containing the wind direction averaged from the ensemble
            realizations.
    """
    from improver.wind_calculations.wind_direction import WindDirection

    result = WindDirection(backup_method=backup_method)(wind_direction)[0]
    return result
