# vim: set et sw=4 sts=4 fileencoding=utf-8:
#
# The colorzero color library
# Copyright (c) 2016-2018 Dave Jones <dave@waveform.org.uk>
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#     * Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#     * Neither the name of the copyright holder nor the
#       names of its contributors may be used to endorse or promote products
#       derived from this software without specific prior written permission.
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

"""
The colorzero package defines a number of classes for representation and
manipulation of colors. The primary class of interest to users is
:class:`Color`.  The other classes are used for manipulation of the attributes
on this class and are:

* :class:`Red`
* :class:`Green`
* :class:`Blue`
* :class:`Hue`
* :class:`Lightness`
* :class:`Saturation`
* :class:`Luma`
"""

from __future__ import (
    unicode_literals,
    print_function,
    division,
    absolute_import,
)

from .color import Color
from .easings import linear, ease_in, ease_out, ease_in_out
from .deltae import euclid, cie1976, cie1994g, cie1994t, ciede2000
from .attr import Red, Green, Blue, Hue, Lightness, Saturation, Luma
from .types import RGB, HLS, HSV, CMY, CMYK, YUV, YIQ, XYZ, Luv, Lab
from .tables import NAMED_COLORS
