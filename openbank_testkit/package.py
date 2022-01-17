#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import platform
import tarfile
import tempfile
import functools
import errno
import os
import sys
import json
from distutils.version import StrictVersion

from .shell import Shell
from .platform import Platform
from .docker import Docker
from .http import Request


class Package(object):

  def __init__(self, name):
    self.__name = name

  @property
  def latest_version(self):
    uri = "https://hub.docker.com/v2/repositories/openbank/{}/tags?page=1".format(self.__name)

    request = Request(method='GET', url=uri)
    request.add_header('Accept', 'application/json')
    response = request.do()

    if not response.status == 200:
      return None

    body = json.loads(response.read().decode('utf-8')).get('results', [])
    tags = []

    for entry in body:
      version = entry['name']
      parts = version.split('-')
      if parts[0] != Platform.arch:
        continue

      if len(parts) < 2:
        continue

      if not parts[1].endswith('.main'):
        continue

      tags.append({
        'semver': StrictVersion(parts[1][:-5]),
        'version': parts[1][:-5],
        'tag': entry['name'],
        'ts': entry['tag_last_pushed']
      })

    compare = lambda x, y: x['ts'] > y['ts'] if x['semver'] == y['semver'] else x['semver'] > y['semver']

    latest = max(tags, key=functools.cmp_to_key(compare))

    if not latest:
      return None

    return latest['version']

  def verify(self, file):
    (code, result, error) = Shell.run(['dpkg', '-c', file])
    if code != 'OK':
      raise RuntimeError('code: {}, stdout: [{}], stderr: [{}]'.format(code, result, error))

  def download(self, version, meta):
    failure = None
    os.makedirs('/tmp/packages', exist_ok=True)

    package = '/tmp/packages/{}_{}_{}.deb'.format(self.__name, version, Platform.arch)

    if os.path.exists(package):
      self.verify(package)
      return

    os.makedirs(os.path.dirname(package), exist_ok=True)

    image_s = 'docker.io/openbank/{}:{}-{}.{}'.format(self.__name, Platform.arch, version, meta)
    package_s = '/opt/artifacts/{}_{}_{}.deb'.format(self.__name, version, Platform.arch)

    scratch_docker_cmd = ['FROM alpine']

    scratch_docker_cmd.append('COPY --from={} {} {}'.format(image_s, package_s, package))

    tag = 'bbtest_{}-artifacts-scratch'.format(self.__name)
    temp = tempfile.NamedTemporaryFile(delete=True)
    try:
      with open(temp.name, 'w') as fd:
        fd.write(str(os.linesep).join(scratch_docker_cmd))
      image, stream = Docker.images.build(fileobj=temp, rm=True, pull=True, tag=tag)
      for chunk in stream:
        if not 'stream' in chunk:
          continue
        for line in chunk['stream'].splitlines():
          l = line.strip(os.linesep)
          if not len(l):
            continue
          sys.stderr.write(l+'\n')

      scratch = Docker.containers.run(tag, ['/bin/true'], detach=True)

      tar_name = tempfile.NamedTemporaryFile(delete=True)
      with open(tar_name.name, 'wb') as fd:
        bits, stat = scratch.get_archive(package)
        for chunk in bits:
          fd.write(chunk)

      archive = tarfile.TarFile(tar_name.name)
      archive.extract(os.path.basename(package), os.path.dirname(package))
      self.verify(package)
      scratch.remove()
    except Exception as ex:
      failure = ex
    finally:
      temp.close()
      try:
        Docker.images.remove(tag, force=True)
      except:
        pass

    if failure:
      raise failure
