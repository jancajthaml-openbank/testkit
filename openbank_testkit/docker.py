#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import docker


class staticproperty(staticmethod):
  def __get__(self, *args):
    return self.__func__()


class Docker(object):

  __instance = None

  @staticmethod 
  def __lazy():
    if Docker.__instance == None:
      Docker()
    return Docker.__instance

  def __init__(self):
    if Docker.__instance == None:
      self.__docker = docker.from_env()
      Docker.__instance = self

  @staticproperty
  def images():
    return Docker.__lazy().__docker.images

  @staticproperty
  def containers():
    return Docker.__lazy().__docker.containers
