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

import sys

from avocado.core import exit_codes
from avocado.core import output
from avocado.core.remote import RemoteTestResult
from avocado.core.remote import RemoteTestRunner
from avocado.plugins.base import CLI

from ..ec2_wrapper import EC2InstanceWrapper

VALID_DISTROS_MSG = ['fedora (for Fedora > 22)',
                     'el (for RHEL/CentOS > 6.0)',
                     'ubuntu (for Ubuntu > 14.04)']

VALID_DISTROS = [distro.split()[0] for distro in VALID_DISTROS_MSG]


class EC2TestResult(RemoteTestResult):

    """
    Amazon EC2 (Elastic Cloud) Test Result class.
    """

    def __init__(self, stream, args):
        super(EC2TestResult, self).__init__(stream, args)
        self.instance = None
        self.keypair = None
        self.command_line_arg_name = '--ec2-ami-id'

    def setup(self):
        self.stream.notify(event='message', msg="AMI_ID     : %s"
                           % self.args.ec2_ami_id)

        try:
            self.instance = EC2InstanceWrapper(self.args, self.stream)
            # Finish remote setup and copy the tests
            self.args.remote_hostname = self.instance.instance.public_ip_address
            self.args.remote_key_file = self.instance.key_pair.key_file
            self.args.remote_port = self.args.ec2_instance_ssh_port
            self.args.remote_username = self.args.ec2_ami_username
            self.args.remote_timeout = self.args.ec2_login_timeout
            self.args.remote_password = None
            self.args.remote_no_copy = False
            super(EC2TestResult, self).setup()
            self._install_avocado(distro_type=self.args.ec2_ami_distro_type)
        except Exception:
            self.tear_down()
            raise

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
            self.stream.notify(event='error', msg=e_msg)
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
        super(EC2TestResult, self).tear_down()
        if self.instance is not None:
            self.instance.destroy()


class EC2Run(CLI):

    """
    Run tests on an EC2 (Amazon Elastic Cloud) instance
    """

    name = 'ec2'
    description = "Amazon Elastic Cloud instance support to 'run' command"
    ec2_parser = None
    configured = False

    def configure(self, parser):
        run_subcommand_parser = parser.subcommands.choices.get('run', None)
        if run_subcommand_parser is None:
            return

        msg = 'test execution on an EC2 (Amazon Elastic Cloud) instance'
        username = 'fedora'

        self.ec2_parser = run_subcommand_parser.add_argument_group(msg)
        self.ec2_parser.add_argument('--ec2-ami-id',
                                     dest='ec2_ami_id',
                                     help=('Amazon Machine Image ID. '
                                           'Example: ami-e08adb8a'))
        self.ec2_parser.add_argument('--ec2-ami-username',
                                     dest='ec2_ami_username',
                                     default=username,
                                     help=('User for the AMI image login. '
                                           'Defaults to root'))
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

    @staticmethod
    def _check_required_args(app_args, enable_arg, required_args):
        """
        :return: True when enable_arg enabled and all required args are set
        :raise sys.exit: When missing required argument.
        """
        if (not hasattr(app_args, enable_arg) or
                not getattr(app_args, enable_arg)):
            return False
        missing = []
        for arg in required_args:
            if not getattr(app_args, arg):
                missing.append(arg)
        if missing:
            from .. import output, exit_codes
            import sys
            view = output.View(app_args=app_args)
            e_msg = ('Use of %s requires %s arguments to be set. Please set %s'
                     '.' % (enable_arg, ', '.join(required_args),
                            ', '.join(missing)))

            view.notify(event='error', msg=e_msg)
            return sys.exit(exit_codes.AVOCADO_FAIL)
        return True

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
            view = output.View(app_args=args)
            e_msg = ('Use of %s requires %s arguments to be set. Please set %s'
                     '.' % (enable_arg, ', '.join(required_args),
                            ', '.join(missing)))

            view.notify(event='error', msg=e_msg)
            return sys.exit(exit_codes.AVOCADO_FAIL)
        return True

    def run(self, args):
        if self._check_required_args(args, 'ec2_ami_id',
                                     ('ec2_ami_id',
                                      'ec2_security_group_ids',
                                      'ec2_subnet_id',
                                      'ec2_instance_type')):
            args.remote_result = EC2TestResult
            args.test_runner = RemoteTestRunner
