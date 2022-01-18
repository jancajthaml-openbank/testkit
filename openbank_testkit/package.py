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
import io
from distutils.version import StrictVersion
from .shell import Shell
from .platform import Platform
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
      if not version.startswith('{}-'.format(Platform.arch)):
        continue
      if not version.endswith('.main'):
        continue
      tags.append({
        'semver': StrictVersion(version[len(Platform.arch)+1:-5]),
        'version': version[len(Platform.arch)+1:-5],
        'tag': entry['name'],
        'ts': entry['tag_last_pushed']
      })

    compare = lambda x, y: x['ts'] > y['ts'] if x['semver'] == y['semver'] else x['semver'] > y['semver']

    latest = max(tags, key=functools.cmp_to_key(compare))

    if not latest:
      return None

    return latest['version']

  def __get_auth_head(self, repository):
    uri = 'https://auth.docker.io/token?service=registry.docker.io&scope=repository:{}:pull'.format(repository)
    request = Request(method='GET', url=uri)
    response = request.do()
    assert response.status == 200, 'unable to authorize docker pull'
    data = json.loads(response.read().decode('utf-8'))
    return {
      'Authorization':'Bearer {}'.format(data['token']),
      'Accept': 'application/vnd.docker.distribution.manifest.v2+json'
    }

  def __get_metadata(self, repository, tag):
    uri = 'https://index.docker.io/v2/{}/manifests/{}'.format(repository, tag)

    auth_headers = self.__get_auth_head(repository)

    request = Request(method='GET', url=uri)
    for key, value in auth_headers.items():
      request.add_header(key, value)
    response = request.do()
    assert response.status == 200, 'unable to docker pull layers and config info'
    data = json.loads(response.read().decode('utf-8'))
    return {
      'layers': data['layers'],
      'digest': data['config']['digest']
    }

  def __extract_file(self, repository, digest, source, target):
    file = source.strip(os.path.sep)
    uri = 'https://index.docker.io/v2/{}/blobs/{}'.format(repository, digest)

    auth_headers = self.__get_auth_head(repository)
    request = Request(method='GET', url=uri)
    for key, value in auth_headers.items():
      request.add_header(key, value)
    response = request.do()
    assert response.status == 200, 'unable to docker pull layer data'

    fileobj = io.BytesIO()

    content_length = response.getheader("Content-Length")

    if content_length is not None:
      try:
        content_length = int(content_length)
      except ValueError:
        content_length = None
      if content_length:
        fileobj.seek(content_length - 1)
        fileobj.write(b"\0")
        fileobj.seek(0)

    window = 4 * 1024

    while 1:
      buf = response.read(window)
      if not buf:
        break
      fileobj.write(buf)

    fileobj.seek(0)

    tarf = tarfile.open(fileobj=fileobj, mode='r:gz')

    for member in tarf.getmembers():
      if member.name != file:
        continue
      tmp_dir = tempfile.TemporaryDirectory()
      tarf.extract(member, path=tmp_dir.name)
      os.rename(os.path.join(tmp_dir.name, file), os.path.join(target, os.path.basename(file)))
      tmp_dir.cleanup()
      return True

    return False

  def download(self, version, meta, output):
    os.makedirs(output, exist_ok=True)

    package = '{}/{}_{}_{}.deb'.format(output, self.__name, version, Platform.arch)

    if os.path.exists(package):
      return True

    os.makedirs(os.path.dirname(package), exist_ok=True)

    metadata = self.__get_metadata('openbank/{}'.format(self.__name), '{}-{}.{}'.format(Platform.arch, version, meta))

    if len(metadata['layers']):
      metadata['layers'].pop()

    for layer in metadata['layers']:
      if self.__extract_file('openbank/{}'.format(self.__name), layer['digest'], '/opt/artifacts/{}_{}_{}.deb'.format(self.__name, version, Platform.arch), output):
        return os.path.exists(package)

    return False

