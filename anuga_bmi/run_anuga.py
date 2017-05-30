"""
Runs ANUGA through a BMI
"""

from __future__ import print_function

import sys
import numpy as np

from bmi_anuga import BmiAnuga

if __name__ == '__main__':

    sww = BmiAnuga()
    sww.initialize('anuga.yaml')

    for time in np.linspace(0., 100., 5):
        sww.update_until(time)
