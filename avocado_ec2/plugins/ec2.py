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

"""
Run tests on an EC2 (Amazon Elastic Cloud) instance.
"""

import os
import sys
import logging

from avocado.core import exit_codes
from avocado.core import remoter
from avocado.core.remote import RemoteTestResult
from avocado.core.remote import RemoteTestRunner
from avocado.plugins.base import CLI
from avocado.core.result import register_test_result_class

from ..ec2_wrapper import EC2InstanceWrapper

VALID_DISTROS_MSG = ['fedora (for Fedora > 22)',
                     'el (for RHEL/CentOS > 6.0)',
                     'ubuntu (for Ubuntu > 14.04)']

VALID_DISTROS = [distro.split()[0] for distro in VALID_DISTROS_MSG]


class EC2TestResult(RemoteTestResult):

    """
    Amazon EC2 Test Result class.
    """

    command_line_arg_name = '--ec2-ami-id'

    def __init__(self, job):
        """
        Creates an instance of RemoteTestResult.

        :param job: an instance of :class:`avocado.core.job.Job`.
        """
        RemoteTestResult.__init__(self, job)
        self.test_dir = os.getcwd()
        self.remote_test_dir = '~/avocado/tests'
        self.urls = self.args.url
        self.remote = None      # Remote runner initialized during setup
        self.output = '-'

    def tear_down(self):
        """ Cleanup after test execution """
        pass


class EC2TestRunner(RemoteTestRunner):

    """
    Run tests on an EC2 (Amazon Elastic Cloud) instance
    """

    name = 'ec2'
    description = "Amazon Elastic Cloud instance support to 'run' command"
    ec2_parser = None
    configured = False
    instance = None

    def _install_avocado(self, distro_type):
        """
        Install avocado on the EC2 instance.

        We won't usually have avocado installed on the AMI, so let's install
        it ourselves. This is a naive implementation that should work OK on
        freshly booted instances.

        :param distro_type: Distro type
        """
        retrieve_cmd = None
        install_cmd = None
        if distro_type not in VALID_DISTROS:
            e_msg = ('Invalid --ec2-ami-distro-type. Valid values: %s' %
                     VALID_DISTROS)
            log = logging.getLogger("avocado.app")
            log.error(e_msg)
            raise ValueError(e_msg)
        if distro_type == 'fedora':
            remote_repo = ('https://repos-avocadoproject.rhcloud.com/static/'
                           'avocado-fedora.repo')
            local_repo = '/etc/yum.repos.d/avocado.repo'
            retrieve_cmd = 'sudo curl %s -o %s' % (remote_repo, local_repo)
            install_cmd = 'sudo dnf install -y avocado'
        elif distro_type == 'el':
            remote_repo = ('https://repos-avocadoproject.rhcloud.com/static/'
                           'avocado-el.repo')
            local_repo = '/etc/yum.repos.d/avocado.repo'
            retrieve_cmd = 'sudo curl %s -o %s' % (remote_repo, local_repo)
            install_cmd = 'sudo yum install -y avocado'
        elif distro_type == 'ubuntu':
            remote_repo = ('deb http://ppa.launchpad.net/lmr/avocado/ubuntu '
                           'wily main')
            local_repo = '/etc/apt/sources.list.d/avocado.list'
            retrieve_cmd = ('sudo echo "%s" > %s' % (remote_repo, local_repo))
            install_cmd = ('sudo apt-get install --yes '
                           '--allow-unauthenticated avocado')

        self.remote.run(retrieve_cmd, timeout=300)
        self.remote.run(install_cmd, timeout=300)

    def tear_down(self):
        super(EC2TestRunner, self).tear_down()
        if self.instance is not None:
            self.instance.destroy()

    def setup(self):
        try:
            # Super called after VM is found and initialized
            self.job.log.info("AMI_ID     : %s", self.job.args.ec2_ami_id)
            self.instance = EC2InstanceWrapper(self.job.args)
            # Finish remote setup and copy the tests
            self.job.args.remote_hostname = self.instance.instance.public_ip_address
            self.job.args.remote_key_file = self.instance.key_pair.key_file
            self.job.args.remote_port = self.job.args.ec2_instance_ssh_port
            self.job.args.remote_username = self.job.args.ec2_ami_username
            self.job.args.remote_timeout = self.job.args.ec2_login_timeout
            self.job.args.remote_password = None
            self.job.args.remote_no_copy = False
            super(EC2TestRunner, self).setup()
            self._install_avocado(distro_type=self.job.args.ec2_ami_distro_type)
        except Exception:
            self.tear_down()
            raise


class EC2Cli(CLI):

    """
    Run tests on an AWS instance
    """

    name = 'ec2'
    description = "Amazon Elastic Cloud instance support to 'run' command"

    def configure(self, parser):
        if remoter.REMOTE_CAPABLE is False:
            return

        username = 'fedora'

        run_subcommand_parser = parser.subcommands.choices.get('run', None)
        if run_subcommand_parser is None:
            return

        msg = 'test execution on an Amazon Elastic Cloud instance'

        self.ec2_parser = run_subcommand_parser.add_argument_group(msg)
        self.ec2_parser.add_argument('--ec2-ami-id',
                                     dest='ec2_ami_id',
                                     help=('Amazon Machine Image ID. '
                                           'Example: ami-e08adb8a'))
        self.ec2_parser.add_argument('--ec2-ami-username',
                                     dest='ec2_ami_username',
                                     default=username,
                                     help=('User for the AMI image login. '
                                           'Defaults to fedora'))
        self.ec2_parser.add_argument('--ec2-ami-distro-type',
                                     dest='ec2_ami_distro_type',
                                     default='fedora',
                                     help=('AMI base Linux Distribution. '
                                           'Valid values: %s. '
                                           'Defaults to fedora' %
                                           ', '.join(VALID_DISTROS_MSG)))
        self.ec2_parser.add_argument('--ec2-instance-ssh-port',
                                     dest='ec2_instance_ssh_port',
                                     default=22,
                                     help=('sshd port for the EC2 instance. '
                                           'Defaults to 22'))
        self.ec2_parser.add_argument('--ec2-security-group-ids',
                                     dest='ec2_security_group_ids',
                                     help=('Comma separated list of EC2 '
                                           'security group IDs. '
                                           'Example: sg-a5e1d7b0'))
        self.ec2_parser.add_argument('--ec2-subnet-id',
                                     dest='ec2_subnet_id',
                                     help=('EC2 subnet ID. '
                                           'Example: subnet-ec4a72c4'))
        self.ec2_parser.add_argument('--ec2-instance-type',
                                     dest='ec2_instance_type',
                                     help=('EC2 instance type. '
                                           'Example: c4.xlarge'))
        self.ec2_parser.add_argument('--ec2-login-timeout', metavar='SECONDS',
                                     help=("Amount of time (in seconds) to "
                                           "wait for a successful connection"
                                           " to the EC2 instance. Defaults"
                                           " to 120 seconds"),
                                     default=120, type=int)

        self.configured = True

    @staticmethod
    def _check_required_args(args, enable_arg, required_args):
        """
        :return: True when enable_arg enabled and all required args are set
        :raise sys.exit: When missing required argument.
        """
        if (not hasattr(args, enable_arg) or
                not getattr(args, enable_arg)):
            return False
        missing = []
        for arg in required_args:
            if not getattr(args, arg):
                missing.append(arg)
        if missing:
            log = logging.getLogger("avocado.app")
            log.error("Use of %s requires %s arguments to be set. Please set "
                      "%s.", enable_arg, ', '.join(required_args),
                      ', '.join(missing))

            return sys.exit(exit_codes.AVOCADO_FAIL)
        return True

    def run(self, args):
        if self._check_required_args(args, 'ec2_ami_id',
                                     ('ec2_ami_id',
                                      'ec2_security_group_ids',
                                      'ec2_subnet_id',
                                      'ec2_instance_type')):
            register_test_result_class(args, EC2TestResult)
            args.test_runner = EC2TestRunner
