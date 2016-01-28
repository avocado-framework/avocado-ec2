# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#

# pylint: disable=E0611
from setuptools import setup

VERSION = '0.32.0'

setup(name='avocado-plugins-ec2',
      version=VERSION,
      description='Avocado EC2 Plugin',
      author='Avocado Developers',
      author_email='avocado-devel@redhat.com',
      url='http://github.com/avocado-framework/avocado-vt',
      packages=['avocado_ec2',
                'avocado_ec2.plugins'],
      entry_points={
          'avocado.plugins.cli': [
              'ec2 = avocado_ec2.plugins.ec2:EC2Run',
              ],
          },
      )
