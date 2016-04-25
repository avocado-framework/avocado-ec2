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

import atexit
import os
import tempfile
import time
import uuid
import logging

import boto3

try:
    from botocore.vendored.requests.packages.urllib3.contrib.pyopenssl import extract_from_urllib3

    # Don't use pyOpenSSL in urllib3 - it causes an ``OpenSSL.SSL.Error``
    # exception when we try an API call on an idled persistent connection.
    # See https://github.com/boto/boto3/issues/220
    extract_from_urllib3()
except ImportError:
    pass

EC2_INSTANCES = []
EC2_KEYPAIR_WRAPPERS = []


def clean_aws_resources_atexit():
    """
    Cleanup AWS resources upon interpreter exit.

    If an unforseen situation did not clean up resources from EC2,
    Let's clean them at python interpreter exit.
    """
    global EC2_INSTANCES
    global EC2_KEYPAIR_WRAPPERS

    for instance in EC2_INSTANCES:
        instance.terminate()

    for key_pair in EC2_KEYPAIR_WRAPPERS:
        key_pair.destroy()


atexit.register(clean_aws_resources_atexit)


def clean_aws_resources(method):
    """
    Ensure that AWS resources are cleaned upon unhandled exceptions.

    :param method: EC2 method to wrap.
    :return: Wrapped method.
    """
    def wrapper(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except Exception:
            args[0].destroy()
            raise
    return wrapper


class KeyPairWrapper(object):

    def __init__(self, service, name):
        self.name = name
        self.key_pair = service.create_key_pair(KeyName=name)
        self.key_file = os.path.join(tempfile.gettempdir(),
                                     '{}.pem'.format(name))
        with open(self.key_file, 'w') as keyfile_obj:
            keyfile_obj.write(self.key_pair.key_material)
        os.chmod(self.key_file, 0o400)
        log = logging.getLogger("avocado.app")
        log.info(str(self))

    def __str__(self):
        return "KEYPAIR    : {} -> {}".format(self.name, self.key_file)

    def destroy(self):
        self.key_pair.delete()
        try:
            os.remove(self.key_file)
        except OSError:
            pass


class EC2InstanceWrapper(object):

    def __init__(self, args):
        self.uuid = uuid.uuid1()
        self.short_id = str(self.uuid)[:8]
        self.name = 'avocado-test-%s' % self.short_id
        self.ec2 = None
        self.instance = None
        self.key_pair = None
        self._init_resources(args)

    @clean_aws_resources
    def _init_resources(self, args):
        self.ec2 = boto3.resource('ec2')
        self.key_pair = KeyPairWrapper(service=self.ec2, name=self.name)
        global EC2_KEYPAIR_WRAPPERS
        EC2_KEYPAIR_WRAPPERS.append(self.key_pair)
        sgid_list = args.ec2_security_group_ids.split(',')
        # Create instance
        inst_list = self.ec2.create_instances(ImageId=args.ec2_ami_id,
                                              MinCount=1, MaxCount=1,
                                              KeyName=self.key_pair.key_pair.name,
                                              SecurityGroupIds=sgid_list,
                                              SubnetId=args.ec2_subnet_id,
                                              InstanceType=args.ec2_instance_type)
        global EC2_INSTANCES
        EC2_INSTANCES += inst_list
        self.instance = inst_list[0]
        log = logging.getLogger("avocado.app")
        log.info("EC2_ID     : %s", self.instance.id)
        # Rename the instance
        self.ec2.create_tags(Resources=[self.instance.id],
                             Tags=[{'Key': 'Name', 'Value': self.name}])
        self.instance.wait_until_running()
        self.wait_public_ip()
        log.info("EC2_IP     : [%s | %s]",
                 self.instance.public_ip_address,
                 self.instance.private_ip_address)

    def wait_public_ip(self):
        while self.instance.public_ip_address is None:
            time.sleep(1)
            self.instance.reload()

    def destroy(self):
        if self.instance is not None:
            self.instance.terminate()
            global EC2_INSTANCES
            EC2_INSTANCES.remove(self.instance)
        if self.key_pair is not None:
            self.key_pair.destroy()
            global EC2_KEYPAIR_WRAPPERS
            EC2_KEYPAIR_WRAPPERS.remove(self.key_pair)
